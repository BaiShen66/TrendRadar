"""
TrendRadar Full MCP with RSS + R2 + Health
- /mcp -> FastMCP 27 tools
- /, /health -> Health check
- trigger_crawl auto-fetches RSS
"""
import os, yaml
from pathlib import Path

from mcp_server.server import mcp, _get_tools
from mcp_server.tools.system import SystemManagementTools
from mcp_server.services.cache_service import get_cache

PROJECT_ROOT = Path(__file__).parent.absolute()
os.chdir(str(PROJECT_ROOT))

async def health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok"})

app = None
try:
    app = mcp.http_app()
    app.add_route("/", health, methods=["GET"])
    app.add_route("/health", health, methods=["GET"])
except:
    pass

_orig = SystemManagementTools.trigger_crawl

def _fetch_rss(self, cfg):
    from trendradar.crawler.rss import RSSFetcher, RSSFeedConfig
    from trendradar.utils.time import get_configured_time
    from trendradar.storage.local import LocalStorageBackend
    rss = cfg.get("rss", {})
    if not rss.get("enabled", True):
        return
    feeds = [RSSFeedConfig(id=f["id"], name=f["name"], url=f["url"])
             for f in rss.get("feeds", []) if f.get("enabled", True)]
    if not feeds:
        return
    adv = cfg.get("advanced", {}).get("rss", {})
    f = RSSFetcher(feeds=feeds, request_interval=adv.get("request_interval", 1000),
                   timeout=adv.get("timeout", 15))
    r = f.fetch_all()
    tz = cfg.get("app", {}).get("timezone", "Asia/Shanghai")
    s = LocalStorageBackend(data_dir=str(self.project_root / "output"), timezone=tz)
    try:
        s.save_rss_data(r)
        print(f"[RSS] done ({get_configured_time(tz).strftime('%H:%M')})")
    finally:
        s.cleanup()

def _enhanced(self, platforms=None, save_to_local=False, include_url=False):
    r = _orig(self, platforms, save_to_local, include_url)
    if r.get("success"):
        try:
            c, _ = self._load_crawl_config()
            _fetch_rss(self, c)
        except Exception as e:
            print(f"[RSS] err: {e}", flush=True)
    get_cache().clear()
    return r

SystemManagementTools.trigger_crawl = _enhanced

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    _get_tools(str(PROJECT_ROOT))
    print(f"TrendRadar MCP :{port}/mcp", flush=True)
    if app:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    else:
        mcp.run(transport="http", host="0.0.0.0", port=port, path="/mcp")
