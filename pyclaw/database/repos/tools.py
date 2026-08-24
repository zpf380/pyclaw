"""工具数据访问 mixin - 供 DatabaseManager 组合"""
from datetime import datetime
from typing import Optional

import json
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from ..models import ToolRegistry


class ToolsMixin:
    """工具注册表相关数据库操作"""

    def get_all_tools(self) -> list[dict]:
        """获取所有工具（按更新时间倒序）"""
        session = self.get_session()
        try:
            tools = session.query(ToolRegistry).order_by(ToolRegistry.updated_at.desc()).all()
            return [tool.to_dict() for tool in tools]
        except SQLAlchemyError as e:
            logger.error(f"获取工具列表失败: {e}")
            return []
        finally:
            self.close_session(session)

    def get_tool_by_name(self, name: str) -> Optional[dict]:
        """根据名称获取工具"""
        session = self.get_session()
        try:
            tool = session.query(ToolRegistry).filter(ToolRegistry.name == name).first()
            return tool.to_dict() if tool else None
        except SQLAlchemyError as e:
            logger.error(f"获取工具失败: {e}")
            return None
        finally:
            self.close_session(session)

    def get_tool_by_id(self, tool_id: int) -> Optional[dict]:
        """根据 ID 获取工具"""
        session = self.get_session()
        try:
            tool = session.query(ToolRegistry).filter(ToolRegistry.id == tool_id).first()
            return tool.to_dict() if tool else None
        except SQLAlchemyError as e:
            logger.error(f"获取工具失败: {e}")
            return None
        finally:
            self.close_session(session)

    def get_inactive_tool_names(self) -> list[str]:
        """获取所有 status=inactive 的工具名（供运行时过滤）"""
        session = self.get_session()
        try:
            rows = session.query(ToolRegistry).filter(ToolRegistry.status == "inactive").all()
            return [row.name for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"获取停用工具失败: {e}")
            return []
        finally:
            self.close_session(session)

    def add_tool(self, name: str, description: str = "", category: str = "custom",
                 version: str = "1.0.0", author: str = "自定义", config: dict | None = None) -> dict:
        """添加工具

        Returns:
            {"success": bool, "tool": dict, "message": str}
        """
        session = self.get_session()
        try:
            # 检查工具名称是否已存在
            existing_tool = session.query(ToolRegistry).filter(ToolRegistry.name == name).first()
            if existing_tool:
                return {"success": False, "message": f"工具 '{name}' 已存在"}

            new_tool = ToolRegistry(
                name=name,
                description=description,
                category=category,
                version=version,
                author=author,
                config=json.dumps(config or {}, ensure_ascii=False),
                status="active"
            )

            session.add(new_tool)
            session.commit()
            session.refresh(new_tool)

            logger.info(f"工具添加成功: {name}")
            return {"success": True, "tool": new_tool.to_dict(), "message": "工具添加成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"添加工具失败: {e}")
            return {"success": False, "message": f"添加工具失败: {str(e)}"}
        finally:
            self.close_session(session)

    def update_tool(self, tool_id: int, **kwargs) -> dict:
        """更新工具信息

        Returns:
            {"success": bool, "tool": dict, "message": str}
        """
        session = self.get_session()
        try:
            tool = session.query(ToolRegistry).filter(ToolRegistry.id == tool_id).first()
            if not tool:
                return {"success": False, "message": "工具未找到"}

            # 更新字段（config 为 dict 时先序列化 JSON）
            for key, value in kwargs.items():
                if hasattr(tool, key) and value is not None:
                    if key == "config" and isinstance(value, dict):
                        value = json.dumps(value, ensure_ascii=False)
                    setattr(tool, key, value)

            session.commit()
            session.refresh(tool)

            logger.info(f"工具更新成功: {tool.name}")
            return {"success": True, "tool": tool.to_dict(), "message": "工具更新成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新工具失败: {e}")
            return {"success": False, "message": f"更新工具失败: {str(e)}"}
        finally:
            self.close_session(session)

    def delete_tool(self, tool_id: int) -> dict:
        """删除工具

        Returns:
            {"success": bool, "message": str}
        """
        session = self.get_session()
        try:
            tool = session.query(ToolRegistry).filter(ToolRegistry.id == tool_id).first()
            if not tool:
                return {"success": False, "message": "工具未找到"}

            session.delete(tool)
            session.commit()

            logger.info(f"工具删除成功: {tool.name}")
            return {"success": True, "message": "工具删除成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"删除工具失败: {e}")
            return {"success": False, "message": f"删除工具失败: {str(e)}"}
        finally:
            self.close_session(session)

    def seed_builtin_tools(self, defs: list[dict]) -> int:
        """启动时把内置工具元数据 upsert 进 tool_registry.

        已存在行只更新元数据，保留用户设置的 status（否则启停状态不持久）。

        Args:
            defs: [{name, description, config, category, version, author}, ...]

        Returns:
            本次新建的工具数量
        """
        session = self.get_session()
        created = 0
        try:
            for d in defs:
                existing = session.query(ToolRegistry).filter(ToolRegistry.name == d["name"]).first()
                if existing:
                    existing.description = d.get("description", existing.description)
                    existing.category = d.get("category", existing.category)
                    existing.version = d.get("version", existing.version)
                    existing.author = d.get("author", existing.author)
                    existing.config = json.dumps(d.get("config") or {}, ensure_ascii=False)
                    # 迁移后老行 builtin 可能为 NULL，seed 时统一修正为 True（否则会被误判为自定义可删除）
                    existing.builtin = True
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(ToolRegistry(
                        name=d["name"],
                        description=d.get("description", ""),
                        category=d.get("category", "system"),
                        version=d.get("version", "1.0.0"),
                        author=d.get("author", "pyclaw"),
                        config=json.dumps(d.get("config") or {}, ensure_ascii=False),
                        status="active",
                        builtin=True,
                    ))
                    created += 1
            session.commit()
            logger.info(f"内置工具同步完成，新增 {created} 个")
            return created
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"内置工具 seed 失败: {e}")
            return 0
        finally:
            self.close_session(session)
