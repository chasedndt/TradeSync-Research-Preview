"""Did a call fire into the regime its rulebook expected?

A rulebook is written for a kind of market. One built to follow trends has no
business being judged on its behaviour in a market that went sideways, and a
run of losses in a regime the rulebook never claimed to handle is a different
finding from a run of losses in the regime it was designed for. Separating
those is what this measures.

Two properties make the verdict trustworthy, and both are the point of the
module:

- **The regime comes from before the entry.** It is the frozen label in
  ``opportunity_entry_regimes``, computed by ``entry_regime`` from candles that
  had fully closed before the signal fired, written once and never recomputed.
  Nothing measured after the decision enters it.
- **The expectation comes from the rulebook as it was, not as it is.** A call
  freezes the digest of the rulebook that produced it. This module judges
  against the configuration carrying that digest, and refuses to judge when it
  is handed anything else. A rulebook edited tomorrow therefore cannot turn
  yesterday's fit into a misfit, which is exactly how a measurement quietly
  becomes a way of proving whatever is currently believed.

Notation
--------

For one call ``c``:

=================  ===============================================  ======
Symbol             Meaning                                          Unit
=================  ===============================================  ======
``r(c)``           regime in force at entry, from closed candles     --
``dir(c)``         the side the call took, LONG or SHORT             --
``d(c)``           digest of the rulebook frozen on the call         hex
``E_d[dir]``       regimes rulebook ``d`` expects for that side      set
=================  ===============================================  ======

``r(c)`` is one of ``rising``, ``falling``, ``flat`` or ``unknown``. The verdict
is ``fit`` when ``r(c)`` is in ``E_d[dir(c)]`` and ``misfit`` when it is not.

Declaring an expectation
------------------------

A rulebook declares one under the optional key ``regime_expectation``::

    "regime_expectation": {
      "schema": "regime_expectation_v1",
      "LONG": ["rising"],
      "SHORT": ["falling"]
    }

**No rulebook in this repository declares one today**, so every current call
abstains with ``undeclared``. That is the honest answer and it is reported as
one: the alternative, treating "the rulebook never said" as a misfit, would
manufacture a finding out of silence. Adding the key to a rulebook changes its
digest, which is a new rulebook version and an operator decision; nothing here
writes one.

Abstaining
----------

Five verdicts abstain, each counted separately because each has a different
remedy: ``undeclared`` (the rulebook expects nothing), ``unlabelled`` (no entry
regime, or ``unknown``), ``digest_mismatch`` (the rulebook offered is not the
one the call was scored under), ``rulebook_altered`` (the stored configuration
no longer hashes to its stored digest) and ``undirected`` (the call took no
side). An abstention is never a misfit and never a zero.

The rate
--------

``regime_fit_rate = fit / (fit + misfit)``, dimensionless, in [0, 1].
Abstentions are excluded from both parts and reported beside it.

Worked example, by hand
-----------------------

Rulebook ``R`` at digest ``d`` declares ``LONG -> {rising}`` and
``SHORT -> {falling}``. Four LONG calls, each frozen at ``d`` unless stated:

===== ================  ===============================================
Call  ``r(c)``          verdict
===== ================  ===============================================
A     ``rising``        ``fit``: rising is in ``E_d[LONG] = {rising}``
B     ``falling``       ``misfit``: falling is not
C     ``unknown``       abstains, ``unlabelled``
D     ``rising``        abstains, ``digest_mismatch``: frozen at ``d'``
===== ================  ===============================================

One fit, one misfit, two abstentions:
``regime_fit_rate = 1 / (1 + 1) = 0.5`` over two judged calls, with the two
abstentions reported rather than folded in. Had they been counted as misfits
the rate would read ``1 / 4 = 0.25`` and would be describing the gaps in the
evidence, not the rulebook.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .entry_regime import REGIMES
from .regime_weights import config_digest

SCHEMA_VERSION = "regime_fit_v1"

# The optional key a rulebook uses to say which regimes it was written for.
EXPECTATION_KEY = "regime_expectation"
EXPECTATION_SCHEMA = "regime_expectation_v1"

DIRECTIONS = ("LONG", "SHORT")
# "unknown" is the absence of a label, so a rulebook cannot expect it.
DECLARABLE_REGIMES = frozenset(r for r in REGIMES if r != "unknown")

FIT, MISFIT = "fit", "misfit"
UNDECLARED, UNLABELLED = "undeclared", "unlabelled"
DIGEST_MISMATCH, RULEBOOK_ALTERED, UNDIRECTED, NO_RULEBOOK = (
    "digest_mismatch", "rulebook_altered", "undirected", "no_rulebook")
ABSTENTIONS = (UNDECLARED, UNLABELLED, DIGEST_MISMATCH, RULEBOOK_ALTERED, UNDIRECTED, NO_RULEBOOK)


class RegimeFitError(ValueError):
    """Raised for a malformed declaration, never for an ordinary abstention."""


def expectation(config: Mapping[str, Any]) -> dict[str, frozenset[str]] | None:
    """The regimes a rulebook expects per side, or None when it declares none.

    A declaration that is present but malformed raises rather than reading as
    "declares nothing": a broken expectation silently becoming an abstention is
    how a rulebook ends up never being judged while appearing to be.
    """
    if not isinstance(config, Mapping):
        raise RegimeFitError("a rulebook configuration must be a mapping")
    declared = config.get(EXPECTATION_KEY)
    if declared is None:
        return None
    if not isinstance(declared, Mapping):
        raise RegimeFitError(f"{EXPECTATION_KEY} must be an object")
    if declared.get("schema") != EXPECTATION_SCHEMA:
        raise RegimeFitError(f"{EXPECTATION_KEY}.schema must be {EXPECTATION_SCHEMA}")
    out: dict[str, frozenset[str]] = {}
    for side in DIRECTIONS:
        regimes = declared.get(side)
        if regimes is None:
            continue
        if not isinstance(regimes, (list, tuple)) or not regimes:
            raise RegimeFitError(f"{EXPECTATION_KEY}.{side} must be a non-empty list of regimes")
        unknown = [r for r in regimes if r not in DECLARABLE_REGIMES]
        if unknown:
            raise RegimeFitError(
                f"{EXPECTATION_KEY}.{side} names regimes that cannot be expected: {sorted(map(str, unknown))}")
        out[side] = frozenset(str(r) for r in regimes)
    if not out:
        raise RegimeFitError(f"{EXPECTATION_KEY} declares no side")
    return out


def _abstain(verdict: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "verdict": verdict, "judged": False,
            "detail": detail, "expected": None, **extra}


def judge(call: Mapping[str, Any], rulebook: Mapping[str, Any] | None) -> dict[str, Any]:
    """Judge one call against the rulebook it was scored under.

    ``call`` carries ``direction`` (``LONG`` or ``SHORT``), ``entry_regime``
    (the frozen label, possibly None or ``unknown``) and ``rulebook_digest``
    (the digest frozen on the call). ``rulebook`` is the stored row: ``config``
    and ``config_digest``, or None when that rulebook is no longer held.
    """
    if not isinstance(call, Mapping):
        raise TypeError("a call must be a mapping")
    frozen = call.get("rulebook_digest")
    observed = call.get("entry_regime")
    direction = call.get("direction")
    common = {"entry_regime": observed, "direction": direction, "call_rulebook_digest": frozen}

    if rulebook is None:
        return _abstain(NO_RULEBOOK, "the rulebook this call was scored under is not held, so nothing declares an "
                                     "expectation for it", **common)
    config = rulebook.get("config")
    stored = rulebook.get("config_digest")
    if not isinstance(config, Mapping) or not stored:
        return _abstain(NO_RULEBOOK, "the rulebook row carries no configuration and digest to judge against", **common)
    if config_digest(config) != stored:
        return _abstain(RULEBOOK_ALTERED,
                        "the stored rulebook configuration no longer hashes to its stored digest; it is not the "
                        "configuration this call was scored under", **common)
    if not frozen or frozen != stored:
        return _abstain(DIGEST_MISMATCH,
                        f"this call was scored under rulebook digest {frozen or 'none recorded'}, not {stored}; "
                        "a later rulebook cannot rewrite an earlier verdict", **common)

    declared = expectation(config)
    if declared is None:
        return _abstain(UNDECLARED, "this rulebook declares no regime expectation, so there is nothing to match "
                                    "the entry regime against", **common)
    if direction not in declared:
        return _abstain(UNDIRECTED, f"the rulebook declares no expectation for direction {direction!r}", **common)
    expected = sorted(declared[direction])
    if observed is None or observed == "unknown":
        return _abstain(UNLABELLED, "no regime was labelled for this entry; the candles before it did not cover the "
                                    "lookback", expected=expected, **common)

    fits = observed in declared[direction]
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": FIT if fits else MISFIT,
        "judged": True,
        "expected": expected,
        "detail": f"entry regime {observed!r} " + ("is" if fits else "is not")
                  + f" among the regimes this rulebook expects for a {direction} call: {', '.join(expected)}",
        **common,
    }


def summarise(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Fit across a cohort, with every abstention kept out of the rate.

    ``abstained_by_reason`` is reported because the reasons are not
    interchangeable: an undeclared expectation is a gap in the rulebook, an
    unlabelled entry is a gap in the candle history, and a digest mismatch is
    a call scored under a rulebook nobody is judging against.
    """
    rows = list(results)
    fits = sum(1 for row in rows if row.get("verdict") == FIT)
    misfits = sum(1 for row in rows if row.get("verdict") == MISFIT)
    judged = fits + misfits
    by_reason = {reason: sum(1 for row in rows if row.get("verdict") == reason) for reason in ABSTENTIONS}
    return {
        "schema_version": SCHEMA_VERSION,
        "calls": len(rows),
        "judged": judged,
        "fit": fits,
        "misfit": misfits,
        "regime_fit_rate": round(fits / judged, 6) if judged else None,
        "abstained": len(rows) - judged,
        "abstained_by_reason": {reason: count for reason, count in by_reason.items() if count},
        "note": (
            "The regime is the entry-time label from candles closed before the call, and the expectation is read "
            "from the rulebook carrying the digest frozen on that call, so a later rulebook change cannot rewrite "
            "an earlier verdict. Abstentions are counted apart and are never misfits."
        ),
    }
