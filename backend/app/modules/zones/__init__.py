"""Zone feature: named cells on an integer grid plus the distance metric.

* ``models.Zone``       - slug, name, grid ``x``/``y`` (one zone per cell)
* ``grid``              - Manhattan ``grid_distance`` (+ its SQL twin)
* ``zone_router``       - ``GET /api/zones`` (public list)

Cooks are placed in a zone (``CookProfile.zone``); the public dish menu
filters on it (``?zone=`` / ``&max_distance=``).
"""

from app.modules.zones.router import zone_router

__all__ = ["zone_router"]
