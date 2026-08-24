"""Gateway WebSocket 服务器

提供 WebSocket RPC 服务器，支持远程控制 Agent 和 Web UI 连接。
监听WebSocket连接，处理RPC请求，管理客户端连接，注册RPC方法路由
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Set, Callable, Any, List

from pydantic import BaseModel, Field

try:
    import websockets.server as ws_server
    from websockets.exceptions import ConnectionClosed
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    ws_server = None
    ConnectionClosed = Exception

from pyclaw.gateway.rpc import (
    GatewayRequest, GatewayResponse, GatewayNotification, GatewayError, GatewayErrorCode,
    GatewayException,
)
from pyclaw.agent.loop import AgentLoop
from pyclaw.config.schema import Config
from pyclaw.auth.service import AuthService, AuthError
from pyclaw.database.database import DatabaseManager
from loguru import logger
from pyclaw.bus.events import InboundMessage, OutboundMessage
from pyclaw.bus.queue import MessageBus


class GatewayConfig(BaseModel):
    """Gateway 服务器配置.

    Attributes:
        host: 监听主机地址
        port: 监听端口
        ping_interval: WebSocket ping 间隔（秒）
        ping_timeout: WebSocket ping 超时（秒）
        max_connections: 最大并发连接数
        debug_mode: 是否启用调试模式
    """

    host: str = Field(
        default="0.0.0.0",
        description="监听主机地址"
    )
    port: int = Field(
        default=18790,
        ge=1,
        le=65535,
        description="监听端口"
    )
    ping_interval: int = Field(
        default=20,
        ge=1,
        description="WebSocket ping 间隔（秒）"
    )
    ping_timeout: int = Field(
        default=20,
        ge=1,
        description="WebSocket ping 超时（秒）"
    )
    max_connections: int = Field(
        default=10,
        ge=1,
        le=100,
        description="最大并发连接数"
    )
    debug_mode: bool = Field(
        default=True,
        description="是否启用调试模式"
    )


@dataclass
class ClientConnection:
    """客户端连接信息.

    Attributes:
        id: 客户端 ID
        websocket: WebSocket 连接对象
        remote_address: 远程地址
        connected_at: 连接时间戳
    """
    id: str
    websocket: Any
    remote_address: str
    connected_at: float


class GatewayServer:
    """Gateway WebSocket RPC 服务器.

    提供 WebSocket RPC 接口，支持：
    1. 远程调用 Agent 方法
    2. 实时接收 Agent 消息
    3. 查询系统状态

    使用示例:
        >>> from pyclaw.gateway import GatewayServer
        >>> from pyclaw.config.schema import Config
        >>>
        >>> config = Config()
        >>> server = GatewayServer(config=config)
        >>> await server.start()
        >>> # 服务器运行在 ws://localhost:8765
    """
    name: str = "GatewayServer"

    # 无需 token 即可调用的方法（登录等）
    AUTH_EXEMPT_METHODS: set[str] = {"system.login"}

    # 仅管理员可调用的管理类方法
    ADMIN_ONLY_METHODS: set[str] = {
        "system.getConfig",
        "agent.addTool",
        "agent.updateTool",
        "agent.deleteTool",
        "agent.testTool",
        "system.listSkills",
        "system.addSkill",
        "system.updateSkill",
        "system.deleteSkill",
        "system.getSkillContent",
        "system.syncSkills",
        "system.generateSkill",
        "system.generateTool",
        "system.listSensitiveRules",
        "system.addSensitiveRule",
        "system.updateSensitiveRule",
        "system.deleteSensitiveRule",
        "system.listUsers",
        "system.updateUserRole",
    }

    def __init__(
        self,
        bus: MessageBus,
        config: Optional[Config] = None,
        gateway_config: Optional[GatewayConfig] = None
    ):
        """初始化 Gateway 服务器.

        Args:
            config: PyClaw 全局配置
            gateway_config: Gateway 服务器配置

        Raises:
            ImportError: 如果 websockets 库未安装
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets library is required for Gateway. "
                "Install it with: pip install websockets"
            )

        self.bus = bus
        self.config = config or Config()
        self.gateway_config = gateway_config or GatewayConfig()

        # Agent 管理
        self._agents: Dict[str, AgentLoop] = {}
        self._default_agent: Optional[AgentLoop] = None

        # 连接管理
        self._connections: Dict[str, ClientConnection] = {}
        self._server: Optional[Any] = None
        self._running = False

        # RPC 方法注册
        self._rpc_methods: Dict[str, Callable] = {}

        # 初始化共享数据库与认证服务
        self.db_manager = DatabaseManager()
        self.auth_service = AuthService(self.db_manager, self.config.auth)
        if self.config.auth.enabled and self.config.auth.seed_admin:
            self.auth_service.ensure_admin()

        # 同步内置工具元数据与 workspace 技能到 DB（幂等，seed 保留用户的启停状态）
        self._seed_tools()
        self._sync_workspace_skills()

        # 初始化 RPC 处理器（注入共享 db_manager）
        from pyclaw.gateway.handlers.agent import AgentRPCHandler
        from pyclaw.gateway.handlers.system import SystemRPCHandler
        self.agent_handler = AgentRPCHandler(self, db_manager=self.db_manager)
        self.system_handler = SystemRPCHandler(self, db_manager=self.db_manager)

        # 注册内置 RPC 方法
        self._register_builtin_methods()

        self._dispatch_task: asyncio.Task | None = None

    def _seed_tools(self) -> None:
        """启动时把内置工具元数据同步进 tool_registry（保留 DB 中的启停状态）."""
        try:
            from pyclaw.agent.tools.seed import builtin_tool_metadata
            self.db_manager.seed_builtin_tools(builtin_tool_metadata())
        except Exception as e:
            logger.error(f"内置工具 seed 失败: {e}")

    def _sync_workspace_skills(self) -> dict:
        """把 workspace/builtin 技能文件同步进 DB（文件→DB，保留 status）.

        Returns:
            {"created": int, "updated": int}
        """
        result = {"created": 0, "updated": 0}
        try:
            from pyclaw.agent.skills import SkillsLoader
            loader = SkillsLoader(self.config.workspace_path)
            for s in loader.list_skills(filter_unavailable=False):
                mtime = None
                try:
                    mtime = datetime.fromtimestamp(Path(s["path"]).stat().st_mtime)
                except Exception:
                    pass
                # 按来源区分 category：workspace 技能 / 内置技能
                category = "workspace" if s["source"] == "workspace" else "builtin"
                res = self.db_manager.upsert_skill(
                    name=s["name"],
                    code=s["name"],
                    description=loader.get_skill_description(s["name"]),
                    category=category,
                    updated_at=mtime,
                )
                if res.get("success"):
                    result["created" if res.get("created") else "updated"] += 1
            logger.info(f"技能文件已同步到 DB: {result}")
        except Exception as e:
            logger.error(f"同步技能文件失败: {e}")
        return result

    def _sync_skill_runtime(self) -> None:
        """把 DB 中 active 的技能 code 同步到默认 Agent 运行时（技能启停/删除后调用）."""
        if not self._default_agent:
            return
        try:
            active = [s["code"] for s in self.db_manager.get_all_skills() if s["status"] == "active"]
            self._default_agent.set_active_skills(active)
        except Exception as e:
            logger.error(f"同步技能启停状态失败: {e}")


    def _register_builtin_methods(self):
        """注册内置 RPC 方法."""
        # Agent 方法
        self.register_rpc_method("agent.run", self.agent_handler.run)
        self.register_rpc_method("agent.getInfo", self.agent_handler.get_info)
        self.register_rpc_method("agent.getHistory", self.agent_handler.get_history)
        self.register_rpc_method("agent.clearHistory", self.agent_handler.clear_history)
        self.register_rpc_method("agent.listTools", self.agent_handler.list_tools)
        self.register_rpc_method("agent.addTool", self.agent_handler.add_tool)
        self.register_rpc_method("agent.updateTool", self.agent_handler.update_tool)
        self.register_rpc_method("agent.deleteTool", self.agent_handler.delete_tool)
        self.register_rpc_method("agent.testTool", self.agent_handler.test_tool)

        # 认证方法
        self.register_rpc_method("system.login", self.auth_service.handle_login)
        self.register_rpc_method("system.logout", self.auth_service.handle_logout)
        self.register_rpc_method("system.listUsers", self.auth_service.handle_list_users)
        self.register_rpc_method("system.updateUserRole", self.auth_service.handle_update_user_role)

        # System 方法
        self.register_rpc_method("system.status", self.system_handler.get_status)
        self.register_rpc_method("system.listAgents", self.system_handler.list_agents)
        self.register_rpc_method("system.getConfig", self.system_handler.get_config)
        self.register_rpc_method("system.listSkills", self.system_handler.list_skills)
        self.register_rpc_method("system.addSkill", self.system_handler.add_skill)
        self.register_rpc_method("system.updateSkill", self.system_handler.update_skill)
        self.register_rpc_method("system.deleteSkill", self.system_handler.delete_skill)
        self.register_rpc_method("system.getSkillContent", self.system_handler.get_skill_content)
        self.register_rpc_method("system.syncSkills", self.system_handler.sync_skills)
        self.register_rpc_method("system.generateSkill", self.system_handler.generate_skill)
        self.register_rpc_method("system.generateTool", self.system_handler.generate_tool)
        self.register_rpc_method("system.addMessage", self.system_handler.add_message)
        self.register_rpc_method("system.listMessages", self.system_handler.list_messages)
        self.register_rpc_method("system.clearMessages", self.system_handler.clear_messages)
        self.register_rpc_method("system.listSensitiveRules", self.system_handler.list_sensitive_rules)
        self.register_rpc_method("system.addSensitiveRule", self.system_handler.add_sensitive_rule)
        self.register_rpc_method("system.updateSensitiveRule", self.system_handler.update_sensitive_rule)
        self.register_rpc_method("system.deleteSensitiveRule", self.system_handler.delete_sensitive_rule)
        self.register_rpc_method("system.filterMessageContent", self.system_handler.filter_message_content)

    def register_rpc_method(self, method: str, handler: Callable):
        """注册 RPC 方法处理器.

        Args:
            method: 方法名（如 "agent.run"）
            handler: 处理函数，签名为 async def handler(params: dict) -> Any
        """
        self._rpc_methods[method] = handler
        if self.gateway_config.debug_mode:
            logger.debug(f"Registered RPC method: {method}")

    def register_agent(self, name: str, agent: AgentLoop, set_default: bool = False):
        """注册 Agent 到 Gateway.

        Args:
            name: Agent 名称
            agent: AgentLoop 实例
            set_default: 是否设置为默认 Agent
        """
        self._agents[name] = agent
        if set_default or self._default_agent is None:
            self._default_agent = agent

        # 按 tool_registry 状态过滤：inactive 的内置工具从运行时卸载
        try:
            inactive = self.db_manager.get_inactive_tool_names()
            for tool_name in inactive:
                agent.set_tool_status(tool_name, False)
            if inactive:
                logger.info(f"已按 tool_registry 状态禁用内置工具: {sorted(inactive)}")
        except Exception as e:
            logger.error(f"应用工具启停状态失败: {e}")

        # 同步自定义工具（tool_registry 中非内置工具 -> ScriptTool 代理）到运行时
        try:
            agent.sync_custom_tools(self.db_manager.get_all_tools())
        except Exception as e:
            logger.error(f"同步自定义工具到运行时失败: {e}")

        # 按 skills 表 status 设置运行时生效技能集合（启停生效：inactive 技能不进 LLM 上下文）
        try:
            active = [s["code"] for s in self.db_manager.get_all_skills() if s["status"] == "active"]
            agent.set_active_skills(active)
        except Exception as e:
            logger.error(f"同步技能启停状态失败: {e}")

        if self.gateway_config.debug_mode:
            logger.debug(f"Registered agent: {name}")

    def get_agent(self, name: Optional[str] = None) -> Optional[AgentLoop]:
        """获取 Agent.

        Args:
            name: Agent 名称（None 表示默认 Agent）

        Returns:
            AgentLoop 实例，如果未找到返回 None
        """
        if name is None:
            return self._default_agent

        return self._agents.get(name)

    async def _dispatch_websocket(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")
        
        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_websocket(),
                    timeout=1.0
                )

                # 发送消息给web端
                disconnected = []
                for client_id, conn in self._connections.items():
                    if client_id == msg.channel:
                        try:
                            # 用 json.dumps 正确序列化，避免多行/引号/控制字符生成非法 JSON
                            await conn.websocket.send(json.dumps(
                                {"jsonrpc": "2.0", "id": "1001", "result": msg.content or ""},
                                ensure_ascii=False,
                            ))
                        except Exception:
                            disconnected.append(client_id)
                for client_id in disconnected:
                    del self._connections[client_id]

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def start(self):
        """启动 Gateway 服务器.

        Raises:
            RuntimeError: 如果服务器已经在运行
        """
        if self._running:
            raise RuntimeError("Gateway server is already running")

        self._running = True

        if self.gateway_config.debug_mode:
            logger.info(f"Starting Gateway server on {self.gateway_config.host}:{self.gateway_config.port}")

        # 创建 WebSocket 服务器
        self._server = await ws_server.serve(
            self._handle_websocket,
            self.gateway_config.host,
            self.gateway_config.port,
            ping_interval=self.gateway_config.ping_interval,
            ping_timeout=self.gateway_config.ping_timeout,
        )
        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_websocket())

        logger.info(f"Gateway server started on ws://{self.gateway_config.host}:{self.gateway_config.port}")

    async def stop(self):
        """停止 Gateway 服务器."""
        if not self._running:
            return

        self._running = False

        # 关闭所有连接
        for conn in list(self._connections.values()):
            try:
                await conn.websocket.close()
            except Exception:
                pass

        self._connections.clear()
        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # 关闭服务器
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("Gateway server stopped")

    async def _handle_websocket(self, websocket: Any, path: str):
        """处理 WebSocket 连接.

        Args:
            websocket: WebSocket 连接对象
            path: 请求路径
        """
        # 检查连接数限制
        if len(self._connections) >= self.gateway_config.max_connections:
            await websocket.close(1013, "Server full")
            return

        # 获取远程地址
        remote_addr = websocket.remote_address if hasattr(websocket, 'remote_address') else "unknown"
        client_id = f"client_{id(websocket)}"

        # 创建连接信息
        import time
        connection = ClientConnection(
            id=client_id,
            websocket=websocket,
            remote_address=remote_addr,
            connected_at=time.time()
        )

        self._connections[client_id] = connection

        if self.gateway_config.debug_mode:
            logger.info(f"Client connected: {client_id} from {remote_addr}")

        try:
            # 处理消息循环
            async for message in websocket:
                try:
                    response = await self._process_message(client_id, message)
                    if response:
                        await websocket.send(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    error_response = GatewayResponse.make_error(
                        "unknown",
                        GatewayError.internal_error(str(e))
                    )
                    await websocket.send(error_response.to_json())

        except ConnectionClosed:
            if self.gateway_config.debug_mode:
                logger.info(f"Client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if client_id in self._connections:
                del self._connections[client_id]

    async def _process_message(self, client_id: str, message: str) -> Optional[str]:
        """处理客户端消息.

        Args:
            client_id: 客户端 ID
            message: 消息内容（JSON 字符串）

        Returns:
            响应 JSON 字符串（如果需要响应）
        """
        try:
            # 解析请求
            request = GatewayRequest.from_json(message)

            if self.gateway_config.debug_mode:
                logger.debug(f"[{client_id}] Request: {request.method}")

            # 路由到对应的处理器
            handler = self._rpc_methods.get(request.method)
            if not handler:
                error = GatewayError.method_not_found(request.method)
                return GatewayResponse.make_error(request.id, error).to_json()

            # 调用处理器
            try:
                request.params['client_id'] = client_id
                # 集中鉴权（校验 token、注入 params['user']、管理员方法校验）
                auth_result = self._authorize(request)
                if auth_result is not None:
                    return auth_result

                result = await handler(request.params)
                # 这个处理器不会立即返回结果，需要等待agent执行返回真正结果
                response = GatewayResponse.success(request.id, result)
            except GatewayException as e:
                response = GatewayResponse.make_error(request.id, e.to_error())
            except AuthError as e:
                response = GatewayResponse.make_error(request.id, e.error)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                error = GatewayError.internal_error(str(e))
                response = GatewayResponse.make_error(request.id, error)
            return response.to_json()

        except ValueError as e:
            # JSON 解析或验证错误
            logger.error(f"Invalid message: {e}")
            error = GatewayError(
                code=GatewayErrorCode.PARSE_ERROR,
                message=str(e)
            )
            return GatewayResponse.make_error("unknown", error).to_json()

    def _authorize(self, request: GatewayRequest) -> Optional[str]:
        """集中鉴权：校验 token 并注入 params['user'].

        Args:
            request: 已解析的 RPC 请求

        Returns:
            需要直接返回的错误响应 JSON 字符串；放行返回 None。
        """
        method = request.method
        params = request.params

        # 鉴权关闭：注入系统管理员角色，保持老部署可用
        if not self.config.auth.enabled:
            params['user'] = {"id": 0, "username": "system", "role": "admin", "display_name": "系统"}
            return None

        # 登录等豁免方法
        if method in self.AUTH_EXEMPT_METHODS:
            return None

        token = params.get("token")
        if not token:
            return GatewayResponse.make_error(
                request.id, GatewayError.auth_required("请先登录")
            ).to_json()

        user = self.auth_service.authenticate(token)
        if not user:
            return GatewayResponse.make_error(
                request.id, GatewayError.auth_invalid("Token 无效或已过期")
            ).to_json()

        params['user'] = user

        # 管理类方法仅管理员可调用
        if method in self.ADMIN_ONLY_METHODS and user.get("role") != "admin":
            return GatewayResponse.make_error(
                request.id, GatewayError.auth_forbidden("权限不足：该操作仅限管理员")
            ).to_json()

        return None

    async def broadcast_notification(self, notification: GatewayNotification):
        """向所有连接的客户端广播通知.

        Args:
            notification: 通知对象
        """
        message = notification.to_json()
        disconnected = []

        for client_id, conn in self._connections.items():
            try:
                await conn.websocket.send(message)
            except Exception:
                disconnected.append(client_id)

        # 清理断开的连接
        for client_id in disconnected:
            del self._connections[client_id]

    async def send_to_client(self, client_id: str, notification: GatewayNotification):
        """向特定客户端发送通知.

        Args:
            client_id: 客户端 ID
            notification: 通知对象
        """
        if client_id not in self._connections:
            logger.warning(f"Client not found: {client_id}")
            return

        try:
            await self._connections[client_id].websocket.send(notification.to_json())
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")

    # ========================================================================
    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to use this bot.
        
        Args:
            sender_id: The sender's identifier.
        
        Returns:
            True if allowed, False otherwise.
        """
        allow_list = getattr(self.config, "allow_from", [])
        
        # If no allow list, allow everyone
        if not allow_list:
            return True
        
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True
        return False
    
    
    # ========================================================================
    # Bus 消息处理器
    # ========================================================================
    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Handle an incoming message from the chat platform.
        
        This method checks permissions and forwards to the bus.
        
        Args:
            sender_id: The sender's identifier.
            chat_id: The chat/channel identifier.
            content: Message text content.
            media: Optional list of media URLs.
            metadata: Optional channel-specific metadata.
        """
        if not self.is_allowed(sender_id):
            return
        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {}
        )
        
        await self.bus.publish_inbound(msg)
    
    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._running

    # ========================================================================
    # 便捷方法
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """获取服务器状态（同步）.

        Returns:
            状态字典
        """
        return {
            "running": self._running,
            "host": self.gateway_config.host,
            "port": self.gateway_config.port,
            "connections": len(self._connections),
            "agents": list(self._agents.keys()),
        }

    @property
    def is_running(self) -> bool:
        """检查服务器是否在运行."""
        return self._running
