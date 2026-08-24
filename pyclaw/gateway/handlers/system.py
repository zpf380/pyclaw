"""System RPC 处理器

提供系统相关的 RPC 方法处理。
系统状态查询、技能管理、消息管理、敏感词过滤、敏感词规则CRUD
"""
import asyncio
import logging
import os
import platform
import json
import re
from typing import Dict, Any, TYPE_CHECKING
from pathlib import Path
import sys

from pyclaw.agent.skills import SkillsLoader

if TYPE_CHECKING:
    from pyclaw.gateway.server import GatewayServer


logger = logging.getLogger("pyclaw.gateway")


class SystemRPCHandler:
    """System RPC 处理器.

    提供系统相关的 RPC 方法，如：
    - system.status: 获取系统状态
    - system.listAgents: 列出所有 Agent
    - system.getConfig: 获取配置
    - system.listSkills: 列出所有技能
    - system.addSkill: 添加技能
    - system.updateSkill: 更新技能
    - system.deleteSkill: 删除技能
    - system.listMessages: 列出消息
    - system.clearMessages: 清空消息
    """

    def __init__(self, server: "GatewayServer", db_manager=None):
        """初始化 System RPC 处理器.

        Args:
            server: GatewayServer 实例
            db_manager: 共享的 DatabaseManager 实例（由 Gateway 注入，避免多实例）
        """
        self.server = server

        # 使用注入的数据库管理器；未注入时自建
        self.db_manager = db_manager
        if self.db_manager is None:
            try:
                from pyclaw.database.database import DatabaseManager
                self.db_manager = DatabaseManager()
                logger.info("数据库管理器初始化成功")
            except ImportError as e:
                logger.error(f"导入数据库管理器失败: {e}")
                self.db_manager = None

    async def get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取系统状态.

        Args:
            params: 空字典

        Returns:
            系统状态字典
        """
        return {
            "server": {
                "running": self.server.is_running,
                "host": self.server.gateway_config.host,
                "port": self.server.gateway_config.port,
                "connections": len(self.server._connections),
            },
            "system": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "hostname": platform.node(),
            },
            "process": {
                "pid": os.getpid(),
                "threads": asyncio.get_event_loop()._num_tasks if hasattr(asyncio.get_event_loop(), '_num_tasks') else 0,
            }
        }

    async def list_agents(self, params: Dict[str, Any]) -> list:
        """列出所有 Agent.

        Args:
            params: 空字典

        Returns:
            Agent 信息列表
        """
        agents = []
        for name, agent in self.server._agents.items():
            info = agent.get_info()
            info["name"] = name
            agents.append(info)
        return agents

    async def get_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取配置.

        Args:
            params: 空字典

        Returns:
            配置字典
        """
        return self.server.config.model_dump()

    async def get_connections(self, params: Dict[str, Any]) -> list:
        """获取当前连接的客户端列表.

        Args:
            params: 空字典

        Returns:
            客户端连接信息列表
        """
        connections = []
        for client_id, conn in self.server._connections.items():
            connections.append({
                "id": client_id,
                "remote_address": conn.remote_address,
                "connected_at": conn.connected_at,
            })
        return connections

    async def list_skills(self, params: Dict[str, Any]) -> list:
        """列出所有技能.

        Args:
            params: 空字典

        Returns:
            技能信息列表
        """
        if not self.db_manager:
            logger.error("数据库管理器未初始化")
            return []
        
        try:
            skills = self.db_manager.get_all_skills()
            logger.info(f"成功加载 {len(skills)} 个技能")
            return skills
        except Exception as e:
            logger.error(f"加载技能列表失败: {e}")
            return []

    async def add_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加技能.

        Args:
            params: {
                "name": str,          # 技能名称
                "code": str,          # 技能编码
                "description": str    # 技能描述
            }

        Returns:
            {"success": bool, "skill": dict}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            name = params.get("name", "").strip()
            code = params.get("code", "").strip()
            description = params.get("description", "").strip()
            content = params.get("content")

            if not name or not code:
                return {"success": False, "message": "技能名称和编码不能为空"}

            # 创建 workspace 技能文件（SKILL.md 文件是正文真相源）
            loader = SkillsLoader(self.server.config.workspace_path)
            try:
                loader.write_skill(code, name, description, content or "")
            except ValueError as e:
                return {"success": False, "message": str(e)}
            except Exception as e:
                return {"success": False, "message": f"创建技能文件失败: {str(e)}"}

            # 添加技能元数据到数据库
            result = self.db_manager.add_skill(name, code, description)

            if result["success"]:
                return {
                    "success": True,
                    "skill": result["skill"],
                    "message": result["message"]
                }
            else:
                # 回滚刚创建的文件，避免 DB 失败时残留孤儿目录
                try:
                    loader.delete_skill_file(code)
                except Exception:
                    pass
                return {
                    "success": False,
                    "message": result["message"]
                }

        except Exception as e:
            logger.error(f"添加技能失败: {e}")
            return {"success": False, "message": f"添加技能失败: {str(e)}"}

    async def update_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """更新技能.

        Args:
            params: {
                "id": int,            # 技能ID
                "name": str,          # 技能名称
                "description": str,   # 技能描述
                "status": str         # 技能状态
            }

        Returns:
            {"success": bool, "skill": dict}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            skill_id = params.get("id")
            if skill_id is None:
                return {"success": False, "message": "技能ID不能为空"}
            
            # 构建更新字段
            updates = {}
            if 'name' in params:
                updates['name'] = params['name']
            if 'description' in params:
                updates['description'] = params['description']
            if 'status' in params:
                updates['status'] = params['status']

            if not updates and params.get("content") is None:
                return {"success": False, "message": "没有需要更新的字段"}

            # 更新技能信息
            result = self.db_manager.update_skill(skill_id, **updates)

            if result["success"]:
                skill = result["skill"]
                # content 落盘到 workspace 文件（正文真相源，DB 只存元数据快照）
                if params.get("content") is not None:
                    loader = SkillsLoader(self.server.config.workspace_path)
                    try:
                        loader.write_skill(
                            skill["code"], skill["name"], skill["description"], params.get("content")
                        )
                    except ValueError as e:
                        return {"success": False, "message": str(e)}
                # 启停变更时重算运行时生效技能集合（inactive 技能不进 LLM 上下文）
                if "status" in updates:
                    try:
                        self.server._sync_skill_runtime()
                    except Exception as e:
                        logger.error(f"同步技能启停状态失败: {e}")
                return {
                    "success": True,
                    "skill": result["skill"],
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result["message"]
                }

        except Exception as e:
            logger.error(f"更新技能失败: {e}")
            return {"success": False, "message": f"更新技能失败: {str(e)}"}

    async def delete_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """删除技能.

        Args:
            params: {"id": int}  # 技能ID

        Returns:
            {"success": bool}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            skill_id = params.get("id")
            if skill_id is None:
                return {"success": False, "message": "技能ID不能为空"}

            # 内置技能保护：内置技能文件在包目录，不可删除
            skill = self.db_manager.get_skill_by_id(skill_id)
            if not skill:
                return {"success": False, "message": "技能未找到"}
            if skill.get("category") == "builtin":
                return {"success": False, "message": "内置技能不可删除"}

            # 删除技能
            result = self.db_manager.delete_skill(skill_id)

            if result["success"]:
                # 删除 workspace 技能文件（与 DB 行同步清理）
                try:
                    SkillsLoader(self.server.config.workspace_path).delete_skill_file(skill["code"])
                except Exception as e:
                    logger.error(f"删除技能文件失败: {e}")
                # 删除可能移除了 active 技能，重算运行时生效集合
                try:
                    self.server._sync_skill_runtime()
                except Exception as e:
                    logger.error(f"同步技能启停状态失败: {e}")
                return {
                    "success": True,
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result["message"]
                }

        except Exception as e:
            logger.error(f"删除技能失败: {e}")
            return {"success": False, "message": f"删除技能失败: {str(e)}"}

    async def get_skill_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取技能正文（SKILL.md 文件是正文真相源）.

        Args:
            params: {"code": str}  # 技能编码（= 目录名）

        Returns:
            {"success": bool, "skill": {code, name, description, content, source, hasFile}}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        try:
            code = (params.get("code") or "").strip()
            if not code:
                return {"success": False, "message": "技能编码不能为空"}
            meta = self.db_manager.get_skill_by_code(code)
            loader = SkillsLoader(self.server.config.workspace_path)
            full = loader.read_skill_full(code)
            # 名称/描述优先取 frontmatter，无则回落 DB 元数据
            name, description = code, (meta or {}).get("description", "")
            if full["has_file"]:
                fm = loader.get_skill_metadata(code) or {}
                if fm.get("name"):
                    name = fm["name"]
                if fm.get("description"):
                    description = fm["description"]
            return {
                "success": True,
                "skill": {
                    "code": code,
                    "name": name,
                    "description": description,
                    "content": full["body"],
                    "source": (meta or {}).get("category", "custom"),
                    "hasFile": full["has_file"],
                },
            }
        except ValueError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            logger.error(f"获取技能内容失败: {e}")
            return {"success": False, "message": f"获取技能内容失败: {str(e)}"}

    async def sync_skills(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """文件↔DB 双向同步技能.

        Args:
            params: {"direction": "import" | "export"}
                - import: 扫描 workspace/builtin 的 SKILL.md 文件 -> DB（保留 status）
                - export: DB 中无对应文件的技能生成 workspace 骨架文件（不覆盖已有）

        Returns:
            {"success": bool, "message": str}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        try:
            direction = (params.get("direction") or "import").strip().lower()
            loader = SkillsLoader(self.server.config.workspace_path)
            if direction == "import":
                res = self.server._sync_workspace_skills()
                self.server._sync_skill_runtime()
                return {
                    "success": True,
                    "message": f"已从文件导入 {res['created']} 个技能（更新 {res['updated']} 个）",
                    **res,
                }
            if direction == "export":
                exported = 0
                for s in self.db_manager.get_all_skills():
                    if s.get("category") == "builtin":
                        continue  # 内置技能文件在包目录，不导出到 workspace
                    try:
                        if loader.export_skill(s["code"], s["name"], s["description"]):
                            exported += 1
                    except Exception as e:
                        logger.error(f"导出技能失败 {s['code']}: {e}")
                return {"success": True, "message": f"已导出 {exported} 个技能到 workspace"}
            return {"success": False, "message": "未知同步方向（import/export）"}
        except Exception as e:
            logger.error(f"同步技能失败: {e}")
            return {"success": False, "message": f"同步技能失败: {str(e)}"}

    # ========================================================================
    # AI 生成技能/工具配置（复用运行中 agent 的 provider 单轮调用，不落盘；
    # 结果填回前端表单由人工确认后，再走 addSkill/updateSkill、addTool/updateTool 落盘）
    # ========================================================================

    def _get_provider(self):
        """返回可用的 (provider, model)：优先复用运行中 agent 的 provider."""
        try:
            agent = self.server.get_agent()
            if agent is not None and getattr(agent, "provider", None) is not None:
                return agent.provider, agent.model
        except Exception:
            pass
        # 兜底：按配置新建 provider（仿 cli/commands.py 的构造方式）
        from pyclaw.providers.litellm_provider import LiteLLMProvider
        cfg = self.server.config
        return (
            LiteLLMProvider(
                api_key=cfg.get_api_key(),
                api_base=cfg.get_api_base(),
                default_model=cfg.agents.defaults.model,
                enable_text_tool_call_fallback=cfg.get_enable_text_tool_call_fallback(),
            ),
            cfg.agents.defaults.model,
        )

    async def _generate(self, prompt: str, task: str) -> str | None:
        """单轮调用 LLM 生成内容（tools=None，纯文本输出，禁止 <tool_call>）.

        Returns:
            生成的文本；失败/无内容返回 None（TimeoutError 向上抛出由调用方处理）
        """
        provider, model = self._get_provider()
        system = (
            "你是 pyclaw 智能体的技能/工具设计助手。只输出要求的内容本身，"
            "不要任何解释、前后缀或多余文字，绝对禁止输出 <tool_call> 标记。\n"
            f"当前任务：{task}"
        )
        resp = await asyncio.wait_for(
            provider.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                model=model,
                max_tokens=8192,
                temperature=0.4,
            ),
            timeout=getattr(provider, "timeout", 120),
        )
        return resp.content if resp.content else None

    @staticmethod
    def _parse_skill_md(raw: str) -> tuple[str, str, str]:
        """解析 LLM 输出的 SKILL.md：frontmatter 的 name/description + 正文.

        frontmatter 缺失时 name/description 回落空串，正文为原始内容。
        """
        name = description = ""
        body = raw.strip()
        m = re.match(r"^---\n(.*?)\n---\n?(.*)", raw, re.DOTALL)
        if m:
            meta_text, body = m.group(1), (m.group(2) or "").strip()
            for line in meta_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip().strip('"\'')
                    if k == "name":
                        name = v
                    elif k == "description":
                        description = v
        return name, description, body

    @staticmethod
    def _parse_tool_json(raw: str) -> dict | None:
        """解析 LLM 输出的工具配置 JSON（容忍 ```json 围栏与前后缀文本）."""
        text = raw.strip()
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        # 定位首 { 到末 }，容忍前后缀解释文本
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    async def generate_skill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """AI 生成技能 SKILL.md（返回 name/description/正文，不落盘）.

        Args:
            params: {"prompt": str}  # 用户对技能的需求描述

        Returns:
            {"success": bool, "skill": {name, description, content}, "message": str}
        """
        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            return {"success": False, "message": "请描述你想要什么技能"}
        try:
            task = (
                "生成一个技能的 SKILL.md 文件内容。格式为 frontmatter（含 name 小写短横线编码、"
                "description 一句话描述）+ markdown 正文（告诉 agent 如何完成该技能任务的操作步骤/要点）。"
            )
            raw = await self._generate(prompt, task)
            if not raw:
                return {"success": False, "message": "AI 生成失败，请稍后重试"}
            name, description, body = self._parse_skill_md(raw)
            return {
                "success": True,
                "skill": {"name": name, "description": description, "content": body},
            }
        except asyncio.TimeoutError:
            return {"success": False, "message": "AI 生成超时，请稍后重试"}
        except Exception as e:
            logger.error(f"生成技能失败: {e}")
            return {"success": False, "message": f"生成技能失败: {str(e)}"}

    async def generate_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """AI 生成自定义工具配置（command/script/parameters，不落盘）.

        Args:
            params: {
                "prompt": str,          # 用户对工具的需求描述
                "toolName": str,        # 当前工具名（上下文）
                "toolDescription": str # 当前工具描述（上下文）
            }

        Returns:
            {"success": bool, "tool": {command, script, parameters}, "message": str}
        """
        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            return {"success": False, "message": "请描述你想要什么工具"}
        try:
            ctx = ""
            tool_name = (params.get("toolName") or "").strip()
            tool_desc = (params.get("toolDescription") or "").strip()
            if tool_name:
                ctx += f"\n工具名称：{tool_name}"
            if tool_desc:
                ctx += f"\n工具描述：{tool_desc}"
            task = (
                "生成一个自定义工具的配置，仅输出一个合法的 JSON 对象（不要 markdown 围栏、不要解释）：\n"
                '{"command": "Windows 命令行模板，{arg} 为占位符，不需要则空串", '
                '"script": "Python 脚本源码，command 为空时使用，不需要则空串", '
                '"parameters": {"type": "object", "properties": {...}}（参数 JSON Schema，可为 null）}'
            )
            raw = await self._generate(prompt + ctx, task)
            if not raw:
                return {"success": False, "message": "AI 生成失败，请稍后重试"}
            data = self._parse_tool_json(raw)
            if data is None:
                return {"success": False, "message": "AI 返回的不是合法 JSON 配置，请重试或调整描述"}
            parameters = data.get("parameters")
            return {
                "success": True,
                "tool": {
                    "command": data.get("command") or "",
                    "script": data.get("script") or "",
                    "parameters": parameters if isinstance(parameters, dict) else None,
                },
            }
        except asyncio.TimeoutError:
            return {"success": False, "message": "AI 生成超时，请稍后重试"}
        except Exception as e:
            logger.error(f"生成工具配置失败: {e}")
            return {"success": False, "message": f"生成工具配置失败: {str(e)}"}

    async def list_messages(self, params: Dict[str, Any]) -> list:
        """列出消息.

        Args:
            params: {
                "session_id": str,  # 会话ID
                "limit": int        # 消息数量限制
            }

        Returns:
            消息列表
        """
        if not self.db_manager:
            logger.error("数据库管理器未初始化")
            return []
        
        try:
            session_id = params.get("session_id", "default")
            limit = params.get("limit", 100)
            
            messages = self.db_manager.get_messages_by_session(session_id, limit)
            logger.info(f"成功加载 {len(messages)} 条消息")
            return messages
        except Exception as e:
            logger.error(f"加载消息列表失败: {e}")
            return []

    async def add_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加消息.

        Args:
            params: {
                "session_id": str,     # 会话ID
                "content": str,        # 消息内容
                "message_type": str,   # 消息类型
                "sender": str,         # 发送者
                "receiver": str        # 接收者
            }

        Returns:
            {"success": bool, "message": dict}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            session_id = params.get("session_id", "default")
            content = params.get("content", "")
            message_type = params.get("message_type", "system")
            sender = params.get("sender")
            receiver = params.get("receiver")
            
            if not content:
                return {"success": False, "message": "消息内容不能为空"}
            
            result = self.db_manager.add_message(session_id, content, message_type, sender, receiver)
            
            if result["success"]:
                return {
                    "success": True,
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result["error"]
                }
                
        except Exception as e:
            logger.error(f"添加消息失败: {e}")
            return {"success": False, "message": f"添加消息失败: {str(e)}"}

    async def clear_messages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """清空消息.

        Args:
            params: {
                "session_id": str  # 会话ID
            }

        Returns:
            {"success": bool, "message": str}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            session_id = params.get("session_id", "default")
            
            result = self.db_manager.clear_session_messages(session_id)
            
            if result["success"]:
                return {
                    "success": True,
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result["message"]
                }
                
        except Exception as e:
            logger.error(f"清空消息失败: {e}")
            return {"success": False, "message": f"清空消息失败: {str(e)}"}

    # 敏感词规则管理API
    async def list_sensitive_rules(self, params: Dict[str, Any]) -> list:
        """列出所有敏感词规则.

        Args:
            params: 空字典

        Returns:
            敏感词规则列表
        """
        if not self.db_manager:
            logger.error("数据库管理器未初始化")
            return []
        
        try:
            rules = self.db_manager.get_all_sensitive_rules()
            logger.info(f"成功加载 {len(rules)} 条敏感词规则")
            return rules
        except Exception as e:
            logger.error(f"加载敏感词规则列表失败: {e}")
            return []

    async def add_sensitive_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加敏感词规则.

        Args:
            params: {
                "keyword": str,        # 敏感词
                "action": str,         # 处理动作
                "replacement": str,    # 替换词
                "category": str,       # 分类
                "severity": str,       # 严重程度
                "description": str     # 描述
            }

        Returns:
            {"success": bool, "rule": dict}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            keyword = params.get("keyword", "").strip()
            action = params.get("action", "block")
            replacement = params.get("replacement")
            category = params.get("category", "general")
            severity = params.get("severity", "medium")
            description = params.get("description", "")
            
            if not keyword:
                return {"success": False, "message": "敏感词不能为空"}
            
            result = self.db_manager.add_sensitive_word_rule(
                keyword=keyword,
                action=action,
                replacement=replacement,
                category=category,
                severity=severity,
                description=description
            )
            
            if result["success"]:
                return {
                    "success": True,
                    "rule": result["rule"],
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result.get("message", result.get("error", "添加敏感词规则失败"))
                }
                
        except Exception as e:
            logger.error(f"添加敏感词规则失败: {e}")
            return {"success": False, "message": f"添加敏感词规则失败: {str(e)}"}

    async def update_sensitive_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """更新敏感词规则.

        Args:
            params: {
                "id": int,              # 规则ID
                "keyword": str,         # 敏感词
                "action": str,          # 处理动作
                "replacement": str,     # 替换词
                "category": str,        # 分类
                "severity": str,        # 严重程度
                "description": str,     # 描述
                "status": str           # 状态
            }

        Returns:
            {"success": bool, "rule": dict}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            rule_id = params.get("id")
            if rule_id is None:
                return {"success": False, "message": "规则ID不能为空"}
            
            # 构建更新字段
            updates = {}
            for key in ["keyword", "action", "replacement", "category", "severity", "description", "status"]:
                if key in params:
                    updates[key] = params[key]
            
            if not updates:
                return {"success": False, "message": "没有需要更新的字段"}
            
            result = self.db_manager.update_sensitive_rule(rule_id, **updates)
            
            if result["success"]:
                return {
                    "success": True,
                    "rule": result["rule"],
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result.get("message", result.get("error", "更新敏感词规则失败"))
                }
                
        except Exception as e:
            logger.error(f"更新敏感词规则失败: {e}")
            return {"success": False, "message": f"更新敏感词规则失败: {str(e)}"}

    async def delete_sensitive_rule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """删除敏感词规则.

        Args:
            params: {"id": int}  # 规则ID

        Returns:
            {"success": bool}
        """
        if not self.db_manager:
            return {"success": False, "message": "数据库管理器未初始化"}
        
        try:
            rule_id = params.get("id")
            if rule_id is None:
                return {"success": False, "message": "规则ID不能为空"}
            
            result = self.db_manager.delete_sensitive_rule(rule_id)
            
            if result["success"]:
                return {
                    "success": True,
                    "message": result["message"]
                }
            else:
                return {
                    "success": False,
                    "message": result.get("message", result.get("error", "删除敏感词规则失败"))
                }
                
        except Exception as e:
            logger.error(f"删除敏感词规则失败: {e}")
            return {"success": False, "message": f"删除敏感词规则失败: {str(e)}"}

    async def filter_message_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """过滤消息内容.

        Args:
            params: {
                "content": str  # 消息内容
            }

        Returns:
            过滤结果
        """
        if not self.db_manager:
            return {
                "passed": True,
                "filtered_content": params.get("content", ""),
                "matched_rules": [],
                "action_taken": "error"
            }
        
        try:
            content = params.get("content", "")
            
            if not content:
                return {
                    "passed": True,
                    "filtered_content": "",
                    "matched_rules": [],
                    "action_taken": "pass"
                }
            
            result = self.db_manager.filter_message(content)
            
            return {
                "passed": result["passed"],
                "filtered_content": result["filtered_content"],
                "matched_rules": result["matched_rules"],
                "action_taken": result["action_taken"]
            }
                
        except Exception as e:
            logger.error(f"过滤消息内容失败: {e}")
            return {
                "passed": True,
                "filtered_content": params.get("content", ""),
                "matched_rules": [],
                "action_taken": "error"
            }