"""
TrendRadar MCP Server with REST API
  - MCP SSE: /sse (for MCP clients like Cherry Studio)
  - Health:  /health
  - REST:    /api/crawl, /api/search, /api/latest, /api/trend
"""
import json
import uvicorn
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.server import mcp, _get_tools


async def health(request):
    return JSONResponse({"status": "ok", "service": "trendradar-mcp"})


# ─── REST API 包装 ─────────────────────────────────────────────

async def api_crawl(request):
    """手动触发爬虫  GET /api/crawl?platforms=weibo,zhihu"""
    params = dict(request.query_params)
    platforms = params.get("platforms")
    if platforms:
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    tools = _get_tools()
    result = await tools["system"].trigger_crawl(
        platforms=platforms,
        save_to_local=False,
        include_url=False
    )
    return JSONResponse(json.loads(result) if isinstance(result, str) else result)


async def api_search(request):
    """搜关键词  GET /api/search?q=数模&limit=10"""
    params = dict(request.query_params)
    q = params.get("q", "")
    if not q:
        return JSONResponse({"error": "missing parameter 'q'"}, 400)
    tools = _get_tools()
    platforms = params.get("platforms")
    if platforms:
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    result = await tools["search"].search_news_unified(
        query=q,
        search_mode=params.get("mode", "keyword"),
        platforms=platforms,
        limit=int(params.get("limit", 50)),
        sort_by=params.get("sort_by", "relevance"),
        threshold=float(params.get("threshold", 0.6)),
        include_url=params.get("include_url", "false").lower() == "true"
    )
    return JSONResponse(json.loads(result) if isinstance(result, str) else result)


async def api_latest(request):
    """最新热搜  GET /api/latest?limit=20"""
    params = dict(request.query_params)
    platforms = params.get("platforms")
    if platforms:
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    tools = _get_tools()
    result = await tools["data_query"].get_latest_news(
        platforms=platforms,
        limit=int(params.get("limit", 50)),
        include_url=params.get("include_url", "false").lower() == "true"
    )
    return JSONResponse(json.loads(result) if isinstance(result, str) else result)


async def api_trend(request):
    """趋势分析  GET /api/trend?topic=数模"""
    params = dict(request.query_params)
    topic = params.get("topic", "")
    if not topic:
        return JSONResponse({"error": "missing parameter 'topic'"}, 400)
    tools = _get_tools()
    result = await tools["analytics"].analyze_topic_trend_unified(
        topic=topic,
        analysis_type=params.get("type", "trend"),
        granularity=params.get("granularity", "day"),
        spike_threshold=float(params.get("spike_threshold", 3.0)),
        time_window=int(params.get("time_window", 24)),
        lookahead_hours=int(params.get("lookahead_hours", 6)),
        confidence_threshold=float(params.get("confidence_threshold", 0.7))
    )
    return JSONResponse(json.loads(result) if isinstance(result, str) else result)


async def api_sentiment(request):
    """情感分析  GET /api/sentiment?topic=AI"""
    params = dict(request.query_params)
    topic = params.get("topic", "")
    if not topic:
        return JSONResponse({"error": "missing parameter 'topic'"}, 400)
    tools = _get_tools()
    result = await tools["analytics"].analyze_topic_trend_unified(
        topic=topic,
        analysis_type="sentiment",
        granularity=params.get("granularity", "day")
    )
    return JSONResponse(json.loads(result) if isinstance(result, str) else result)


async def api_summary(request):
    """生成日报  GET /api/summary"""
    tools = _get_tools()
    result = await tools["analytics"].generate_summary_report(
        report_type="daily",
        date=None
    )
    return JSONResponse(json.loads(result) if isinstance(result, str) else result)


# ─── 挂载路由 ──────────────────────────────────────────────────

app = mcp.sse_app()

app.routes.extend([
    Route("/health", endpoint=health, methods=["GET"]),
    Route("/api/crawl", endpoint=api_crawl, methods=["GET"]),
    Route("/api/search", endpoint=api_search, methods=["GET"]),
    Route("/api/latest", endpoint=api_latest, methods=["GET"]),
    Route("/api/trend", endpoint=api_trend, methods=["GET"]),
    Route("/api/sentiment", endpoint=api_sentiment, methods=["GET"]),
    Route("/api/summary", endpoint=api_summary, methods=["GET"]),
])

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    uvicorn.run(app, host="0.0.0.0", port=port)
