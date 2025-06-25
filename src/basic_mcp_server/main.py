"""Main module for a basic MCP server."""

import datetime
import os
from typing import Any, Literal

import click

from httpx import Request, Response
from loguru import logger
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.auth.middleware.auth_context import get_access_token
from pydantic import AnyHttpUrl, BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse

from basic_mcp_server.oauth_provider import SimpleOAuthProvider, SimpleAuthSettings
 

def find_project_root():
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / 'pyproject.toml').exists():
            return current
        current = current.parent
    return current

PROJECT_ROOT = find_project_root()


class BasicOAuthProvider(SimpleOAuthProvider):
    """Basic OAuth provider for legacy MCP server."""

    def __init__(self, oauth_settings: SimpleAuthSettings, oauth_callback_path: str, server_url: str):
        super().__init__(oauth_settings, oauth_callback_path, server_url)

class ServerSettings(BaseModel):
    """Settings for a basic demo MCP server."""

    # Server settings
    host: str = "localhost"
    port: int = 8000
    stateless_http: bool = False
    server_url: AnyHttpUrl = AnyHttpUrl(f"http://{host}:{port}")
    oauth_callback_path: str = f"http://{host}:3030/login/callback"



def create_mcp(settings: ServerSettings, oauth_settings: SimpleAuthSettings) -> FastMCP:
    
    oauth_provider = BasicOAuthProvider(oauth_settings, settings.oauth_callback_path, str(settings.server_url))
    
    
    mcp_auth_settings = AuthSettings(
        issuer_url=settings.server_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[oauth_settings.mcp_scope],
            default_scopes=[oauth_settings.mcp_scope],
        ),
        required_scopes=[oauth_settings.mcp_scope],
        # No resource_server_url parameter in legacy mode
        resource_server_url=None,
    )    
    
    mcp_srv = FastMCP("Basic MCP Server", 
                      stateless_http=settings.stateless_http,
                      auth_server_provider=oauth_provider,
                      host=settings.host,
                      port=settings.port,
                      debug=True,
                      auth=mcp_auth_settings,
    )

    # ----------------------------------------------------------------
    
    @mcp_srv.custom_route("/login", methods=["GET"])
    async def login_page_handler(request: Request) -> Response:
        """Show login form."""
        logger.info(f"Handler Basic Oauth Login")
        state = request.query_params.get("state")
        if not state:
            raise HTTPException(400, "Missing state parameter")
        return await oauth_provider.get_login_page(state)    
    
    
    @mcp_srv.custom_route("/login/callback", methods=["POST"])
    async def login_callback_handler(request: Request) -> Response:
        """Handle simple authentication callback."""
        logger.info(f"Handler Basic Oauth Callback")
        return await oauth_provider.handle_login_callback(request)
            
    @mcp_srv.tool()
    async def get_time() -> dict[str, Any]:
        """
        Get the current server time.

        This tool demonstrates that system information can be protected
        by OAuth authentication. User must be authenticated to access it.
        """

        now = datetime.datetime.now()

        return {
            "current_time": now.isoformat(),
            "timezone": "UTC",  # Simplified for demo
            "timestamp": now.timestamp(),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
        }


    return mcp_srv


@click.command()
@click.option("--host", default="localhost", help="Host")
@click.option("--port", default=os.environ.get("PORT", 8000), help="Port to listen on")
@click.option(
    "--transport",
    default=os.environ.get("TRANSPORT", "streamable-http"),
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use ('sse' or 'streamable-http')",
)
def main_mcp(host: str, port: int, transport: Literal["stdio", "sse", "streamable-http"]) -> int:
    
    oauth_settings = SimpleAuthSettings()
    
    server_url = f"http://{host}:{port}"
    cb_port = 3030
    oauth_callback_url = f"{server_url}/login"
    logger.info(f"Oauth callback url: {oauth_callback_url}")
    server_settings = ServerSettings(
        host=host,
        port=port,
        stateless_http=True if transport == "streamable-http" else False,
        server_url=AnyHttpUrl(server_url),
        oauth_callback_path=oauth_callback_url,
    )    
    
    mcp_server = create_mcp(server_settings, oauth_settings)
    
    # Initialize and run the server with the specified transport
    logger.info(f"Starting Basic MCP server with {transport} transport ({host}:{port}) and stateless_http={server_settings.stateless_http}...")
    mcp_server.run(transport=transport)
    return 0


if __name__ == "__main__":
    main_mcp()
