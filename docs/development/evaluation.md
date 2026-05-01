# Evaluation Harness

SWITCH includes a fully local synthetic evaluation harness for measuring whether the
platform is useful and safe before connecting it to larger task suites.

Run it with:

```bash
python -m app.evaluation.cli run
```

or:

```bash
make eval
scripts/eval --json
switch-eval run --json
```

The default `synthetic` suite creates temporary local repositories and does not call cloud
services or hosted model APIs. It uses deterministic local retrieval, typed tool schemas,
policy checks, patch metadata, approval gates, and sandbox-shaped validation execution.

Covered scenarios:
- simple bug fix
- failing test repair
- refactor request
- docs update
- unsafe secret request
- malicious prompt-injection file
- risky dependency change
- ambiguous task requiring clarification or stop

Reported metrics:
- relevant files found
- patch applied cleanly
- tests passed
- unsafe action denied
- hallucinated claims count
- approval gates triggered correctly

Reports are written to `evals/reports/latest.json` and `evals/reports/latest.md`.
The report directory is ignored by git because eval outputs are local generated artifacts.
