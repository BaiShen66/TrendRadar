"""
TrendRadar MCP Bridge (Manual JSON-RPC - Full Tools + RSS + Health)
- POST /mcp → JSON-RPC (23 tools)
- GET /, /health → Health checks
- trigger_crawl auto-fetches RSS 
- R2 storage via env vars
"""
import json, os, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()
os.chdir(str(PROJECT_ROOT))

from mcp_server.tools.data_query import DataQueryTools
from mcp_server.tools.analytics import AnalyticsTools
from mcp_server.tools.search_tools import SearchTools
from mcp_server.tools.system import SystemManagementTools
from mcp_server.tools.article_reader import ArticleReaderTools
from mcp_server.tools.storage_sync import StorageSyncTools
from mcp_server.tools.notification import NotificationTools
from mcp_server.utils.date_parser import DateParser
from mcp_server.services.cache_service import get_cache

_tools = {
    "data": DataQueryTools(str(PROJECT_ROOT)),
    "analytics": AnalyticsTools(str(PROJECT_ROOT)),
    "search": SearchTools(str(PROJECT_ROOT)),
    "system": SystemManagementTools(str(PROJECT_ROOT)),
    "article": ArticleReaderTools(str(PROJECT_ROOT)),
    "storage": StorageSyncTools(str(PROJECT_ROOT)),
    "notification": NotificationTools(str(PROJECT_ROOT)),
}
print(f"[TrendRadar] {len(_tools)} tool modules loaded", flush=True)

# ===== Tool implementations =====
def _d(result):
    if isinstance(result, dict) and "data" in result:
        return [{"type": "text", "text": json.dumps(d, ensure_ascii=False)} for d in result["data"]]
    return [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]

def _date(exp):
    return json.loads(DateParser.resolve_date_range_expression(exp))

IMPLS = {}

def reg(name):
    def deco(fn):
        IMPLS[name] = fn
        return fn
    return deco

@reg("resolve_date_range")
def _(a): return _date(a["expression"])

@reg("get_latest_news")
def _(a): return _tools["data"].get_latest_news(a.get("platforms"), a.get("limit", 50), a.get("include_url", False))

@reg("get_trending_topics")
def _(a): return _tools["data"].get_trending_topics(a.get("top_n", 10), a.get("mode", "current"), a.get("extract_mode", "keywords"))

@reg("get_latest_rss")
def _(a): return _tools["data"].get_latest_rss(a.get("feeds"), a.get("days", 1), a.get("limit", 50), a.get("include_summary", False))

@reg("search_rss")
def _(a): return _tools["data"].search_rss(a["keyword"], a.get("feeds"), a.get("days", 7), a.get("limit", 50), a.get("include_summary", False))

@reg("search_news")
def _(a): return _tools["search"].search_news_unified(query=a.get("query",""), search_mode="keyword", date_range=a.get("date_range"), platforms=a.get("platforms"), limit=a.get("limit",50), sort_by=a.get("sort_by","relevance"), threshold=a.get("threshold",0.6), include_url=a.get("include_url",False), include_rss=a.get("include_rss",False), rss_limit=a.get("rss_limit",20))

@reg("search_news_advanced")
def _(a): return _tools["search"].search_news_advanced(a.get("query",""), a.get("date_range"), a.get("platforms"), a.get("limit",50), a.get("sort_by","relevance"), a.get("threshold",0.6), a.get("include_url",False), a.get("include_rss",False), a.get("include_processed",False))

@reg("get_news_statistics")
def _(a): return _tools["data"].get_news_statistics(a.get("platforms"), a.get("date_range"), a.get("group_by","platform"))

@reg("analyze_sentiment")
def _(a): return _tools["analytics"].analyze_sentiment(a.get("topic",""), a.get("date_range"), a.get("platforms"), a.get("time_range",24))

@reg("analyze_topic_trend")
def _(a): return _tools["analytics"].analyze_topic_trend_unified(a.get("topic",""), a.get("analysis_type","trend"), a.get("date_range"), a.get("granularity","day"))

@reg("analyze_cross_platform")
def _(a): return _tools["analytics"].analyze_cross_platform(a.get("topic",""), a.get("platforms"), a.get("date_range"), a.get("include_overlap",True), a.get("include_timeline",True))

@reg("generate_summary_report")
def _(a): return _tools["analytics"].generate_summary_report(a.get("topic",""), a.get("date_range"), a.get("platforms"), a.get("granularity","day"), a.get("report_type","overview"))

@reg("get_platform_summary")
def _(a): return _tools["data"].get_platform_summary(a.get("platforms"), a.get("include_platform_names",True))

@reg("get_system_status")
def _(a): return _tools["system"].get_system_status(a.get("include_dates",True), a.get("include_cache",True))

@reg("sync_from_remote")
def _(a): return _tools["storage"].sync_from_remote(a.get("days",7))

@reg("get_storage_status")
def _(a): return _tools["storage"].get_storage_status()

@reg("list_available_dates")
def _(a): return _tools["storage"].list_available_dates(a.get("source","both"))

@reg("read_article")
def _(a): return _tools["article"].read_article(a["url"], min(max(a.get("timeout",30),10),60))

@reg("read_articles_batch")
def _(a): return _tools["article"].read_articles_batch(a["urls"], min(max(a.get("timeout",30),10),60))

@reg("get_channel_format_guide")
def _(a): return _tools["notification"].get_channel_format_guide(a.get("channel"))

@reg("get_notification_channels")
def _(a): return _tools["notification"].get_notification_channels()

@reg("send_notification")
def _(a): return _tools["notification"].send_notification(a["message"], a.get("title","TrendRadar通知"), a.get("channels"))

# Enhanced trigger_crawl
_orig_crawl = _tools["system"].trigger_crawl

def _fetch_rss_after():
    try:
        cfg, _ = _tools["system"]._load_crawl_config()
        rss = cfg.get("rss", {})
        if not rss.get("enabled", True):
            return
        from trendradar.crawler.rss import RSSFetcher, RSSFeedConfig
        from trendradar.utils.time import get_configured_time
        from trendradar.storage.local import LocalStorageBackend
        feeds = [RSSFeedConfig(id=f["id"], name=f["name"], url=f["url"])
                 for f in rss.get("feeds", []) if f.get("enabled", True)]
        if not feeds:
            return
        adv = cfg.get("advanced", {}).get("rss", {})
        f = RSSFetcher(feeds=feeds, request_interval=adv.get("request_interval", 1000), timeout=adv.get("timeout", 15))
        r = f.fetch_all()
        tz = cfg.get("app", {}).get("timezone", "Asia/Shanghai")
        s = LocalStorageBackend(data_dir=str(PROJECT_ROOT / "output"), timezone=tz)
        try:
            s.save_rss_data(r)
            print(f"[RSS] done", flush=True)
        finally:
            s.cleanup()
    except Exception as e:
        print(f"[RSS] {e}", flush=True)

@reg("trigger_crawl")
def _(a):
    r = _orig_crawl(platforms=a.get("platforms"), save_to_local=a.get("save_to_local",False), include_url=a.get("include_url",False))
    if r.get("success"):
        _fetch_rss_after()
    get_cache().clear()
    return r

print(f"[TrendRadar] {len(IMPLS)} tools registered", flush=True)

TOOLS_LIST = sorted([
    {"name": k, "description": IMPLS[k].__doc__ or k.replace("_"," "), "inputSchema": {"type": "object", "properties": {}, "required": []}}
    for k in IMPLS
], key=lambda x: x["name"])

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send(200, json.dumps({"status": "ok", "service": "trendradar", "tools": len(IMPLS)}))
        else:
            self.send_response(404); self.end_headers()
    def do_POST(self):
        if self.path != "/mcp":
            self.send_response(404); self.end_headers(); return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            m, i, p = body.get("method"), body.get("id"), body.get("params", {})
            if m == "initialize":
                resp = {"jsonrpc":"2.0", "result":{"protocolVersion":p.get("protocolVersion","2024-11-05"),"capabilities":{"tools":{}},"serverInfo":{"name":"trendradar","version":"2.0"}}, "id":i}
            elif m == "notifications/initialized":
                resp = None
            elif m == "tools/list":
                resp = {"jsonrpc":"2.0", "result":{"tools":TOOLS_LIST}, "id":i}
            elif m == "tools/call":
                fn = IMPLS.get(p.get("name"))
                if not fn:
                    resp = {"jsonrpc":"2.0", "error":{"code":-32601,"message":f"Unknown: {p.get('name')}"}, "id":i}
                else:
                    try:
                        r = fn(p.get("arguments",{}))
                        resp = {"jsonrpc":"2.0", "result":{"content":_d(r)}, "id":i}
                    except Exception as e:
                        resp = {"jsonrpc":"2.0", "error":{"code":-32603,"message":str(e),"data":traceback.format_exc()}, "id":i}
            else:
                resp = {"jsonrpc":"2.0", "error":{"code":-32601,"message":f"Unknown method: {m}"}, "id":i}
            if resp:
                self._send(200, json.dumps(resp))
            else:
                self.send_response(202); self.end_headers()
        except json.JSONDecodeError:
            self._send(400, json.dumps({"jsonrpc":"2.0","error":{"code":-32700,"message":"Parse error"}}))
        except Exception as e:
            self._send(500, json.dumps({"jsonrpc":"2.0","error":{"code":-32603,"message":str(e)}}))
    def _send(self, s, b):
        self.send_response(s)
        self.send_header("Content-Type","application/json")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        try: self.wfile.write(b.encode())
        except BrokenPipeError: pass
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"TrendRadar MCP on :{port}/mcp ({len(IMPLS)} tools)", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
