"""TraderBot MCP Server — stdio JSON-RPC server for OpenClaw gateway (DD-015).

This is the main entry point for the `traderbot-mcp-server` command.
OpenClaw launches this as a subprocess and communicates via stdio.

Usage:
    traderbot-mcp-server

Registration:
    openclaw mcp add traderbot --command traderbot-mcp-server
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from traderbot.mcp.tools import TOOL_DEFINITIONS, TOOL_HANDLER_MAP

logger = logging.getLogger(__name__)

app = Server("traderbot")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available TraderBot MCP tools."""
    return [
        Tool(
            name=td["name"],
            description=td["description"],
            inputSchema=td["inputSchema"],
        )
        for td in TOOL_DEFINITIONS
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Dispatch a tool call to the appropriate handler."""
    if arguments is None:
        arguments = {}

    handler = TOOL_HANDLER_MAP.get(name)
    if handler is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result))]
    except TypeError as e:
        return [TextContent(type="text", text=json.dumps({"error": f"Invalid arguments for {name}: {e}"}))]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": f"Internal error: {e}"}))]


async def main() -> None:
    """Run the MCP server on stdio."""
    logger.info("TraderBot MCP server starting (pid=%d)", sys.getpid())
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def run_server() -> None:
    """Entry point for the traderbot-mcp-server console script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(main())