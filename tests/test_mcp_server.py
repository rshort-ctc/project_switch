import json
from typing import Any

from pytest import MonkeyPatch
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app import mcp_server


def test_mcp_lists_courthouse_tools() -> None:
    response = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response is not None
    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert "switch_memory_compile_context" in tool_names
    assert "switch_memory_propose_claims" in tool_names


def test_mcp_proposes_candidate_claims_only(
    engine: Engine, monkeypatch: MonkeyPatch
) -> None:
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(mcp_server, "SessionLocal", session_factory)

    evidence_payload = _call_tool(
        "switch_memory_submit_evidence",
        {
            "content": "Decision: keep approval gates",
            "source_type": "chat",
            "workspace": "switch",
        },
    )
    evidence_id = evidence_payload["evidence"]["id"]

    claims_payload = _call_tool(
        "switch_memory_propose_claims",
        {"evidence_id": evidence_id, "default_claim_type": "project_state"},
    )

    claims = claims_payload["claims"]
    assert claims
    assert {claim["status"] for claim in claims} == {"candidate"}
    assert claims[0]["claim_type"] == "decision"

    docket_payload = _call_tool(
        "switch_memory_list_docket", {"workspace": "switch", "status": "candidate"}
    )
    assert [claim["id"] for claim in docket_payload["claims"]] == [claims[0]["id"]]


def test_mcp_compile_context_includes_open_loops(
    engine: Engine, monkeypatch: MonkeyPatch
) -> None:
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(mcp_server, "SessionLocal", session_factory)

    loop_payload = _call_tool(
        "switch_memory_open_loop_add",
        {
            "title": "Document MCP startup",
            "workspace": "switch",
            "next_action": "Run switch-mcp under a local MCP client",
        },
    )
    packet = _call_tool(
        "switch_memory_compile_context",
        {
            "task": "resume governed memory work",
            "workspace": "switch",
            "include_raw_evidence": False,
        },
    )

    assert packet["open_loops"][0]["id"] == loop_payload["open_loop"]["id"]
    assert packet["snapshot_id"]


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    assert "error" not in response
    content = response["result"]["content"]
    assert content[0]["type"] == "text"
    payload = json.loads(content[0]["text"])
    assert isinstance(payload, dict)
    return payload
