"""
TrendRadar MCP Bridge (Direct Mode - no subprocess)
  - POST /mcp → JSON-RPC (initialize, tools/list, tools/call)
  - GET / 和 /health → 健康检查
"""
import json, sys, os, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from mcp_server.server import trigger_crawl, search_news, get_latest_news, analyze_topic_trend

# MCP 工具注册表
TOOLS = []
mcp_name = "trendradar"
mcp_version = "1.0.0"


def get_tools():
    """生成 tools/list 响应"""
    return [
        {
            "name": "trigger_crawl",
            "description": "触发全平台热搜爬取",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "platforms": {"type": "array", "items": {"type": "string"}, "description": "平台列表，如 weibo,zhihu,baidu,bilibili"}
                }
            }
        },
        {
            "name": "search_news",
            "description": "搜索新闻/热搜",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "platforms": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "number", "description": "返回条数"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_latest_news",
            "description": "获取最新热搜数据",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "platforms": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "number"}
                }
            }
        },
        {
            "name": "analyze_topic_trend",
            "description": "分析话题趋势",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "话题关键词"},
                    "analysis_type": {"type": "string", "enum": ["trend", "sentiment", "overview"]},
                    "granularity": {"type": "string", "enum": ["hour", "day", "week"]}
                },
                "required": ["topic"]
            }
        }
    ]


async def call_tool(name, args):
    """调用 MCP 工具并返回结果"""
    fn_map = {
        "trigger_crawl": lambda: trigger_crawl(
            platforms=args.get("platforms"),
            save_to_local=False,
            include_url=False
        ),
        "search_news": lambda: search_news(
            query=args.get("query", ""),
            platforms=args.get("platforms"),
            limit=args.get("limit", 50),
            include_url=True
        ),
        "get_latest_news": lambda: get_latest_news(
            platforms=args.get("platforms"),
            limit=args.get("limit", 50),
            include_url=True
        ),
        "analyze_topic_trend": lambda: analyze_topic_trend(
            topic=args.get("topic", ""),
            analysis_type=args.get("analysis_type", "trend"),
            granularity=args.get("granularity", "day")
        ),
    }
    fn = fn_map.get(name)
    if not fn:
        raise ValueError(f"Unknown tool: {name}")
    result = fn()
    if isinstance(result, str):
        result = json.loads(result)
    if isinstance(result, dict) and "data" in result:
        content = [{"type": "text", "text": json.dumps(d, ensure_ascii=False)} for d in result["data"]]
    else:
        content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
    return {"content": content}


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ("/", "/health"):
            resp = json.dumps({"status": "ok", "service": "trendradar-mcp"})
            self._send_json(200, resp)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/mcp":
            self.send_response(404)
            self.end_headers()
            return

        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))

            method = body.get("method", "")
            msg_id = body.get("id")
            params = body.get("params", {})

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": mcp_name, "version": mcp_version}
                    },
                    "id": msg_id
                }

            elif method == "notifications/initialized":
                resp = {"jsonrpc": "2.0", "id": msg_id} if msg_id else None

            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "result": {"tools": get_tools()},
                    "id": msg_id
                }

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                try:
                    import asyncio
                    result = asyncio.run(call_tool(tool_name, tool_args))
                    resp = {"jsonrpc": "2.0", "result": result, "id": msg_id}
                except Exception as e:
                    resp = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": str(e), "data": traceback.format_exc()},
                        "id": msg_id
                    }

            else:
                resp = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": msg_id
                }

            if resp is not None:
                self._send_json(200, json.dumps(resp))
            else:
                self.send_response(202)
                self.end_headers()

        except json.JSONDecodeError:
            self._send_json(400, json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}))
        except Exception as e:
            self._send_json(500, json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}))

    def _send_json(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            self.wfile.write(body.encode())
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 10000))
    print(f"TrendRadar MCP Bridge on :{port}, endpoint: /mcp", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
