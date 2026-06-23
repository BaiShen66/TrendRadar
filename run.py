"""
TrendRadar MCP Server with REST API
  - MCP SSE: /sse (for MCP clients)
  - Health:  /health
  - REST:    /api/crawl, /api/search, /api/latest, /api/tools
"""
import json
import uvicorn
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.server import mcp
from mcp_server.server import trigger_crawl, search_news, get_latest_news, analyze_topic_trend


async def health(request):
    return JSONResponse({"status": "ok", "service": "trendradar-mcp"})


async def api_crawl(request):
    params = dict(request.query_params)
    platforms = params.get("platforms")
    if platforms:
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    result = await trigger_crawl(
        platforms=platforms,
        save_to_local=False,
        include_url=False
    )
    return JSONResponse(json.loads(result))


async def api_search(request):
    params = dict(request.query_params)
    q = params.get("q", "")
    if not q:
        return JSONResponse({"error": "missing 'q'"}, 400)
    platforms = params.get("platforms")
    if platforms:
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    result = await search_news(
        query=q,
        platforms=platforms,
        limit=int(params.get("limit", 50)),
        include_url=True
    )
    return JSONResponse(json.loads(result))


async def api_latest(request):
    params = dict(request.query_params)
    platforms = params.get("platforms")
    if platforms:
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    result = await get_latest_news(
        platforms=platforms,
        limit=int(params.get("limit", 50)),
        include_url=True
    )
    return JSONResponse(json.loads(result))


async def api_trend(request):
    params = dict(request.query_params)
    topic = params.get("topic", "")
    if not topic:
        return JSONResponse({"error": "missing 'topic'"}, 400)
    result = await analyze_topic_trend(
        topic=topic,
        analysis_type=params.get("type", "trend"),
        granularity=params.get("granularity", "day")
    )
    return JSONResponse(json.loads(result))


app = mcp.sse_app()
app.routes.extend([
    Route("/health", endpoint=health, methods=["GET"]),
    Route("/api/crawl", endpoint=api_crawl, methods=["GET"]),
    Route("/api/search", endpoint=api_search, methods=["GET"]),
    Route("/api/latest", endpoint=api_latest, methods=["GET"]),
    Route("/api/trend", endpoint=api_trend, methods=["GET"]),
])

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    uvicorn.run(app, host="0.0.0.0", port=port)
