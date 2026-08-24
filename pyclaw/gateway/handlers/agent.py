"""Agent RPC 处理器

提供 Agent 相关的 RPC 方法处理。
处理 agent.run 等方法，AI 对话逻辑，消息生成和返回。
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

from pyclaw.gateway.rpc import GatewayException


class AgentRPCHandler:
    """Agent RPC 处理器.

    提供 Agent 相关的 RPC 方法：
    - agent.run: 将消息投递到消息总线，由 AgentLoop 异步处理后经 bus 推送结果
    - agent.getInfo: 获取 Agent 信息
    - agent.getHistory: 获取会话历史
    - agent.clearHistory: 清除会话历史
    - agent.listTools / addTool / updateTool / deleteTool: 工具管理（tool_registry 真实持久化）
    """

    def __init__(self, server, db_manager=None):
        """初始化 Agent RPC 处理器.

        Args:
            server: GatewayServer 实例（提供 agent 注册表、bus、db_manager 等）
            db_manager: 数据库管理器，默认取 server.db_manager
        """
        self.server = server
        self.db_manager = db_manager or getattr(server, "db_manager", None)

    def get_agent(self, name: str | None):
        """获取 Agent 实例（None → 默认 agent）."""
        return self.server.get_agent(name)

    # ====================================================================
    # 统一响应 envelope（add/update/delete 工具方法共用同一返回结构）
    # ====================================================================
    @staticmethod
    def _ok(message: str, **data) -> dict:
        """成功响应：{"success": True, "message": ..., **data}."""
        return {"success": True, "message": message, **data}

    @staticmethod
    def _err(message: str) -> dict:
        """失败响应：{"success": False, "message": ...}."""
        return {"success": False, "message": message}

    def _sync_tool_runtime(self, tool: dict) -> None:
        """把一个工具的启停状态同步到默认 Agent 运行时.

        内置工具走 set_tool_status（有原生实现）；自定义工具由 sync_custom_tools
        以 ScriptTool 代理注册/卸载。
        """
        agent = self.server._default_agent
        if not agent:
            return
        name = tool["name"]
        active = tool.get("status") == "active"
        if name in agent.DEFAULT_TOOL_NAMES:
            agent.set_tool_status(name, active)
        else:
            agent.sync_custom_tools([tool])

    def _resync_tool_runtime(self, tool: dict) -> None:
        """把一个工具的任何变更同步到运行时（任意字段改动立即生效）.

        内置工具按启停状态重建原生实现；自定义工具走全量对账
        （改名/删除/配置变更都能正确同步，修复旧名残留）。
        """
        agent = self.server._default_agent
        if not agent:
            return
        name = tool["name"]
        active = tool.get("status") == "active"
        if name in agent.DEFAULT_TOOL_NAMES:
            agent.set_tool_status(name, active)
        else:
            agent.sync_custom_tools(self.db_manager.get_all_tools())

    async def run(self, params: Dict[str, Any]) -> None:
        """处理 agent.run 请求.

        将消息转发到消息总线，AgentLoop 处理完经消息 bus 异步推送结果，
        此处不直接返回（与 server 原实现一致）。
        """
        agent_name = params.get("agent")
        message = params.get("message", "")
        chat_id = params.get("id")
        client_id = params.get("client_id")
        system_prompt = params.get("system")

        agent = self.get_agent(agent_name)
        if not agent:
            raise GatewayException.agent_not_found(agent_name or "default")

        # 设置系统提示词（若 agent 支持；AgentLoop 无 system_prompt 属性则忽略）
        original_system = None
        if system_prompt and hasattr(agent, "system_prompt"):
            original_system = agent.system_prompt
            agent.system_prompt = system_prompt

        try:
            user = params.get("user") or {}
            await self.server._handle_message(
                sender_id=client_id,
                chat_id=chat_id,
                content=message,
                metadata={
                    "message_id": str(uuid.uuid4()),
                    "chat_type": params.get("chat_type", "group"),
                    "msg_type": params.get("msg_type", "text"),
                    "user_id": user.get("id"),
                    "username": user.get("username", ""),
                    "role": user.get("role", "member"),
                    "timestamp": datetime.utcnow().isoformat(),
                    # 按需注入技能：agent.run 的 skills 参数 -> 对话级技能选择
                    "skill_names": params.get("skills") or None,
                },
            )
        finally:
            if original_system is not None:
                agent.system_prompt = original_system

    async def get_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取 Agent 信息.

        Returns:
            Agent 信息字典
        """
        agent = self.get_agent(params.get("agent"))
        if not agent:
            raise GatewayException.agent_not_found(params.get("agent") or "default")
        return agent.get_info()

    async def get_history(self, params: Dict[str, Any]) -> list:
        """获取会话历史.

        Returns:
            按 LLM 格式的消息列表（role/content）
        """
        agent = self.get_agent(params.get("agent"))
        if not agent:
            raise GatewayException.agent_not_found(params.get("agent") or "default")
        return agent.get_history(
            session_key=params.get("session_key", "cli:direct"),
            max_messages=params.get("limit", 50),
        )

    async def clear_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """清除会话历史.

        Returns:
            {"success": bool, "agent": str}
        """
        agent = self.get_agent(params.get("agent"))
        if not agent:
            raise GatewayException.agent_not_found(params.get("agent") or "default")
        agent.clear_history(session_key=params.get("session_key", "cli:direct"))
        return {"success": True, "agent": params.get("agent") or agent.name}

    async def list_tools(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """处理 agent.listTools 请求.

        以 tool_registry 为真实数据源，统一输出语义：
        - 每项含 builtin（内置/自定义）与 registered（当前是否注册到运行时）
        - description 一律取 DB 存值（修复"内置工具改描述被运行时覆盖"）
        - 内置工具 config 统一为 {"parameters": 运行时 schema}（未注册则回落 DB）
        - 自定义工具 config 保留 DB 完整对象（command/script/parameters）

        Returns:
            agent注册的tools列表
        """
        agent = self.get_agent(params.get("agent"))

        # 运行时已注册工具名（判断 registered 状态）
        registered_names = set()
        if agent:
            for t in agent.get_tools():
                registered_names.add(t["function"]["name"])

        full_tools = []
        for meta in self.db_manager.get_all_tools():
            name = meta["name"]
            is_builtin = bool(meta.get("builtin")) or name in (
                set(agent.DEFAULT_TOOL_NAMES) if agent else set()
            )
            config = meta["config"]
            if is_builtin:
                # 内置工具 config 统一为参数 schema 包装；优先运行时最新值
                runtime_params = None
                if agent:
                    for t in agent.get_tools():
                        if t["function"]["name"] == name:
                            runtime_params = t["function"].get("parameters")
                            break
                if runtime_params is not None:
                    config = {"parameters": runtime_params}
                else:
                    db_params = meta["config"].get("parameters", {}) if isinstance(meta["config"], dict) else {}
                    config = {"parameters": db_params}
            full_tools.append({
                "id": meta["id"],
                "name": name,
                "category": meta["category"],
                "version": meta["version"],
                "status": meta["status"],
                "description": meta["description"],
                "author": meta["author"],
                "builtin": is_builtin,
                "registered": name in registered_names,
                "config": config,
                "createTime": meta["createTime"],
                "updateTime": meta["updateTime"],
            })

        return full_tools

    async def add_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理 agent.addTool 请求（写入 tool_registry，仅管理员可调）."""
        name = (params.get("name") or "").strip()
        if not name:
            return self._err("工具名称不能为空")
        result = self.db_manager.add_tool(
            name=name,
            description=params.get("description", ""),
            category=params.get("category", "custom"),
            version=params.get("version", "1.0.0"),
            author=params.get("author", "自定义"),
            config=params.get("config") or {},
        )
        if not result["success"]:
            return self._err(result.get("message", "添加工具失败"))
        # 新增的自定义工具（active）立即注册到运行时
        self._sync_tool_runtime(result["tool"])
        return self._ok(result["message"], tool=result["tool"])

    async def update_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理 agent.updateTool 请求.

        更新 tool_registry；内置工具仅允许改 description/status，其余字段拒绝；
        成功后**无条件**同步运行时（改 name/description/config 也立即生效，
        不再仅 status 触发）。
        """
        tool_id = params.get("id")
        if tool_id is None:
            return self._err("工具ID不能为空")
        updates = {}
        for k in ("name", "description", "category", "version", "status", "author", "config"):
            if k in params:
                updates[k] = params[k]
        if not updates:
            return self._err("没有需要更新的字段")

        # 内置工具保护：仅放行 description/status
        existing = self.db_manager.get_tool_by_id(tool_id)
        if existing:
            agent = self.server._default_agent
            is_builtin = bool(existing.get("builtin")) or existing["name"] in (
                set(agent.DEFAULT_TOOL_NAMES) if agent else set()
            )
            if is_builtin:
                forbidden = [k for k in updates if k not in ("description", "status")]
                if forbidden:
                    return self._err(f"内置工具不可修改字段: {', '.join(forbidden)}")

        result = self.db_manager.update_tool(tool_id, **updates)
        if not result["success"]:
            return self._err(result.get("message", "更新工具失败"))
        # 任意字段变更都同步运行时（自定义工具全量对账，处理改名/删除残留）
        self._resync_tool_runtime(result["tool"])
        return self._ok(result["message"], tool=result["tool"])

    async def delete_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理 agent.deleteTool 请求（仅管理员可调；内置工具不可删除）."""
        tool_id = params.get("id")
        if tool_id is None:
            return self._err("工具ID不能为空")
        existing = self.db_manager.get_tool_by_id(tool_id)
        if existing and existing.get("builtin"):
            return self._err("内置工具不可删除")
        result = self.db_manager.delete_tool(tool_id)
        if not result["success"]:
            return self._err(result.get("message", "删除工具失败"))
        # 全量重同步：把已注册的同名自定义工具从运行时卸载（含改名残留清理）
        try:
            if self.server._default_agent:
                self.server._default_agent.sync_custom_tools(self.db_manager.get_all_tools())
        except Exception as e:
            logger.error(f"删除工具后同步运行时失败: {e}")
        return self._ok(result["message"])

    async def test_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """试运行工具（不改变运行时注册状态）.

        Args:
            params: {"id": int, "args": {...}}

        Returns:
            {"success": bool, "output": str, "duration_ms": int}
        """
        import time

        tool_id = params.get("id")
        if tool_id is None:
            return self._err("工具ID不能为空")
        args = params.get("args") or {}
        if not isinstance(args, dict):
            return self._err("args 必须是 JSON 对象")

        meta = self.db_manager.get_tool_by_id(tool_id)
        if not meta:
            return self._err("工具未找到")

        agent = self.server._default_agent
        start = time.time()
        try:
            builtin_names = set(agent.DEFAULT_TOOL_NAMES) if agent else set()
            if bool(meta.get("builtin")) or meta["name"] in builtin_names:
                # 内置工具：走运行时注册表（须已注册）
                if not agent or not agent.tools.has(meta["name"]):
                    return self._err(f"内置工具 '{meta['name']}' 未注册（可能已禁用）")
                output = await agent.tools.execute(meta["name"], args)
            else:
                # 自定义工具：用 DB config 临时构造 ScriptTool 直接执行（不注册、不污染运行时）
                from pyclaw.agent.tools.custom import ScriptTool

                tool = ScriptTool(
                    name=meta["name"],
                    description=meta.get("description", ""),
                    config=meta.get("config") or {},
                    workspace=agent.workspace if agent else None,
                    exec_config=agent.exec_config if agent else None,
                )
                errors = tool.validate_params(args)
                if errors:
                    output = "Error: 参数校验失败: " + "; ".join(errors)
                else:
                    output = await tool.execute(**args)
            duration_ms = int((time.time() - start) * 1000)
            success = not output.startswith("Error")
            return {
                "success": success,
                "output": output[:10000],
                "duration_ms": duration_ms,
            }
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return {"success": False, "output": f"Error: {str(e)}", "duration_ms": duration_ms}
