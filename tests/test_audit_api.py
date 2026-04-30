from sqlalchemy.orm import Session

from app.api.routes.audit import audit_log
from app.services.runs import RunService

EXPECTED_AUDIT_EVENTS = 2


def test_audit_log_returns_recent_events(session: Session) -> None:
    service = RunService(session)
    user = service.create_user(email="audit@example.test", display_name="Audit User")
    service.register_repository(name="demo", local_path="/tmp/demo", default_branch="main")
    session.commit()

    response = audit_log(session, limit=10)

    assert len(response.events) == EXPECTED_AUDIT_EVENTS
    assert response.events[0].event_type == "repository.created"
    assert response.events[1].actor_user_id == user.id
