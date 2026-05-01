.PHONY: install format lint typecheck test eval migrate run start start-web start-desktop stop restart status logs deploy-config backup restore dashboard-install dashboard-lint dashboard-typecheck dashboard-build dashboard-dev dashboard-desktop-check dashboard-desktop-dev dashboard-desktop-build extension-install extension-check extension-test

install:
	python3.12 -m venv .venv
	. .venv/bin/activate && pip install -e ".[dev]"
	chmod +x scripts/install scripts/format scripts/lint scripts/typecheck scripts/test scripts/eval scripts/migrate scripts/run scripts/switch scripts/backup scripts/restore

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

start:
	scripts/switch start

start-web:
	scripts/switch start --web

start-desktop:
	scripts/switch start --desktop

stop:
	scripts/switch stop

restart:
	scripts/switch restart

status:
	scripts/switch status

logs:
	scripts/switch logs

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

dashboard-desktop-check:
	cd dashboard && npm run desktop:check

dashboard-desktop-dev:
	cd dashboard && npm run desktop:dev

dashboard-desktop-build:
	cd dashboard && npm run desktop:build

extension-install:
	cd extensions/vscode-switch && npm install

extension-check:
	cd extensions/vscode-switch && npm run check

extension-test:
	cd extensions/vscode-switch && npm test
