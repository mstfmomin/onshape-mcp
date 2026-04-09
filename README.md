# Onshape MCP Server (Extended)

Enhanced Model Context Protocol (MCP) server for programmatic CAD modeling with Onshape. Built for AI-assisted sheet metal design, DFM analysis, and FeatureScript automation.

This is a fork of [clarsbyte/onshape-mcp](https://github.com/clarsbyte/onshape-mcp) (which forked [hedless/onshape-mcp](https://github.com/hedless/onshape-mcp)), extended by [Palki Motors](https://palkimotors.com) with OAuth support, FeatureScript evaluation, body detail inspection, and custom feature injection.

## What's New in This Fork

- **OAuth 2.0 authentication** with auto-refresh (no API keys needed)
- **`evaluate_featurescript`** — run any FeatureScript query against a Part Studio (bounding boxes, hole counting, geometry inspection)
- **`add_custom_feature`** — push Claude-generated FeatureScript as features (shell, draft, pattern, sweep, loft, mirror, chamfer, sheet metal bends)
- **`get_body_details`** — get full topology (faces, edges, vertices) for DFM analysis
- **27 tools total** (24 original + 3 new)

## Features

### Core Capabilities (from upstream)
- **Document Discovery** — search/list projects, find Part Studios, navigate workspaces
- **Parametric Sketch Creation** — rectangles, circles, lines, compound sketches
- **Feature Management** — extrudes, fillets, holes, thicken
- **Mechanical Components** — gears with customizable teeth/module/ratio
- **Edge Query & Discovery** — find edges by radius, type, or parent feature
- **Variable Tables** — read/write Onshape variables for parametric designs
- **Assembly Management** — get assembly structure and instances

### New in This Fork
- **FeatureScript Evaluation** — query geometry, compute bounding boxes, count faces/edges, measure distances
- **Custom Feature Injection** — add any Onshape feature type via API (shell, draft, pattern, sweep, loft, mirror, boolean, chamfer, sheet metal operations)
- **Body Detail Inspection** — get topology with face/edge/vertex counts, circular edge detection for hole counting
- **OAuth with Auto-Refresh** — tokens refresh automatically before expiry, no manual renewal needed

## Installation

### Prerequisites

- Python 3.10 or higher
- Onshape account (Professional or higher)

### Setup

```bash
git clone https://github.com/mstfmomin/onshape-mcp.git
cd onshape-mcp
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

## Authentication

This fork supports two auth methods. Use whichever is available on your account.

### Option A: OAuth 2.0 (recommended — works without developer API key access)

1. Go to [Onshape Developer Portal](https://cad.onshape.com/appstore/dev-portal/oauthApps) and create an OAuth application
2. Set redirect URL to `http://localhost:8099/callback`
3. Enable permissions: Read Profile, Read Documents, Write Documents, Delete Documents
4. Run the included OAuth setup script:

```bash
python oauth_setup.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

5. Approve in browser, then set environment variables:

```bash
export ONSHAPE_OAUTH_TOKEN="<access_token>"
export ONSHAPE_OAUTH_CLIENT_ID="<client_id>"
export ONSHAPE_OAUTH_CLIENT_SECRET="<client_secret>"
export ONSHAPE_OAUTH_REFRESH_TOKEN="<refresh_token>"
```

### Option B: API Keys (Basic Auth)

Requires developer access enabled by Onshape support (email api-support@onshape.com).

```bash
export ONSHAPE_ACCESS_KEY="your_access_key"
export ONSHAPE_SECRET_KEY="your_secret_key"
```

## Usage

### Running the Server

```bash
# stdio mode (for Claude Code / MCP clients)
onshape-mcp

# or directly
python -m onshape_mcp.server

# SSE mode (for web-based MCP clients)
python -m onshape_mcp.server --sse --port 3000
```

### Configuring with Claude Code

Add to your `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "onshape": {
      "command": "/absolute/path/to/onshape-mcp/venv/bin/python",
      "args": ["-m", "onshape_mcp.server"],
      "env": {
        "ONSHAPE_OAUTH_TOKEN": "your_token",
        "ONSHAPE_OAUTH_CLIENT_ID": "your_client_id",
        "ONSHAPE_OAUTH_CLIENT_SECRET": "your_client_secret",
        "ONSHAPE_OAUTH_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

Restart Claude Code after editing `mcp.json`. Verify with: "Can you list my Onshape documents?"

## All 27 Tools

| Category | Tool | Description |
|----------|------|-------------|
| **Sketches** | `create_sketch` | Multi-entity sketch (lines, circles, rectangles) |
| | `create_sketch_rectangle` | Rectangle with optional variable refs |
| | `create_sketch_line` | Line sketch |
| | `create_sketch_circle` | Circle sketch |
| **Features** | `create_extrude` | Extrude with NEW/ADD/REMOVE/INTERSECT |
| | `create_stepped_extrude` | Multi-step extrude |
| | `create_hole` | Hole feature |
| | `create_fillet` | Fillet (EDGE/FACE/FULL_ROUND) |
| | `create_thicken` | Thicken surface |
| | `create_gear` | Spur gear with teeth/module/bore |
| **Edges** | `get_edges` | All edges with geometry info |
| | `find_circular_edges` | Circular edges by radius |
| | `find_edges_by_feature` | Edges from a specific feature |
| **Variables** | `get_variables` | Read variable table |
| | `set_variable` | Set/update a variable |
| **Documents** | `list_documents` | List with filtering/sorting |
| | `search_documents` | Search by name |
| | `get_document` | Document details |
| | `get_document_summary` | Full summary with workspaces/elements |
| | `find_part_studios` | Find Part Studios by name pattern |
| | `get_parts` | Parts in a Part Studio |
| | `get_elements` | All elements in workspace |
| | `get_features` | Feature tree of Part Studio |
| | `get_assembly` | Assembly structure |
| **NEW** | `evaluate_featurescript` | Run FeatureScript queries |
| **NEW** | `add_custom_feature` | Push any feature type via API |
| **NEW** | `get_body_details` | Full topology inspection |

## Architecture

```
onshape_mcp/
├── api/
│   ├── client.py         # HTTP client — Basic Auth + OAuth with auto-refresh
│   ├── documents.py      # Document discovery & navigation
│   ├── partstudio.py     # Part Studio management + FeatureScript evaluation
│   ├── variables.py      # Variable table management
│   └── edges.py          # Edge query & discovery
├── builders/
│   ├── sketch.py         # Sketch feature builder
│   ├── extrude.py        # Extrude feature builder
│   ├── stepped_extrude.py # Stepped extrude builder
│   ├── fillet.py         # Fillet feature builder
│   ├── thicken.py        # Thicken feature builder
│   └── gear.py           # Gear feature builder
├── tools/
│   └── __init__.py       # MCP tool definitions
├── server.py             # Main MCP server (27 tools)
└── oauth_setup.py        # OAuth token setup helper
```

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov

# Code formatting
black .
ruff check .
```

## Use Case: Sheet Metal DFM with AI

This fork was built for AI-assisted sheet metal design at [Palki Motors](https://palkimotors.com), where Claude designs battery pack enclosures for electric vehicles. The workflow:

1. Claude generates FeatureScript for flat patterns (2D laser cut profiles)
2. `add_custom_feature` pushes sheet metal bends
3. `get_body_details` inspects topology for DFM validation
4. `evaluate_featurescript` computes bounding boxes and hole counts
5. All designs constrained to: **flat sheet -> laser cut -> brake press bend**

## Contributing

Contributions welcome! Please submit a Pull Request.

## License

MIT License

## Acknowledgments

- Original MCP server: [hedless/onshape-mcp](https://github.com/hedless/onshape-mcp)
- Extended fork: [clarsbyte/onshape-mcp](https://github.com/clarsbyte/onshape-mcp)
- OAuth + FeatureScript + DFM extensions: [Palki Motors](https://palkimotors.com)
- Built on the [Model Context Protocol](https://modelcontextprotocol.io/)
- Onshape API docs: https://onshape-public.github.io/docs/
