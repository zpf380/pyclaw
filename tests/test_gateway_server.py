# -*- coding: utf-8 -*-
"""GatewayServer 集成测试（进程内启动真实 WebSocket 服务器 + 假 Agent，不调用 LLM）."""
import asyncio
import json

import pytest
import websockets

from pyclaw.bus.queue import MessageBus
from pyclaw.config.schema import Config
from pyclaw.database.database import DatabaseManager


class FakeAgent:
    """不调用 LLM 的最小 Agent 替身，满足 GatewayServer 需要的接口."""

    name = "FakeAgent"
    DEFAULT_TOOL_NAMES = ("read_file", "exec")

    def __init__(self):
        self.workspace = None
        self.exec_config = None

    def get_info(self):
        return {"name": self.name, "model": "fake-model"}

    def get_tools(self):
        return [
            {"type": "function", "function": {"name": "read_file", "description": "read", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "exec", "description": "exec", "parameters": {"type": "object", "properties": {}}}},
        ]

    def get_history(self, session_key="cli:direct", max_messages=50):
        return []

    def clear_history(self, session_key="cli:direct"):
        return True

    def set_tool_status(self, name, enabled):
        return True

    def sync_custom_tools(self, tool_defs):
        return 0

    def set_active_skills(self, codes):
        pass


@pytest.fixture()
async def server(tmp_path):
    """在临时端口上启动 GatewayServer（临时 DB + 假 Agent），返回 (server, port)."""
    import pyclaw.gateway.server as server_module
    from pyclaw.gateway.server import GatewayServer, GatewayConfig

    # 临时数据库
    db_path = tmp_path / "gw.db"
    db = DatabaseManager(f"sqlite:///{db_path}")
    server_module.DatabaseManager = lambda: db  # 注入临时 DB，避免写项目 pyclaw.db

    # 临时 workspace
    ws = tmp_path / "ws"
    (ws / "skills").mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.agents.defaults.workspace = str(ws)

    # GatewayConfig 要求 port >= 1，先探测一个空闲端口
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()

    gw = GatewayServer(
        bus=MessageBus(),
        config=cfg,
        gateway_config=GatewayConfig(host="127.0.0.1", port=free_port),
    )
    fake = FakeAgent()
    gw.register_agent("FakeAgent", fake, set_default=True)
    await gw.start()
    yield gw, free_port
    await gw.stop()


async def _rpc(ws, method, params, req_id, timeout=10):
    await ws.send(json.dumps({"id": req_id, "jsonrpc": "2.0", "method": method, "params": params}))
    while True:
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if resp.get("id") == req_id:
            return resp


async def _login(ws):
    resp = await _rpc(ws, "system.login", {"username": "admin", "password": "admin123"}, "login")
    assert resp.get("error") is None, resp
    return resp["result"]["token"]


@pytest.mark.asyncio
async def test_full_rpc_flow(server):
    gw, port = server
    uri = f"ws://127.0.0.1:{port}"
    async with websockets.connect(uri) as ws:
        token = await _login(ws)
        assert token
        AUTH = {"token": token}

        # 无 token 被拒绝
        resp = await _rpc(ws, "system.status", {}, "r1")
        assert resp["error"]["code"] == -32005

        # 系统状态
        resp = await _rpc(ws, "system.status", AUTH, "r2")
        assert resp["result"]["server"]["running"] is True

        # agent 信息
        resp = await _rpc(ws, "agent.getInfo", {**AUTH, "agent": "FakeAgent"}, "r3")
        assert resp["result"]["name"] == "FakeAgent"

        # agent 工具列表（内置 seed 工具 + 假 agent 的运行时工具）
        resp = await _rpc(ws, "agent.listTools", {**AUTH, "agent": "FakeAgent"}, "r4")
        tools = resp["result"]
        assert isinstance(tools, list)
        names = {t["name"] for t in tools}
        assert "read_file" in names  # 内置工具已 seed 进 DB

        # 技能列表
        resp = await _rpc(ws, "system.listSkills", AUTH, "r5")
        assert isinstance(resp["result"], list)

        # 非管理员方法放行（member 角色无管理权限测试）
        resp = await _rpc(ws, "system.listAgents", AUTH, "r6")
        assert isinstance(resp["result"], list)

        # 登出后 token 失效
        resp = await _rpc(ws, "system.logout", AUTH, "r7")
        assert resp["result"]["success"] is True
        resp = await _rpc(ws, "system.status", AUTH, "r8")
        assert resp["error"]["code"] == -32006


@pytest.mark.asyncio
async def test_admin_only_methods_require_admin(server):
    """管理员专属方法对非管理员用户应返回 AUTH_FORBIDDEN."""
    gw, port = server
    uri = f"ws://127.0.0.1:{port}"

    # 先创建一个普通用户
    db = gw.db_manager
    from pyclaw.auth.service import hash_password, hash_token
    from datetime import datetime, timedelta

    salt, pw_hash = hash_password("member123")
    db.create_user("member", pw_hash, salt, role="member")
    member_id = db.get_user_by_username("member")["id"]

    async with websockets.connect(uri) as ws:
        resp = await _rpc(ws, "system.login", {"username": "member", "password": "member123"}, "m1")
        token = resp["result"]["token"]

        # 调用管理方法应被拒
        resp = await _rpc(ws, "system.listSkills", {"token": token}, "m2")
        assert resp["error"]["code"] == -32007  # AUTH_FORBIDDEN

        # 普通方法放行（成功响应不含 error 键）
        resp = await _rpc(ws, "system.status", {"token": token}, "m3")
        assert resp.get("error") is None
        assert resp["result"]["server"]["running"] is True
