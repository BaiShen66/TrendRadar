from mcp_server.server import mcp
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn
import sys

async def health(request):
    return JSONResponse({"status": "ok"})

app = mcp.sse_app()
app.routes.append(Route("/health", health, methods=["GET"]))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(sys.argv[1]) if len(sys.argv) > 1 else 10000)
