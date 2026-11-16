"""MCP tool server exposing the Meraki tools (stdio by default)."""

from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer

from .client import MerakiClient
from .schema import bind
from .tools import TOOLS


def build_server(client: MerakiClient | None = None) -> MCPServer:
    client = client or MerakiClient()
    server = MCPServer(
        name="netops-meraki",
        instructions="Read-only tools for the Cisco Meraki Dashboard API: orgs, networks, devices, ports, clients, events.",
    )
    for fn in TOOLS:
        server.add_tool(bind(fn, client))
    return server


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    build_server().run(transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
