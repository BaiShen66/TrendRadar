"""
TrendRadar MCP Bridge (23 Tools + RSS + R2 + Health)
- POST /mcp 1 JSON-RPC (23 tools with full schemas)
- GET /, /health 1 Health checks
- trigger_crawl auto-fetches RSS
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

# ===== Tool definitions with proper schemas =====
TOOLS = []

def tool(name, desc, **props):
    TOOLS.append({"name": name, "description": desc, "inputSchema": props})

tool("tr_resolve_date_range", "Parse a natural language date expression into a standard date range",
     type="object", properties={"expression": {"type": "string"}}, required=["expression"])

tool("tr_get_latest_news", "Get the latest batch of crawled news/hotlist data",
     type="object", properties={
         "platforms": {"type": "array", "items": {"type": "string"}, "description": "Platform IDs (e.g. zhihu, weibo)"},
         "limit": {"type": "number", "default": 50, "description": "Max results (max 1000)"},
         "include_url": {"type": "boolean", "default": False, "description": "Include URLs in results"}
     })

tool("tr_get_trending_topics", "Get trending topic frequency statistics",
     type="object", properties={
         "top_n": {"type": "number", "default": 10},
         "mode": {"type": "string", "enum": ["daily", "current"], "default": "current"},
         "extract_mode": {"type": "string", "enum": ["keywords", "auto_extract"], "default": "keywords"}
     })

tool("tr_get_latest_rss", "Get the latest RSS feed data (supports multi-day)",
     type="object", properties={
         "feeds": {"type": "array", "items": {"type": "string"}, "description": "Feed IDs (e.g. hacker-news, 36kr)"},
         "days": {"type": "number", "default": 1, "description": "Days to look back (max 30)"},
         "limit": {"type": "number", "default": 50, "description": "Max results (max 500)"},
         "include_summary": {"type": "boolean", "default": False}
     })

tool("tr_search_rss", "Search RSS data by keyword",
     type="object", properties={
         "keyword": {"type": "string", "description": "Search keyword"},
         "feeds": {"type": "array", "items": {"type": "string"}, "description": "Feed IDs to search"},
         "days": {"type": "number", "default": 7},
         "limit": {"type": "number", "default": 50},
         "include_summary": {"type": "boolean", "default": False}
     }, required=["keyword"])

tool("tr_search_news", "Search news/hotlist data by keyword",
     type="object", properties={
         "query": {"type": "string", "description": "Search query"},
         "platforms": {"type": "array", "items": {"type": "string"}},
         "limit": {"type": "number", "default": 50},
         "include_url": {"type": "boolean", "default": False},
         "include_rss": {"type": "boolean", "default": False}
     }, required=["query"])

tool("tr_search_news_advanced", "Advanced news search with more filter options",
     type="object", properties={
         "query": {"type": "string"},
         "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}},
         "platforms": {"type": "array", "items": {"type": "string"}},
         "limit": {"type": "number", "default": 50},
         "sort_by": {"type": "string", "enum": ["relevance", "date", "platform"]},
         "include_url": {"type": "boolean", "default": False},
         "include_rss": {"type": "boolean", "default": False}
     }, required=["query"])

tool("tr_get_news_statistics", "Get news statistics grouped by platform or date",
     type="object", properties={
         "platforms": {"type": "array", "items": {"type": "string"}},
         "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}},
         "group_by": {"type": "string", "enum": ["platform", "date"], "default": "platform"}
     })

tool("tr_analyze_sentiment", "Analyze sentiment/emotion trends for a topic over time",
     type="object", properties={
         "topic": {"type": "string", "description": "Topic keyword"},
         "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}},
         "platforms": {"type": "array", "items": {"type": "string"}},
         "time_range": {"type": "number", "default": 24}
     }, required=["topic"])

tool("tr_analyze_topic_trend", "Analyze how a topic's popularity trend changes over time",
     type="object", properties={
         "topic": {"type": "string"},
         "analysis_type": {"type": "string", "enum": ["trend", "lifecycle", "viral", "predict"], "default": "trend"},
         "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}},
         "granularity": {"type": "string", "enum": ["hour", "day", "week"], "default": "day"}
     }, required=["topic"])

tool("tr_analyze_cross_platform", "Cross-platform comparison analysis for a topic",
     type="object", properties={
         "topic": {"type": "string"},
         "platforms": {"type": "array", "items": {"type": "string"}},
         "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}}
     }, required=["topic"])

tool("tr_generate_summary_report", "Generate a comprehensive summary report for a topic",
     type="object", properties={
         "topic": {"type": "string"},
         "date_range": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}},
         "platforms": {"type": "array", "items": {"type": "string"}},
         "report_type": {"type": "string", "enum": ["overview", "detailed", "trend"], "default": "overview"}
     }, required=["topic"])

tool("tr_get_platform_summary", "Get platform summary information with readable names",
     type="object", properties={
         "platforms": {"type": "array", "items": {"type": "string"}},
         "include_platform_names": {"type": "boolean", "default": True}
     })

tool("tr_get_system_status", "Get system health status including dates, cache, and storage info",
     type="object", properties={})

tool("tr_trigger_crawl", "Trigger a manual crawl of hotlist data + RSS feeds",
     type="object", properties={
         "platforms": {"type": "array", "items": {"type": "string"}, "description": "Platform IDs to crawl (all if omitted)"},
         "save_to_local": {"type": "boolean", "default": False},
         "include_url": {"type": "boolean", "default": False}
     })

tool("tr_sync_from_remote", "Sync data from remote storage (R2) to local SQLite",
     type="object", properties={
         "days": {"type": "number", "default": 7, "description": "Days of data to sync"}
     })

tool("tr_get_storage_status", "Get storage configuration and status (local + remote)",
     type="object", properties={})

tool("tr_list_available_dates", "List available data dates from local/remote/both storage",
     type="object", properties={
         "source": {"type": "string", "enum": ["local", "remote", "both"], "default": "both"}
     })

tool("tr_read_article", "Read a full article from a URL and return clean Markdown",
     type="object", properties={
         "url": {"type": "string", "description": "Article URL (https://...)"},
         "timeout": {"type": "number", "default": 30}
     }, required=["url"])

tool("tr_read_articles_batch", "Batch read multiple articles (max 5, spaced 5s apart)",
     type="object", properties={
         "urls": {"type": "array", "items": {"type": "string"}, "description": "Article URLs (max 5)"},
         "timeout": {"type": "number", "default": 30}
     }, required=["urls"])

tool("tr_get_channel_format_guide", "Get notification channel formatting guide",
     type="object", properties={
         "channel": {"type": "string", "description": "Channel ID (feishu, dingtalk, telegram, email, etc.)"}
     })

tool("tr_get_notification_channels", "Get all configured notification channels and their status",
     type="object", properties={})

tool("tr_send_notification", "Send a notification message via configured channels",
     type="object", properties={
         "message": {"type": "string", "description": "Markdown message content"},
         "title": {"type": "string", "default": "TrendRadar "},
         "channels": {"type": "array", "items": {"type": "string"}, "description": "Target channels (all if omitted)"}
     }, required=["message"])


def result_json(r):
    return [{"type": "text", "text": json.dumps(r, ensure_ascii=False)}]


# Enhanced trigger_crawl with RSS
_orig_crawl = _tools["system"].trigger_crawl

def _run_rss():
    try:
        cfg, _ = _tools["system"]._load_crawl_config()
        rss = cfg.get("rss", {})
        if not rss.get("enabled", True): return
        from trendradar.crawler.rss import RSSFetcher, RSSFeedConfig
        from trendradar.utils.time import get_configured_time
        from trendradar.storage.local import LocalStorageBackend
        feeds = [RSSFeedConfig(id=f["id"], name=f["name"], url=f["url"])
                 for f in rss.get("feeds", []) if f.get("enabled", True)]
        if not feeds: return
        adv = cfg.get("advanced", {}).get("rss", {})
        f = RSSFetcher(feeds=feeds, request_interval=adv.get("request_interval", 1000), timeout=adv.get("timeout", 15))
        r = f.fetch_all()
        tz = cfg.get("app", {}).get("timezone", "Asia/Shanghai")
        s = LocalStorageBackend(data_dir=str(PROJECT_ROOT / "output"), timezone=tz)
        try:
            s.save_rss_data(r)
            print("[RSS] done", flush=True)
        finally:
            s.cleanup()
    except Exception as e:
        print(f"[RSS] {e}", flush=True)


# ===== Call handler =====
def run_tool(name, args):
    if name == "tr_resolve_date_range":
        return DateParser.resolve_date_range_expression(args["expression"])
    elif name == "tr_get_latest_news":
        return _tools["data"].get_latest_news(args.get("platforms"), args.get("limit", 50), args.get("include_url", False))
    elif name == "tr_get_trending_topics":
        return _tools["data"].get_trending_topics(args.get("top_n", 10), args.get("mode", "current"), args.get("extract_mode", "keywords"))
    elif name == "tr_get_latest_rss":
        return _tools["data"].get_latest_rss(args.get("feeds"), args.get("days", 1), args.get("limit", 50), args.get("include_summary", False))
    elif name == "tr_search_rss":
        return _tools["data"].search_rss(args["keyword"], args.get("feeds"), args.get("days", 7), args.get("limit", 50), args.get("include_summary", False))
    elif name == "tr_search_news":
        return _tools["search"].search_news_unified(
            query=args.get("query",""), search_mode="keyword", date_range=args.get("date_range"),
            platforms=args.get("platforms"), limit=args.get("limit",50), sort_by=args.get("sort_by","relevance"),
            threshold=args.get("threshold",0.6), include_url=args.get("include_url",False),
            include_rss=args.get("include_rss",False), rss_limit=args.get("rss_limit",20))
    elif name == "tr_search_news_advanced":
        return _tools["search"].search_news_unified(
            query=args.get("query",""),
            search_mode="keyword",
            date_range=args.get("date_range"),
            platforms=args.get("platforms"),
            limit=args.get("limit",50),
            sort_by=args.get("sort_by","relevance"),
            threshold=args.get("threshold",0.6),
            include_url=args.get("include_url",False),
            include_rss=args.get("include_rss",False),
            rss_limit=args.get("rss_limit",20))
    elif name == "tr_get_news_statistics":
        # DataQueryTools  get_news_statistics，用 get_latest_news 聚合实现
        r = _tools["data"].get_latest_news(
            platforms=args.get("platforms"),
            limit=1000,
            include_url=False
        )
        if not r.get("success"):
            return r
        group_by = args.get("group_by", "platform")
        from collections import defaultdict
        from datetime import datetime
        groups = defaultdict(list)
        for item in r.get("data", []):
            key = item.get("platform_name" if group_by == "platform" else "date", "unknown")
            groups[key].append(item)
        stats = {k: {"count": len(v), "items": v[:5]} for k, v in groups.items()}
        return {
            "success": True,
            "group_by": group_by,
            "total": len(r.get("data", [])),
            "groups": list(groups.keys()),
            "statistics": stats
        }
    elif name == "tr_analyze_sentiment":
        return _tools["analytics"].analyze_sentiment(
            topic=args.get("topic"),
            platforms=args.get("platforms"),
            date_range=args.get("date_range"),
            limit=args.get("limit", 50),
            sort_by_weight=args.get("sort_by_weight", True),
            include_url=args.get("include_url", False))
    elif name == "tr_analyze_topic_trend":
        return _tools["analytics"].analyze_topic_trend_unified(
            topic=args.get("topic", ""),
            analysis_type=args.get("analysis_type", "trend"),
            date_range=args.get("date_range"),
            granularity=args.get("granularity", "day"))
    elif name == "tr_analyze_cross_platform":
        return _tools["analytics"].analyze_data_insights_unified(
            insight_type="platform_compare",
            topic=args.get("topic"),
            date_range=args.get("date_range"))
    elif name == "tr_generate_summary_report":
        # 签名: generate_summary_report(report_type="daily|weekly", date_range=None)
        # report_type 映射: overview  daily, detailed/weekly  weekly, trend  daily
        rt = args.get("report_type", "daily")
        if rt in ("detailed", "trend", "weekly"):
            rt = "weekly"
        else:
            rt = "daily"
        return _tools["analytics"].generate_summary_report(
            report_type=rt,
            date_range=args.get("date_range"))
    elif name == "tr_get_platform_summary":
        import yaml
        config_path = PROJECT_ROOT / "config" / "config.yaml"
        if not config_path.exists():
            return {"success": False, "error": {"code": "CONFIG_NOT_FOUND", "message": "config.yaml 不存在"}}
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        sources = cfg.get("platforms", {}).get("sources", [])
        include_names = args.get("include_platform_names", True)
        result = []
        for s in sources:
            if s.get("enabled", True):
                item = {"id": s["id"]}
                if include_names:
                    item["name"] = s.get("name", s["id"])
                result.append(item)
        # 也加入 RSS 源
        rss = cfg.get("rss", {})
        if rss.get("enabled", True):
            for f in rss.get("feeds", []):
                if f.get("enabled", True):
                    item = {"id": f["id"], "type": "rss"}
                    if include_names:
                        item["name"] = f.get("name", f["id"])
                    result.append(item)
        return {"success": True, "platforms": result, "total": len(result)}
    elif name == "tr_get_system_status":
        return _tools["system"].get_system_status()
    elif name == "tr_trigger_crawl":
        r = _orig_crawl(args.get("platforms"), args.get("save_to_local",False), args.get("include_url",False))
        if r.get("success"):
            _run_rss()
            _tools["storage"].sync_from_remote(days=1)
        get_cache().clear()
        return r
    elif name == "tr_sync_from_remote":
        return _tools["storage"].sync_from_remote(args.get("days",7))
    elif name == "tr_get_storage_status":
        return _tools["storage"].get_storage_status()
    elif name == "tr_list_available_dates":
        return _tools["storage"].list_available_dates(args.get("source","both"))
    elif name == "tr_read_article":
        return _tools["article"].read_article(args["url"], min(max(args.get("timeout",30),10),60))
    elif name == "tr_read_articles_batch":
        return _tools["article"].read_articles_batch(args["urls"], min(max(args.get("timeout",30),10),60))
    elif name == "tr_get_channel_format_guide":
        return _tools["notification"].get_channel_format_guide(args.get("channel"))
    elif name == "tr_get_notification_channels":
        return _tools["notification"].get_notification_channels()
    elif name == "tr_send_notification":
        return _tools["notification"].send_notification(args["message"], args.get("title","TrendRadar通知"), args.get("channels"))
    else:
        raise ValueError(f"Unknown tool: {name}")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_json(200, {"status": "ok", "service": "trendradar", "tools": len(TOOLS)})
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path != "/mcp":
            self.send_response(404); self.end_headers(); return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            method, msg_id, params = body.get("method"), body.get("id"), body.get("params", {})
            if method == "initialize":
                resp = {"jsonrpc":"2.0","result":{"protocolVersion":params.get("protocolVersion","2024-11-05"),"capabilities":{"tools":{}},"serverInfo":{"name":"trendradar","version":"2.0"}},"id"[...]
            elif method == "notifications/initialized":
                resp = None
            elif method == "tools/list":
                resp = {"jsonrpc":"2.0","result":{"tools":TOOLS},"id":msg_id}
            elif method == "tools/call":
                try:
                    r = run_tool(params.get("name"), params.get("arguments", {}))
                    resp = {"jsonrpc":"2.0","result":{"content":result_json(r)},"id":msg_id}
                except Exception as e:
                    resp = {"jsonrpc":"2.0","error":{"code":-32603,"message":str(e),"data":traceback.format_exc()},"id":msg_id}
            else:
                resp = {"jsonrpc":"2.0","error":{"code":-32601,"message":f"Unknown: {method}"},"id":msg_id}
            if resp: self.send_json(200, resp)
            else: self.send_response(202); self.end_headers()
        except json.JSONDecodeError:
            self.send_json(400, {"jsonrpc":"2.0","error":{"code":-32700,"message":"Parse error"}})
        except Exception as e:
            self.send_json(500, {"jsonrpc":"2.0","error":{"code":-32603,"message":str(e)}})

    def send_json(self, status, obj):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try: self.wfile.write(json.dumps(obj).encode())
        except BrokenPipeError: pass
    def log_message(self, *a): pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"TrendRadar MCP v2.0 :{port}/mcp ({len(TOOLS)} tools with schemas)", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
