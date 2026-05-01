from app.models.enums import AuthorityLevel, ClaimType, Exposure, PrivacyClass

EXPOSURE_RANK: dict[str, int] = {
    Exposure.PRIVATE_INTERNAL: 0,
    Exposure.USER_VISIBLE: 1,
    Exposure.TOOL_SAFE: 2,
    Exposure.REPO_SAFE: 3,
    Exposure.PUBLIC_SAFE: 4,
    Exposure.NEVER_EXPORT: 99,
}

AUTHORITY_RANK: dict[str, int] = {
    AuthorityLevel.RAW_EVIDENCE: 0,
    AuthorityLevel.EXTRACTED_CANDIDATE: 1,
    AuthorityLevel.AGENT_OBSERVATION: 2,
    AuthorityLevel.USER_STATEMENT: 3,
    AuthorityLevel.ACCEPTED_PREFERENCE: 4,
    AuthorityLevel.PROJECT_NOTE: 4,
    AuthorityLevel.DECISION_RECORD: 6,
    AuthorityLevel.REPO_SOURCE: 6,
    AuthorityLevel.POLICY_CONSTRAINT: 7,
    AuthorityLevel.CANONICAL_STATE: 8,
    AuthorityLevel.SUPERSEDED: -1,
    AuthorityLevel.CONTRADICTED: -1,
    AuthorityLevel.VAULTED: -1,
}


def exposure_allowed(item_exposure: str, exposure_ceiling: str) -> bool:
    if item_exposure == Exposure.NEVER_EXPORT:
        return False
    if exposure_ceiling == Exposure.NEVER_EXPORT:
        return True
    return EXPOSURE_RANK.get(item_exposure, 99) <= EXPOSURE_RANK.get(exposure_ceiling, 0)


def privacy_allowed(
    privacy_class: str,
    exposure_ceiling: str,
    claim_type: str | None = None,
    explicit_policy_override: bool = False,
) -> bool:
    if privacy_class == PrivacyClass.SECRETS_POSSIBLE:
        return exposure_ceiling not in {
            Exposure.TOOL_SAFE,
            Exposure.REPO_SAFE,
            Exposure.PUBLIC_SAFE,
        }
    return not (
        claim_type == ClaimType.PRIVATE_FACT
        and exposure_ceiling in {Exposure.TOOL_SAFE, Exposure.REPO_SAFE}
        and not explicit_policy_override
    )


def authority_at_least(left: str, right: str) -> bool:
    return AUTHORITY_RANK.get(left, -1) >= AUTHORITY_RANK.get(right, -1)
