"""
TrendRadar MCP SDK Mode - 通过 stdio 协议通信
由 run.py 作为子进程启动
"""
from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport='stdio')
