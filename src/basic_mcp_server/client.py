"""
MCP client with OAuth support.

Connects to an MCP server using streamable HTTP transport with OAuth.

"""

import asyncio
import json
import os
import threading
import time
import webbrowser
import traceback
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import click

from loguru import logger
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken


AUTH_SUCCESSFUL_MSG=b"""
<html>
<body>
    <h1>Authorization Successful!</h1>
    <p>You can close this window and return to the terminal.</p>
    <script>setTimeout(() => window.close(), 2000);</script>
</body>
</html>
"""

def get_failure_msg(query_params: dict) -> bytes:
    return f"""
<html>
<body>
    <h1>Authorization Failed</h1>
    <p>Error: {query_params['error'][0]}</p>
    <p>You can close this window and return to the terminal.</p>
</body>
</html>
""".encode()


class InMemoryTokenStorage(TokenStorage):
    """In-memory token storage."""

    def __init__(self):
        logger.info("In memory Storage Initialization")
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        logger.info(f"Getting tokens {self._tokens}")
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        logger.info(f"Setting tokens {tokens}")
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        logger.info(f"Getting client info {self._client_info}")
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        logger.info(f"Setting client info {self._client_info}")
        self._client_info = client_info


class CallbackHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to capture OAuth callback."""

    def __init__(self, request, client_address, server, callback_data):
        """Initialize with callback data storage."""
        self.callback_data = callback_data
        super().__init__(request, client_address, server)
        logger.info(f"Callback data: {callback_data} and {urlparse(self.path)}")

    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        logger.info("Query params: {query_params}")

        if "code" in query_params:
            self.callback_data["authorization_code"] = query_params["code"][0]
            self.callback_data["state"] = query_params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(AUTH_SUCCESSFUL_MSG)
        elif "error" in query_params:
            self.callback_data["error"] = query_params["error"][0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(get_failure_msg(query_params))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class CallbackServer:
    """Server to handle OAuth callbacks."""

    def __init__(self, cb_host: str="localhost", cb_port: int=3000):
        self.host = cb_host
        self.port = cb_port
        self.server_instance = None
        self.thread = None
        self.callback_data = {"authorization_code": None, "state": None, "error": None}

    def _create_handler_with_data(self):
        """Create a handler class with access to callback data."""
        callback_data = self.callback_data

        class DataCallbackHandler(CallbackHandler):
            def __init__(self, request, client_address, server):
                logger.info(f"Request {request}")
                logger.info(f"Client Addr {client_address}")
                logger.info(f"Server {server}")
                super().__init__(request, client_address, server, callback_data)

        return DataCallbackHandler

    def start(self):
        logger.info("*" * 80)
        logger.info("Starting callback server...")
        handler_class = self._create_handler_with_data()
        self.server_instance = HTTPServer((self.host, self.port), handler_class)
        self.thread = threading.Thread(target=self.server_instance.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"🖥️  Started callback server on http://{self.host}:{self.port}")
        logger.info("*" * 80)

    def stop(self):
        logger.info("*" * 80)
        logger.info("Stopping callback server...")
        logger.info("*" * 80)
        if self.server_instance:
            self.server_instance.shutdown()
            self.server_instance.server_close()
        if self.thread:
            self.thread.join(timeout=1)

    def wait_for_callback(self, timeout=300):
        """Wait for OAuth callback with timeout."""
        logger.info(f"Waiting for authorization callback for {timeout} seconds...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            # logger.info(f"Waiting for callback.... {time.time() - start_time}")
            if self.callback_data["authorization_code"]:
                logger.info(f"Callback received! Auth code: {self.callback_data["authorization_code"]}")
                return self.callback_data["authorization_code"]
            elif self.callback_data["error"]:
                raise Exception(f"OAuth error: {self.callback_data['error']}")

            time.sleep(0.1)
        raise Exception("Timeout waiting for OAuth callback")

    def get_state(self):
        """Get the received state parameter."""
        return self.callback_data["state"]


class MCPAuthClient:
    """MCP client with OAuth support."""

    def __init__(self, server_url: str, cb_host: str, cb_port: int, transport: str = "streamable_http"):
        self.server_url = server_url
        self.cb_host = cb_host
        self.cb_port = cb_port
        self.transport = transport
        self.session: ClientSession | None = None

    async def connect_2_mcp_server(self):
        logger.info(f"🔗 Attempting to connect to {self.server_url}...")

        try:
            callback_server = CallbackServer(cb_host=self.cb_host, cb_port=self.cb_port)
            callback_server.start()

            async def callback_handler() -> tuple[str, str | None]:
                """Wait for OAuth callback and return auth code and state."""
                logger.info("⏳ Waiting for authorization callback...")
                try:
                    auth_code = callback_server.wait_for_callback(timeout=300)
                    logger.info(f"Auth code:{auth_code} Callback server state {callback_server.get_state()}")
                    return auth_code, callback_server.get_state()
                finally:
                    callback_server.stop()

            async def _default_redirect_handler(authorization_url: str) -> None:
                """Default redirect handler that opens the URL in a browser."""
                logger.info(f"Opening browser for authorization: {authorization_url}")
                webbrowser.open(authorization_url)

            client_metadata_dict = {
                "client_name": "fps_github_mcp_server",
                "redirect_uris": ["http://localhost:3030/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
            }


            # Create OAuth authentication handler using the new interface
            logger.warning(f"Server url: {self.server_url}")
            oauth_auth = OAuthClientProvider(
                server_url=self.server_url.replace("/mcp", ""),
                client_metadata=OAuthClientMetadata.model_validate(
                    client_metadata_dict
                ),
                storage=InMemoryTokenStorage(),
                redirect_handler=_default_redirect_handler,
                callback_handler=callback_handler,
            )

            # Create transport with auth handler based on transport type
            match self.transport:
                case "sse":
                    logger.info("📡 Opening SSE transport connection with auth...")
                    async with sse_client(
                        url=self.server_url,
                        auth=oauth_auth,
                        timeout=60,
                    ) as (read_stream, write_stream):
                        await self._run_session(read_stream, write_stream, None)
                case 'streamable-http':
                    logger.info("📡 Opening StreamableHTTP transport connection with auth...")
                    async with streamablehttp_client(
                        url=self.server_url,
                        auth=oauth_auth,
                        timeout=timedelta(seconds=60),
                    ) as (read_stream, write_stream, get_session_id):
                        await self._run_session(read_stream, write_stream, get_session_id)
                case _:
                    raise ValueError(f"Non supported transport {self.transport}!!!")

        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")

            traceback.print_exc()

    async def _run_session(self, read_stream, write_stream, get_session_id):
        """Run the MCP session with the given streams."""
        logger.info("🤝 Initializing MCP session...")
        async with ClientSession(read_stream, write_stream) as session:
            self.session = session
            logger.info(f"⚡ Starting session initialization {session}...")
            await session.initialize()
            logger.info("✨ Session initialization complete!")

            logger.info(f"\n✅ Connected to MCP server at {self.server_url}")
            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    print(f"Session ID: {session_id}")

            await self.interactive_loop()

    async def list_tools(self):
        """List available tools from the server."""
        if not self.session:
            logger.warning("❌ Not connected to server")
            return

        try:
            result = await self.session.list_tools()
            if hasattr(result, "tools") and result.tools:
                logger.info("\n📋 Available tools:")
                for i, tool in enumerate(result.tools, 1):
                    logger.info(f"{i}. {tool.name}")
                    if tool.description:
                        logger.info(f"\tDescription: {tool.description}")
                    
            else:
                logger.warning("No tools available")
        except Exception as e:
            logger.error(f"❌ Failed to list tools: {e}")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None):
        """Call a specific tool."""
        if not self.session:
            logger.warning("❌ Not connected to server")
            return

        try:
            result = await self.session.call_tool(tool_name, arguments or {})
            logger.info(f"\n🔧 Tool '{tool_name}' result:")
            if hasattr(result, "content"):
                if result.isError:
                    logger.error(f"Error calling tool {tool_name}\n\n{result.content[0].text}\n\n")
                    return
                                
                for content in result.content:
                    if content.type == "text":
                        logger.info(content.text)
                    else:
                        logger.warning(f"Content wo text: {content}")
            else:
                logger.warning("Result with no content!\n\m{result}")
        except Exception as e:
            logger.error(f"❌ Failed to call tool '{tool_name}': {e}")

    async def interactive_loop(self):
        """Run interactive command loop."""
        logger.info("\n🎯 Interactive MCP Client")
        logger.info("Commands:")
        logger.info("  list - List available tools")
        logger.info("  call <tool_name> [args] - Call a tool")
        logger.info("  quit - Exit the client\n")

        while True:
            try:
                command = input("mcp> ").strip()

                if not command:
                    continue

                if command == "quit":
                    break

                elif command == "list":
                    await self.list_tools()

                elif command.startswith("call "):
                    parts = command.split(maxsplit=2)
                    tool_name = parts[1] if len(parts) > 1 else ""

                    if not tool_name:
                        print("❌ Please specify a tool name")
                        continue

                    arguments = {}
                    if len(parts) > 2:
                        try:
                            arguments = json.loads(parts[2])
                        except json.JSONDecodeError:
                            logger.error("❌ Invalid arguments format (expected JSON)")
                            continue
                    logger.info(f"\n\nCalling {tool_name} with arguments:\n\n{arguments}")
                    await self.call_tool(tool_name, arguments)

                else:
                    logger.warning("❌ Unknown command. Try 'list', 'call <tool_name>', or 'quit'")

            except KeyboardInterrupt:
                logger.info("\n\n👋 Goodbye!")
                break
            except EOFError:
                break


async def main(host: str, port: int, cbhost: str, cbport: int, transport: Literal["stdio", "sse", "streamable-http"]):
    server_url = f"http://{host}:{port}" + ("/mcp" if transport == "streamable-http" else "/sse")
    logger.info(f"🚀 MCP Auth Client connecting to: {server_url} ({transport})")

    client = MCPAuthClient(server_url, cbhost, cbport, transport)
    await client.connect_2_mcp_server()


@click.command()
@click.option("--host", default="localhost", help="Host")
@click.option("--port", default=os.environ.get("PORT", 8000), help="Port to listen on")
@click.option(
    "--transport",
    default=os.environ.get("TRANSPORT", "streamable-http"),
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use ('sse' or 'streamable-http')",
)
@click.option("--cbhost", default="localhost", help="Callback Host")
@click.option("--cbport", default=os.environ.get("CB_PORT", 3030), help="Callback port to listen on")
def cli(host: str, port: int, cbhost: str, cbport: int, transport: Literal["stdio", "sse", "streamable-http"]):
    """CLI entry point for uv script."""
    asyncio.run(main(host, port, cbhost, cbport, transport))


if __name__ == "__main__":
    cli()
