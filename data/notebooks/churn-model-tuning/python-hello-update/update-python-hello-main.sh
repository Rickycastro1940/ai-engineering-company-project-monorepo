#!/usr/bin/env bash
# Update Rickycastro1940/python-hello main with the StreamLoop Pipeline + cv_results_ fix.
# Run on a machine where YOUR GitHub credentials can push that fork.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Rickycastro1940/python-hello.git}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="${1:-$SCRIPT_DIR/streamloop-python-hello.patch}"
WORKDIR="${WORKDIR:-/tmp/python-hello-main-update}"

if [[ ! -f "$PATCH" ]]; then
  echo "Patch not found: $PATCH" >&2
  echo "Download streamloop-python-hello.patch from the Cloud Agent artifacts first." >&2
  exit 1
fi

rm -rf "$WORKDIR"
git clone "$REPO_URL" "$WORKDIR"
cd "$WORKDIR"
git checkout main
git pull --ff-only origin main

# 3-commit mailbox patch (format-patch); applies cleanly on current main
git am "$PATCH"

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
if bad:
    print("CHECK FAILED:", "; ".join(bad))
    sys.exit(1)
print("CHECK OK: Pipeline + cv_results_ mean/std; no external get_dummies/scaler")
PY

git push origin main
echo "Done. python-hello main now has the StreamLoop fix — resubmit in 4Geeks."
