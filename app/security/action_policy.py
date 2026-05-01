from enum import StrEnum


class ActionClass(StrEnum):
    READ_ONLY = "read_only"
    DRAFT_ONLY = "draft_only"
    REQUIRES_APPROVAL = "requires_approval"
    ADMIN_ONLY = "admin_only"
    BLOCKED = "blocked"


ACTION_CLASSIFICATIONS: dict[str, ActionClass] = {
    "summarize_ticket": ActionClass.READ_ONLY,
    "lookup_site": ActionClass.READ_ONLY,
    "draft_vendor_email": ActionClass.DRAFT_ONLY,
    "generate_escalation_packet": ActionClass.DRAFT_ONLY,
    "send_vendor_email": ActionClass.REQUIRES_APPROVAL,
    "modify_ticket_record": ActionClass.REQUIRES_APPROVAL,
    "change_network_config": ActionClass.ADMIN_ONLY,
    "delete_records": ActionClass.ADMIN_ONLY,
    "export_sensitive_data": ActionClass.BLOCKED,
}


def classify_action(action_name: str) -> ActionClass:
    normalized = normalize_action_name(action_name)
    if not normalized:
        return ActionClass.BLOCKED
    return ACTION_CLASSIFICATIONS.get(normalized, ActionClass.BLOCKED)


def normalize_action_name(action_name: str) -> str:
    return action_name.strip().lower().replace("-", "_").replace(" ", "_")
