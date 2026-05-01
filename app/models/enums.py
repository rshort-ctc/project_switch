from enum import StrEnum


class TaskStatus(StrEnum):
    OPEN = "open"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolCallStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PatchStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RepoIndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class PolicyDecisionResult(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class AuditStatus(StrEnum):
    PROPOSED = "proposed"
    DRAFTED = "drafted"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    BLOCKED = "blocked"


class PrivacyClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PII_POTENTIAL = "pii_potential"
    SENSITIVE = "sensitive"
    SECRETS_POSSIBLE = "secrets_possible"


class Exposure(StrEnum):
    PRIVATE_INTERNAL = "private_internal"
    USER_VISIBLE = "user_visible"
    TOOL_SAFE = "tool_safe"
    REPO_SAFE = "repo_safe"
    PUBLIC_SAFE = "public_safe"
    NEVER_EXPORT = "never_export"


class ClaimType(StrEnum):
    DECISION = "decision"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    OPEN_LOOP = "open_loop"
    PROJECT_STATE = "project_state"
    RELATIONSHIP = "relationship"
    PROCEDURE = "procedure"
    ARTIFACT = "artifact"
    RISK = "risk"
    PRIVATE_FACT = "private_fact"
    EXTERNAL_FACT = "external_fact"


class ClaimStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    EXPIRED = "expired"


class Verdict(StrEnum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_SCOPE = "accepted_with_scope"
    ACCEPTED_UNTIL = "accepted_until"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    AMBIGUOUS = "ambiguous"
    PRIVATE_VAULT_ONLY = "private_vault_only"
    TOOL_BLOCKED = "tool_blocked"
    EXPIRED = "expired"


class AuthorityLevel(StrEnum):
    RAW_EVIDENCE = "raw_evidence"
    EXTRACTED_CANDIDATE = "extracted_candidate"
    AGENT_OBSERVATION = "agent_observation"
    USER_STATEMENT = "user_statement"
    ACCEPTED_PREFERENCE = "accepted_preference"
    PROJECT_NOTE = "project_note"
    DECISION_RECORD = "decision_record"
    REPO_SOURCE = "repo_source"
    POLICY_CONSTRAINT = "policy_constraint"
    CANONICAL_STATE = "canonical_state"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"
    VAULTED = "vaulted"
