"""Make sure similar model names land on the right watchlist entry."""
import pytest

from pricebot.config import load_config
from pricebot.matching import match_part

CASES = [
    ("MSI GeForce RTX 4070 Ti SUPER 16G Ventus 3X", "RTX 4070 Ti Super"),
    ("ASUS TUF Gaming GeForce RTX 4070 Ti OC 12GB", "RTX 4070 Ti"),
    ("GIGABYTE GeForce RTX 4070 SUPER WINDFORCE OC 12G", "RTX 4070 Super"),
    ("PNY GeForce RTX 4070 12GB VERTO Dual Fan", "RTX 4070"),
    ("ZOTAC Gaming GeForce RTX 4080 SUPER Trinity Black", "RTX 4080 Super"),
    ("EVGA GeForce RTX 3080 Ti FTW3 Ultra", "RTX 3080 Ti"),
    ("EVGA GeForce RTX 3080 FTW3 Ultra 10GB LHR", "RTX 3080"),
    ("ASUS Dual GeForce RTX 3060 Ti V2 OC Edition", "RTX 3060 Ti"),
    ("MSI Gaming GeForce RTX 3060 12GB Ventus 2X", "RTX 3060"),
    ("Sapphire Nitro+ AMD Radeon RX 7900 XTX Vapor-X 24GB", "RX 7900 XTX"),
    ("XFX Speedster MERC310 AMD Radeon RX 7900XT 20GB", "RX 7900 XT"),
    ("ASRock Challenger Radeon RX 7600 8GB", "RX 7600"),
    ("AMD Ryzen 7 5800X3D 8-core, 16-Thread Desktop Processor", "Ryzen 7 5800X3D"),
    ("AMD Ryzen 7 5800X 8-core, 16-Thread Unlocked Desktop Processor", "Ryzen 7 5800X"),
    ("AMD Ryzen 5 5600X 6-core Desktop Processor with Wraith Stealth Cooler", "Ryzen 5 5600X"),
    ("AMD Ryzen 5 5600 6-Core, 12-Thread Unlocked Desktop Processor", "Ryzen 5 5600"),
    ("AMD Ryzen 5 5600G with Radeon Graphics", None),
    ("Intel Core i7-14700KF Desktop Processor 20 cores", "Core i7-14700K"),
    ("Corsair Vengeance LPX DDR4 RAM 32GB (2x16GB) 3200MHz", "DDR4 32GB kit"),
    ("MSI MAG B550 TOMAHAWK Gaming Motherboard AM4", "AM4 motherboard (X570 / B550)"),
    ("Corsair RM850x Fully Modular 850 Watt Power Supply", "850W power supply"),
    ("LG UltraGear 27 inch QHD 1440p 180Hz Gaming Monitor", "1440p gaming monitor"),
    ("ASUS ROG Ally X 24GB 1TB Handheld", "ROG Ally"),
]


@pytest.mark.parametrize("title,expected", CASES)
def test_watchlist_matching(root, title, expected):
    part = match_part(title, load_config(root / "config.yaml").parts)
    assert (part.name if part else None) == expected
