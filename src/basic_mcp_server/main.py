"""Main module for a basic MCP server."""

import os

from loguru import logger
from pathlib import Path

from mcp.server.fastmcp import FastMCP

    
# Configure transport and statelessness
trspt = "stdio"
stateless_http = False
match os.environ.get("TRANSPORT", "stdio"):
    case "stdio":
        trspt = "stdio"
        stateless_http = False
    case "sse":
        trspt = "sse"
        stateless_http = False
    case "streamable-http":
        trspt = "streamable-http"
        stateless_http = True
    case _:
        trspt = "stdio"
        stateless_http = False


def find_project_root():
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / 'pyproject.toml').exists():
            return current
        current = current.parent
    return current

PROJECT_ROOT = find_project_root()


# Initialize FastMCP server
host = os.environ.get("HOST", "0.0.0.0")  # render.com needs '0.0.0.0' specified as host when deploying the service
port = int(os.environ.get("PORT", 10000))  # render.com has '10000' as default port
mcp = FastMCP("basic_mcp_server", stateless_http=stateless_http, host=host, port=port)


# NOTE: We have to wrap the resources to be accessible from the prompts

@mcp.tool()
def connect() -> str:
    """
    Connects to the mcp server and retrieve a basic message.
    """
    return "This is a basic mcp server!"


if __name__ == "__main__":
    # Initialize and run the server with the specified transport
    logger.info(f"Starting Basic MCP server with {trspt} transport ({host}:{port}) and stateless_http={stateless_http}...")
    mcp.run(transport=trspt)
