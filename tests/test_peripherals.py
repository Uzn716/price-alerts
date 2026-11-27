"""Pro esports peripherals: right model, accessories filtered, nothing else broken."""
import pytest

from pricebot.config import load_config
from pricebot.detector import resolve_part
from pricebot.models import Listing

cases = {
 "Logitech G PRO X SUPERLIGHT 2 LIGHTSPEED Wireless Gaming Mouse, 60g, HERO 2, for PC/Laptop - Black": "Logitech G Pro X Superlight 2",
 "Logitech G PRO X SUPERLIGHT Wireless Gaming Mouse, 25K Sensor, 2.4GHz, Ultra-Lightweight": "Logitech G Pro X Superlight (gen 1)",
 "Logitech G PRO X SUPERLIGHT 2 DEX Wireless Gaming Mouse": "Logitech G Pro X Superlight 2 DEX",
 "Logitech G PRO X SUPERLIGHT 2c Wireless Gaming Mouse": "Logitech G Pro X Superlight 2c",
 "Logitech G PRO X2 SUPERSTRIKE Wireless Gaming Mouse, Haptic Inductive Trigger": "Logitech G Pro X2 Superstrike",
 "Logitech G Pro X3 Superstrike Gaming Mouse Magenta": "Logitech G Pro X3 Superstrike",
 "Razer Viper V3 Pro Wireless Esports Gaming Mouse - Black": "Razer Viper V3 Pro",
 "Razer DeathAdder V4 Pro Wireless Gaming Mouse": "Razer DeathAdder V4 Pro",
 "BenQ ZOWIE EC2-DW Wireless Esports Gaming Mouse": "ZOWIE EC mouse",
 "Wooting 60HE+ Analog Keyboard": "Wooting 60HE",
 "Wooting 80HE Frost Hall Effect Gaming Keyboard": "Wooting 80HE",
 "Razer Huntsman V3 Pro TKL 8KHz Analog Optical Esports Keyboard": "Razer Huntsman V3 Pro",
 "Logitech G PRO X TKL RAPID Wired Gaming Keyboard": "Logitech G Pro X TKL Rapid",
 "BenQ ZOWIE G-SR-SE Rouge Gaming Mouse Pad": "ZOWIE G-SR / G-TR mousepad",
 "SteelSeries QcK Heavy XXL Gaming Mouse Pad": "SteelSeries QcK Heavy",
 "ARTISAN Ninja FX Zero Soft XL Mousepad": "ARTISAN mousepad",
 "HyperX Cloud II Gaming Headset for PC, PS5, Laptop": "HyperX Cloud II",
 "HyperX Cloud III Wireless Gaming Headset": "HyperX Cloud III",
 "Logitech G PRO X 2 LIGHTSPEED Wireless Gaming Headset": "Logitech G Pro X 2 Lightspeed",
 "Razer BlackShark V2 Pro Wireless Esports Headset": "Razer BlackShark V2 Pro",
 "Razer BlackShark V2 Wired Gaming Headset": "Razer BlackShark V2",
 "BenQ ZOWIE XL2566K 24.5 inch 360Hz TN Gaming Monitor for Esports": "ZOWIE XL2566K (360Hz)",
 "BenQ ZOWIE XL2586X+ 600Hz Esports Gaming Monitor": "ZOWIE XL2586X+ (600Hz)",
 "Grip Tape for Logitech G Pro X Superlight 2, Anti-Slip": None,
 "Mouse Skates for Razer Viper V3 Pro, PTFE Glides": None,
 "Replacement Ear Pads for HyperX Cloud II": None,
 "Keycaps compatible with Wooting 60HE": None,
 "ASUS TUF Gaming Laptop RTX 5070": None,
 "Skytech Gaming PC Desktop Ryzen 7 7800X3D RTX 5070 32GB DDR5": "Prebuilt PC: RTX 5070",
 "MSI Gaming GeForce RTX 5070 12G Graphics Card": "RTX 5070",
 "Logitech G502 Gaming Mouse for PC": None,
}


@pytest.mark.parametrize("title,expected", list(cases.items()))
def test_peripheral_matching(root, title, expected):
    c = load_config(root / "config.yaml")
    part = resolve_part(Listing("t", "S", "1", title, "u", 150), c.parts, c.settings)
    assert (part.name if part else None) == expected


def test_peripherals_need_30_percent(root):
    from pricebot.detector import evaluate
    c = load_config(root / "config.yaml")
    title = "Logitech G PRO X SUPERLIGHT 2 Wireless Gaming Mouse"
    assert evaluate(Listing("t", "S", "1", title, "u", 99), c.parts, c.settings, learned_typical=129) is None  # 23% off
    a = evaluate(Listing("t", "S", "1", title, "u", 85), c.parts, c.settings, learned_typical=129)            # 34% off
    assert a and a.part.name == "Logitech G Pro X Superlight 2"
