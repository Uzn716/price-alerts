from pricebot.config import Settings, load_config, parse_asin
from pricebot.detector import evaluate
from pricebot.matching import match_part, tokenize
from pricebot.models import Listing, Part


def parts(root):
    return load_config(root / "config.yaml").parts


def name_of(title, root):
    p = match_part(title, parts(root))
    return p.name if p else None


def test_tokenize_splits_letter_digit_boundaries():
    assert tokenize("RTX5070Ti") == ["rtx", "5070", "ti"]
    assert tokenize("Ryzen™ 7 9800X3D") == ["ryzen", "7", "9800", "x", "3", "d"]


def test_gpu_titles_map_to_the_right_part(root):
    assert name_of("MSI GeForce RTX 5070 Ti 16G Gaming Trio OC", root) == "RTX 5070 Ti"
    assert name_of("ASUS Prime GeForce RTX™ 5070 12GB GDDR7", root) == "RTX 5070"
    assert name_of("GIGABYTE GeForce RTX5070Ti Eagle", root) == "RTX 5070 Ti"
    assert name_of("Sapphire PULSE AMD Radeon RX 9070 XT 16GB", root) == "RX 9070 XT"
    assert name_of("XFX Swift AMD Radeon RX 9070 16GB", root) == "RX 9070"
    assert name_of("AMD Ryzen 7 9800X3D 8-Core Desktop Processor", root) == "Ryzen 7 9800X3D"
    assert name_of("Intel Core Ultra 7 Desktop Processor 265K", root) == "Core Ultra 7 265K"


def test_memory_and_storage(root):
    assert name_of("CORSAIR Vengeance DDR5 RAM 64GB (2x32GB) 6000MHz CL30", root) == "DDR5 64GB kit"
    assert name_of("G.SKILL Trident Z5 RGB DDR5 32GB (2x16GB) 6000", root) == "DDR5 32GB kit"
    assert name_of("Samsung 990 PRO 2TB PCIe 4.0 NVMe M.2 SSD", root) == "2TB NVMe SSD"
    assert name_of("Crucial DDR5 SODIMM 32GB laptop memory", root) is None
    assert name_of("Logitech wireless mouse", root) is None


def test_parse_asin_from_links():
    assert parse_asin("B0DT7L98J1") == "B0DT7L98J1"
    assert parse_asin("https://www.amazon.com/MSI-GeForce-Graphics/dp/B0DT7L98J1/ref=sr_1_3?x=1") == "B0DT7L98J1"
    assert parse_asin("https://www.amazon.com/gp/product/B0DT7L98J1") == "B0DT7L98J1"


def _listing(title, price, ref=None, **kw):
    return Listing(source="t", store="S", item_id="1", title=title, url="u", price=price,
                   reference_price=ref, reference_label="avg", **kw)


def test_detector_rules(root):
    cfg = load_config(root / "config.yaml")
    ps, st = cfg.parts, cfg.settings
    assert st.min_drop_percent == 30

    # Normal price: no alert
    assert evaluate(_listing("PNY GeForce RTX 5080 16GB", 999, 1049), ps, st) is None
    # 25% off is a nice sale, but under the 30% bar: no alert
    assert evaluate(_listing("PNY GeForce RTX 5080 16GB", 785, 1049), ps, st) is None
    # 41% below the usual price: alert
    a = evaluate(_listing("PNY GeForce RTX 5080 16GB", 620, 1049), ps, st)
    assert a and a.reasons == ["41% below avg"]
    # Part with no starting price and nothing learned yet: no known normal price, no alert
    assert evaluate(_listing("EVGA GeForce RTX 3090 FTW3 24GB", 300, None), ps, st) is None
    # Called a "price error" but no proof it's 30% off: no alert
    assert evaluate(_listing("Price mistake? RTX 3090 $500", 500, None, error_words=True), ps, st) is None
    # Starting price is used until the bot has learned one ($1,699 for an RTX 5080)
    a = evaluate(_listing("PNY GeForce RTX 5080 16GB", 1099, None), ps, st)
    assert a and a.reasons == ["35% below its typical price right now (starting estimate)"]
    assert evaluate(_listing("PNY GeForce RTX 5080 16GB", 1299, None), ps, st) is None  # only 24% off
    # Once a learned price exists, it replaces the starting price
    assert evaluate(_listing("PNY GeForce RTX 5080 16GB", 1099, None), ps, st, learned_typical=1400) is None
    a = evaluate(_listing("PNY GeForce RTX 5080 16GB", 899, None), ps, st, learned_typical=1400)
    assert a and "36% below its typical price over the last 30 days" in a.reasons[0]
    # Broad groups (RAM, SSDs, monitors...) need 45%, since models vary a lot in price
    assert evaluate(_listing("Corsair DDR5 32GB 6000MHz kit", 60, 100), ps, st) is None   # 40% off
    assert evaluate(_listing("Corsair DDR5 32GB 6000MHz kit", 50, 100), ps, st) is not None  # 50% off
    # ...but when it IS 30%+ off, the alert mentions the price-error claim too
    a = evaluate(_listing("Price mistake? RTX 5090 $1000", 1000, 2000, error_words=True), ps, st)
    assert a and a.reasons[-1] == "The post also calls it a possible price error"
    # Learned typical price is used when it's lower than the store's own "usual" price
    a = evaluate(_listing("PNY GeForce RTX 5080 16GB", 600, 1200), ps, st, learned_typical=950)
    assert a and "37% below its typical price over the last 30 days" in a.reasons[0]
    assert a.listing.reference_price == 950
    assert evaluate(_listing("PNY GeForce RTX 5080 16GB", 700, 1200), ps, st, learned_typical=950) is None
    # Accessory under the part's min_price is ignored
    assert evaluate(_listing("RTX 5080 GPU anti-sag holder", 19, 40), ps, st) is None
    # Laptop excluded even though cheap
    assert evaluate(_listing("Gaming Laptop RTX 5080 32GB", 500, 2500), ps, st) is None
    # Untracked PC part needs the stricter general threshold (50%)
    assert evaluate(_listing("ASRock A620M motherboard", 80, 130), ps, st) is None
    assert evaluate(_listing("ASRock A620M motherboard", 60, 130), ps, st) is not None
    # Unrelated product never alerts
    assert evaluate(_listing("Instant Pot 6qt", 20, 100), ps, st) is None


def test_direct_watch_skips_title_matching():
    part = Part(name="Mine", match=["zzz"], alert_below=100)
    lst = _listing("Totally different title", 90, part_hint=part)
    a = evaluate(lst, [], Settings())
    assert a and a.part is part
