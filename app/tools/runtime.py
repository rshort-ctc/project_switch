import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.enums import ToolCallStatus
from app.security import PolicyEngine, PolicyViolation
from app.services.audit import AuditService
from app.services.tools import ToolCallService
from app.tools.schemas import ToolContext, ToolError

MAX_OUTPUT_SUMMARY_CHARS = 1000
MAX_AGENT_TEXT_CHARS = 12000

OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass
class ToolRuntime:
    session: Session
    policy: PolicyEngine
    context: ToolContext

    def run(
        self,
        *,
        tool_name: str,
        input_model: BaseModel,
        output_factory: Callable[[ToolError], OutputT],
        action: Callable[[], OutputT],
        approval_required: bool = False,
    ) -> OutputT:
        started = time.monotonic()
        try:
            output = action()
            status = (
                ToolCallStatus.SUCCEEDED
                if bool(output.model_dump().get("success"))
                else ToolCallStatus.FAILED
            )
            error = output.model_dump().get("error")
            error_text = str(error) if error else None
        except PolicyViolation as exc:
            output = output_factory(ToolError(code="policy_denied", message=str(exc)))
            status = ToolCallStatus.DENIED
            error_text = str(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope for tool boundary
            output = output_factory(ToolError(code="tool_error", message=str(exc)))
            status = ToolCallStatus.FAILED
            error_text = str(exc)

        duration_ms = int((time.monotonic() - started) * 1000)
        ToolCallService(self.session).record_tool_call(
            agent_step_id=self.context.agent_step_id,
            agent_run_id=self.context.agent_run_id,
            tool_name=tool_name,
            input_summary=_compact(str(input_model.model_dump(mode="json"))),
            output_summary=_compact(str(output.model_dump(mode="json"))),
            status=status,
            duration_ms=duration_ms,
            approval_required=approval_required,
            error=error_text,
        )
        AuditService(self.session).record(
            event_type="tool.executed",
            summary=f"tool executed: {tool_name} status={status}",
            subject_type="tool",
            subject_id=tool_name,
            actor_user_id=self.context.actor_user_id,
            agent_run_id=self.context.agent_run_id,
        )
        return output

    def artifact_path(self, name: str) -> Path:
        root = self.context.workspace_path / ".switch" / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        return root / name


def compact_text(text: str, *, max_chars: int = MAX_AGENT_TEXT_CHARS) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _compact(value: str) -> str:
    if len(value) <= MAX_OUTPUT_SUMMARY_CHARS:
        return value
    return value[:MAX_OUTPUT_SUMMARY_CHARS] + "...[truncated]"
