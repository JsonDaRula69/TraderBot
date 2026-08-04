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
import os
import sys

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from traderbot.mcp.tools import TOOL_DEFINITIONS, TOOL_HANDLER_MAP
from traderbot.secrets.rotation import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


async def handle_list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    """Return all available TraderBot MCP tools."""
    return ListToolsResult(
        tools=[
            Tool(
                name=td["name"],
                description=td["description"],
                input_schema=td["inputSchema"],
            )
            for td in TOOL_DEFINITIONS
        ]
    )


async def handle_call_tool(
    ctx: ServerRequestContext, params: CallToolRequestParams
) -> CallToolResult:
    """Dispatch a tool call to the appropriate handler."""
    name = params.name
    arguments = params.arguments or {}

    handler = TOOL_HANDLER_MAP.get(name)
    if handler is None:
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))],
            is_error=True,
        )

    try:
        result = await handler(**arguments)
        # Handlers signal failure via an {"error": ...} dict; surface that as
        # a protocol-level error result so clients see the call failed.
        if isinstance(result, dict) and "error" in result:
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result))],
                is_error=True,
            )
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
    except TypeError as e:
        return CallToolResult(
            content=[
                TextContent(
                    type="text", text=json.dumps({"error": f"Invalid arguments for {name}: {e}"})
                )
            ],
            is_error=True,
        )
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": f"Internal error: {e}"}))],
            is_error=True,
        )


app = Server(
    "traderbot",
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool,
)


async def main() -> None:
    """Run the MCP server on stdio."""
    logger.info("TraderBot MCP server starting (pid=%s)", os.getpid())
    await start_scheduler()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        await stop_scheduler()


def run_server() -> None:
    """Entry point for the traderbot-mcp-server console script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(main())


if __name__ == "__main__":
    # Allows `python -m traderbot.mcp.server` as an alternative to the
    # traderbot-mcp-server console script (handy for local debugging).
    run_server()
