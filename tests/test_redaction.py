from app.security.redaction import contains_secret, redact_secrets


def test_redaction_handles_env_yaml_bearer_and_known_token_shapes() -> None:
    value = "\n".join(
        [
            "API_KEY=sk-local-secret",
            "password: super-secret",
            "Authorization: Bearer abcdef123456",
            "aws=AKIA1234567890ABCDEF",
            "github_pat_abcdefghijklmnopqrstuvwxyz123456",
            "-----BEGIN PRIVATE KEY-----",
        ]
    )

    redacted = redact_secrets(value)

    assert redacted is not None
    assert "sk-local-secret" not in redacted
    assert "super-secret" not in redacted
    assert "abcdef123456" not in redacted
    assert "AKIA1234567890ABCDEF" not in redacted
    assert "github_pat_" not in redacted
    assert "PRIVATE KEY" not in redacted
    assert contains_secret(value)
