"""技能数据访问 mixin - 供 DatabaseManager 组合"""
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from ..models import Skill


class SkillsMixin:
    """技能相关数据库操作"""

    def get_all_skills(self) -> list[dict]:
        """获取所有技能"""
        session = self.get_session()
        try:
            skills = session.query(Skill).order_by(Skill.updated_at.desc()).all()
            return [skill.to_dict() for skill in skills]
        except SQLAlchemyError as e:
            logger.error(f"获取技能列表失败: {e}")
            return []
        finally:
            self.close_session(session)

    def get_skill_by_id(self, skill_id: int) -> Optional[dict]:
        """根据ID获取技能"""
        session = self.get_session()
        try:
            skill = session.query(Skill).filter(Skill.id == skill_id).first()
            return skill.to_dict() if skill else None
        except SQLAlchemyError as e:
            logger.error(f"获取技能失败: {e}")
            return None
        finally:
            self.close_session(session)

    def get_skill_by_code(self, code: str) -> Optional[dict]:
        """根据技能编码获取技能"""
        session = self.get_session()
        try:
            skill = session.query(Skill).filter(Skill.code == code).first()
            return skill.to_dict() if skill else None
        except SQLAlchemyError as e:
            logger.error(f"获取技能失败: {e}")
            return None
        finally:
            self.close_session(session)

    def add_skill(self, name: str, code: str, description: str = "", category: str = "custom") -> dict:
        """添加技能

        Returns:
            {"success": bool, "skill": dict, "message": str}
        """
        session = self.get_session()
        try:
            # 检查技能编码是否已存在
            existing_skill = session.query(Skill).filter(Skill.code == code).first()
            if existing_skill:
                return {"success": False, "message": f"技能编码 '{code}' 已存在"}

            new_skill = Skill(
                name=name,
                code=code,
                description=description,
                category=category,
                status="active"
            )

            session.add(new_skill)
            session.commit()
            session.refresh(new_skill)

            logger.info(f"技能添加成功: {name} ({code})")
            return {"success": True, "skill": new_skill.to_dict(), "message": "技能添加成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"添加技能失败: {e}")
            return {"success": False, "message": f"添加技能失败: {str(e)}"}
        finally:
            self.close_session(session)

    def update_skill(self, skill_id: int, **kwargs) -> dict:
        """更新技能

        Returns:
            {"success": bool, "skill": dict, "message": str}
        """
        session = self.get_session()
        try:
            skill = session.query(Skill).filter(Skill.id == skill_id).first()
            if not skill:
                return {"success": False, "message": "技能未找到"}

            # 更新字段
            for key, value in kwargs.items():
                if hasattr(skill, key):
                    setattr(skill, key, value)

            session.commit()
            session.refresh(skill)

            logger.info(f"技能更新成功: {skill.name} ({skill.code})")
            return {"success": True, "skill": skill.to_dict(), "message": "技能更新成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新技能失败: {e}")
            return {"success": False, "message": f"更新技能失败: {str(e)}"}
        finally:
            self.close_session(session)

    def delete_skill(self, skill_id: int) -> dict:
        """删除技能

        Returns:
            {"success": bool, "message": str}
        """
        session = self.get_session()
        try:
            skill = session.query(Skill).filter(Skill.id == skill_id).first()
            if not skill:
                return {"success": False, "message": "技能未找到"}

            session.delete(skill)
            session.commit()

            logger.info(f"技能删除成功: {skill.name} ({skill.code})")
            return {"success": True, "message": "技能删除成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"删除技能失败: {e}")
            return {"success": False, "message": f"删除技能失败: {str(e)}"}
        finally:
            self.close_session(session)

    def upsert_skill(self, name: str, code: str, description: str = "",
                     category: str = "custom", updated_at=None) -> dict:
        """按 code（目录名）幂等同步 workspace 技能进 DB.

        存在则更新 name/description/category/updated_at（不重置 status），
        否则新建且 status='active'。

        Args:
            name: 技能名称（目录名）
            code: 唯一标识（目录名）
            description: 技能描述
            category: 技能类别
            updated_at: 目录 SKILL.md 的修改时间（mtime 秒级时间戳或 datetime）

        Returns:
            {"success": bool, "created": bool, "skill": dict}
        """
        session = self.get_session()
        created = False
        try:
            # mtime 时间戳 → datetime
            ts = updated_at
            if isinstance(ts, (int, float)):
                ts = datetime.utcfromtimestamp(ts)

            skill = session.query(Skill).filter(Skill.code == code).first()
            if skill:
                skill.name = name
                skill.description = description
                skill.category = category
                if ts is not None:
                    skill.updated_at = ts
            else:
                skill = Skill(
                    name=name, code=code, description=description,
                    category=category, status="active",
                    updated_at=ts if ts is not None else datetime.utcnow(),
                )
                session.add(skill)
                created = True

            session.commit()
            session.refresh(skill)
            logger.info(f"技能同步: {name} ({'新建' if created else '已更新'})")
            return {"success": True, "created": created, "skill": skill.to_dict()}
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"技能同步失败: {code}: {e}")
            return {"success": False, "created": False, "message": str(e)}
        finally:
            self.close_session(session)
