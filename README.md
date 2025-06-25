# Basic MCP Server with Basic OAuth

A Python-based MCP (Model Context Protocol) server that gets the current time from the server-side.

This project follows the `src` layout for Python packaging.

# TL;DR Install for Claude Desktop Access to the MCP time server

TODO: Not working yet!!! Lack the proper OAuth Config. I don't think it's possible yet!!!
See this error when launching (in current code I `hide` the mcp variable inside a function to allow CLI parameters throught he `click` library):

```bash
$ TRANSPORT=streamable-http uv run --with "mcp[cli]" mcp run /Users/fperez/dev/basic-mcp/src/basic_mcp_server/main.py
No server object found in /Users/fperez/dev/basic-mcp/src/basic_mcp_server/main.py. Please either:
1. Use a standard variable name (mcp, server, or app)
2. Specify the object name with file:object syntax3. If the server creates the FastMCP object within main()    or another function, refactor the FastMCP object to be a    global variable named mcp, server, or app.
```


```bash
# 1.a) Install the mcp server access in Claude Desktop
./install_claude_desktop_mcp.sh

# 1.b) or manually integrate this JSON snippet to the `mcpServers` section of your `claude_desktop_config.json` (e.g. `~/Library/Application\ Support/Claude/claude_desktop_config.json`)

{
  "fps_basic_oauth_mcp_local": {
    "command": "uv",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}


{
  "fps_basic_oauth_mcp": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}

# 2) Restart Claude and check that the 'Add from basic_mcp_server` option is available in the mcp servers list


e.g. TODO
```

## Features

- Serves current time from an MCP server
- Built with FastAPI for high performance and with Pixi for dependency management and task running
- Source code organized in the `src/` directory
- Includes configurations for:
  - Docker (optional, for containerization)
  - Linting (Ruff, Black, iSort)
  - Formatting
  - Type checking (MyPy)

## Prerequisites

- Python 3.11+
- [Pixi](https://pixi.sh/) (for dependency management and task execution)
- Docker (optional, for containerization)
- Access to your LinkedIn profile

## Project Structure

```bash
.
├── .dockerignore
├── .gitignore
├── Dockerfile
├── pyproject.toml    # Python project metadata and dependencies (PEP 621)
├── README.md
├── src/
│   └── basic_mcp_server/
│       ├── __init__.py
│       ├── client.py
│       └── main.py     # FastAPI application logic
├── tests/             # Test files (e.g., tests_main.py)
```

## Setup and Installation

1. **Clone the repository** (if applicable) or ensure you are in the project root directory.

2. **Install dependencies using Pixi**:

This command will create a virtual environment and install all necessary dependencies:

```bash
pixi install
```

## Running the Server

Pixi tasks are defined in `pyproject.toml`:

### mcps (MCP Server)

```bash
pixi run mcps --transport stdio
```

### Development Mode (with auto-reload)

```bash
# Using pixi directly
pixi run mcps --transport stdio  # or sse, streamable-http

# Alternatively, using uv directly
uv run --with "mcp[cli]" mcp run src/basic_mcp_server/main.py --transport streamable-http

# Go to http://127.0.0.1:10000/mcp
```

The server will start at `http://localhost:10000`. It will automatically reload if you make changes to files in the `src/` directory.

### MCP Inspection Mode

```bash
# Using pixi
DANGEROUSLY_OMIT_AUTH=true  npx @modelcontextprotocol/inspector pixi run mcps --transport stdio

# Direct execution
DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector pixi run python src/basic_mcp_server/main.py --transport streamable-http
```

This starts the inspector for the MCP Server.

### Server

```sh
TRANSPORT=streamable-http pixi run python src/basic_mcp_server/main.py

# or

pixi run mcps
```

### Client

```sh
TRANSPORT=streamable-http pixi run python src/basic_mcp_server/client.py

# or

pixi run mcpc
```

Then, the client will redirect you to the basic auth page, put the following credentials:

```
user="demo_user"
password="demo_password"
```

and press enter. If succeeds, you'll be able to access the CLI interface and exercise `call get_time` to obtain the time from the MCP server.

## Development Tasks

### Run Tests

```bash
pixi run test
```

### Lint and Check Formatting

```bash
pixi run lint
```

### Apply Formatting and Fix Lint Issues

```bash
pixi run format
```

### Build the Package

Creates sdist and wheel in `dist/`:

```bash
pixi run build
```

### Remote Configuration for Claude Desktop

TODO: Not working yet

For connecting to a remote MCP server:

```json
{
  "fps_basic_oauth_mcp": {
    "command": "npx",
    "args": ["mcp-remote", "http://localhost:10000/mcp"]
  }
}
```


## License

This project is licensed under the MIT License. See `pyproject.toml` (See `LICENSE` file) for details.
