"""Unit checks for the predeclared fresh sparse-abstention gate."""

from scripts.evaluate_sparse_abstention_fresh_cohort import _gate


def metrics(*, shown=13, skill=20.0, coverage=100.0):
    return {
        "shown_weeks": shown,
        "skill_vs_zero_percent": skill if shown else None,
        "coverage_percent": coverage,
    }


def summaries(*, overall_skill=20.0, removed_skill=-10.0, removed_weeks=13, stratum_skill=20.0):
    return {
        "overall": metrics(skill=overall_skill),
        "by_stratum": {"dense": metrics(skill=stratum_skill)},
        "removed_control_forecasts": metrics(
            shown=removed_weeks,
            skill=removed_skill,
            coverage=10.0 if removed_weeks else 0.0,
        ),
    }


def product(*, sparse=False, current=True, candidate=True, selected="last_week_total"):
    return {
        "decision": {
            "training_sparse": sparse,
            "selected_method": selected,
            "permissions": {
                "current_control": current,
                "sparse_abstention": candidate,
            },
        }
    }


def test_gate_passes_when_weak_sparse_forecasts_are_removed_only():
    products = [
        product(),
        product(sparse=True, current=True, candidate=False),
    ]
    result = _gate(summaries(), summaries(), products)
    assert result["status"] == "passed"
    assert result["failure_reasons"] == []


def test_gate_fails_if_candidate_changes_non_sparse_permission():
    result = _gate(summaries(), summaries(), [product(current=True, candidate=False)])
    assert result["status"] == "failed"
    assert "non_sparse_permission_changed" in result["failure_reasons"]


def test_gate_fails_if_retained_forecasts_do_not_beat_zero():
    result = _gate(summaries(), summaries(overall_skill=-1), [product()])
    assert result["status"] == "failed"
    assert "candidate_did_not_beat_zero_overall" in result["failure_reasons"]


def test_gate_fails_if_one_retained_stratum_does_not_beat_zero():
    result = _gate(summaries(), summaries(stratum_skill=0), [product()])
    assert result["status"] == "failed"
    assert "candidate_did_not_beat_zero_in_dense" in result["failure_reasons"]


def test_gate_fails_if_removed_sparse_forecasts_were_useful():
    result = _gate(
        summaries(),
        summaries(removed_skill=15),
        [product(sparse=True, current=True, candidate=False)],
    )
    assert result["status"] == "failed"
    assert "candidate_removed_sparse_forecasts_that_beat_zero" in result["failure_reasons"]


def test_gate_is_inconclusive_without_sparse_forecasts_to_challenge():
    result = _gate(summaries(), summaries(removed_weeks=0), [product()])
    assert result["status"] == "inconclusive"
    assert (
        "current_policy_showed_no_sparse_forecasts_to_challenge" in (result["inconclusive_reasons"])
    )


def test_gate_does_not_call_zero_coverage_perfect_accuracy():
    candidate = summaries()
    candidate["overall"] = metrics(shown=0, coverage=0)
    result = _gate(summaries(), candidate, [product(current=False, candidate=False, selected=None)])
    assert result["status"] == "inconclusive"
    assert "candidate_showed_no_forecasts" in result["inconclusive_reasons"]
