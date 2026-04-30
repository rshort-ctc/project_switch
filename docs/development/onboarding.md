# Developer Onboarding

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
npm install --prefix dashboard
```

Before handing off changes:

```bash
ruff format . --check
ruff check .
mypy app
pytest
python -m app.evaluation.cli run
cd dashboard && npm run lint && npm run typecheck && npm run build
```

Keep all new features local-only, audited, typed, and covered by focused tests.
