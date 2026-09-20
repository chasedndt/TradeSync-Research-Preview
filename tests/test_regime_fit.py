"""Regime fit: the entry-time regime against the expectation of the rulebook that scored the call.

The load-bearing property is that an old verdict cannot be rewritten. A call is
judged only against the configuration carrying the digest frozen on it, and
anything else abstains.
"""

import pytest

from tradesync_core import regime_fit
from tradesync_core.regime_weights import config_digest


def config(expect=True, **over):
    base = {"schema_version": "regime_rulebook_v1", "rulebook_id": "tradesync-intraday-regime", "version": "1.0.0"}
    if expect:
        base[regime_fit.EXPECTATION_KEY] = {"schema": "regime_expectation_v1",
                                            "LONG": ["rising"], "SHORT": ["falling"]}
    base.update(over)
    return base


def stored(cfg=None):
    cfg = config() if cfg is None else cfg
    return {"config": cfg, "config_digest": config_digest(cfg)}


def call(regime="rising", direction="LONG", digest=None, rulebook=None):
    rulebook = stored() if rulebook is None else rulebook
    return {"direction": direction, "entry_regime": regime,
            "rulebook_digest": rulebook["config_digest"] if digest is None else digest}


def test_a_long_in_a_rising_market_fits_the_rulebook_that_expects_one():
    book = stored()
    result = regime_fit.judge(call(rulebook=book), book)
    assert result["verdict"] == "fit" and result["judged"] is True
    assert result["expected"] == ["rising"]


def test_a_long_in_a_falling_market_is_a_misfit():
    book = stored()
    result = regime_fit.judge(call("falling", rulebook=book), book)
    assert result["verdict"] == "misfit" and result["judged"] is True


def test_a_short_is_judged_against_its_own_expected_regimes():
    book = stored()
    assert regime_fit.judge(call("falling", "SHORT", rulebook=book), book)["verdict"] == "fit"
    assert regime_fit.judge(call("rising", "SHORT", rulebook=book), book)["verdict"] == "misfit"


def test_a_rulebook_that_declares_nothing_abstains_and_is_never_a_misfit():
    """Every rulebook in this repository is this case today. Silence is not a failure."""
    book = stored(config(expect=False))
    result = regime_fit.judge(call(rulebook=book), book)
    assert result["verdict"] == "undeclared" and result["judged"] is False
    assert "nothing to match" in result["detail"]


def test_an_unlabelled_entry_abstains_and_still_reports_what_was_expected():
    book = stored()
    for regime in (None, "unknown"):
        result = regime_fit.judge(call(regime, rulebook=book), book)
        assert result["verdict"] == "unlabelled" and result["judged"] is False
        assert result["expected"] == ["rising"]


def test_a_later_rulebook_cannot_rewrite_an_earlier_verdict():
    """The call was scored under one digest; a different rulebook is refused.

    Without this, editing a rulebook would silently restate the history of every
    call ever scored under the version it replaced.
    """
    book = stored()
    later = stored(config(version="2.0.0"))
    assert later["config_digest"] != book["config_digest"]
    result = regime_fit.judge(call(rulebook=book), later)
    assert result["verdict"] == "digest_mismatch" and result["judged"] is False
    assert "cannot rewrite an earlier verdict" in result["detail"]


def test_a_call_that_froze_no_digest_cannot_be_judged():
    book = stored()
    assert regime_fit.judge(call(digest="", rulebook=book), book)["verdict"] == "digest_mismatch"


def test_a_stored_configuration_that_no_longer_hashes_to_its_digest_is_refused():
    book = stored()
    tampered = {"config": {**book["config"], "version": "1.0.1"}, "config_digest": book["config_digest"]}
    result = regime_fit.judge(call(rulebook=book), tampered)
    assert result["verdict"] == "rulebook_altered" and result["judged"] is False


def test_a_missing_rulebook_abstains():
    assert regime_fit.judge(call(), None)["verdict"] == "no_rulebook"
    assert regime_fit.judge(call(), {"config": None, "config_digest": None})["verdict"] == "no_rulebook"


def test_a_call_with_no_side_abstains():
    book = stored()
    result = regime_fit.judge(call(direction="NONE", rulebook=book), book)
    assert result["verdict"] == "undirected" and result["judged"] is False


def test_a_rulebook_that_declares_only_one_side_abstains_on_the_other():
    cfg = config(**{regime_fit.EXPECTATION_KEY: {"schema": "regime_expectation_v1", "LONG": ["rising"]}})
    book = stored(cfg)
    assert regime_fit.judge(call(rulebook=book), book)["verdict"] == "fit"
    assert regime_fit.judge(call("falling", "SHORT", rulebook=book), book)["verdict"] == "undirected"


def test_a_declaration_may_name_several_regimes():
    cfg = config(**{regime_fit.EXPECTATION_KEY: {"schema": "regime_expectation_v1", "LONG": ["rising", "flat"]}})
    book = stored(cfg)
    assert regime_fit.judge(call("flat", rulebook=book), book)["verdict"] == "fit"
    assert regime_fit.judge(call("falling", rulebook=book), book)["verdict"] == "misfit"


def test_no_rulebook_in_the_repository_declares_an_expectation_yet():
    """Recorded so that the day one does, this test is the place it is noticed."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "config" / "regime" / "regime-rulebook-v1.json"
    assert regime_fit.expectation(json.loads(path.read_text(encoding="utf-8"))) is None


def test_a_malformed_declaration_raises_rather_than_reading_as_silence():
    """A broken expectation that abstained would never be judged and never noticed."""
    for broken in (
        {"schema": "wrong_schema", "LONG": ["rising"]},
        {"schema": "regime_expectation_v1"},
        {"schema": "regime_expectation_v1", "LONG": []},
        {"schema": "regime_expectation_v1", "LONG": "rising"},
        {"schema": "regime_expectation_v1", "LONG": ["sideways"]},
        # A rulebook cannot expect the absence of a label.
        {"schema": "regime_expectation_v1", "LONG": ["unknown"]},
    ):
        with pytest.raises(regime_fit.RegimeFitError):
            regime_fit.expectation(config(**{regime_fit.EXPECTATION_KEY: broken}))


def test_the_worked_example_rate_excludes_both_abstentions():
    """One fit, one misfit, one unlabelled, one digest mismatch: 1 / (1 + 1) = 0.5.

    Counting the abstentions as misfits would read 1 / 4 = 0.25 and would be
    describing the gaps in the evidence rather than the rulebook.
    """
    book = stored()
    other = stored(config(version="2.0.0"))
    rows = [
        regime_fit.judge(call("rising", rulebook=book), book),
        regime_fit.judge(call("falling", rulebook=book), book),
        regime_fit.judge(call("unknown", rulebook=book), book),
        regime_fit.judge(call("rising", digest=other["config_digest"]), book),
    ]
    summary = regime_fit.summarise(rows)
    assert summary["calls"] == 4 and summary["judged"] == 2
    assert summary["fit"] == 1 and summary["misfit"] == 1
    assert summary["regime_fit_rate"] == 0.5
    assert summary["abstained"] == 2
    assert summary["abstained_by_reason"] == {"unlabelled": 1, "digest_mismatch": 1}


def test_a_cohort_that_could_not_be_judged_has_no_rate_rather_than_a_zero():
    book = stored(config(expect=False))
    summary = regime_fit.summarise([regime_fit.judge(call(rulebook=book), book) for _ in range(3)])
    assert summary["regime_fit_rate"] is None and summary["judged"] == 0
    assert summary["abstained_by_reason"] == {"undeclared": 3}
