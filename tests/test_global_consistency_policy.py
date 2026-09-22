"""Checks for the evaluation-only global consistency advancement gate."""

from scripts.compare_global_consistency_policy import _gate


def evidence(*, shown=13, skill=10.0):
    return {
        "shown_weeks": shown,
        "skill_vs_zero_percent": skill if shown else None,
    }


def candidate(*, overall=10.0, stratum=10.0, removed=-1.0, removed_weeks=13):
    return {
        "overall": evidence(skill=overall),
        "by_stratum": {"dense": evidence(skill=stratum)},
        "removed_control_forecasts": evidence(shown=removed_weeks, skill=removed),
    }


def product(*, current=True, consistency=False):
    return {
        "decision": {
            "permissions": {
                "current_control": current,
                "global_consistency": consistency,
            }
        }
    }


def test_gate_passes_only_when_removed_forecasts_do_not_add_value():
    assert _gate(candidate(), [product(current=True, consistency=False)])["status"] == "passed"


def test_gate_rejects_useful_removed_forecasts():
    result = _gate(candidate(removed=5), [product()])
    assert result["status"] == "failed"
    assert "consistency_removed_forecasts_that_beat_zero" in result["failure_reasons"]


def test_gate_rejects_weak_retained_stratum():
    result = _gate(candidate(stratum=0), [product()])
    assert result["status"] == "failed"
    assert "retained_forecasts_did_not_beat_zero_in_dense" in result["failure_reasons"]


def test_gate_rejects_bypass_of_current_policy():
    result = _gate(candidate(), [product(current=False, consistency=True)])
    assert result["status"] == "failed"
    assert "consistency_bypassed_current_gate" in result["failure_reasons"]


def test_gate_is_inconclusive_when_nothing_is_removed():
    result = _gate(candidate(removed_weeks=0), [product()])
    assert result["status"] == "inconclusive"
    assert "consistency_removed_no_current_forecasts" in result["inconclusive_reasons"]


def test_gate_is_inconclusive_when_nothing_remains():
    value = candidate()
    value["overall"] = evidence(shown=0)
    result = _gate(value, [product()])
    assert result["status"] == "inconclusive"
    assert "candidate_showed_no_forecasts" in result["inconclusive_reasons"]
