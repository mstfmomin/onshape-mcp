"""Onshape MCP Server - Model Context Protocol implementation."""

import asyncio
import json
import os
from typing import Any

from mcp.server import Server, NotificationOptions
from mcp.types import Tool, TextContent, Image, ImageMimeType
import httpx
from loguru import logger

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import OnshapeDocuments
from onshape_mcp.api.partstudio import OnshapePartStudio
from onshape_mcp.api.variables import OnshapeVariables
from onshape_mcp.api.edges import OnshapeEdges
from onshape_mcp.builders.sketch import SketchBuilder
from onshape_mcp.builders.extrude import ExtrudeBuilder
from onshape_mcp.builders.stepped_extrude import SteppedExtrudeBuilder
from onshape_mcp.builders.fillet import FilletBuilder
from onshape_mcp.builders.thicken import ThickenBuilder
from onshape_mcp.builders.gear import GearBuilder

# Initialize server
server = Server("onshape-mcp")

# Global client (initialized on startup)
client: Optional[OnshapeClient] = None
documents_api: Optional[OnshapeDocuments] = None
partstudio_api: Optional[OnshapePartStudio] = None
variables_api: Optional[OnshapeVariables] = None
edges_api: Optional[OnshapeEdges] = None


def _load_credentials() -> OnshapeCredentials:
    """Load Onshape credentials from environment variables."""
    # Check for OAuth credentials (preferred)
    if os.getenv("ONSHAPE_OAUTH_TOKEN"):
        logger.info("Using OAuth 2.0 authentication")
        return OnshapeCredentials(
            oauth_token=os.getenv("ONSHAPE_OAUTH_TOKEN", ""),
            oauth_client_id=os.getenv("ONSHAPE_OAUTH_CLIENT_ID", ""),
            oauth_client_secret=os.getenv("ONSHAPE_OAUTH_CLIENT_SECRET", ""),
            oauth_refresh_token=os.getenv("ONSHAPE_OAUTH_REFRESH_TOKEN", ""),
        )
    
    # Fall back to API keys
    if os.getenv("ONSHAPE_ACCESS_KEY"):
        logger.info("Using API Key authentication")
        return OnshapeCredentials(
            access_key=os.getenv("ONSHAPE_ACCESS_KEY", ""),
            secret_key=os.getenv("ONSHAPE_SECRET_KEY", ""),
        )
    
    raise ValueError(
        "No Onshape credentials found. Set either:\n"
        "  OAuth: ONSHAPE_OAUTH_TOKEN, ONSHAPE_OAUTH_CLIENT_ID, ONSHAPE_OAUTH_CLIENT_SECRET, ONSHAPE_OAUTH_REFRESH_TOKEN\n"
        "  API Keys: ONSHAPE_ACCESS_KEY, ONSHAPE_SECRET_KEY"
    )


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools for Onshape."""
    return [
        # Sketch tools
        Tool(
            name="create_sketch",
            description="Create a multi-entity sketch with lines, circles, and rectangles",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_plane": {"type": "string", "description": "Sketch plane (e.g., 'XY', 'XZ', 'YZ')"},
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["line", "circle", "rectangle"]},
                                "start": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
                                "end": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
                                "center": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
                                "radius": {"type": "number"},
                                "width": {"type": "number"},
                                "height": {"type": "number"},
                            }
                        }
                    }
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_plane", "entities"]
            }
        ),
        Tool(
            name="create_sketch_rectangle",
            description="Create a rectangle sketch",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_plane": {"type": "string", "description": "Sketch plane (e.g., 'XY')"},
                    "x": {"type": "number", "description": "X position"},
                    "y": {"type": "number", "description": "Y position"},
                    "width": {"type": "number", "description": "Rectangle width"},
                    "height": {"type": "number", "description": "Rectangle height"},
                    "width_var": {"type": "string", "description": "Optional variable ref for width"},
                    "height_var": {"type": "string", "description": "Optional variable ref for height"},
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_plane", "x", "y", "width", "height"]
            }
        ),
        Tool(
            name="create_sketch_line",
            description="Create a line sketch",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_plane": {"type": "string", "description": "Sketch plane"},
                    "start_x": {"type": "number", "description": "Start X position"},
                    "start_y": {"type": "number", "description": "Start Y position"},
                    "end_x": {"type": "number", "description": "End X position"},
                    "end_y": {"type": "number", "description": "End Y position"},
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_plane", "start_x", "start_y", "end_x", "end_y"]
            }
        ),
        Tool(
            name="create_sketch_circle",
            description="Create a circle sketch",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_plane": {"type": "string", "description": "Sketch plane"},
                    "center_x": {"type": "number", "description": "Center X position"},
                    "center_y": {"type": "number", "description": "Center Y position"},
                    "radius": {"type": "number", "description": "Circle radius"},
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_plane", "center_x", "center_y", "radius"]
            }
        ),
        # Feature tools
        Tool(
            name="create_extrude",
            description="Create an extrude feature from a sketch",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_id": {"type": "string", "description": "Sketch feature ID"},
                    "depth": {"type": "number", "description": "Extrusion depth (mm)"},
                    "operation": {"type": "string", "enum": ["NEW", "ADD", "REMOVE", "INTERSECT"], "description": "Feature operation"},
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_id", "depth", "operation"]
            }
        ),
        Tool(
            name="create_stepped_extrude",
            description="Create a stepped extrude for counterbores",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_id": {"type": "string", "description": "Sketch feature ID"},
                    "depths": {"type": "array", "items": {"type": "number"}, "description": "List of extrusion depths"},
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_id", "depths"]
            }
        ),
        Tool(
            name="create_hole",
            description="Create a hole feature",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "sketch_id": {"type": "string", "description": "Sketch feature ID"},
                    "depth": {"type": "number", "description": "Hole depth (mm)"},
                },
                "required": ["document_id", "workspace_id", "element_id", "sketch_id", "depth"]
            }
        ),
        Tool(
            name="create_fillet",
            description="Create a fillet feature",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "edge_ids": {"type": "array", "items": {"type": "string"}, "description": "Edge IDs to fillet"},
                    "radius": {"type": "number", "description": "Fillet radius (mm)"},
                    "fillet_type": {"type": "string", "enum": ["EDGE", "FACE", "FULL_ROUND"], "description": "Fillet type"},
                },
                "required": ["document_id", "workspace_id", "element_id", "edge_ids", "radius", "fillet_type"]
            }
        ),
        Tool(
            name="create_thicken",
            description="Create a thicken feature on a surface",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "face_ids": {"type": "array", "items": {"type": "string"}, "description": "Face IDs to thicken"},
                    "thickness": {"type": "number", "description": "Thickness value (mm)"},
                },
                "required": ["document_id", "workspace_id", "element_id", "face_ids", "thickness"]
            }
        ),
        Tool(
            name="create_gear",
            description="Create a spur gear with customizable teeth, module, and bore",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "num_teeth": {"type": "integer", "description": "Number of teeth"},
                    "module": {"type": "number", "description": "Gear module (mm)"},
                    "bore_diameter": {"type": "number", "description": "Center bore diameter (mm)"},
                    "face_width": {"type": "number", "description": "Face width (mm)"},
                    "pressure_angle": {"type": "number", "description": "Pressure angle (degrees)"},
                },
                "required": ["document_id", "workspace_id", "element_id", "num_teeth", "module", "bore_diameter", "face_width"]
            }
        ),
        # Edge tools
        Tool(
            name="get_edges",
            description="Get all edges in a Part Studio body",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "body_id": {"type": "string", "description": "Body ID (optional)"},
                },
                "required": ["document_id", "workspace_id", "element_id"]
            }
        ),
        Tool(
            name="find_circular_edges",
            description="Find circular edges by radius in a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "radius": {"type": "number", "description": "Search radius (mm)"},
                    "tolerance": {"type": "number", "description": "Tolerance (mm)"},
                    "body_id": {"type": "string", "description": "Body ID (optional)"},
                },
                "required": ["document_id", "workspace_id", "element_id", "radius", "tolerance"]
            }
        ),
        Tool(
            name="find_edges_by_feature",
            description="Find edges created by a specific feature",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "feature_id": {"type": "string", "description": "Feature ID"},
                },
                "required": ["document_id", "workspace_id", "element_id", "feature_id"]
            }
        ),
        # Variable tools
        Tool(
            name="get_variables",
            description="Get all variables from a Part Studio variable table",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                },
                "required": ["document_id", "workspace_id", "element_id"]
            }
        ),
        Tool(
            name="set_variable",
            description="Set or update a variable in the variable table",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "variable_name": {"type": "string", "description": "Variable name"},
                    "value": {"type": ["number", "string"], "description": "Variable value"},
                    "expression": {"type": "string", "description": "Optional expression (overrides value)"},
                },
                "required": ["document_id", "workspace_id", "element_id", "variable_name", "value"]
            }
        ),
        # Document tools
        Tool(
            name="list_documents",
            description="List Onshape documents with filtering and sorting",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Filter documents by owner ('all', 'me', or owner name)"},
                    "sort": {"type": "string", "enum": ["name", "created", "modified"], "description": "Sort order"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
            }
        ),
        Tool(
            name="search_documents",
            description="Search Onshape documents by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_document",
            description="Get document details by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                },
                "required": ["document_id"]
            }
        ),
        Tool(
            name="get_document_summary",
            description="Get full document summary with all workspaces and elements",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                },
                "required": ["document_id"]
            }
        ),
        Tool(
            name="find_part_studios",
            description="Find Part Studios by name pattern",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "name_pattern": {"type": "string", "description": "Name pattern to search"},
                },
                "required": ["document_id", "name_pattern"]
            }
        ),
        Tool(
            name="get_parts",
            description="Get all parts in a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                },
                "required": ["document_id", "workspace_id", "element_id"]
            }
        ),
        Tool(
            name="get_elements",
            description="Get all elements (Part Studios, assemblies, etc.) in a workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                },
                "required": ["document_id", "workspace_id"]
            }
        ),
        Tool(
            name="get_features",
            description="Get the feature tree of a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                },
                "required": ["document_id", "workspace_id", "element_id"]
            }
        ),
        Tool(
            name="get_assembly",
            description="Get assembly structure and instances",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Assembly element ID"},
                },
                "required": ["document_id", "workspace_id", "element_id"]
            }
        ),
        # NEW: FeatureScript and custom features
        Tool(
            name="evaluate_featurescript",
            description="Evaluate FeatureScript queries against a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "script": {"type": "string", "description": "FeatureScript code to evaluate"},
                },
                "required": ["document_id", "workspace_id", "element_id", "script"]
            }
        ),
        Tool(
            name="add_custom_feature",
            description="Add a custom feature (shell, draft, pattern, sweep, loft, mirror, chamfer, sheet metal bends)",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "feature_type": {"type": "string", "enum": ["shell", "draft", "pattern", "sweep", "loft", "mirror", "boolean", "chamfer", "bend"], "description": "Feature type"},
                    "feature_data": {"type": "object", "description": "Feature-specific parameters"},
                },
                "required": ["document_id", "workspace_id", "element_id", "feature_type", "feature_data"]
            }
        ),
        Tool(
            name="get_body_details",
            description="Get full topology details (faces, edges, vertices) for DFM analysis",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Onshape document ID"},
                    "workspace_id": {"type": "string", "description": "Onshape workspace ID"},
                    "element_id": {"type": "string", "description": "Part Studio element ID"},
                    "body_id": {"type": "string", "description": "Body ID (optional)"},
                },
                "required": ["document_id", "workspace_id", "element_id"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | Image]:
    """Handle MCP tool calls."""
    logger.info(f"Tool called: {name} with args: {arguments}")
    
    try:
        # Initialize API clients if not already done
        if not client or not documents_api:
            raise ValueError("Client not initialized. Server may not have started properly.")
        
        # Sketch tools
        if name == "create_sketch":
            builder = SketchBuilder(client)
            result = await builder.create_sketch(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_plane"],
                arguments["entities"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_sketch_rectangle":
            builder = SketchBuilder(client)
            result = await builder.create_sketch_rectangle(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_plane"],
                arguments["x"],
                arguments["y"],
                arguments["width"],
                arguments["height"],
                arguments.get("width_var"),
                arguments.get("height_var")
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_sketch_line":
            builder = SketchBuilder(client)
            result = await builder.create_sketch_line(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_plane"],
                arguments["start_x"],
                arguments["start_y"],
                arguments["end_x"],
                arguments["end_y"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_sketch_circle":
            builder = SketchBuilder(client)
            result = await builder.create_sketch_circle(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_plane"],
                arguments["center_x"],
                arguments["center_y"],
                arguments["radius"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        # Feature tools
        elif name == "create_extrude":
            builder = ExtrudeBuilder(client)
            result = await builder.create_extrude(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_id"],
                arguments["depth"],
                arguments["operation"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_stepped_extrude":
            builder = SteppedExtrudeBuilder(client)
            result = await builder.create_stepped_extrude(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_id"],
                arguments["depths"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_hole":
            builder = ExtrudeBuilder(client)
            result = await builder.create_hole(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["sketch_id"],
                arguments["depth"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_fillet":
            builder = FilletBuilder(client)
            result = await builder.create_fillet(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["edge_ids"],
                arguments["radius"],
                arguments["fillet_type"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
        
        elif name == "create_thicken":
            builder = ThickenBuilder(client)
            result = await builder.create_thicken(
                arguments["document_id"],
                arguments["workspace_id"],
                arguments["element_id"],
                arguments["face_ids"],
                arguments["thickness"]
            )
            return [TextContent(type="text", text=json.dumps(result))]
            body = json.loads(args.get("body", "{}"))
            ps_id = body.get("part_studio_id")
            ws_id = body.get("workspace_id")
            doc_id = body.get("document_id")
            element_id = body.get("element_id")
            feature_type = body.get("feature_type")
            sketch_id = body.get("sketch_id")
            x_offset = body.get("x_offset", 0)
            y_offset = body.get("y_offset", 0)
            profile_references = body.get("profile_references", [])
            start_vertex = body.get("start_vertex")
            end_vertex = body.get("end_vertex")
            radius = body.get("radius", 0)
            mode = body.get("mode", "NEW")
            chamfer_type = body.get("chamfer_type", "EQUAL_EDGES")
            chamfer_size = body.get("chamfer_size", 0)
            
            # GET request for extrude (use json array or list of dicts for profile refs)
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/{ps_id}/features"
            
            # Create feature request object
            feature_data = {
                "type": feature_type,
                "branchId": None,
                "documentId": doc_id,
                "workspaceId": ws_id,
                "elementId": element_id,
                "partStudioId": ps_id,
            }
            
            # Add type-specific parameters
            if feature_type == "extrude" and sketch_id:
                feature_data.update({
                    "mode": mode,
                    "profileReferences": profile_references or [],
                    "depth": body.get("depth", 0),
                })
            elif feature_type == "fillet" and body.get("edge_ids"):
                feature_data.update({
                    "edgeReferences": body.get("edge_ids", []),
                    "radius": radius,
                })
            elif feature_type == "hole" and sketch_id:
                feature_data.update({
                    "sketchId": sketch_id,
                })
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.post(path, data=feature_data)
            
            return {"success": True, "feature": result}
        
        elif tool_name == "create_gear":
            body = json.loads(args.get("body", "{}"))
            ps_id = body.get("part_studio_id")
            ws_id = body.get("workspace_id")
            doc_id = body.get("document_id")
            element_id = body.get("element_id")
            num_teeth = body.get("num_teeth", 20)
            module = body.get("module", 2.0)
            bore_diameter = body.get("bore_diameter", 10)
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/{ps_id}/features"
            feature_data = {
                "type": "customFeature",
                "featureType": "gear",
                "num_teeth": num_teeth,
                "module": module,
                "bore_diameter": bore_diameter,
            }
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.post(path, data=feature_data)
            
            return {"success": True, "gear_feature": result}
        
        elif tool_name == "get_edges":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            ps_id = body.get("part_studio_id")
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/{ps_id}/edges"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"edges": result}
        
        elif tool_name == "find_circular_edges":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            ps_id = body.get("part_studio_id")
            target_radius = body.get("target_radius")
            tolerance = body.get("tolerance", 0.1)
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/{ps_id}/edges"
            
            async with OnshapeClient(self.credentials) as client:
                all_edges = await client.get(path)
            
            circular_edges = [
                e for e in all_edges.get("edges", [])
                if e.get("type") == "CIRCLE"
                and abs(e.get("radius", 0) - target_radius) <= tolerance
            ]
            
            return {"circular_edges": circular_edges, "count": len(circular_edges)}
        
        elif tool_name == "find_edges_by_feature":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            ps_id = body.get("part_studio_id")
            feature_id = body.get("feature_id")
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/{ps_id}/edges"
            
            async with OnshapeClient(self.credentials) as client:
                all_edges = await client.get(path)
            
            feature_edges = [
                e for e in all_edges.get("edges", [])
                if e.get("feature_id") == feature_id
            ]
            
            return {"edges_from_feature": feature_edges, "count": len(feature_edges)}        
        elif tool_name == "get_variables":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            
            path = f"/api/v9/documents/{doc_id}/workspaces/{ws_id}/elements/{element_id}/variables"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"variables": result.get("variables", [])}
        
        elif tool_name == "set_variable":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            var_name = body.get("variable_name")
            var_value = body.get("variable_value")
            
            path = f"/api/v9/documents/{doc_id}/workspaces/{ws_id}/elements/{element_id}/variables/{var_name}"
            
            data = {"value": var_value}
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.post(path, data=data)
            
            return {"success": True, "variable": result}
        
        elif tool_name == "list_documents":
            query = args.get("query", "")
            sort_by = args.get("sort_by", "modifiedAt")
            limit = int(args.get("limit", 20))
            
            path = "/api/v9/documents"
            params = {
                "q": query,
                "sortBy": sort_by,
                "limit": limit,
            }
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path, params=params)
            
            documents = []
            for doc in result.get("documents", []):
                documents.append({
                    "id": doc.get("id"),
                    "name": doc.get("name"),
                    "owner": doc.get("owner"),
                    "createdAt": doc.get("createdAt"),
                    "modifiedAt": doc.get("modifiedAt"),
                    "public": doc.get("public"),
                })
            
            return {"documents": documents}
        
        elif tool_name == "search_documents":
            query = args.get("query", "")
            
            path = "/api/v9/documents"
            params = {"q": query}
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path, params=params)
            
            return {"search_results": result.get("documents", [])}        
        elif tool_name == "get_document":
            doc_id = args.get("document_id")
            
            path = f"/api/v9/documents/{doc_id}"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"document": result}
        
        elif tool_name == "get_document_summary":
            doc_id = args.get("document_id")
            
            path = f"/api/v9/documents/{doc_id}"
            
            async with OnshapeClient(self.credentials) as client:
                doc = await client.get(path)
            
            summary = {
                "id": doc.get("id"),
                "name": doc.get("name"),
                "owner": doc.get("owner"),
                "createdAt": doc.get("createdAt"),
                "modifiedAt": doc.get("modifiedAt"),
                "public": doc.get("public"),
                "workspaces": [],
            }
            
            for workspace in doc.get("workspaces", []):
                summary["workspaces"].append({
                    "id": workspace.get("id"),
                    "name": workspace.get("name"),
                    "type": workspace.get("workspaceType"),
                    "elements": [
                        {"id": e.get("id"), "name": e.get("name"), "type": e.get("elementType")}
                        for e in workspace.get("elements", [])
                    ],
                })
            
            return {"summary": summary}
        
        elif tool_name == "find_part_studios":
            doc_id = args.get("document_id")
            pattern = args.get("pattern", "")
            
            path = f"/api/v9/documents/{doc_id}"
            
            async with OnshapeClient(self.credentials) as client:
                doc = await client.get(path)
            
            part_studios = []
            for workspace in doc.get("workspaces", []):
                for element in workspace.get("elements", []):
                    if element.get("elementType") == "Part Studio":
                        if not pattern or pattern.lower() in element.get("name", "").lower():
                            part_studios.append({
                                "id": element.get("id"),
                                "name": element.get("name"),
                                "workspace_id": workspace.get("id"),
                            })            
            return {"part_studios": part_studios}
        
        elif tool_name == "get_parts":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/parts"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"parts": result.get("parts", [])}
        
        elif tool_name == "get_elements":
            doc_id = args.get("document_id")
            ws_id = args.get("workspace_id")
            
            path = f"/api/v9/documents/{doc_id}/workspaces/{ws_id}/elements"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"elements": result.get("elements", [])}
        
        elif tool_name == "get_features":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/features"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"features": result.get("features", [])}
        
        elif tool_name == "get_assembly":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            
            path = f"/api/v9/assemblies/{doc_id}/{ws_id}/{element_id}"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            return {"assembly": result}
        
        elif tool_name == "evaluate_featurescript":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            script = body.get("script", "")
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/featurescript/eval"
            
            data = {"script": script}
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.post(path, data=data)            
            return {"evaluation_result": result}
        
        elif tool_name == "add_custom_feature":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            ps_id = body.get("part_studio_id")
            feature_type = body.get("feature_type")
            parameters = body.get("parameters", {})
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/{ps_id}/features"
            
            feature_data = {
                "type": feature_type,
                "parameters": parameters,
            }
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.post(path, data=feature_data)
            
            return {"success": True, "feature": result}
        
        elif tool_name == "get_body_details":
            body = json.loads(args.get("body", "{}"))
            doc_id = body.get("document_id")
            ws_id = body.get("workspace_id")
            element_id = body.get("element_id")
            body_id = body.get("body_id")
            
            path = f"/api/v9/partstudios/{doc_id}/{ws_id}/{element_id}/bodies/{body_id}"
            
            async with OnshapeClient(self.credentials) as client:
                result = await client.get(path)
            
            # Extract topology details
            topology = {
                "faces": len(result.get("faces", [])),
                "edges": len(result.get("edges", [])),
                "vertices": len(result.get("vertices", [])),
                "circular_edges": len([e for e in result.get("edges", []) if e.get("type") == "CIRCLE"]),
                "face_details": result.get("faces", []),
                "edge_details": result.get("edges", []),
            }
            
            return {"topology": topology}
        
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON in request body: {e}"}
    except Exception as e:
        logger.error(f"Error handling tool {tool_name}: {e}")
        return {"error": str(e)}


async def main():
    """Main entry point for the MCP server."""
    
    # Load credentials from environment
    credentials = OnshapeCredentials(
        access_key=os.getenv("ONSHAPE_ACCESS_KEY", ""),
        secret_key=os.getenv("ONSHAPE_SECRET_KEY", ""),
        oauth_token=os.getenv("ONSHAPE_OAUTH_TOKEN", ""),
        oauth_client_id=os.getenv("ONSHAPE_OAUTH_CLIENT_ID", ""),
        oauth_client_secret=os.getenv("ONSHAPE_OAUTH_CLIENT_SECRET", ""),
        oauth_refresh_token=os.getenv("ONSHAPE_OAUTH_REFRESH_TOKEN", ""),
    )
    
    # Initialize server with handlers
    server = Server("onshape-mcp")
    server.add_resource(list_tools)
    server.add_resource(call_tool)
    
    logger.info("Onshape MCP Server starting...")    
    # Check for SSE mode
    if "--sse" in sys.argv:
        import uvicorn
        port = 3000
        if "--port" in sys.argv:
            idx = sys.argv.index("--port")
            if idx + 1 < len(sys.argv):
                port = int(sys.argv[idx + 1])
        
        logger.info(f"Running in SSE mode on port {port}")
        
        from sse_starlette.endpoints import ServerSentEventResponse
        from fastapi import FastAPI
        
        app = FastAPI()
        
        @app.get("/sse")
        async def sse_endpoint():
            """SSE endpoint for web-based MCP clients."""
            async def event_generator():
                yield "connected\n\n"
            return ServerSentEventResponse(event_generator())
        
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Stdio mode (default for Claude Code)
        logger.info("Running in stdio mode")
        async with stdio_server(server) as (input_stream, output_stream):
            logger.info("Onshape MCP Server ready for stdio communication")
            await server.run(input_stream, output_stream)


if __name__ == "__main__":
    import sys
    asyncio.run(main())
