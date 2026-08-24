"""Agent loop: the core processing engine.
Agent核心循环 - Agent运行主循环，消息处理流程，工具调用协调"""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from pyclaw.bus.events import InboundMessage, OutboundMessage, WebsocketMessage
from pyclaw.bus.queue import MessageBus
from pyclaw.providers.base import LLMProvider
from pyclaw.agent.context import ContextBuilder
from pyclaw.agent.tools.registry import ToolRegistry
from pyclaw.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from pyclaw.agent.tools.shell import ExecTool
from pyclaw.agent.tools.web import WebSearchTool, WebFetchTool
from pyclaw.agent.tools.message import MessageTool
from pyclaw.agent.tools.spawn import SpawnTool
from pyclaw.agent.tools.cron import CronTool
from pyclaw.agent.tools.custom import ScriptTool
from pyclaw.agent.subagent import SubagentManager
from pyclaw.session.manager import SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    name: str = "AgentLoop"

    # 默认工具名集合（_build_tool 构建，初始注册与运行时启停复用）
    DEFAULT_TOOL_NAMES = (
        "read_file", "write_file", "edit_file", "list_dir", "exec",
        "web_search", "web_fetch", "message", "spawn", "cron",
    )

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
    ):
        from pyclaw.config.schema import ExecToolConfig
        from pyclaw.cron.service import CronService
        self.bus = bus
        self.provider = provider
        # 解析为绝对路径：避免相对路径在 ExecTool 以 working_dir 为 cwd 执行时
        # 把脚本/命令的相对路径二次拼接导致路径翻倍（workspace/workspace/...）
        self.workspace = Path(workspace).expanduser().resolve()
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service

        # 运行时生效的技能 code 集合（None=全部文件技能生效；由网关 set_active_skills 设置）
        self.active_skill_codes: set[str] | None = None
        self.context = ContextBuilder(workspace, active_skill_codes=self.active_skill_codes)
        self.sessions = SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
        )
        
        self._running = False
        self._register_default_tools()

    def set_active_skills(self, codes: list[str] | None) -> None:
        """设置运行时生效的技能 code 集合（None=全部文件技能生效）.

        与 ContextBuilder 共享同一 set 引用，保证后续 prompt 构建读到最新状态。
        """
        if codes is None:
            self.active_skill_codes = None
        else:
            if self.active_skill_codes is None:
                self.active_skill_codes = set()
            self.active_skill_codes.clear()
            self.active_skill_codes.update(codes)
        self.context.active_skill_codes = self.active_skill_codes
        count = len(self.active_skill_codes) if self.active_skill_codes is not None else "all"
        logger.info(f"技能生效集合已更新: {count}")

    def _build_tool(self, name: str):
        """按名称构建工具实例（初始注册与运行时启停复用）."""
        if name == "read_file":
            return ReadFileTool(workspace=self.workspace)
        if name == "write_file":
            return WriteFileTool(workspace=self.workspace)
        if name == "edit_file":
            return EditFileTool(workspace=self.workspace)
        if name == "list_dir":
            return ListDirTool(workspace=self.workspace)
        if name == "exec":
            return ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.exec_config.restrict_to_workspace,
            )
        if name == "web_search":
            return WebSearchTool(api_key=self.brave_api_key)
        if name == "web_fetch":
            return WebFetchTool()
        if name == "message":
            return MessageTool(send_callback=self.bus.publish_outbound)
        if name == "spawn":
            return SpawnTool(manager=self.subagents)
        if name == "cron":
            return CronTool(self.cron_service) if self.cron_service else None
        return None

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        for name in self.DEFAULT_TOOL_NAMES:
            tool = self._build_tool(name)
            if tool is not None:
                self.tools.register(tool)

    def set_tool_status(self, name: str, enabled: bool) -> bool:
        """启用/禁用工具（影响运行时注册表，供网关按 tool_registry 状态调用）.

        Args:
            name: 工具名称
            enabled: True 注册工具，False 卸载工具

        Returns:
            操作是否成功
        """
        if enabled:
            tool = self._build_tool(name)
            if tool is None:
                logger.warning(f"未找到工具实现: {name}")
                return False
            self.tools.register(tool)
        else:
            self.tools.unregister(name)
            logger.info(f"工具状态变更: {name} -> disabled")
            return True
        logger.info(f"工具状态变更: {name} -> enabled")
        return True

    def sync_custom_tools(self, tool_defs: list[dict]) -> int:
        """全量对账自定义工具（tool_registry 中非内置的工具）到运行时.

        内置工具由 set_tool_status 管理启停，这里只处理不在 DEFAULT_TOOL_NAMES
        中的自定义工具。先卸载所有非内置自定义工具（清理改名/删除后残留的旧名），
        再按 status=active 用 ScriptTool 注册。

        Args:
            tool_defs: [{name, description, config, status, ...}]（get_all_tools 输出）

        Returns:
            本次启用（注册）的自定义工具数量
        """
        builtin = set(self.DEFAULT_TOOL_NAMES)
        # 1. 卸载所有非内置自定义工具（全量对账，修复改名/删除后旧名残留）
        for name in list(self.tools.tool_names):
            if name not in builtin:
                self.tools.unregister(name)
        # 2. 按 DB status 注册 active 的自定义工具
        enabled = 0
        for d in tool_defs:
            name = d.get("name")
            if not name or name in builtin:
                continue
            if d.get("status") == "active":
                self.tools.register(ScriptTool(
                    name=name,
                    description=d.get("description", ""),
                    config=d.get("config") or {},
                    workspace=self.workspace,
                    exec_config=self.exec_config,
                ))
                enabled += 1
        if enabled or tool_defs:
            logger.info(f"自定义工具同步完成: 启用 {enabled} 个")
        return enabled

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        # 按响应类型路由：WebsocketMessage → websocketbound 队列（网关推送
                        # 给对应 client_id），OutboundMessage → outbound 队列（IM 渠道）。
                        # 子代理 announce（system 消息）可能把 Web UI 结果路由回 websocket，
                        # 因此不能仅凭原始 msg.channel 判断。
                        if isinstance(response, WebsocketMessage):
                            await self.bus.publish_websocket(response)
                        else:
                            await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    if msg.channel == "GatewayServer":
                            await self.bus.publish_websocket(WebsocketMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"Sorry, I encountered an error: {str(e)}"
                        ))
                    else:
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"Sorry, I encountered an error: {str(e)}"
                        ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    def _is_privileged(self, msg: InboundMessage) -> bool:
        """判断消息来源是否具有高权限（管理员用户或内部渠道）.

        内部渠道（cli/cron/heartbeat/system）为系统触发，视为可信；
        否则仅显式标注 role=admin 的用户具备高权限。
        """
        if msg.channel in {"cli", "cron", "heartbeat", "system"}:
            return True
        return msg.metadata.get("role") == "admin"

    @staticmethod
    def _is_privileged_tool(name: str) -> bool:
        """需要高权限才能调用的工具.

        覆盖 exec（shell）、spawn（子代理自带 ExecTool，可绕过）、
        cron（定时任务内部执行，可绕过）。
        """
        return name in {"exec", "spawn", "cron"}

    async def _run_agent_loop(self, messages: list, msg: InboundMessage, fallback: str) -> str:
        """运行 LLM 工具调用循环（含工具权限门控）.

        Args:
            messages: LLM 对话消息列表（会原地扩展）
            msg: 当前入站消息（用于权限判断）
            fallback: 未产出内容时的兜底回复

        Returns:
            最终回复内容
        """
        iteration = 0
        final_content = None
        privileged = self._is_privileged(msg)

        while iteration < self.max_iterations:
            iteration += 1

            # Call LLM（wait_for 硬超时兜底，避免 provider 内部挂起导致循环永久阻塞）
            try:
                response = await asyncio.wait_for(
                    self.provider.chat(
                        messages=messages,
                        tools=self.tools.get_definitions(),
                        model=self.model
                    ),
                    timeout=getattr(self.provider, "timeout", 120),
                )
            except asyncio.TimeoutError:
                return "对不起，模型响应超时，请稍后再试。"

            # Provider 调用异常：finish_reason="error" 时 content 为原始错误串，
            # 不能把它当正常回复展示给用户，给出友好兜底并记录日志
            if getattr(response, "finish_reason", "stop") == "error":
                logger.error(f"LLM 调用失败: {response.content}")
                return "抱歉，模型调用出错了，请稍后再试。"

            # Handle tool calls
            if response.has_tool_calls:
                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # Must be JSON string
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts
                )

                # Execute tools（含权限门控）
                for tool_call in response.tool_calls:
                    if not privileged and self._is_privileged_tool(tool_call.name):
                        result = (
                            "Error: 权限不足——此工具仅限管理员或内部任务使用，"
                            "请向用户解释无法执行该操作。"
                        )
                        logger.warning(
                            f"Blocked privileged tool '{tool_call.name}' for "
                            f"channel={msg.channel} role={msg.metadata.get('role')}"
                        )
                    else:
                        args_str = json.dumps(tool_call.arguments)
                        logger.debug(f"Executing tool: {tool_call.name} with arguments: {args_str}")
                        result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # No tool calls, we're done
                final_content = response.content
                break

        if final_content is None:
            final_content = fallback

        return final_content

    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | WebsocketMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}")
        
        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            # Web UI 来源传 sender_id（client_id），子代理完成后按连接路由回结果
            spawn_tool.set_context(msg.channel, msg.chat_id, msg.sender_id)

        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)

        # Build initial messages (use get_history for LLM-formatted messages)
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            skill_names=msg.metadata.get("skill_names"),
        )

        # Agent loop（含工具权限门控）
        final_content = await self._run_agent_loop(
            messages, msg, "I've completed processing but have no response to give."
        )

        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        if msg.channel == "GatewayServer":
            return WebsocketMessage(
                channel=msg.sender_id, # 这地方把channel改为sender_id是为了区分websocket接收客户端，channel对于websocket就是不同的连接客户端
                chat_id=msg.chat_id,
                content=final_content
            )
        else:
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content
            )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
            skill_names=msg.metadata.get("skill_names"),
        )
        
        # Agent loop (limited for announce handling, 含工具权限门控)
        final_content = await self._run_agent_loop(
            messages, msg, "Background task completed."
        )

        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        # Web UI 来源：子代理结果是发回发起请求的那个 websocket 连接，
        # channel 需为 client_id（网关按连接 id 匹配推送），否则结果会走 outbound
        # 队列被网关丢弃（Unknown channel）。sender_id 已由 announce 填入 client_id。
        if origin_channel == "GatewayServer":
            return WebsocketMessage(
                channel=msg.sender_id,
                chat_id=origin_chat_id,
                content=final_content,
            )
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier.
            channel: Source channel (for context).
            chat_id: Source chat ID (for context).
        
        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""

    def get_info(self) -> dict:
        """Get information about the agent.

        Returns:
            Dictionary with agent information
        """
        info = {
            "name": self.name,
            "model": self.model,
         
        }

        return info

    def get_tools(self) -> list[dict[str, Any]]:
        return self.tools.get_definitions()

    def get_history(self, session_key: str = "cli:direct", max_messages: int = 50) -> list[dict[str, Any]]:
        """获取指定会话的对话历史（供 agent.getHistory RPC 使用）.

        Args:
            session_key: 会话标识，默认 cli:direct
            max_messages: 返回的最大消息数

        Returns:
            按 LLM 格式的消息列表（role/content）
        """
        session = self.sessions.get_or_create(session_key)
        return session.get_history(max_messages)

    def clear_history(self, session_key: str = "cli:direct") -> bool:
        """清除指定会话的对话历史（供 agent.clearHistory RPC 使用）.

        Args:
            session_key: 会话标识，默认 cli:direct

        Returns:
            是否成功
        """
        session = self.sessions.get_or_create(session_key)
        session.clear()
        self.sessions.save(session)
        return True