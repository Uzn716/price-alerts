"""DealNews RSS feeds: editor-checked deals from many stores, with the
price and store name included as structured data."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..http import SourceError
from .feeds import FeedItem, FeedSource, plain


def _local(tag: str) -> tuple[str, str]:
    """Split '{namespace}name' into (namespace, name)."""
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def _money(text: str | None) -> float | None:
    try:
        value = float(str(text).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class DealNewsSource(FeedSource):
    name = "dealnews"
    store = "DealNews"

    @property
    def feeds_config(self):
        return self.config.dealnews

    def parse(self, content: bytes) -> list[FeedItem]:
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            raise SourceError("feed could not be read") from None
        items = []
        for node in root.iter("item"):
            fields: dict[str, str] = {}
            image = None
            for child in node:
                ns, name = _local(child.tag)
                if "dealnews" in ns:
                    fields[f"dn:{name}"] = (child.text or "").strip()
                elif "search.yahoo.com/mrss" in ns and name in ("content", "thumbnail"):
                    image = image or child.get("url")
                elif not ns:
                    fields[name] = child.text or ""
            title = plain(fields.get("title", ""))
            items.append(
                FeedItem(
                    item_id=(fields.get("guid") or fields.get("link") or title).strip(),
                    title=title,
                    url=fields.get("link", "").strip(),
                    body=plain(fields.get("description", "")),
                    price=_money(fields.get("dn:price")),
                    store=fields.get("dn:retailer") or None,
                    image_url=image,
                )
            )
        return items
