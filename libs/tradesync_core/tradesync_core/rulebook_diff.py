"""Comparing two rulebook versions: what moved, and by how much.

Moved out of ``regime_weights.py`` unchanged. Only differences are reported, so
a champion-and-challenger review reads as the change it actually is rather than
as two full configurations side by side.
"""

from __future__ import annotations

from typing import Any

from .feature_weights import diff_feature_weights
from .rulebook_validation import RegimeRulebook


def diff_rulebooks(before: RegimeRulebook, after: RegimeRulebook) -> dict[str, Any]:
    """Return a focused, machine-readable comparison of two rulebooks."""

    block_names = sorted(set(before.weights) | set(after.weights))
    weight_changes = {
        name: {
            "before": before.weights.get(name),
            "after": after.weights.get(name),
            "delta": (
                None
                if name not in before.weights or name not in after.weights
                else after.weights[name] - before.weights[name]
            ),
        }
        for name in block_names
        if before.weights.get(name) != after.weights.get(name)
    }

    cap_names = sorted(set(before.risk_caps) | set(after.risk_caps))
    risk_cap_changes = {
        name: {
            "before": before.risk_caps.get(name),
            "after": after.risk_caps.get(name),
        }
        for name in cap_names
        if before.risk_caps.get(name) != after.risk_caps.get(name)
    }

    return {
        "before": {"version": before.version, "digest": before.digest},
        "after": {"version": after.version, "digest": after.digest},
        "weight_changes": weight_changes,
        "feature_weight_changes": diff_feature_weights(before.feature_weights, after.feature_weights),
        "risk_cap_changes": risk_cap_changes,
        "compression_k": {
            "before": before.compression_k,
            "after": after.compression_k,
        },
    }
