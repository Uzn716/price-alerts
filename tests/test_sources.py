import json
from datetime import datetime, timedelta, timezone

from conftest import FakeResponse, FakeSession

from pricebot.config import load_config
from pricebot.models import Part
from pricebot.sources.bestbuy import BestBuySource
from pricebot.sources.keepa import KeepaSource
from pricebot.sources.slickdeals import SlickdealsSource, extract_price, extract_store
from pricebot.state import State

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def cfg(root, **env):
    c = load_config(root / "config.yaml")
    c.keepa_api_key = env.get("keepa", "k")
    c.bestbuy_api_key = env.get("bestbuy", "b")
    return c


# ---------------- Keepa ----------------

def _deal(asin, title, price_cents, avg90_cents, axis="interval_first"):
    n_types = 35
    if axis == "interval_first":  # [interval][priceType]
        avg = [[-1] * n_types for _ in range(4)]
        avg[2][0] = avg90_cents
        avg[3][0] = avg90_cents
    else:  # [priceType][interval]
        avg = [[-1, -1, -1, -1] for _ in range(n_types)]
        avg[0] = [-1, -1, avg90_cents, avg90_cents]
    current = [-1] * n_types
    current[0] = price_cents
    return {"asin": asin, "title": title, "current": current, "avg": avg, "image": [ord(c) for c in "abc.jpg"]}


def test_keepa_deals_and_watch(root):
    c = cfg(root)
    c.parts.append(Part(name="Watched 5080", match=["rtx 5080"], alert_below=650, amazon=["B0WATCH001"]))
    deals = {
        "deals": {
            "dr": [
                _deal("B0AAAAAAA1", "ASUS TUF RTX 5090 32GB", 109999, 219999),
                _deal("B0AAAAAAA2", "Some Blender", 3000, 9000, axis="type_first"),
                {"asin": "B0OOS", "title": "Out of stock", "current": [-1]},
            ]
        },
        "tokensLeft": 40,
    }
    stats = {"current": [62999, 62999], "avg30": [99999, 99000], "avg90": [101999, 100000]}
    products = {"products": [{"asin": "B0WATCH001", "title": "PNY RTX 5080", "stats": stats, "imagesCSV": "x.jpg,y.jpg"}], "tokensLeft": 39}
    session = FakeSession([
        ("/token", FakeResponse(200, {"tokensLeft": 45})),
        ("/deal", FakeResponse(200, deals)),
        ("/product", FakeResponse(200, products)),
    ])
    state = State()
    src = KeepaSource(c, state, session, NOW)
    listings = src.fetch()
    by = {l.item_id: l for l in listings}
    assert by["B0AAAAAAA1"].price == 1099.99 and by["B0AAAAAAA1"].reference_price == 2199.99
    assert by["B0AAAAAAA1"].image_url.endswith("/abc.jpg")
    assert by["B0AAAAAAA2"].reference_price == 90.0  # other axis order also parsed
    assert "B0OOS" not in by
    w = by["B0WATCH001"]
    assert w.price == 629.99 and w.reference_price == 999.99 and w.part_hint.name == "Watched 5080"
    # selection sent correctly
    deal_call = [p for u, p in session.calls if "/deal" in u][0]
    sel = json.loads(deal_call["selection"])
    assert sel["includeCategories"] == [172282] and sel["priceTypes"] == [0] and sel["deltaPercentRange"] == [30, 100]
    assert state.keepa["last_deals_at"]


def test_keepa_respects_token_budget(root):
    c = cfg(root)
    c.parts = [Part(name=f"p{i}", match=["x"], amazon=[f"B0WATCH00{i}"]) for i in range(5)]
    session = FakeSession([
        ("/token", FakeResponse(200, {"tokensLeft": 3})),
        ("/product", lambda u, p: FakeResponse(200, {"products": [], "tokensLeft": 0})),
    ])
    state = State()
    KeepaSource(c, state, session, NOW).fetch()
    # Not enough for a deal search (5); only 3 ASINs requested, rotation advanced
    assert not any("/deal" in u for u, _ in session.calls)
    prod = [p for u, p in session.calls if "/product" in u][0]
    assert prod["asin"].count(",") == 2
    assert state.keepa["rotate"] == 3


def test_keepa_bad_key_raises(root):
    import pytest
    from pricebot.http import SourceError
    session = FakeSession([("/token", FakeResponse(402, {"error": {"message": "payment required"}}))])
    with pytest.raises(SourceError):
        KeepaSource(cfg(root), State(), session, NOW).fetch()


# ---------------- Best Buy ----------------

def test_bestbuy(root):
    c = cfg(root)
    products = {"products": [
        {"sku": 111, "name": "NVIDIA - GeForce RTX 5080 16GB GDDR7 Graphics Card", "salePrice": 549.99,
         "regularPrice": 999.99, "url": "https://bestbuy.com/111", "condition": "New", "onlineAvailability": True},
        {"sku": 222, "name": "HP - OMEN Gaming Laptop - RTX 5080", "salePrice": 1999.99, "regularPrice": 2499.99,
         "condition": "New", "onlineAvailability": True},
        {"sku": 333, "name": "Refurb RTX 5080", "salePrice": 500, "regularPrice": 999, "condition": "Refurbished"},
        {"sku": 444, "name": "Unrelated thing", "salePrice": 5, "regularPrice": 10, "condition": "New"},
    ]}
    session = FakeSession([("api.bestbuy.com", FakeResponse(200, products))])
    state = State()
    # pre-seed 6 days of history at $899 for sku 111, so typical < regular
    for d in range(1, 7):
        state.record_price("bestbuy:111", 899.0, NOW - timedelta(days=d))
    import pricebot.sources.bestbuy as bb
    bb.PAUSE_SECONDS = 0
    listings = BestBuySource(c, state, session, NOW).fetch()
    ids = {l.item_id for l in listings}
    assert ids == {"111", "222"}  # refurb + unrelated dropped (laptop dropped later by detector excludes)
    l111 = [l for l in listings if l.item_id == "111"][0]
    assert l111.reference_price == 899.0 and "usual" in l111.reference_label
    assert state.history["bestbuy:111"][NOW.date().isoformat()] == 549.99
    first_url = session.calls[0][0]
    assert first_url.endswith("products(search=rtx&search=5090)")


# ---------------- Slickdeals ----------------

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Hot Deals</title>
{items}
</channel></rss>"""

ITEM = """<item><title>{title}</title><link>https://slickdeals.net/f/{id}</link>
<guid isPermaLink="false">{id}</guid><description><![CDATA[{body}]]></description></item>"""


def rss(items):
    return RSS.format(items="".join(ITEM.format(**i) for i in items)).encode()


def test_price_and_store_extraction():
    assert extract_price("MSI RTX 5070 Ti 16GB $549.99 + Free Shipping") == 549.99
    assert extract_price("$50 off RTX 5080 now $899 at Newegg") == 899
    assert extract_price("Save $200: Ryzen 7 9800X3D $279") == 279
    assert extract_price("Samsung 990 Pro 4TB $1,099.99") == 1099.99
    assert extract_price("No price here") is None
    assert extract_store("RTX 5080 $899 at Newegg", "Slickdeals") == "Newegg"
    assert extract_store("B&H: Ryzen 9 9950X3D $499", "Slickdeals") == "B&H"
    assert extract_store("RTX 5080 $899", "Slickdeals") == "Slickdeals"


def test_slickdeals_first_run_seeds_then_alerts(root):
    c = cfg(root)
    old = [{"id": "1", "title": "RTX 5090 $999 at Newegg", "body": ""}]
    new = old + [
        {"id": "2", "title": "Gigabyte RTX 5080 $549 at Micro Center", "body": ""},
        {"id": "3", "title": "Kitchen towels $5", "body": "price error lol"},
        {"id": "4", "title": "Ryzen 7 9800X3D $399 @ Walmart", "body": "Looks like a pricing error, buy fast"},
    ]
    state = State()
    feeds = iter([rss(old), rss(old), rss(new), rss(new)])
    session = FakeSession([("slickdeals.net", lambda u, p: FakeResponse(200, content=next(feeds)))])

    first = SlickdealsSource(c, state, session, NOW).fetch()
    assert first and all(l.learn_only for l in first)  # old posts: learn prices, never alert
    second = SlickdealsSource(c, state, session, NOW).fetch()
    assert not any(l.learn_only for l in second)
    ids = {l.item_id for l in second}
    assert ids == {"2", "3", "4"}  # 1 already seen; the second feed also returns the same items
    l4 = [l for l in second if l.item_id == "4"][0]
    assert l4.error_words and l4.price == 399 and l4.store == "Walmart"


def test_slickdeals_partial_failure_is_ok(root):
    c = cfg(root)
    state = State()
    calls = {"n": 0}

    def route(u, p):
        calls["n"] += 1
        return FakeResponse(403, content=b"blocked") if "frontpage" in u else FakeResponse(200, content=rss([]))

    session = FakeSession([("slickdeals.net", route)])
    assert SlickdealsSource(c, state, session, NOW).fetch() == []


# ---------------- DealNews ----------------

DN_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dealnews="https://www.dealnews.com/rss/" xmlns:media="http://search.yahoo.com/mrss/">
<channel><title>DealNews - Computers</title>
<item><title>Lenovo Legion 5a Gaming Laptop for $1,249.99 + free shipping</title>
<link>https://www.dealnews.com/x/22406089.html?iref=rss-c39</link><guid>https://www.dealnews.com/22406089.html?iref=rss-c39</guid>
<description><![CDATA[<p>Laptop deal</p>]]></description>
<dealnews:retailer>B&amp;H Photo Video</dealnews:retailer><dealnews:price currency="USD">1249.99</dealnews:price>
<media:content url="https://img.dealnews.com/a.jpg" medium="image"/></item>
</channel></rss>"""

DN_FEED_2 = DN_FEED.replace(b"</channel>", b"""<item><title>MSI GeForce RTX 5080 16GB Graphics Card for $579 + free shipping</title>
<link>https://www.dealnews.com/x/2.html</link><guid>https://www.dealnews.com/2.html</guid>
<description><![CDATA[<p>Possible price mistake, lowest we've seen</p>]]></description>
<dealnews:retailer>Newegg</dealnews:retailer><dealnews:price currency="USD">579.00</dealnews:price>
<media:content url="https://img.dealnews.com/b.jpg" medium="image"/></item></channel>""")


def test_dealnews(root):
    from pricebot.detector import evaluate
    from pricebot.sources.dealnews import DealNewsSource
    c = cfg(root)
    state = State()
    feeds = iter([DN_FEED, DN_FEED_2])
    session = FakeSession([("dealnews.com", lambda u, p: FakeResponse(200, content=next(feeds)))])
    first = DealNewsSource(c, state, session, NOW).fetch()
    assert first and all(l.learn_only for l in first)  # first run only learns
    listings = DealNewsSource(c, state, session, NOW).fetch()
    assert len(listings) == 1
    l = listings[0]
    assert (l.price, l.store, l.image_url) == (579.0, "Newegg", "https://img.dealnews.com/b.jpg")
    assert l.error_words
    alert = evaluate(l, c.parts, c.settings)
    assert alert and alert.part.name == "RTX 5080" and "Under your $599 target" in alert.reasons[0]


# ---------------- eBay ----------------

def _ebay_item(i, title, price, pct="99.6", score=1500):
    return {"itemId": f"v1|{i}|0", "title": title, "price": {"value": str(price), "currency": "USD"},
            "itemWebUrl": f"https://www.ebay.com/itm/{i}", "image": {"imageUrl": f"https://i.ebayimg.com/{i}.jpg"},
            "seller": {"username": f"seller{i}", "feedbackPercentage": pct, "feedbackScore": score}}


def test_ebay(root):
    from pricebot.detector import evaluate
    from pricebot.sources.ebay import EbaySource
    c = cfg(root)
    c.ebay_client_id, c.ebay_client_secret = "id", "secret"
    c.parts = [p for p in c.parts if p.name == "RTX 5080"]
    items = [_ebay_item(i, f"ZOTAC GeForce RTX 5080 16GB Solid #{i}", 1200 + i * 10) for i in range(8)]
    items += [
        _ebay_item(100, "PNY GeForce RTX 5080 16GB OC", 700),                       # big drop, good seller
        _ebay_item(101, "MSI GeForce RTX 5080 16GB", 650, pct="91.0"),              # bad seller -> skipped
        _ebay_item(102, "RTX 5080 Founders Edition BOX ONLY", 320),                 # trick listing -> skipped
        _ebay_item(103, "ASUS ROG Strix RTX 5080 Gaming Laptop", 1000),              # laptop -> skipped
    ]
    session = FakeSession(
        [("item_summary/search", FakeResponse(200, {"itemSummaries": items}))],
        post_routes=[("oauth2/token", FakeResponse(200, {"access_token": "T", "expires_in": 7200}))],
    )
    state = State()
    listings = EbaySource(c, state, session, NOW).fetch()
    ids = {l.item_id for l in listings}
    assert "v1|100|0" in ids and "v1|101|0" not in ids and "v1|102|0" not in ids and "v1|103|0" not in ids
    deal = [l for l in listings if l.item_id == "v1|100|0"][0]
    assert deal.reference_price == 1225.0  # median of all 10 matching new listings (any seller)
    alert = evaluate(deal, c.parts, c.settings)
    assert alert and alert.drop_percent > 40 and "seller100" in deal.note
    search = [p for u, p in session.calls if "item_summary" in u][0]
    assert "conditionIds:{1000}" in search["filter"] and "price:[300..]" in search["filter"]
    # Not due again 5 minutes later (every_minutes: 15)
    session.calls.clear()
    assert EbaySource(c, state, session, NOW + timedelta(minutes=5)).fetch() == []
    assert session.calls == []


def test_ebay_bad_keys(root):
    import pytest
    from pricebot.http import SourceError
    from pricebot.sources.ebay import EbaySource
    c = cfg(root)
    c.ebay_client_id, c.ebay_client_secret = "id", "wrong"
    session = FakeSession([], post_routes=[("oauth2/token", FakeResponse(401, {"error": "invalid_client"}))])
    with pytest.raises(SourceError, match="PRODUCTION"):
        EbaySource(c, State(), session, NOW).fetch()
