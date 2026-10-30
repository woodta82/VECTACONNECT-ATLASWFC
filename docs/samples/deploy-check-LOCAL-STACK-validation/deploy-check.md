# Deployment check — http://127.0.0.1:3000

Expected release 4.9.0-wfc.20, schema wfc_0019.

| Item | Result | Detail |
|---|---|---|
| version | **PASSED** | {"expected": {"release": "4.9.0-wfc.20", "schema_revision": "wfc_0019"}, "live": {"status": "live", "release": "4.9.0-wfc.20", "build": "local-stack"}, "ready": {"status": "ready", "release": "4.9.0-wfc.20", "build": "local-stack", "schema_revision": "wfc_0019", "degraded_integrations": []}} |
| login | **PASSED** | {"shared login": true, "wrong password refused": true} |
| persistence | **PASSED** | {"marker": "deploy-check marker 20261030T093338Z", "recorded_at": "2026-10-30T09:33:38Z", "found_after_restart": true} |
| airports | **FAILED** | {"using": "seed", "total_records": 424, "dataset": {"key": "airport_seed", "name": "ATLAS bundled airport seed", "source": "curated by the ATLAS build (public knowledge; codes as published by ICAO/IATA)", "url": null, "licence": "no restriction", "version": "2026-10-30", "refreshed_at": "2026-10-30T00:00:00+00:00", "loaded_at": "2026-10-30T09:33:38.353743+00:00", "rows_loaded": 424}, "last_attempt |
| budget | **FAILED** | {"budget": {}, "kill_switch": true, "extractor": "connected", "search": "connected"} |
| failures | **PASSED** | {"failed_or_dead_jobs_listed": 0, "queue": [{"status": "succeeded", "n": 2, "oldest_seconds": "6.022667"}]} |
| backup | **NOT CHECKED** | "follow docs/RESTORE_RUNBOOK.md, then re-run with --backup-restored" |
| browser | **FAILED** | {"signed_in": true, "dashboard_summaries": ["Priority opportunities", "Deadlines approaching", "Companies and people researched", "Research gaps and next actions"], "directory_panel": "Directory in use: Bundled seed only\nSeed\nTotal records\n424 (0 from the maintained dataset, 424 from the bundled seed)\nSource\ncurated by the ATLAS build (public knowledge; codes as published by ICAO/IATA) \u00b7 |
