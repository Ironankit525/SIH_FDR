"""Regression gate: the risk engine must not detect less, or alarm more, on the fixed evaluation corpus.

After an intended change that moves these numbers, inspect the full report (`python -m evaluation`) and
rewrite the baseline with `python -m evaluation --gate`.
"""
import json
from pathlib import Path

from app.seed import DEMO_PASSWORD
from evaluation import corpus, harness

BASELINE = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "baseline.json").read_text())


def test_detection_does_not_regress(env):
    factory, client = env
    names, cases = corpus.build(**BASELINE["corpus"])
    measured = harness.metrics(harness.run(factory, client, names, cases, DEMO_PASSWORD))
    for stage, expected in BASELINE["metrics"]["stages"].items():
        now = measured["stages"][stage]
        assert now["recall_at_medium"] >= expected["recall_at_medium"], (stage, "fewer problem cases reach medium")
        assert now["recall_at_high"] >= expected["recall_at_high"], (stage, "fewer problem cases reach high")
        assert now["false_positive_rate_at_medium"] <= expected["false_positive_rate_at_medium"], (stage, "more genuine cases alarmed")
        assert now["auc"] >= expected["auc"] - 0.02, (stage, "separation between problem and genuine cases fell")
        for kind, values in expected["per_kind"].items():
            if kind in corpus.COMPLIANCE_KINDS:
                # Declared non-compliance is not scored; it must be stopped by an open requirement instead.
                assert now["per_kind"][kind]["stopped_by_requirement"] >= values.get("stopped_by_requirement", 1.0), (stage, kind)
            elif kind in corpus.PROBLEM_KINDS:
                assert now["per_kind"][kind]["at_least_medium"] >= values["at_least_medium"], (stage, kind)


def test_evaluation_summary_is_for_officials(env):
    _, client = env
    summary = client("officer").get("/api/risk/evaluation")
    assert summary.status_code == 200 and "Not real-world" in summary.json()["notice"]
    assert set(summary.json()["stages"]) == {"intake", "after_bank_check"}
    assert client().get("/api/risk/evaluation").status_code == 403
