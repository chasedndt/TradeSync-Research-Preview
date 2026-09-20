"""The two execution environment flags, read on every call rather than assumed.

Moved out of ``app/main.py`` unchanged. ``app.main`` still exposes both names.
"""

import os


def execution_gate_enabled() -> bool:
    """Whether the global execution gate is actually open.

    Read rather than assumed: three rejection paths previously reported
    `execution_enabled: True` from a literal while `EXECUTION_ENABLED` was
    false, which is precisely the kind of untruthful status this system exists
    to avoid.
    """
    return os.getenv("EXECUTION_ENABLED", "false").strip().lower() == "true"


def paper_mode_enabled() -> bool:
    """Whether the system is in paper mode. Defaults to true, like the boundary.

    Used on paths where nothing was ever sent to a venue — a risk rejection, an
    RPC failure. Those reported `dry_run: False` from a literal, which asserts
    "this was a live action" about a request that never left the building. It is
    the same untruthful-status defect as `execution_enabled` above, one level
    down, and it reads far worse: a consumer seeing `dry_run: false` would
    reasonably conclude the system is live.

    Same variable and same fail-safe default as `exec-hl-svc`, so the two cannot
    disagree about which mode the system is in.
    """
    return os.getenv("DRY_RUN", "true").strip().lower() == "true"
