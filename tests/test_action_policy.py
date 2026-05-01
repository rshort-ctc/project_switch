import pytest

from app.security.action_policy import ActionClass, classify_action, normalize_action_name


@pytest.mark.parametrize(
    ("action_name", "expected"),
    [
        ("summarize_ticket", ActionClass.READ_ONLY),
        ("lookup_site", ActionClass.READ_ONLY),
        ("draft_vendor_email", ActionClass.DRAFT_ONLY),
        ("generate_escalation_packet", ActionClass.DRAFT_ONLY),
        ("send_vendor_email", ActionClass.REQUIRES_APPROVAL),
        ("modify_ticket_record", ActionClass.REQUIRES_APPROVAL),
        ("change_network_config", ActionClass.ADMIN_ONLY),
        ("delete_records", ActionClass.ADMIN_ONLY),
        ("export_sensitive_data", ActionClass.BLOCKED),
    ],
)
def test_action_policy_classifies_known_actions(
    action_name: str, expected: ActionClass
) -> None:
    assert classify_action(action_name) is expected


def test_action_policy_normalizes_action_names() -> None:
    assert classify_action(" Draft Vendor Email ") is ActionClass.DRAFT_ONLY
    assert classify_action("generate-escalation-packet") is ActionClass.DRAFT_ONLY
    assert normalize_action_name("Modify Ticket Record") == "modify_ticket_record"


@pytest.mark.parametrize("action_name", ["", "  ", "unknown_action", "send_customer_sms"])
def test_action_policy_blocks_unknown_or_empty_actions(action_name: str) -> None:
    assert classify_action(action_name) is ActionClass.BLOCKED
