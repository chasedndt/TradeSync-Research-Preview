"""Every research-trial specification version, and the evaluator that belongs to it.

A registered trial is evaluated by the version it was registered under, found in
the stored specification itself, so a new version can never re-read an old
registration under new rules. v1 stays registerable nowhere and evaluable
forever: trials already registered under it keep working exactly as they were,
and new registrations use the version that describes what a managed paper
position actually is (``research_trial_v2``).

v1 is not offered for new registrations because its own text would be wrong the
moment it was used: it names three markets and scenario funding, and every
position it could admit now runs over the configured universe with settled
hourly funding. Freezing a specification means never editing it; it does not
mean going on registering one that no longer describes the experiment.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import research_trial as v1
from . import research_trial_v2 as v2

LATEST = v2.SCHEMA
VERSIONS = (v1.specification("scalp")["schema"], v2.SCHEMA)
REGISTERABLE = (v2.SCHEMA,)
RETIRED_FOR_REGISTRATION = {
    v1.specification("scalp")["schema"]: (
        "research-trial-v1 is frozen for the trials registered under it: its text names three markets and "
        "scenario funding, while managed paper positions run over the configured universe with settled hourly "
        "funding. Register research-trial-v2 instead."
    )
}


def version_of(spec: Mapping[str, Any]) -> str:
    """The version a stored specification was registered under."""
    schema = spec.get("schema") if isinstance(spec, Mapping) else None
    if schema not in VERSIONS:
        raise ValueError("Unknown research-trial specification version")
    return schema


def specification(style: str, *, version: str = LATEST, symbols: Sequence[str] | None = None) -> dict[str, Any]:
    """A fresh specification to register. Only versions in ``REGISTERABLE`` are offered."""
    if version in RETIRED_FOR_REGISTRATION:
        raise ValueError(RETIRED_FOR_REGISTRATION[version])
    if version != v2.SCHEMA:
        raise ValueError("Unknown research-trial specification version")
    return v2.specification(style, symbols)


def fingerprint(spec: Mapping[str, Any]) -> str:
    """The canonical-JSON fingerprint, the same function for every version."""
    return v1.fingerprint(spec)


def evaluate(spec: Mapping[str, Any], registered_at: float, now: float,
             rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate a stored specification with the evaluator of its own version."""
    version = version_of(spec)
    if version == v2.SCHEMA:
        return v2.evaluate(spec, registered_at, now, rows)
    return {"schema": version, **v1.evaluate(spec, registered_at, now, rows)}
