from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.courthouse import CourthouseService, MemoryGovernanceError
from app.courthouse.service import utc_now
from app.models.entities import CanonicalState, ContextSnapshot, EvidenceItem, VerdictRecord
from app.models.enums import AuthorityLevel, ClaimStatus, ClaimType, Exposure, PrivacyClass, Verdict

SHA256_HEX_LENGTH = 64
SNAPSHOT_COUNT = 2


def test_court_database_initializes(session: Session) -> None:
    tables = session.execute(select(EvidenceItem)).scalars().all()
    assert tables == []


def test_evidence_can_be_submitted_and_hashed(session: Session) -> None:
    evidence = CourthouseService(session).submit_evidence(
        content="Decision: use local-only memory.",
        source_type="chat",
        workspace="switch",
    )
    session.commit()

    persisted = session.get(EvidenceItem, evidence.id)
    assert persisted is not None
    assert len(persisted.content_hash) == SHA256_HEX_LENGTH
    assert persisted.content_text == "Decision: use local-only memory."


def test_claims_start_as_candidate(session: Session) -> None:
    service = CourthouseService(session)
    evidence = service.submit_evidence(
        content="Use host dashboard for metrics.", source_type="chat"
    )
    claim = service.extract_or_submit_claim(
        evidence_id=evidence.id,
        claim_type=ClaimType.DECISION,
        subject="dashboard",
        predicate="used_for",
        object_value="metrics",
    )

    assert claim.status == ClaimStatus.CANDIDATE


def test_proposed_claims_are_candidates_without_verdicts(session: Session) -> None:
    service = CourthouseService(session)
    evidence = service.submit_evidence(
        content="Decision: keep approval gates.\nRisk: raw retrieval is not truth.",
        source_type="chat",
        workspace="switch",
    )

    claims = service.propose_claims_from_evidence(evidence_id=evidence.id)

    assert [claim.status for claim in claims] == [ClaimStatus.CANDIDATE, ClaimStatus.CANDIDATE]
    assert {claim.claim_type for claim in claims} == {ClaimType.DECISION, ClaimType.RISK}
    assert session.execute(select(VerdictRecord)).scalars().all() == []


def test_verdict_can_accept_claim(session: Session) -> None:
    service = CourthouseService(session)
    evidence = service.submit_evidence(content="Use separate ports.", source_type="chat")
    claim = service.extract_or_submit_claim(evidence_id=evidence.id, claim_type=ClaimType.DECISION)
    verdict = service.adjudicate_claim(
        claim_id=claim.id,
        verdict=Verdict.ACCEPTED,
        authority_level=AuthorityLevel.DECISION_RECORD,
    )

    assert verdict.verdict == Verdict.ACCEPTED
    assert claim.status == ClaimStatus.ACCEPTED


def test_canonical_state_requires_accepted_verdict(session: Session) -> None:
    service = CourthouseService(session)
    evidence = service.submit_evidence(content="Candidate only.", source_type="chat")
    claim = service.extract_or_submit_claim(
        evidence_id=evidence.id, claim_type=ClaimType.PROJECT_STATE
    )

    with pytest.raises(MemoryGovernanceError):
        service.set_canonical_state(key="x", value={"value": True}, source_verdict_id=claim.id)

    with pytest.raises(MemoryGovernanceError):
        service.adjudicate_claim(claim_id=claim.id, authority_level=AuthorityLevel.RAW_EVIDENCE)


def test_canonical_state_can_be_set_from_accepted_valid_verdict(session: Session) -> None:
    service = CourthouseService(session)
    evidence = service.submit_evidence(content="Host dashboard owns metrics.", source_type="chat")
    claim = service.extract_or_submit_claim(evidence_id=evidence.id, claim_type=ClaimType.DECISION)
    verdict = service.adjudicate_claim(
        claim_id=claim.id,
        authority_level=AuthorityLevel.DECISION_RECORD,
    )

    state = service.set_canonical_state(
        key="dashboard.metrics_surface",
        value={"surface": "host"},
        source_verdict_id=verdict.id,
        workspace="switch",
    )

    assert session.get(CanonicalState, state.id) is not None
    assert service.get_canonical_state(workspace="switch", key="dashboard.metrics_surface")[
        0
    ].value_json == {"surface": "host"}


def test_newer_same_scope_correction_supersedes_older_claim(session: Session) -> None:
    service = CourthouseService(session)
    old_evidence = service.submit_evidence(
        content="Web handles metrics.", source_type="chat", workspace="switch"
    )
    old_claim = service.extract_or_submit_claim(
        evidence_id=old_evidence.id,
        claim_type=ClaimType.DECISION,
        subject="metrics",
        predicate="surface",
        object_value="web",
        workspace="switch",
    )
    service.adjudicate_claim(claim_id=old_claim.id, authority_level=AuthorityLevel.DECISION_RECORD)

    new_evidence = service.submit_evidence(
        content="Correction: host handles metrics.", source_type="chat", workspace="switch"
    )
    new_claim = service.extract_or_submit_claim(
        evidence_id=new_evidence.id,
        claim_type=ClaimType.DECISION,
        subject="metrics",
        predicate="surface",
        object_value="host",
        workspace="switch",
    )
    verdict = service.adjudicate_claim(
        claim_id=new_claim.id, authority_level=AuthorityLevel.DECISION_RECORD
    )

    assert verdict.supersedes_claim_id == old_claim.id
    assert old_claim.status == ClaimStatus.SUPERSEDED


def test_private_and_secrets_evidence_blocked_from_tool_safe_context(session: Session) -> None:
    service = CourthouseService(session)
    secret = service.submit_evidence(
        content="token=super-secret",
        source_type="note",
        privacy_class=PrivacyClass.SECRETS_POSSIBLE,
        exposure=Exposure.PRIVATE_INTERNAL,
    )
    claim = service.extract_or_submit_claim(
        evidence_id=secret.id,
        claim_type=ClaimType.PRIVATE_FACT,
        normalized_text="token is super-secret",
    )
    service.adjudicate_claim(claim_id=claim.id, authority_level=AuthorityLevel.USER_STATEMENT)

    packet = service.compile_context(task="debug", exposure_ceiling=Exposure.TOOL_SAFE)

    assert packet["selected_raw_evidence"] == []
    assert any(item["id"] == secret.id for item in packet["excluded_memories"])


def test_superseded_claims_excluded_from_normal_context(session: Session) -> None:
    service = CourthouseService(session)
    old = service.file_claim(
        normalized_text="old decision",
        claim_type=ClaimType.DECISION,
        extracted_from_evidence_id=None,
        status=ClaimStatus.SUPERSEDED,
    )
    packet = service.compile_context(task="restore", include_raw_evidence=False)
    assert all(fact["id"] != old.id for fact in packet["facts"])


def test_contradicted_claims_are_warnings_not_facts(session: Session) -> None:
    service = CourthouseService(session)
    claim = service.file_claim(
        normalized_text="contradicted fact",
        claim_type=ClaimType.PROJECT_STATE,
        extracted_from_evidence_id=None,
        status=ClaimStatus.CONTRADICTED,
    )
    packet = service.compile_context(task="restore", include_raw_evidence=False)

    assert all(fact["id"] != claim.id for fact in packet["facts"])
    assert any(warning["claim_id"] == claim.id for warning in packet["contradictions_warnings"])


def test_open_loops_are_included_in_context_packets(session: Session) -> None:
    service = CourthouseService(session)
    loop = service.open_loop(title="Wire memory into chat", next_action="Add compiler call")

    packet = service.compile_context(task="continue work", include_raw_evidence=False)

    assert packet["open_loops"][0]["id"] == loop.id


def test_restore_snapshots_are_append_only_and_hash_deterministically(session: Session) -> None:
    service = CourthouseService(session)
    packet = service.compile_context(
        task="restore", include_raw_evidence=False, persist_snapshot=False
    )
    first = service.record_snapshot(task="restore", packet=packet)
    second = service.record_snapshot(task="restore", packet=packet)
    session.commit()

    assert first.id != second.id
    assert first.snapshot_hash == second.snapshot_hash
    assert len(session.execute(select(ContextSnapshot)).scalars().all()) == SNAPSHOT_COUNT


def test_memory_health_reports_obvious_broken_state(session: Session) -> None:
    service = CourthouseService(session)
    evidence = service.submit_evidence(content="orphan", source_type="note")
    claim = service.file_claim(
        normalized_text="accepted without evidence",
        claim_type=ClaimType.PROJECT_STATE,
        extracted_from_evidence_id=None,
        status=ClaimStatus.ACCEPTED,
    )
    service.open_loop(title="stale", stale_after=utc_now() - timedelta(days=1))
    session.add(
        CanonicalState(
            key="broken",
            value_json={"x": True},
            authority_level=AuthorityLevel.CANONICAL_STATE,
            source_verdict_id="missing",
            status="active",
        )
    )
    session.flush()

    report = service.memory_health()

    assert evidence.id in report["orphaned_evidence"]
    assert claim.id in report["accepted_claims_without_evidence"]
    assert report["stale_open_loops"]
    assert report["canonical_state_missing_verdict"]
    assert report["ok"] is False
