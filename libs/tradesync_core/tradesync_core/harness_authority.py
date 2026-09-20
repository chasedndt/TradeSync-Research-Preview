"""What counts as a harness claiming authority, found wherever it is hidden.

Moved out of ``agent_harness.py`` unchanged. A model's answer is refused if it
carries a scoring, approval or execution field at the top level, nested at any
depth up to eight, or as structure inside its own prose content — including JSON
wrapped in a code fence. A sentence that merely uses the word "approved" is
prose and is not refused: the check is for structure, not vocabulary.
``agent_harness`` re-exports every public name here.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

# Fields a response must never carry. A harness output that sets any of these is
# claiming an authority the harness does not have. Refused by name rather than
# stripped: a model emitting `approved: true` is a signal about the prompt it
# was given, and silently deleting it destroys that signal.
FORBIDDEN_RESPONSE_FIELDS = frozenset(
    {
        "admitted",
        "approved",
        "approval",
        "authority",
        "confidence_score",
        "direction",
        "execute",
        "execution_authority",
        "gate",
        "order",
        "score",
        "scoring_allowed",
        "side",
        "signal",
        "signal_kind",
        "tier",
        "trust",
        "weight",
    }
)


def content_claims_authority(content: str) -> list[str]:
    """Forbidden fields inside an answer that is itself JSON.

    Only fires when the whole answer parses as a JSON object or array — a
    sentence that happens to contain the word "approved" is prose, and refusing
    prose for using an English word would make the harness useless. The check is
    for structure, not vocabulary.
    """
    text = content.strip()
    # Models often fence their JSON. Unwrap one fence before giving up.
    if text.startswith("```"):
        without_fence = text.split("```")
        text = without_fence[1] if len(without_fence) > 1 else text
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    if not text or text[0] not in "{[":
        return []
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return []
    top = (
        sorted(FORBIDDEN_RESPONSE_FIELDS.intersection(parsed))
        if isinstance(parsed, Mapping)
        else []
    )
    return sorted(set(top) | set(_nested_forbidden(parsed)))


def _nested_forbidden(value: Any, path: str = "", depth: int = 0) -> list[str]:
    """Every forbidden key anywhere in the structure, with its path."""
    if depth > 8:
        return []
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            here = f"{path}.{key}" if path else str(key)
            if depth > 0 and key in FORBIDDEN_RESPONSE_FIELDS:
                found.append(here)
            found.extend(_nested_forbidden(child, here, depth + 1))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_nested_forbidden(child, f"{path}[{index}]", depth + 1))
    return sorted(found)
