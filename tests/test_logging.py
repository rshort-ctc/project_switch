import json
import logging

from app.core.config import Settings
from app.core.logging import configure_logging


def test_json_logging_includes_structured_extra(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(Settings(log_json=True))
    logging.getLogger("switch.test").info("event_name", extra={"run_id": "abc123"})

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["message"] == "event_name"
    assert payload["run_id"] == "abc123"
    assert payload["level"] == "INFO"
