"""
TrendRadar HTTP → MCP 桥接服务
完全对标 wenyan-bridge 的方案
  - HTTP POST /mcp → JSON-RPC → 子进程 stdio → JSON-RPC 响应
  - GET /health → 健康检查
  - GET /api/search, /api/latest, /api/crawl, /api/trend → REST API
"""
import subprocess, json, threading, time, sys, os, re
from http.server import HTTPServer, BaseHTTPRequestHandler

proc = None  # MCP 子进程
pending = {}  # 等待响应的回调 {id: callback}
buf = ""     # stdout 缓冲区


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"trendradar-mcp"}')
            return

        # REST API 代理 - 通过 MCP 工具调用
        if self.path.startswith("/api/"):
            self._proxy_api()
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/mcp":
            self.send_response(404)
            self.end_headers()
            return

        # 读取请求体
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))

        # 确保消息有 id
        mid = body.get("id", int(time.time() * 1000))
        body["id"] = mid

        # 注册回调
        ev = threading.Event()
        res = [None]
        def cb(r):
            res[0] = r
            ev.set()
        pending[mid] = cb

        # 转发到 MCP 子进程
        proc.stdin.write((json.dumps(body) + "\n").encode())
        proc.stdin.flush()

        # 等待响应（30秒超时）
        ev.wait(30)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res[0] or {"error": "timeout"}).encode())

    def _proxy_api(self):
        """将 REST API 请求转为 MCP tools/call 请求"""
        path = self.path.split("?")[0]
        params = {}
        if "?" in self.path:
            for part in self.path.split("?", 1)[1].split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v

        # 映射路径到 MCP 工具
        tool_map = {
            "/api/crawl": ("trigger_crawl", {"platforms": params.get("platforms", "").split(",") if params.get("platforms") else None, "save_to_local": False, "include_url": False}),
            "/api/search": ("search_news", {"query": params.get("q", ""), "platforms": params.get("platforms", "").split(",") if params.get("platforms") else None, "limit": int(params.get("limit", 50)), "include_url": True}),
            "/api/latest": ("get_latest_news", {"platforms": params.get("platforms", "").split(",") if params.get("platforms") else None, "limit": int(params.get("limit", 50)), "include_url": True}),
            "/api/trend": ("analyze_topic_trend", {"topic": params.get("topic", ""), "analysis_type": params.get("type", "trend"), "granularity": params.get("granularity", "day")}),
        }

        if path not in tool_map:
            self.send_response(404)
            self.end_headers()
            return

        tool_name, args = tool_map[path]
        if path == "/api/search" and not args["query"]:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"missing q"}')
            return
        if path == "/api/trend" and not args["topic"]:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"missing topic"}')
            return

        # 构建 MCP tools/call 请求
        req = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
            "id": int(time.time() * 1000)
        }

        mid = req["id"]
        ev = threading.Event()
        res = [None]
        def cb(r):
            res[0] = r
            ev.set()
        pending[mid] = cb

        proc.stdin.write((json.dumps(req) + "\n").encode())
        proc.stdin.flush()
        ev.wait(30)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        result = res[0]
        if result and "result" in result:
            content = result["result"].get("content", [])
            # 提取文本内容
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            self.wfile.write(json.dumps({"data": texts, "raw": result["result"]}).encode())
        elif result and "error" in result:
            self.wfile.write(json.dumps({"error": result["error"]}).encode())
        else:
            self.wfile.write(json.dumps({"error": "timeout"}).encode())

    def log_message(self, format, *args):
        pass  # 安静运行


def reader():
    """后台线程：持续读取 MCP 子进程 stdout"""
    global buf
    while proc:
        d = proc.stdout.readline()
        if not d:
            break
        buf += d.decode()
        _parse()


def _parse():
    """解析 stdout 缓冲区，提取完整的 JSON-RPC 响应"""
    global buf
    while True:
        m = re.search(r'(?s)\{.*?"jsonrpc"[^}]*\}', buf)
        if not m:
            break
        try:
            obj = json.loads(m.group())
            pid = obj.get("id")
            if pid in pending:
                pending[pid](obj)
                del pending[pid]
        except json.JSONDecodeError:
            pass
        buf = buf[m.end():].lstrip()


def start_mcp():
    """启动 MCP 子进程"""
    global proc
    proc = subprocess.Popen(
        [sys.executable, "mcp_stdio.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ}
    )
    threading.Thread(target=reader, daemon=True).start()


if __name__ == "__main__":
    start_mcp()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    print(f"TrendRadar MCP Bridge on :{port}, endpoint: /mcp", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
