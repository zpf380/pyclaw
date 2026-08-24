"""PyClaw Gateway 模块

提供 WebSocket RPC 服务器，支持远程控制和 Web UI 连接。

本模块实现了 Gateway 服务器，允许：
1. 远程控制 Agent 运行
2. 实时消息推送
3. Web UI 连接
4. 系统状态查询

示例:
    >>> from pyclaw.gateway import GatewayServer
    >>> server = GatewayServer(host="localhost", port=8765)
    >>> await server.start()
"""

from pyclaw.gateway.server import GatewayServer, GatewayConfig
from pyclaw.gateway.rpc import (
    GatewayRequest,
    GatewayResponse,
    GatewayError,
    GatewayException,
    GatewayErrorCode,
    GatewayNotification,
)
from pyclaw.gateway.handlers.agent import AgentRPCHandler
from pyclaw.gateway.handlers.system import SystemRPCHandler

__all__ = [
    "GatewayServer",
    "GatewayConfig",
    "GatewayRequest",
    "GatewayResponse",
    "GatewayError",
    "GatewayException",
    "GatewayErrorCode",
    "GatewayNotification",
    "AgentRPCHandler",
    "SystemRPCHandler",
]