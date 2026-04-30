# Testing

Core checks:

```bash
ruff check .
mypy app
pytest
python -m app.evaluation.cli run --json
docker compose config --quiet
```

Focused hardening checks:

```bash
pytest tests/test_config.py tests/test_sandbox.py tests/test_policy_engine.py
pytest tests/test_redaction.py tests/test_evaluation.py
```
