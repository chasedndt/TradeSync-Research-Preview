"""Versioned, explainable regime weighting for paper-shadow evaluation.

This module deliberately does not replace the legacy production scorer. It is a
deterministic foundation for loading, validating, explaining, and comparing
versioned rulebooks before any rulebook can be promoted.

It is the stable import surface and the command line
(``python -m tradesync_core.regime_weights``). The work lives beside it, one
responsibility per file:

- ``rulebook_validation``: validating a rulebook and binding it to its digest;
- ``block_evaluation``: the quality-weighted score and the paper-risk cap;
- ``rulebook_diff``: comparing two rulebook versions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .block_evaluation import bounded_z_score, evaluate_blocks
from .rulebook_diff import diff_rulebooks
from .rulebook_validation import (
    RegimeRulebook,
    RulebookValidationError,
    config_digest,
    load_rulebook,
    validate_rulebook,
)

__all__ = [
    "RegimeRulebook",
    "RulebookValidationError",
    "bounded_z_score",
    "build_cli",
    "config_digest",
    "diff_rulebooks",
    "evaluate_blocks",
    "load_rulebook",
    "main",
    "validate_rulebook",
]


def _read_inputs(path: str | Path) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise RulebookValidationError("score input root must be an object")
    return value


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradesync_core.regime_weights",
        description="Validate, explain, score, and compare TradeSync regime rulebooks.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate one rulebook")
    validate.add_argument("rulebook")

    explain = commands.add_parser("explain", help="show the active mathematical choices")
    explain.add_argument("rulebook")

    score = commands.add_parser("score", help="score one block-input fixture")
    score.add_argument("rulebook")
    score.add_argument("inputs")

    diff = commands.add_parser("diff", help="compare two rulebook versions")
    diff.add_argument("before")
    diff.add_argument("after")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    try:
        if args.command == "validate":
            rulebook = load_rulebook(args.rulebook)
            _print_json(
                {
                    "valid": True,
                    "rulebook_id": rulebook.rulebook_id,
                    "version": rulebook.version,
                    "digest": rulebook.digest,
                    "block_count": len(rulebook.weights),
                    "weight_sum": sum(rulebook.weights.values()),
                }
            )
            return 0

        if args.command == "explain":
            rulebook = load_rulebook(args.rulebook)
            _print_json(
                {
                    "rulebook_id": rulebook.rulebook_id,
                    "version": rulebook.version,
                    "normalization": f"tanh(z / {rulebook.compression_k:g})",
                    "weights": rulebook.weights,
                    "paper_risk_rule": "minimum active cap wins",
                    "paper_risk_caps": rulebook.risk_caps,
                    "activation_mode": rulebook.data["governance"]["activation_mode"],
                }
            )
            return 0

        if args.command == "score":
            rulebook = load_rulebook(args.rulebook)
            inputs = _read_inputs(args.inputs)
            _print_json(
                evaluate_blocks(
                    rulebook,
                    inputs.get("block_scores", {}),
                    inputs.get("data_quality", {}),
                    inputs.get("risk_flags", []),
                )
            )
            return 0

        if args.command == "diff":
            _print_json(diff_rulebooks(load_rulebook(args.before), load_rulebook(args.after)))
            return 0
    except (OSError, json.JSONDecodeError, RulebookValidationError) as exc:
        print(f"ERROR: {exc}")
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
