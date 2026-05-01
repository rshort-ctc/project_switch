from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.courthouse.extraction import ClaimExtractor, DeterministicClaimExtractor
from app.courthouse.policy import authority_at_least, exposure_allowed, privacy_allowed
from app.models.entities import (
    CanonicalState,
    Claim,
    ContextSnapshot,
    EvidenceItem,
    OpenLoop,
    VerdictRecord,
)
from app.models.enums import AuthorityLevel, ClaimStatus, ClaimType, Exposure, PrivacyClass, Verdict
from app.services.audit import AuditService

COMPILER_VERSION = "court-context-v1"
ACCEPTING_VERDICTS = {
    Verdict.ACCEPTED,
    Verdict.ACCEPTED_WITH_SCOPE,
    Verdict.ACCEPTED_UNTIL,
}


class MemoryGovernanceError(ValueError):
    pass


class CourthouseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def submit_evidence(
        self,
        *,
        content: str,
        source_type: str,
        drawer_id: str | None = None,
        source_uri: str | None = None,
        observed_at: datetime | None = None,
        adapter_name: str | None = None,
        adapter_version: str | None = None,
        transform_chain: dict[str, object] | None = None,
        privacy_class: PrivacyClass = PrivacyClass.INTERNAL,
        exposure: Exposure = Exposure.PRIVATE_INTERNAL,
        workspace: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> EvidenceItem:
        evidence = EvidenceItem(
            drawer_id=drawer_id,
            source_uri=source_uri,
            source_type=source_type,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            observed_at=observed_at,
            ingested_at=utc_now(),
            adapter_name=adapter_name,
            adapter_version=adapter_version,
            transform_chain=transform_chain,
            privacy_class=privacy_class,
            exposure=exposure,
            workspace=workspace,
            metadata_json=metadata or {},
            content_text=content,
        )
        self.session.add(evidence)
        self.session.flush()
        self._audit(
            "memory.evidence_submitted",
            f"evidence submitted source_type={source_type}",
            evidence.id,
        )
        return evidence

    def file_claim(
        self,
        *,
        normalized_text: str,
        claim_type: ClaimType,
        extracted_from_evidence_id: str | None,
        subject: str | None = None,
        predicate: str | None = None,
        object_value: str | None = None,
        scope: str | None = None,
        workspace: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        extractor: str | None = None,
        extractor_version: str | None = None,
        confidence: float = 0.5,
        status: ClaimStatus = ClaimStatus.CANDIDATE,
    ) -> Claim:
        claim = Claim(
            normalized_text=normalized_text.strip(),
            claim_type=claim_type,
            subject=subject,
            predicate=predicate,
            object=object_value,
            scope=scope,
            workspace=workspace,
            valid_from=valid_from,
            valid_to=valid_to,
            extracted_from_evidence_id=extracted_from_evidence_id,
            extractor=extractor,
            extractor_version=extractor_version,
            confidence=confidence,
            status=status,
        )
        self.session.add(claim)
        self.session.flush()
        self._audit(
            "memory.claim_filed", f"claim filed type={claim_type} status={status}", claim.id
        )
        return claim

    def extract_or_submit_claim(
        self,
        *,
        evidence_id: str,
        normalized_text: str | None = None,
        claim_type: ClaimType = ClaimType.PROJECT_STATE,
        **kwargs: Any,
    ) -> Claim:
        evidence = self.session.get(EvidenceItem, evidence_id)
        if evidence is None:
            raise MemoryGovernanceError(f"evidence not found: {evidence_id}")
        text = normalized_text or (evidence.content_text or "").strip()
        if not text:
            raise MemoryGovernanceError("claim text is required")
        return self.file_claim(
            normalized_text=text,
            claim_type=claim_type,
            extracted_from_evidence_id=evidence.id,
            workspace=kwargs.pop("workspace", evidence.workspace),
            **kwargs,
        )

    def propose_claims_from_evidence(
        self,
        *,
        evidence_id: str,
        default_claim_type: ClaimType = ClaimType.PROJECT_STATE,
        extractor: ClaimExtractor | None = None,
        max_claims: int = 10,
    ) -> list[Claim]:
        evidence = self.session.get(EvidenceItem, evidence_id)
        if evidence is None:
            raise MemoryGovernanceError(f"evidence not found: {evidence_id}")
        if not evidence.content_text:
            raise MemoryGovernanceError("evidence content is required for claim proposals")
        selected_extractor = extractor or DeterministicClaimExtractor()
        proposals = selected_extractor.propose(
            content=evidence.content_text,
            default_claim_type=default_claim_type,
        )[:max_claims]
        claims = [
            self.file_claim(
                normalized_text=proposal.normalized_text,
                claim_type=proposal.claim_type,
                extracted_from_evidence_id=evidence.id,
                subject=proposal.subject,
                predicate=proposal.predicate,
                object_value=proposal.object_value,
                scope=proposal.scope,
                workspace=evidence.workspace,
                extractor=selected_extractor.name,
                extractor_version=selected_extractor.version,
                confidence=proposal.confidence,
                status=ClaimStatus.CANDIDATE,
            )
            for proposal in proposals
        ]
        self._audit(
            "memory.claims_proposed",
            f"candidate claims proposed count={len(claims)} extractor={selected_extractor.name}",
            evidence.id,
        )
        return claims

    def adjudicate_claim(
        self,
        *,
        claim_id: str,
        verdict: Verdict = Verdict.ACCEPTED,
        authority_level: AuthorityLevel = AuthorityLevel.USER_STATEMENT,
        confidence: float = 1.0,
        decided_by: str = "system",
        reason: str | None = None,
        supersedes_claim_id: str | None = None,
        contradicts_claim_id: str | None = None,
        appeal_status: str = "none",
    ) -> VerdictRecord:
        claim = self._claim(claim_id)
        if authority_level == AuthorityLevel.RAW_EVIDENCE and verdict in ACCEPTING_VERDICTS:
            raise MemoryGovernanceError(
                "raw evidence cannot be promoted directly to accepted truth"
            )
        if (
            claim.claim_type == ClaimType.PREFERENCE
            and authority_level == AuthorityLevel.ACCEPTED_PREFERENCE
        ):
            pass
        elif (
            authority_level == AuthorityLevel.ACCEPTED_PREFERENCE
            and claim.claim_type == ClaimType.EXTERNAL_FACT
        ):
            raise MemoryGovernanceError(
                "accepted_preference is not authoritative for external facts"
            )

        auto_supersedes = self._newer_same_scope_claim(claim)
        supersedes_claim_id = supersedes_claim_id or (
            auto_supersedes.id if auto_supersedes else None
        )
        record = VerdictRecord(
            claim_id=claim.id,
            verdict=verdict,
            authority_level=authority_level,
            confidence=confidence,
            decided_by=decided_by,
            decided_at=utc_now(),
            reason=reason,
            supersedes_claim_id=supersedes_claim_id,
            contradicts_claim_id=contradicts_claim_id,
            appeal_status=appeal_status,
        )
        self.session.add(record)
        claim.status = _claim_status_for_verdict(verdict)
        if supersedes_claim_id:
            old = self.session.get(Claim, supersedes_claim_id)
            if old is not None:
                old.status = ClaimStatus.SUPERSEDED
        if contradicts_claim_id:
            other = self.session.get(Claim, contradicts_claim_id)
            if other is not None:
                other.status = ClaimStatus.CONTRADICTED
        self.session.flush()
        self._audit("memory.verdict_recorded", f"verdict recorded verdict={verdict}", record.id)
        return record

    def explain_verdict(self, verdict_id: str) -> dict[str, object]:
        record = self.session.get(VerdictRecord, verdict_id)
        if record is None:
            raise MemoryGovernanceError(f"verdict not found: {verdict_id}")
        claim = self._claim(record.claim_id)
        return {
            "verdict_id": record.id,
            "claim_id": claim.id,
            "claim": claim.normalized_text,
            "verdict": record.verdict,
            "authority_level": record.authority_level,
            "confidence": record.confidence,
            "reason": record.reason,
            "supersedes_claim_id": record.supersedes_claim_id,
            "contradicts_claim_id": record.contradicts_claim_id,
        }

    def set_canonical_state(
        self,
        *,
        key: str,
        value: dict[str, object],
        source_verdict_id: str,
        workspace: str | None = None,
        status: str = "active",
    ) -> CanonicalState:
        verdict = self.session.get(VerdictRecord, source_verdict_id)
        if verdict is None:
            raise MemoryGovernanceError(f"verdict not found: {source_verdict_id}")
        if verdict.verdict not in ACCEPTING_VERDICTS:
            raise MemoryGovernanceError("canonical state requires an accepted verdict")
        if not authority_at_least(verdict.authority_level, AuthorityLevel.AGENT_OBSERVATION):
            raise MemoryGovernanceError("canonical state requires authority above raw evidence")
        state = self._state_for_key(key, workspace) or CanonicalState(
            key=key,
            workspace=workspace,
            value_json={},
            authority_level=verdict.authority_level,
            source_verdict_id=source_verdict_id,
            status=status,
        )
        state.value_json = value
        state.authority_level = verdict.authority_level
        state.source_verdict_id = source_verdict_id
        state.status = status
        self.session.add(state)
        self.session.flush()
        self._audit("memory.canonical_state_set", f"canonical state set key={key}", state.id)
        return state

    def get_canonical_state(
        self, *, workspace: str | None = None, key: str | None = None
    ) -> list[CanonicalState]:
        statement: Select[tuple[CanonicalState]] = select(CanonicalState).where(
            CanonicalState.status == "active"
        )
        statement = _scope(statement, CanonicalState.workspace, workspace)
        if key is not None:
            statement = statement.where(CanonicalState.key == key)
        return list(self.session.execute(statement.order_by(CanonicalState.key)).scalars())

    def open_loop(
        self,
        *,
        title: str,
        workspace: str | None = None,
        priority: int = 0,
        blocking_question: str | None = None,
        next_action: str | None = None,
        source_evidence_id: str | None = None,
        source_verdict_id: str | None = None,
        stale_after: datetime | None = None,
    ) -> OpenLoop:
        loop = OpenLoop(
            title=title,
            workspace=workspace,
            priority=priority,
            blocking_question=blocking_question,
            next_action=next_action,
            source_evidence_id=source_evidence_id,
            source_verdict_id=source_verdict_id,
            stale_after=stale_after,
        )
        self.session.add(loop)
        self.session.flush()
        self._audit("memory.open_loop_added", f"open loop added title={title}", loop.id)
        return loop

    def update_loop(self, loop_id: str, **updates: object) -> OpenLoop:
        loop = self._loop(loop_id)
        for key in (
            "title",
            "status",
            "priority",
            "blocking_question",
            "next_action",
            "stale_after",
        ):
            if key in updates:
                setattr(loop, key, updates[key])
        self.session.flush()
        self._audit("memory.open_loop_updated", f"open loop updated id={loop.id}", loop.id)
        return loop

    def resolve_loop(self, loop_id: str) -> OpenLoop:
        return self.update_loop(loop_id, status="resolved")

    def compile_context(
        self,
        *,
        task: str,
        workspace: str | None = None,
        mode: str | None = "normal",
        token_budget: int | None = 4000,
        exposure_ceiling: Exposure = Exposure.TOOL_SAFE,
        include_raw_evidence: bool = True,
        persist_snapshot: bool = True,
    ) -> dict[str, object]:
        excluded: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        canonical = [_state_payload(row) for row in self.get_canonical_state(workspace=workspace)]
        claims = self._claims_for_context(workspace)
        facts: list[dict[str, object]] = []
        for claim in claims:
            evidence = (
                self.session.get(EvidenceItem, claim.extracted_from_evidence_id)
                if claim.extracted_from_evidence_id
                else None
            )
            if claim.status == ClaimStatus.SUPERSEDED and mode != "historical":
                excluded.append({"type": "claim", "id": claim.id, "reason": "superseded"})
                continue
            if claim.status == ClaimStatus.CONTRADICTED:
                warnings.append(
                    {"type": "contradiction", "claim_id": claim.id, "claim": claim.normalized_text}
                )
                continue
            if evidence and not self._allowed(evidence, exposure_ceiling, claim.claim_type):
                excluded.append(
                    {"type": "claim", "id": claim.id, "reason": "privacy_or_exposure_gate"}
                )
                continue
            facts.append(_claim_payload(claim))
        loops = [
            _loop_payload(loop)
            for loop in self.session.execute(
                _scope(select(OpenLoop), OpenLoop.workspace, workspace)
                .where(OpenLoop.status != "resolved")
                .order_by(OpenLoop.priority.desc(), OpenLoop.created_at)
            ).scalars()
        ]
        raw_evidence: list[dict[str, object]] = []
        if include_raw_evidence:
            for evidence in self._evidence_for_context(workspace):
                if self._allowed(evidence, exposure_ceiling, None):
                    raw_evidence.append(_evidence_payload(evidence))
                else:
                    excluded.append(
                        {
                            "type": "evidence",
                            "id": evidence.id,
                            "reason": "privacy_or_exposure_gate",
                        }
                    )
        packet: dict[str, object] = {
            "task_interpretation": {"task": task, "workspace": workspace, "mode": mode},
            "canonical_state": canonical,
            "active_constraints": [f for f in facts if f["claim_type"] == ClaimType.CONSTRAINT],
            "relevant_decisions": [f for f in facts if f["claim_type"] == ClaimType.DECISION],
            "facts": facts,
            "open_loops": loops,
            "recent_changes": [],
            "selected_raw_evidence": raw_evidence,
            "contradictions_warnings": warnings,
            "excluded_memories": excluded,
            "source_references": _source_references(facts, raw_evidence),
            "next_actions": [loop["next_action"] for loop in loops if loop.get("next_action")],
        }
        self._fit_budget(packet, excluded, token_budget)
        if persist_snapshot:
            snapshot = self.record_snapshot(
                task=task,
                workspace=workspace,
                mode=mode,
                token_budget=token_budget,
                packet=packet,
            )
            packet["snapshot_id"] = snapshot.id
            packet["snapshot_hash"] = snapshot.snapshot_hash
        return packet

    def record_snapshot(
        self,
        *,
        task: str,
        packet: dict[str, object],
        workspace: str | None = None,
        mode: str | None = "normal",
        token_budget: int | None = None,
    ) -> ContextSnapshot:
        included = {
            k: v
            for k, v in packet.items()
            if k not in {"excluded_memories", "contradictions_warnings"}
        }
        excluded = cast(list[dict[str, object]], packet.get("excluded_memories", []))
        warnings = cast(list[dict[str, object]], packet.get("contradictions_warnings", []))
        payload = {
            "task": task,
            "workspace": workspace,
            "mode": mode,
            "compiler_version": COMPILER_VERSION,
            "token_budget": token_budget,
            "included": included,
            "excluded": excluded,
            "warnings": warnings,
        }
        snapshot = ContextSnapshot(
            task=task,
            workspace=workspace,
            mode=mode,
            compiler_version=COMPILER_VERSION,
            token_budget=token_budget,
            included_json=included,
            excluded_json=excluded,
            warnings_json=warnings,
            snapshot_hash=_stable_hash(payload),
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def context_diff(self, left_snapshot_id: str, right_snapshot_id: str) -> dict[str, object]:
        left = self._snapshot(left_snapshot_id)
        right = self._snapshot(right_snapshot_id)
        return {
            "left": left.id,
            "right": right.id,
            "same_hash": left.snapshot_hash == right.snapshot_hash,
            "left_hash": left.snapshot_hash,
            "right_hash": right.snapshot_hash,
            "included_changed": left.included_json != right.included_json,
            "excluded_changed": left.excluded_json != right.excluded_json,
            "warnings_changed": left.warnings_json != right.warnings_json,
        }

    def memory_health(self, *, workspace: str | None = None) -> dict[str, object]:
        claims = self._claims_for_context(workspace, include_all=True)
        evidence_ids = {row.id for row in self._evidence_for_context(workspace, include_all=True)}
        claimed_evidence_ids = {
            claim.extracted_from_evidence_id for claim in claims if claim.extracted_from_evidence_id
        }
        state_rows = self.get_canonical_state(workspace=workspace)
        verdict_ids = {row.id for row in self.session.execute(select(VerdictRecord)).scalars()}
        now = utc_now()
        report: dict[str, object] = {
            "active_contradictions": [
                claim.id for claim in claims if claim.status == ClaimStatus.CONTRADICTED
            ],
            "stale_open_loops": [
                loop.id
                for loop in self.session.execute(
                    _scope(select(OpenLoop), OpenLoop.workspace, workspace)
                ).scalars()
                if loop.status != "resolved"
                and loop.stale_after is not None
                and _as_aware(loop.stale_after) < now
            ],
            "accepted_claims_without_evidence": [
                claim.id
                for claim in claims
                if claim.status == ClaimStatus.ACCEPTED and not claim.extracted_from_evidence_id
            ],
            "canonical_state_missing_verdict": [
                state.id for state in state_rows if state.source_verdict_id not in verdict_ids
            ],
            "blocked_from_tool_safe_export": [
                evidence.id
                for evidence in self._evidence_for_context(workspace, include_all=True)
                if not self._allowed(evidence, Exposure.TOOL_SAFE, None)
            ],
            "superseded_claims": [
                claim.id for claim in claims if claim.status == ClaimStatus.SUPERSEDED
            ],
            "orphaned_evidence": sorted(evidence_ids - claimed_evidence_ids),
        }
        report["ok"] = not any(value for value in report.values())
        return report

    def _claim(self, claim_id: str) -> Claim:
        claim = self.session.get(Claim, claim_id)
        if claim is None:
            raise MemoryGovernanceError(f"claim not found: {claim_id}")
        return claim

    def _loop(self, loop_id: str) -> OpenLoop:
        loop = self.session.get(OpenLoop, loop_id)
        if loop is None:
            raise MemoryGovernanceError(f"open loop not found: {loop_id}")
        return loop

    def _snapshot(self, snapshot_id: str) -> ContextSnapshot:
        snapshot = self.session.get(ContextSnapshot, snapshot_id)
        if snapshot is None:
            raise MemoryGovernanceError(f"snapshot not found: {snapshot_id}")
        return snapshot

    def _state_for_key(self, key: str, workspace: str | None) -> CanonicalState | None:
        return (
            self.session.execute(
                _scope(select(CanonicalState), CanonicalState.workspace, workspace).where(
                    CanonicalState.key == key
                )
            )
            .scalars()
            .first()
        )

    def _newer_same_scope_claim(self, claim: Claim) -> Claim | None:
        if not claim.subject:
            return None
        return (
            self.session.execute(
                _scope(select(Claim), Claim.workspace, claim.workspace)
                .where(
                    Claim.id != claim.id,
                    Claim.subject == claim.subject,
                    Claim.predicate == claim.predicate,
                    Claim.scope == claim.scope,
                    Claim.status == ClaimStatus.ACCEPTED,
                )
                .order_by(Claim.created_at.desc(), Claim.id.desc())
            )
            .scalars()
            .first()
        )

    def _claims_for_context(self, workspace: str | None, include_all: bool = False) -> list[Claim]:
        statement = _scope(select(Claim), Claim.workspace, workspace)
        if not include_all:
            statement = statement.where(
                Claim.status.in_(
                    [ClaimStatus.ACCEPTED, ClaimStatus.SUPERSEDED, ClaimStatus.CONTRADICTED]
                )
            )
        return list(
            self.session.execute(
                statement.order_by(Claim.created_at.desc(), Claim.id.desc())
            ).scalars()
        )

    def _evidence_for_context(
        self, workspace: str | None, include_all: bool = False
    ) -> list[EvidenceItem]:
        statement = _scope(select(EvidenceItem), EvidenceItem.workspace, workspace)
        if not include_all:
            statement = statement.order_by(EvidenceItem.created_at.desc()).limit(20)
        return list(self.session.execute(statement).scalars())

    def _allowed(
        self, evidence: EvidenceItem, exposure_ceiling: Exposure, claim_type: ClaimType | None
    ) -> bool:
        return exposure_allowed(evidence.exposure, exposure_ceiling) and privacy_allowed(
            evidence.privacy_class, exposure_ceiling, claim_type
        )

    def _fit_budget(
        self, packet: dict[str, object], excluded: list[dict[str, object]], token_budget: int | None
    ) -> None:
        if token_budget is None:
            return
        while _estimate_tokens(packet) > token_budget and packet["selected_raw_evidence"]:
            raw = packet["selected_raw_evidence"]
            if not isinstance(raw, list):
                break
            removed = raw.pop()
            excluded.append({"type": "evidence", "id": removed.get("id"), "reason": "token_budget"})

    def _audit(self, event_type: str, summary: str, subject_id: str) -> None:
        self.audit.record(
            event_type=event_type,
            summary=summary,
            subject_type="memory",
            subject_id=subject_id,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _scope(statement: Select[Any], column: Any, workspace: str | None) -> Select[Any]:
    if workspace is None:
        return statement.where(column.is_(None))
    return statement.where(or_(column == workspace, column.is_(None)))


def _claim_status_for_verdict(verdict: Verdict) -> ClaimStatus:
    if verdict in ACCEPTING_VERDICTS:
        return ClaimStatus.ACCEPTED
    if verdict == Verdict.REJECTED:
        return ClaimStatus.REJECTED
    if verdict == Verdict.SUPERSEDED:
        return ClaimStatus.SUPERSEDED
    if verdict == Verdict.CONTRADICTED:
        return ClaimStatus.CONTRADICTED
    if verdict == Verdict.EXPIRED:
        return ClaimStatus.EXPIRED
    return ClaimStatus.NEEDS_REVIEW


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _estimate_tokens(payload: object) -> int:
    return max(1, len(json.dumps(payload, default=str)) // 4)


def _evidence_payload(evidence: EvidenceItem) -> dict[str, object]:
    return {
        "id": evidence.id,
        "source_type": evidence.source_type,
        "source_uri": evidence.source_uri,
        "content_hash": evidence.content_hash,
        "content": evidence.content_text,
        "privacy_class": evidence.privacy_class,
        "exposure": evidence.exposure,
    }


def _claim_payload(claim: Claim) -> dict[str, object]:
    return {
        "id": claim.id,
        "claim": claim.normalized_text,
        "claim_type": claim.claim_type,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "scope": claim.scope,
        "workspace": claim.workspace,
        "status": claim.status,
    }


def _state_payload(state: CanonicalState) -> dict[str, object]:
    return {
        "id": state.id,
        "key": state.key,
        "value": state.value_json,
        "workspace": state.workspace,
        "authority_level": state.authority_level,
        "source_verdict_id": state.source_verdict_id,
    }


def _loop_payload(loop: OpenLoop) -> dict[str, object]:
    return {
        "id": loop.id,
        "title": loop.title,
        "workspace": loop.workspace,
        "status": loop.status,
        "priority": loop.priority,
        "blocking_question": loop.blocking_question,
        "next_action": loop.next_action,
    }


def _source_references(
    facts: list[dict[str, object]], raw_evidence: list[dict[str, object]]
) -> list[dict[str, object]]:
    refs = [{"type": "claim", "id": fact["id"]} for fact in facts]
    refs.extend({"type": "evidence", "id": evidence["id"]} for evidence in raw_evidence)
    return refs
