"""Test phần logic chatbot (không gọi API thật)."""
import json

from blockchain.node import Network
from chatbot import build_system, get_status, run_tool


def make_network():
    net = Network()
    net.create_node("Node-1", "127.0.0.1", 5001)
    net.create_node("Node-2", "127.0.0.1", 5002)
    return net


def test_system_contains_docs():
    assert "NOI DUNG TEST" in build_system(docs="NOI DUNG TEST")


def test_status_has_no_secrets_and_lists_nodes():
    status = get_status(make_network())
    assert {n["node"] for n in status["nodes"]} == {"Node-1", "Node-2"}
    assert "private" not in json.dumps(status).lower()


def test_run_tool_verify_not_found():
    out = json.loads(run_tool(make_network(), "verify_credential", {"credential_id": "CRED-X"}))
    assert out["status"] == "NOT_FOUND"


def test_run_tool_unknown():
    assert "error" in json.loads(run_tool(make_network(), "hack", {}))
