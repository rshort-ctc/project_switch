from dataclasses import dataclass
from typing import Protocol

from app.models.enums import ClaimType


@dataclass(frozen=True)
class ClaimProposal:
    normalized_text: str
    claim_type: ClaimType = ClaimType.PROJECT_STATE
    subject: str | None = None
    predicate: str | None = None
    object_value: str | None = None
    scope: str | None = None
    confidence: float = 0.5


class ClaimExtractor(Protocol):
    name: str
    version: str

    def propose(self, *, content: str, default_claim_type: ClaimType) -> list[ClaimProposal]:
        """Return proposed claims only; adjudication remains deterministic."""


class DeterministicClaimExtractor:
    name = "deterministic_line_extractor"
    version = "1"

    def propose(self, *, content: str, default_claim_type: ClaimType) -> list[ClaimProposal]:
        proposals: list[ClaimProposal] = []
        for raw_line in content.splitlines():
            line = raw_line.strip(" -\t")
            if not line:
                continue
            proposals.append(
                ClaimProposal(
                    normalized_text=line,
                    claim_type=_classify(line, default_claim_type),
                    confidence=0.5,
                )
            )
        if not proposals and content.strip():
            proposals.append(
                ClaimProposal(
                    normalized_text=content.strip(),
                    claim_type=default_claim_type,
                    confidence=0.5,
                )
            )
        return proposals


def _classify(text: str, default_claim_type: ClaimType) -> ClaimType:
    lowered = text.lower()
    if lowered.startswith(("todo:", "open loop:", "blocked:", "question:")):
        return ClaimType.OPEN_LOOP
    if lowered.startswith(("decision:", "decided:", "we will:", "we chose:")):
        return ClaimType.DECISION
    if lowered.startswith(("constraint:", "must:", "must not:", "policy:")):
        return ClaimType.CONSTRAINT
    if lowered.startswith(("risk:", "warning:")):
        return ClaimType.RISK
    return default_claim_type
