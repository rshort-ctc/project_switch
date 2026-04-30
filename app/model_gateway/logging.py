from hashlib import sha256
from typing import Any

from app.model_gateway.schemas import ChatMessage
from app.security.redaction import redact_secrets


def text_fingerprint(value: str) -> str:
    redacted = redact_secrets(value) or ""
    return sha256(redacted.encode("utf-8")).hexdigest()


def summarize_messages(messages: list[ChatMessage]) -> dict[str, Any]:
    return {
        "message_count": len(messages),
        "roles": [message.role for message in messages],
        "content_chars": sum(len(message.content) for message in messages),
        "content_fingerprint": text_fingerprint("\n".join(message.content for message in messages)),
    }


def summarize_texts(values: list[str]) -> dict[str, Any]:
    return {
        "item_count": len(values),
        "content_chars": sum(len(value) for value in values),
        "content_fingerprint": text_fingerprint("\n".join(values)),
    }
