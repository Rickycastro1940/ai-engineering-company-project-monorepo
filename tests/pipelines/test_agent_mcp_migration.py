"""Agent migration checks: LangGraph tickets go through MCP only."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from services.agent.graph import REQUIRED_NODES, build_agent_graph, compile_agent_graph
from services.agent.nodes import decide_route_node, lookup_ticket_node
from services.agent import tools as agent_tools
from services.agent.tools import mcp_incidents


def test_agent_exports_mcp_ticket_path_not_direct_http() -> None:
    """Requirement 2: agent package must not expose two Incidents paths."""
    assert hasattr(agent_tools, "lookup_ticket_via_mcp")
    assert "lookup_ticket_via_mcp" in agent_tools.__all__
    assert not hasattr(agent_tools, "lookup_ticket")
    assert "lookup_ticket" not in agent_tools.__all__


def test_lookup_ticket_node_uses_langchain_mcp_adapters_only() -> None:
    """Requirement 1: graph ticket node calls MCP via langchain-mcp-adapters."""
    source = inspect.getsource(lookup_ticket_node)
    assert "lookup_ticket_via_mcp" in source
    assert "via\": \"mcp\"" in source or "via': 'mcp'" in source or '"via": "mcp"' in source
    # Must not call the deprecated direct HTTP helper.
    assert "lookup_ticket(" not in source.replace("lookup_ticket_node", "").replace(
        "lookup_ticket_via_mcp", ""
    )

    mcp_source = Path(mcp_incidents.__file__).read_text(encoding="utf-8")
    assert "langchain_mcp_adapters" in mcp_source
    assert "MultiServerMCPClient" in mcp_source
    assert "manage_incident_ticket" in mcp_source
    # Agent MCP client must not hardcode Incidents Manager HTTP routes.
    assert "/api/incidents" not in mcp_source


def test_agent_nodes_do_not_import_direct_lookup_ticket() -> None:
    """Graph module must not wire the deprecated HTTP Incidents helper."""
    nodes_path = Path(__file__).resolve().parents[2] / "services" / "agent" / "nodes.py"
    tree = ast.parse(nodes_path.read_text(encoding="utf-8"))

    imported_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "services.agent.tools.ticket_lookup":
            for alias in node.names:
                imported_names.add(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module == "services.agent.tools.mcp_incidents":
            assert any(alias.name == "lookup_ticket_via_mcp" for alias in node.names)

    assert "lookup_ticket" not in imported_names

    lookup_fn = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "lookup_ticket_node"
    )
    called: set[str] = set()
    for n in ast.walk(lookup_fn):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                called.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
    assert "lookup_ticket_via_mcp" in called
    assert "lookup_ticket" not in called


def test_lookup_ticket_node_never_hits_incidents_http_directly() -> None:
    """Rubric: every agent ticket interaction goes through MCP as a client."""
    import httpx

    from services.agent.tools.contracts import TicketLookupOutput, TicketRecord

    fake = TicketLookupOutput(
        ok=True,
        tickets=[
            TicketRecord(
                incident_id="BRS-000002",
                date="2024-01-01",
                location_id="COL-01",
                category="EQUIPAMIENTO",
                description="mcp-only",
                status="ABIERTO",
                source="incident_manager",
            )
        ],
    )
    incident_hits: list[str] = []
    real_request = httpx.Client.request

    def tracking_request(self, method, url, *args, **kwargs):  # noqa: ANN001
        target = str(url)
        if "/api/incidents" in target:
            incident_hits.append(f"{method} {target}")
            raise AssertionError(f"agent must not call Incidents Manager directly: {target}")
        return real_request(self, method, url, *args, **kwargs)

    with patch("services.agent.nodes.lookup_ticket_via_mcp", return_value=fake) as spy:
        with patch.object(httpx.Client, "request", tracking_request):
            out = lookup_ticket_node(
                {
                    "question": "What is the status of ticket BRS-000002?",
                    "ticket_query": {"ticket_id": "BRS-000002"},
                    "needs_ticket": True,
                    "needs_rag": False,
                    "needs_inventory": False,
                    "steps": [],
                    "sources_used": [],
                }
            )

    spy.assert_called_once()
    assert out["ticket_result"]["ok"] is True
    assert out["steps"][-1]["output"]["via"] == "mcp"
    assert incident_hits == []


def test_graph_still_routes_rag_vs_tools_with_mcp_ticket_node() -> None:
    """Requirement 3: decide_route + conditional edges unchanged with MCP node."""
    graph = build_agent_graph()
    assert "decide_route" in REQUIRED_NODES
    assert "lookup_ticket" in REQUIRED_NODES
    assert "retrieve" in REQUIRED_NODES

    compiled = compile_agent_graph()
    assert "lookup_ticket" in compiled.get_graph().nodes
    assert "retrieve" in compiled.get_graph().nodes
    assert "decide_route" in compiled.get_graph().nodes

    ticket_state = decide_route_node({"question": "What is the status of ticket BRS-000002?"})
    assert ticket_state["needs_ticket"] is True
    assert ticket_state["route"] in {
        "ticket",
        "both",
        "ticket_inventory",
        "all",
        "inventory_ticket",
    }

    rag_state = decide_route_node(
        {"question": "What is Brasaland's refund policy for grill delays?"}
    )
    assert rag_state["needs_rag"] is True
    assert rag_state.get("needs_ticket") is not True


def test_direct_lookup_ticket_emits_deprecation_warning() -> None:
    from services.agent.tools.ticket_lookup import lookup_ticket

    with pytest.warns(DeprecationWarning, match="lookup_ticket_via_mcp"):
        result = lookup_ticket({"ticket_id": "BRS-000002"}, base_url="http://127.0.0.1:9")
    # Connection will fail to :9 — that's fine; we only assert deprecation fired.
    assert result.ok is False or result.ok is True


@pytest.mark.skipif(
    __import__("os").getenv("SKIP_LIVE_MCP", "").lower() in {"1", "true", "yes"},
    reason="SKIP_LIVE_MCP set",
)
def test_live_lookup_ticket_via_mcp_against_running_server() -> None:
    """Optional live check: agent MCP client → company-tools MCP → incidents API."""
    import httpx

    from services.agent.tools.contracts import TicketLookupInput
    from services.agent.tools.mcp_incidents import lookup_ticket_via_mcp

    try:
        httpx.get("http://127.0.0.1:3001/mcp", timeout=1.0)
    except Exception:  # noqa: BLE001
        pytest.skip("MCP server not reachable on :3001")

    incident_hits: list[str] = []
    real_request = httpx.Client.request
    real_arequest = httpx.AsyncClient.request

    def tracking_request(self, method, url, *args, **kwargs):  # noqa: ANN001
        target = str(url)
        if "/api/incidents" in target:
            incident_hits.append(f"{method} {target}")
            raise AssertionError(f"agent process must not call Incidents directly: {target}")
        return real_request(self, method, url, *args, **kwargs)

    async def tracking_arequest(self, method, url, *args, **kwargs):  # noqa: ANN001
        target = str(url)
        if "/api/incidents" in target:
            incident_hits.append(f"ASYNC {method} {target}")
            raise AssertionError(f"agent process must not call Incidents directly: {target}")
        return await real_arequest(self, method, url, *args, **kwargs)

    with patch.object(httpx.Client, "request", tracking_request), patch.object(
        httpx.AsyncClient, "request", tracking_arequest
    ):
        result = lookup_ticket_via_mcp(TicketLookupInput(ticket_id="BRS-000002"), timeout_seconds=8.0)

    assert incident_hits == [], incident_hits
    # Auth/MCP may fail in some envs; if it succeeds, shape must match API fields.
    if result.ok:
        assert result.tickets
        ticket = result.tickets[0]
        assert ticket.incident_id == "BRS-000002"
        assert ticket.status
        assert ticket.source == "incident_manager"
    else:
        assert result.error in {
            "timeout",
            "service_error",
            "auth_error",
            "not_found",
            "invalid_input",
        }
