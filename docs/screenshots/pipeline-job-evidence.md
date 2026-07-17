# Pipeline job evidence (submission)

## Success — completed run

```text
[success-demo] acquired processing lock for brasaland_weekly_performance_pipeline / 2026-07-06 — holding 0.2s
[success-demo] work finished
[success-demo] done status=completed job_id=135013f0-eb13-43ad-a452-d66abea1b668 target_date=2026-07-06
```

## Blocked — processing lock held (second instance)

```text
[holder] acquired processing lock for brasaland_weekly_performance_pipeline / 2026-07-13 — holding 5.0s
[blocked] LOCKED OUT: processing lock held for job_name=brasaland_weekly_performance_pipeline target_date=2026-07-13 by job_id=70736d0b-6716-45c6-ab98-86ccbd88ca79
[holder] work finished
[holder] done status=completed job_id=70736d0b-6716-45c6-ab98-86ccbd88ca79 target_date=2026-07-13
```

## Failed — simulated DB timeout → status=failed

```text
raised: simulated DB timeout
job status: failed
error_message: simulated DB timeout
target_date: 2026-07-20
```

## Schedule dry-run (cron + week window)

```text
schedule: 0 9 * * 1 (Every Monday at 09:00 UTC (Monday morning))
window: start=2026-07-06 end=2026-07-13 target_date=2026-07-06
dry-run: skipping pipeline execution
```
