from sqlalchemy.orm import Session

from app.db.repositories import PolicyDecisionRepository, ToolCallRepository
from app.models.entities import PolicyDecision, ToolCall
from app.models.enums import PolicyDecisionResult, ToolCallStatus
from app.security.redaction import redact_secrets
from app.services.audit import AuditService


class ToolCallService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tool_calls = ToolCallRepository(session)
        self.policy_decisions = PolicyDecisionRepository(session)
        self.audit = AuditService(session)

    def record_tool_call(
        self,
        *,
        agent_step_id: str,
        agent_run_id: str,
        tool_name: str,
        input_summary: str,
        output_summary: str | None,
        status: ToolCallStatus,
        duration_ms: int,
        approval_required: bool,
        error: str | None = None,
    ) -> ToolCall:
        tool_call = self.tool_calls.create(
            agent_step_id=agent_step_id,
            tool_name=tool_name,
            input_summary=redact_secrets(input_summary) or "",
            output_summary=redact_secrets(output_summary),
            status=status,
            duration_ms=duration_ms,
            approval_required=approval_required,
            error=redact_secrets(error),
        )
        self.audit.record(
            event_type="tool_call.recorded",
            summary=f"tool call recorded: {tool_name} status={status}",
            subject_type="tool_call",
            subject_id=tool_call.id,
            agent_run_id=agent_run_id,
        )
        return tool_call

    def record_policy_decision(
        self,
        *,
        decision: PolicyDecisionResult,
        policy_name: str,
        reason: str,
        enforced: bool,
        agent_run_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> PolicyDecision:
        policy_decision = self.policy_decisions.create(
            decision=decision,
            policy_name=policy_name,
            reason=redact_secrets(reason) or "",
            enforced=enforced,
            agent_run_id=agent_run_id,
            tool_call_id=tool_call_id,
        )
        self.audit.record(
            event_type="policy.decision",
            summary=f"policy decision: {policy_name}={decision}",
            subject_type="policy_decision",
            subject_id=policy_decision.id,
            agent_run_id=agent_run_id,
        )
        return policy_decision
