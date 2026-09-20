"""The headers a legacy alias answers with, naming the route that replaced it.

Moved out of ``app/main.py`` unchanged, so the aliases that moved with their routes
and the ones that stayed there share one definition.
"""

from fastapi import Response


def apply_deprecation_headers(response: Response, successor: str):
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'
