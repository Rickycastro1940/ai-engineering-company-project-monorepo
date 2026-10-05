#!/usr/bin/env bash
# Update Rickycastro1940/python-hello main with the StreamLoop Pipeline + cv_results_ fix.
# Run on a machine where YOUR GitHub credentials can push that fork.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Rickycastro1940/python-hello.git}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
READY_DIR="${READY_DIR:-$SCRIPT_DIR/ready}"
WORKDIR="${WORKDIR:-/tmp/python-hello-main-update}"

if [[ ! -f "$READY_DIR/notebooks/streamloop_churn_eda.ipynb" ]]; then
  echo "Ready notebook not found: $READY_DIR/notebooks/streamloop_churn_eda.ipynb" >&2
  exit 1
fi
if [[ ! -f "$READY_DIR/tuning_report.md" ]]; then
  echo "Ready report not found: $READY_DIR/tuning_report.md" >&2
  exit 1
fi

rm -rf "$WORKDIR"
git clone "$REPO_URL" "$WORKDIR"
cd "$WORKDIR"
git checkout main
git pull --ff-only origin main

mkdir -p notebooks
cp "$READY_DIR/notebooks/streamloop_churn_eda.ipynb" notebooks/streamloop_churn_eda.ipynb
cp "$READY_DIR/tuning_report.md" tuning_report.md
if [[ -f "$READY_DIR/notebooks/churn-requirements.txt" ]]; then
  cp "$READY_DIR/notebooks/churn-requirements.txt" notebooks/churn-requirements.txt
fi

# Sanity: grader checklist
python3 - <<'PY'
import json, re, sys
nb = json.load(open("notebooks/streamloop_churn_eda.ipynb"))
src = "\n".join("".join(c.get("source", [])) for c in nb["cells"])
bad = []
if "get_dummies(" in src:
    bad.append("still has get_dummies")
if re.search(r"scaler\.fit_transform", src):
    bad.append("still has scaler.fit_transform")
if "Pipeline(" not in src:
    bad.append("missing Pipeline")
if "cv_results_" not in src or "std_test_score" not in src:
    bad.append("missing cv_results_ mean/std inspection")
if "scoring='roc_auc'" not in src and 'scoring="roc_auc"' not in src:
    bad.append("missing roc_auc scoring")
if "trade-off" not in src.lower() and "Trade-off" not in open("tuning_report.md").read():
    bad.append("missing final-model trade-off")
if bad:
    print("CHECK FAILED:", "; ".join(bad))
    sys.exit(1)
print("CHECK OK: Pipeline + roc_auc + cv_results_ mean/std + trade-off; no external get_dummies/scaler")
PY

git add notebooks/streamloop_churn_eda.ipynb tuning_report.md
if [[ -f notebooks/churn-requirements.txt ]]; then
  git add notebooks/churn-requirements.txt
fi

if git diff --cached --quiet; then
  echo "Nothing to commit — python-hello main already has the fix."
  exit 0
fi

git commit -m "$(cat <<'EOF'
Fix StreamLoop churn notebook for Pipeline + CV stability resubmit

Put imputer/encoder/scaler + classifier in one sklearn Pipeline, keep
ROC-AUC search, inspect cv_results_ mean/std, and document the final
model trade-off in tuning_report.md.
EOF
)"

git push origin main
echo "Done. python-hello main now has the StreamLoop fix — resubmit in 4Geeks."
