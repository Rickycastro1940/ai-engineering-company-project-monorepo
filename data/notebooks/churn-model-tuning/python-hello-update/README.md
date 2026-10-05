# Update `Rickycastro1940/python-hello` main

Cloud Agent cannot push that fork (403 for `cursor[bot]`). Run this **as Rickycastro1940**
to resubmit StreamLoop with the grader fixes:

1. Preprocessing in one sklearn `Pipeline` (no `get_dummies` / external scaler)
2. Keep **ROC-AUC** search rationale
3. Inspect `cv_results_` mean **and** fold std
4. Document final-model trade-off in `tuning_report.md`

```bash
cd data/notebooks/churn-model-tuning/python-hello-update
bash update-python-hello-main.sh
```

The script copies files from `ready/` into a fresh clone of `python-hello`, runs the
grader checklist, commits, and pushes `main`.
