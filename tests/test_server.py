import asyncio

from netops_agent.server import build_server
from netops_agent.tools import TOOLS


def test_server_lists_all_tools_without_client_param(client):
    server = build_server(client)
    listed = asyncio.run(server.list_tools())
    assert {t.name for t in listed} == {f.__name__ for f in TOOLS}
    for t in listed:
        assert "client" not in t.input_schema.get("properties", {})


def test_server_calls_tool(client):
    result = asyncio.run(build_server(client).call_tool("list_organizations", {}))
    assert result.structured_content == {"result": [{"id": "669910444571370859", "name": "DevNet-47LAwcsYS1sK"}]}
