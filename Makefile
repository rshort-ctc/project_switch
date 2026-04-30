.PHONY: install format lint typecheck test eval migrate run deploy-config backup restore dashboard-install dashboard-lint dashboard-typecheck dashboard-build dashboard-dev extension-install extension-check extension-test

install:
	python3.12 -m venv .venv
	. .venv/bin/activate && pip install -e ".[dev]"
	chmod +x scripts/install scripts/format scripts/lint scripts/typecheck scripts/test scripts/eval scripts/migrate scripts/run scripts/backup scripts/restore

format:
	ruff format .
	ruff check . --fix

lint:
	ruff check .

typecheck:
	mypy app

test:
	pytest

eval:
	.venv/bin/python -m app.evaluation.cli run

migrate:
	alembic upgrade head

run:
	uvicorn app.main:create_app --factory --reload

deploy-config:
	docker compose config --quiet

backup:
	scripts/backup

restore:
	scripts/restore $(BACKUP_DIR)

dashboard-install:
	cd dashboard && npm install

dashboard-lint:
	cd dashboard && npm run lint

dashboard-typecheck:
	cd dashboard && npm run typecheck

dashboard-build:
	cd dashboard && npm run build

dashboard-dev:
	cd dashboard && npm run dev

extension-install:
	cd extensions/vscode-switch && npm install

extension-check:
	cd extensions/vscode-switch && npm run check

extension-test:
	cd extensions/vscode-switch && npm test
