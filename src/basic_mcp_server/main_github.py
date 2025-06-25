"""Main module for a basic MCP server.

NOTE: The github connection has been switched to a more generic 
auth process not tied to a third party.
"""

import os
from typing import Literal

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

from basic_mcp_server.github_oauth_provider import GitHubOAuthProvider, GitHubOAuthSettings
 

def find_project_root():
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / 'pyproject.toml').exists():
            return current
        current = current.parent
    return current

PROJECT_ROOT = find_project_root()


class SimpleGitHubOAuthProvider(GitHubOAuthProvider):
    """GitHub OAuth provider for legacy MCP server."""

    def __init__(self, github_settings: GitHubOAuthSettings, github_callback_path: str):
        super().__init__(github_settings, github_callback_path)

class ServerSettings(BaseModel):
    """Settings for a simple GitHub MCP server."""

    # Server settings
    host: str = "localhost"
    port: int = 8000
    stateless_http: bool = False
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    github_callback_path: str = "http://localhost:3030/github/callback"



def create_mcp(settings: ServerSettings, github_settings: GitHubOAuthSettings) -> FastMCP:
    
    oauth_provider = SimpleGitHubOAuthProvider(github_settings, settings.github_callback_path)
    
    
    auth_settings = AuthSettings(
        issuer_url=settings.server_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[github_settings.mcp_scope],
            default_scopes=[github_settings.mcp_scope],
        ),
        required_scopes=[github_settings.mcp_scope],
        # No resource_server_url parameter in legacy mode
        # resource_server_url=None,
    )    
    
    mcp_srv = FastMCP("basic_mcp_server", 
                      stateless_http=settings.stateless_http,
                      auth_server_provider=oauth_provider,
                      host=settings.host,
                      port=settings.port,
                      debug=True,
                      auth=auth_settings,

    )

    # ----------------------------------------------------------------
    
    mcp_srv.custom_route("/github/callback", methods=["GET"])
    async def github_callback_handler(request: Request) -> Response:
        """Handle GitHub OAuth callback."""
        logger.info(f"Handler Github Oauth")
        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if not code or not state:
            raise HTTPException(400, "Missing code or state parameter")

        redirect_uri = await oauth_provider.handle_github_callback(code, state)
        logger.info(f"Redirect URL in server: {redirect_url}")
        return RedirectResponse(status_code=302, url=redirect_uri)

    @mcp_srv.tool()
    async def gh_connect() -> str:
        """
        Connects to github and retrieve basic user info.
        """
        logger.info("On 'connect' tool call...")
        access_token = get_access_token()
        logger.info(f"Access token: {access_token}")
        if not access_token:
            logger.error("Not Authenticated")
            raise ValueError("Not authenticated")
        logger.info(f"Client Authenticated with token {access_token}")
        return await oauth_provider.get_github_user_info(access_token.token)

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
    
    github_settings = GitHubOAuthSettings()
    
    server_url = f"http://{host}:{port}"
    cb_port = 3030
    github_callback_url = f"http://{host}:{cb_port}/github/callback"
    logger.info(f"Github callback url: {github_callback_url}")
    server_settings = ServerSettings(
        host=host,
        port=port,
        stateless_http=True if transport == "streamable-http" else False,
        server_url=AnyHttpUrl(server_url),
        github_callback_path=github_callback_url,
    )    
    
    mcp_server = create_mcp(server_settings, github_settings)
    
    # Initialize and run the server with the specified transport
    logger.info(f"Starting Basic MCP server with {transport} transport ({host}:{port}) and stateless_http={server_settings.stateless_http}...")
    mcp_server.run(transport=transport)
    return 0


if __name__ == "__main__":
    main_mcp()
