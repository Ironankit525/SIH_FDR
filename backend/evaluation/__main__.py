"""Measure the risk engine on the synthetic corpus.

    cd backend && ../.venv/bin/python -m evaluation            # full run, writes the report
    cd backend && ../.venv/bin/python -m evaluation --gate     # small corpus, rewrites the test baseline

Uses a throwaway database and document store; local demo data is never touched.
"""
import argparse
import json
import os
import tempfile
from datetime import date
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--genuine", type=int, default=60)
parser.add_argument("--per-problem", type=int, default=6)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--gate", action="store_true", help="run the small regression corpus and rewrite baseline.json")
args = parser.parse_args()

workdir = tempfile.mkdtemp(prefix="depositflow-eval-")
os.environ.update(DATABASE_URL=f"sqlite:///{workdir}/eval.db", STORAGE_PATH=f"{workdir}/documents", ENVIRONMENT="development",
                  JOB_MODE="local", EXTRACTION_PROVIDER="ocr", REQUIRE_MALWARE_SCAN="false", CLAMAV_HOST="")

from fastapi.testclient import TestClient  # noqa: E402  (configuration must be set first)
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import DEMO_PASSWORD, seed  # noqa: E402
from . import corpus, harness, report  # noqa: E402

GATE = {"genuine": 12, "per_problem": 2, "seed": 11}
HERE = Path(__file__).resolve().parent

Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed(db)
size = GATE if args.gate else {"genuine": args.genuine, "per_problem": args.per_problem, "seed": args.seed}
names, cases = corpus.build(**size)
clients = []


def client(_role=None):
    c = TestClient(app)
    clients.append(c)
    return c


results = harness.run(SessionLocal, client, names, cases, DEMO_PASSWORD)
summary = harness.metrics(results)
for c in clients:
    c.close()
if args.gate:
    (HERE / "baseline.json").write_text(json.dumps({"corpus": size, "metrics": summary}, indent=2) + "\n")
    print("Baseline written:", HERE / "baseline.json")
else:
    payload = {"generated_on": date.today().isoformat(), "corpus": size, "metrics": summary,
               "cases": [{key: value for key, value in r.items() if key != "deposit_id"} for r in results]}
    (HERE / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    (HERE.parents[1] / "docs" / "RISK_EVALUATION.md").write_text(report.markdown(payload))
    print("Report written: docs/RISK_EVALUATION.md and backend/evaluation/latest.json")
for stage, values in summary["stages"].items():
    print(f"{stage:>17}: AUC {values['auc']}  recall≥medium {values['recall_at_medium']}  recall≥high {values['recall_at_high']}  "
          f"FPR≥medium {values['false_positive_rate_at_medium']}  precision@10 {values['precision_at_10']}")
