# LOCAL STACK — script validation, not a deployment

Output of tools/deploy_check.py against the build session's local stack (real API, worker, migrations, PostgreSQL; web pages from the verification bundle; bundled airport seed only). Airports, budget and browser are FAILED there by design of the check: the full directory is not loaded and no budget was set.
