"""Small geodesy helpers and the public map data of the synthetic city.

Only *public* geography lives here: zone centres and landmark names that a real
app would get from a map service. The popular routes runners actually use are
ground truth and live in generator.py.
"""
from __future__ import annotations

import numpy as np

LAT0, LON0 = 19.05, 72.85  # projection origin (central Mumbai)
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON = 111_320.0 * np.cos(np.radians(LAT0))

ZONE_CENTERS = {
    "South Mumbai": (18.935, 72.825),
    "Central Mumbai": (19.015, 72.840),
    "Western Suburbs": (19.075, 72.835),
    "Eastern Suburbs": (19.105, 72.905),
    "North Suburbs": (19.195, 72.865),
}

LANDMARKS = {
    "Marine Drive": (18.9420, 72.8228),
    "Gateway of India": (18.9220, 72.8347),
    "Shivaji Park": (19.0269, 72.8384),
    "Worli Sea Face": (19.0135, 72.8160),
    "Bandra Bandstand": (19.0555, 72.8222),
    "Juhu Beach": (19.0985, 72.8265),
    "Powai Lake": (19.1270, 72.9050),
    "Aarey Colony": (19.1600, 72.8760),
    "Sanjay Gandhi National Park": (19.2290, 72.8730),
    "Bandra Kurla Complex": (19.0660, 72.8680),
    "Andheri Sports Complex": (19.1240, 72.8380),
}


def to_xy(lat, lon):
    """Equirectangular projection to metres around (LAT0, LON0)."""
    return (np.asarray(lon) - LON0) * M_PER_DEG_LON, (np.asarray(lat) - LAT0) * M_PER_DEG_LAT


def to_latlon(x, y):
    return LAT0 + np.asarray(y) / M_PER_DEG_LAT, LON0 + np.asarray(x) / M_PER_DEG_LON


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres; works element-wise on arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def nearest_zone(lat: float, lon: float) -> str:
    return min(ZONE_CENTERS, key=lambda z: haversine_m(lat, lon, *ZONE_CENTERS[z]))


def nearest_landmark(lat: float, lon: float) -> tuple[str, float]:
    name = min(LANDMARKS, key=lambda k: haversine_m(lat, lon, *LANDMARKS[k]))
    return name, float(haversine_m(lat, lon, *LANDMARKS[name]))
