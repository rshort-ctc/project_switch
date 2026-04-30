# Secrets Handling

SWITCH uses path filtering, secret-looking filename exclusion, and summary
redaction. Operators should still assume secret detection is a guardrail, not a
complete DLP system.

Do not register repositories containing committed secrets. If a secret is found,
rotate it, remove it from the repository, reindex, and review audit records.
