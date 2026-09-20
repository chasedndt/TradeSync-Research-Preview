"""One place for the jsonb quirk every read path here has to handle.

asyncpg returns a ``jsonb`` column as a decoded value on some paths and as the
raw string on others, depending on how the query was prepared. Routes that read
stored JSON all needed the same two lines; this is those two lines, moved out of
``app/main.py`` unchanged so the route modules can share them.
"""

from __future__ import annotations

import json
from typing import Any


def as_json(value: Any) -> Any:
    """asyncpg returns jsonb as str on some paths and as a value on others."""
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value
