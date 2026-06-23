"""
TrendRadar MCP HTTP Server — with /health endpoint for Render
"""
import uvicorn
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.server import mcp

async def health_check(request):
    return JSONResponse({"status": "ok", "service": "trendradar-mcp"})

# Get the MCP ASGI app and add a health check endpoint
app = mcp.sse_app()
app.routes.append(
    Route("/health", endpoint=health_check, methods=["GET"])
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
