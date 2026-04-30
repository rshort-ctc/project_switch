from pathlib import Path

from alembic.config import Config

from alembic import command


def test_migrations_run_cleanly(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path}")

    command.upgrade(config, "head")

    assert db_path.exists()
