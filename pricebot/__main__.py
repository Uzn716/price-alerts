"""Entry point: `python -m pricebot` runs one price check and exits.

GitHub Actions runs this on a schedule, so nothing has to stay running.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import ConfigError, load_config
from .detector import evaluate, price_floor, resolve_part
from .http import SourceError, make_session
from .models import Alert, Listing, Part
from .notify import BLUE, GREY, Discord, alert_embed, info_embed
from .sources import ALL_SOURCES
from .state import State

WARN_AFTER_FAILURES = 3


def run(config_path: str, state_path: str, dry_run: bool = False, now: datetime | None = None, session=None) -> int:
    now = now or datetime.now(timezone.utc)
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"CONFIG PROBLEM: {exc}")
        return 2

    if not dry_run and not config.discord_webhook_url:
        print("DISCORD_WEBHOOK_URL is not set. Add it as a repository secret (see README).")
        return 2

    session = session or make_session()
    state = State.load(state_path)
    _migrate(state, config)
    discord = None if dry_run else Discord(config.discord_webhook_url, config.settings.mention, session,
                                             config.settings.resale_fee_percent)

    run_stats = {"checked": 0, "matched": 0}
    alerts: list[Alert] = []
    alerted_keys: set[str] = set()  # the same post can appear in two feeds in one run
    warnings: list[dict] = []

    for source_cls in ALL_SOURCES:
        source = source_cls(config, state, session, now)
        if not source.available:
            print(f"- {source.name}: skipped (not enabled or no API key)")
            continue
        try:
            listings: list[Listing] = source.fetch()
        except (SourceError, Exception) as exc:  # one broken store shouldn't stop the others
            message = str(exc) if isinstance(exc, SourceError) else f"{exc.__class__.__name__}: {exc}"
            count = state.record_failure(source.name, message)
            print(f"- {source.name}: FAILED ({count} in a row): {message}")
            entry = state.errors[source.name]
            if count >= WARN_AFTER_FAILURES and not entry.get("warned"):
                entry["warned"] = True
                warnings.append(
                    info_embed(
                        f"⚠️ {source.name} isn't working",
                        f"The last {count} checks failed. Latest error:\n```{message[:900]}```"
                        "Other stores are still being checked. You'll get this warning once.",
                        GREY,
                    )
                )
            continue
        state.record_success(source.name)

        found = learned = matched = 0
        st = config.settings
        for listing in listings:
            part = resolve_part(listing, config.parts, st)
            if part and not listing.learn_only:
                matched += 1
            low_key = f"prices:{part.name}" if part else None
            typical = (
                state.typical_price(low_key, now, min_days=st.learn_min_days, days=st.learn_window_days)
                if part else None
            )
            if not listing.learn_only:
                days = state.days_of_data(low_key, now, st.learn_window_days) if part else 0
                gpu_normal = _gpu_normal(part, config, state, now) if part and part.prebuilt else None
                alert = evaluate(listing, config.parts, st, learned_typical=typical, part=part,
                                 learned_days=days, gpu_normal=gpu_normal)
                if (
                    alert
                    and listing.key not in alerted_keys
                    and state.should_alert(listing.key, listing.price, st.realert_after_hours, now)
                ):
                    alerts.append(alert)
                    alerted_keys.add(listing.key)
                    found += 1
            # Remember this price so the bot learns what "normal" looks like for the part.
            if part and listing.price is not None and listing.price >= price_floor(part, st):
                state.record_price(low_key, listing.price, now)
                learned += 1
        print(f"- {source.name}: checked {len(listings)} listings, {matched} matched your parts, "
              f"{found} alert(s), learned {learned} price(s)")
        run_stats["checked"] += sum(1 for l in listings if not l.learn_only)
        run_stats["matched"] += matched

    for alert in alerts:
        lst = alert.listing
        price = f"${lst.price:,.2f}" if lst.price is not None else "?"
        print(f"  ALERT [{lst.store}] {price} {lst.title[:90]} -> {'; '.join(alert.reasons)}")

    if dry_run:
        print("Dry run: nothing sent to Discord and state not saved.")
        return 0

    summary = _update_daily_summary(state, config, now, run_stats, len(alerts))
    try:
        if warnings:
            discord.send(warnings)
        discord.send_alerts(alerts)
        if summary:
            discord.send([summary])
            state.meta["summary"] = {"last_sent": _local_now(config, now).date().isoformat(), "since": now.isoformat()}
    except Exception as exc:
        print(f"Couldn't post to Discord: {exc}")
        state.save(state_path, now)  # keep progress; alerts will retry next run
        return 1

    for alert in alerts:
        state.mark_alerted(alert.listing.key, alert.listing.price, now)
    state.save(state_path, now)
    return 0


def _migrate(state: State, config) -> None:
    """One-time fixes to saved data."""
    done = state.meta.setdefault("migrations", [])
    if "split-prebuilt-prices" not in done:
        # Before prebuilt PCs were recognized, a "gaming desktop with an RTX 5070" was
        # recorded as an RTX 5070 price. Drop daily prices that are far above a
        # component's own range (> 1.5x its lowest known price).
        removed = 0
        for part in config.parts:
            days = state.history.get(f"prices:{part.name}")
            if part.prebuilt or not days:
                continue
            base = min([*days.values(), *([part.starting_price] if part.starting_price else [])])
            for day, price in list(days.items()):
                if price > base * 1.5:
                    del days[day]
                    removed += 1
        done.append("split-prebuilt-prices")
        if removed:
            print(f"  cleanup: removed {removed} prebuilt-PC price(s) from component price history")


def _gpu_normal(part, config, state: State, now: datetime) -> float | None:
    """Normal price of the graphics card inside a prebuilt (learned, else starting price)."""
    gpu = next((p for p in config.parts if p.name == part.gpu and not p.prebuilt), None)
    if not gpu:
        return None
    st = config.settings
    learned = state.typical_price(f"prices:{gpu.name}", now, min_days=st.learn_min_days, days=st.learn_window_days)
    return learned or gpu.starting_price


def _local_now(config, now: datetime) -> datetime:
    try:
        return now.astimezone(ZoneInfo(config.settings.timezone))
    except (ZoneInfoNotFoundError, ValueError):
        return now


def _update_daily_summary(state: State, config, now: datetime, run_stats: dict, alerts: int) -> dict | None:
    """Add this run to today's tally; return a summary embed once a day."""
    s = state.meta.setdefault("summary", {})
    for k in ("runs", "checked", "matched", "alerts"):
        s.setdefault(k, 0)
    s.setdefault("since", now.isoformat())
    s["runs"] += 1
    s["checked"] += run_stats["checked"]
    s["matched"] += run_stats["matched"]
    s["alerts"] += alerts

    st = config.settings
    local = _local_now(config, now)
    if not st.daily_summary or local.hour < st.daily_summary_hour or s.get("last_sent") == local.date().isoformat():
        return None

    ready = sum(
        1 for p in config.parts
        if p.starting_price or state.typical_price(f"prices:{p.name}", now, st.learn_min_days, st.learn_window_days)
    )
    problems = [f"⚠️ {name}: {e.get('last_error', 'failing')[:120]}" for name, e in state.errors.items()]
    lines = [
        f"**{s['runs']}** checks • **{s['checked']:,}** new listings/posts read",
        f"**{s['matched']}** matched your parts • **{s['alerts']}** alert(s) sent",
        f"**{ready}/{len(config.parts)}** parts have a normal price to compare against",
    ]
    lines += problems or ["✅ All sources working"]
    if s["alerts"] == 0:
        lines.append(f"\nNo deals hit {st.min_drop_percent:g}%+ below normal yet. That's expected: deals that deep are rare.")
    return info_embed("📊 Daily check-in: the bot is running", "\n".join(lines), BLUE)


def send_test(config_path: str) -> int:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"CONFIG PROBLEM: {exc}")
        return 2
    if not config.discord_webhook_url:
        print("DISCORD_WEBHOOK_URL is not set. Add it as a repository secret (see README).")
        return 2
    sample_part = Part(name="RTX 5080", match=["rtx 5080"], alert_below=599)
    sample = Alert(
        listing=Listing(
            source="test",
            store="Example Store",
            item_id="test",
            title="TEST ALERT: Example GeForce RTX 5080 16GB Graphics Card",
            url="https://example.com",
            price=489.99,
            reference_price=999.99,
            reference_label="its 90-day average",
        ),
        part=sample_part,
        reasons=["This is a test message: your webhook works! 🎉", "Under your $599 target for RTX 5080"],
        drop_percent=51.0,
    )
    keys = {
        "Keepa (Amazon)": bool(config.keepa_api_key),
        "Best Buy": bool(config.bestbuy_api_key),
        "eBay": bool(config.ebay_client_id and config.ebay_client_secret),
        "Slickdeals (no key needed)": config.slickdeals.enabled,
        "DealNews (no key needed)": config.dealnews.enabled,
    }
    status = "\n".join(f"{'✅' if ok else '➖'} {name}" for name, ok in keys.items())
    Discord(config.discord_webhook_url, config.settings.mention).send(
        [info_embed("PC Price Alerts is connected", f"Sources ready:\n{status}\n\nTracking {len(config.parts)} parts."), alert_embed(sample)],
        f"{config.settings.mention} Test from PC Price Alerts".strip(),
    )
    print("Test message sent.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pricebot", description="Check PC part prices once and post price errors to Discord.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--dry-run", action="store_true", help="print alerts instead of posting them")
    parser.add_argument("--test-discord", action="store_true", help="send a test message and exit")
    args = parser.parse_args(argv)
    if args.test_discord:
        return send_test(args.config)
    return run(args.config, args.state, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
