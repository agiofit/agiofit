"""Mapping tables between garment measurements, body measurements and fit zones.

Everything in this module is a *default*. A Cut Profile that declares its own
``intended_ease`` or ``critical_zones`` overrides what is here, and the implementation lowers
confidence whenever it has to fall back on these values instead.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ZoneMapping:
    zone: str
    garment_key: str
    body_key: str
    doubles_when_flat_laid: bool
    linear: bool  # linear zones (shoulder, sleeve) tolerate far less ease than girths
    offset_scale: float  # how much of a learned brand offset applies here

    # A brand that "runs small" runs small in the torso. Applying the same centimetre shift to a
    # collar, where 1 cm is a whole size, turns a useful correction into a wrong answer.


ZONE_MAPPINGS: tuple[ZoneMapping, ...] = (
    ZoneMapping("chest", "chest_width", "chest_circumference", True, False, 1.0),
    ZoneMapping("waist", "waist_width", "waist_circumference", True, False, 1.0),
    ZoneMapping("hip", "hip_width", "hip_circumference", True, False, 1.0),
    ZoneMapping("thigh", "thigh_width", "thigh_circumference", True, False, 0.5),
    ZoneMapping("neck", "neck_circumference", "neck_circumference", False, False, 0.2),
    ZoneMapping("shoulders", "shoulder_width", "shoulder_width", False, True, 0.25),
    ZoneMapping("sleeve_length", "sleeve_length", "arm_length", False, True, 0.25),
    ZoneMapping("inseam", "inseam", "inseam", False, True, 0.25),
)

# Zones that cannot be altered or tolerated when wrong, per category.
CRITICAL_ZONES: dict[str, tuple[str, ...]] = {
    "shirts": ("shoulders", "neck"),
    "tailoring": ("shoulders", "chest"),
    "outerwear": ("shoulders", "chest"),
    "knitwear": ("chest",),
    "tops": ("chest",),
    "trousers": ("waist", "hip"),
    "jeans": ("waist", "hip"),
    "dresses": ("bust", "waist"),
    "skirts": ("waist",),
    "footwear": ("foot_length", "foot_width"),
}

# Used only when the garment publishes no intended_ease for a zone.
DEFAULT_EASE: dict[tuple[str, str], tuple[float, float]] = {
    ("shirts", "chest"): (10.0, 22.0),
    ("shirts", "waist"): (10.0, 28.0),
    ("shirts", "shoulders"): (0.0, 2.0),
    ("shirts", "neck"): (1.0, 2.5),
    ("shirts", "sleeve_length"): (-1.0, 2.5),
    ("knitwear", "chest"): (8.0, 24.0),
    ("tailoring", "chest"): (10.0, 16.0),
    ("tailoring", "shoulders"): (0.0, 1.5),
    ("trousers", "waist"): (1.0, 4.0),
    ("trousers", "hip"): (4.0, 12.0),
    ("jeans", "waist"): (0.0, 3.0),
}

GENERIC_EASE: dict[bool, tuple[float, float]] = {
    False: (6.0, 20.0),  # girths
    True: (0.0, 3.0),    # linear
}

# How a stated preference shifts the acceptable ease band, in cm, for a girth zone.
# Linear zones use a quarter of the shift.
PREFERENCE_SHIFT: dict[str, float] = {
    "very_fitted": -7.0,
    "fitted": -3.5,
    "regular": 0.0,
    "relaxed": 4.0,
    "oversized": 10.0,
}

# Comfortable extension usable for fit, by declared stretch class.
STRETCH_CLASS_FRACTION: dict[str, float] = {
    "none": 0.0,
    "low": 0.02,
    "medium": 0.05,
    "high": 0.10,
}


def critical_zones(category: str, garment: dict) -> set[str]:
    declared = garment.get("critical_zones")
    if declared:
        return set(declared)
    return set(CRITICAL_ZONES.get(category, ()))


def default_ease(category: str, zone: str, linear: bool) -> tuple[float, float]:
    if (category, zone) in DEFAULT_EASE:
        return DEFAULT_EASE[(category, zone)]
    return GENERIC_EASE[linear]
