"""用户/Token 数据访问 mixin - 供 DatabaseManager 组合"""
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from ..models import User, ApiToken


class UsersMixin:
    """用户与 Token 相关数据库操作"""

    def create_user(self, username: str, password_hash: str, salt: str,
                    role: str = "member", display_name: str = None) -> dict:
        """创建用户

        Returns:
            {"success": bool, "user": dict, "message": str}
        """
        session = self.get_session()
        try:
            existing = session.query(User).filter(User.username == username).first()
            if existing:
                return {"success": False, "message": f"用户名 '{username}' 已存在"}

            new_user = User(
                username=username,
                password_hash=password_hash,
                salt=salt,
                role=role,
                display_name=display_name or username,
                status="active"
            )

            session.add(new_user)
            session.commit()
            session.refresh(new_user)

            logger.info(f"用户创建成功: {username} ({role})")
            return {"success": True, "user": new_user.to_dict(), "message": "用户创建成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"创建用户失败: {e}")
            return {"success": False, "message": f"创建用户失败: {str(e)}"}
        finally:
            self.close_session(session)

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """根据用户名获取用户"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            return user.to_dict() if user else None
        except SQLAlchemyError as e:
            logger.error(f"获取用户失败: {e}")
            return None
        finally:
            self.close_session(session)

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """根据ID获取用户"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return user.to_dict() if user else None
        except SQLAlchemyError as e:
            logger.error(f"获取用户失败: {e}")
            return None
        finally:
            self.close_session(session)

    def get_user_record_by_username(self, username: str) -> Optional[dict]:
        """根据用户名获取用户记录（含密码哈希/盐值，仅内部使用）.

        返回纯 dict 而非 ORM 对象：避免 session 关闭后访问 detached 对象
        触发 DetachedInstanceError 的脆弱模式。
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "status": user.status,
                "salt": user.salt,
                "password_hash": user.password_hash,
            }
        except SQLAlchemyError as e:
            logger.error(f"获取用户记录失败: {e}")
            return None
        finally:
            self.close_session(session)

    def list_users(self) -> list[dict]:
        """获取所有用户"""
        session = self.get_session()
        try:
            users = session.query(User).order_by(User.created_at.desc()).all()
            return [user.to_dict() for user in users]
        except SQLAlchemyError as e:
            logger.error(f"获取用户列表失败: {e}")
            return []
        finally:
            self.close_session(session)

    def update_user_role(self, user_id: int, role: str) -> dict:
        """更新用户角色

        Returns:
            {"success": bool, "user": dict, "message": str}
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"success": False, "message": "用户未找到"}

            user.role = role
            session.commit()
            session.refresh(user)

            logger.info(f"用户角色更新成功: {user.username} -> {role}")
            return {"success": True, "user": user.to_dict(), "message": "用户角色更新成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新用户角色失败: {e}")
            return {"success": False, "message": f"更新用户角色失败: {str(e)}"}
        finally:
            self.close_session(session)

    def set_user_status(self, user_id: int, status: str) -> dict:
        """设置用户状态（active/inactive）"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"success": False, "message": "用户未找到"}

            user.status = status
            session.commit()
            session.refresh(user)

            return {"success": True, "user": user.to_dict(), "message": "用户状态更新成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新用户状态失败: {e}")
            return {"success": False, "message": f"更新用户状态失败: {str(e)}"}
        finally:
            self.close_session(session)

    # ====================================================================
    # Token 管理
    # ====================================================================
    def issue_token(self, user_id: int, token_hash: str, expires_at) -> dict:
        """签发 token（存哈希）

        Returns:
            {"success": bool, "token": dict, "message": str}
        """
        session = self.get_session()
        try:
            existing = session.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
            if existing:
                return {"success": False, "message": "Token 已存在"}

            new_token = ApiToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at
            )

            session.add(new_token)
            session.commit()
            session.refresh(new_token)

            return {"success": True, "token": new_token.to_dict(), "message": "Token 签发成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"签发 Token 失败: {e}")
            return {"success": False, "message": f"签发 Token 失败: {str(e)}"}
        finally:
            self.close_session(session)

    def get_token_by_hash(self, token_hash: str) -> Optional[dict]:
        """根据 token 哈希获取 token"""
        session = self.get_session()
        try:
            token = session.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
            return token.to_dict() if token else None
        except SQLAlchemyError as e:
            logger.error(f"获取 Token 失败: {e}")
            return None
        finally:
            self.close_session(session)

    def get_token_record_by_hash(self, token_hash: str) -> Optional[dict]:
        """根据 token 哈希获取 token 记录（含完整字段，仅内部使用）.

        返回纯 dict 而非 ORM 对象：避免 session 关闭后访问 detached 对象
        触发 DetachedInstanceError 的脆弱模式。
        """
        session = self.get_session()
        try:
            token = session.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
            if not token:
                return None
            return {
                "id": token.id,
                "user_id": token.user_id,
                "token_hash": token.token_hash,
                "expires_at": token.expires_at,
            }
        except SQLAlchemyError as e:
            logger.error(f"获取 Token 记录失败: {e}")
            return None
        finally:
            self.close_session(session)

    def update_token_last_used(self, token_hash: str) -> dict:
        """更新 token 最后使用时间"""
        session = self.get_session()
        try:
            token = session.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
            if not token:
                return {"success": False, "message": "Token 未找到"}

            token.last_used_at = datetime.utcnow()
            session.commit()
            return {"success": True}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新 Token 使用时间失败: {e}")
            return {"success": False, "message": f"更新 Token 使用时间失败: {str(e)}"}
        finally:
            self.close_session(session)

    def revoke_token(self, token_hash: str) -> dict:
        """吊销 token"""
        session = self.get_session()
        try:
            token = session.query(ApiToken).filter(ApiToken.token_hash == token_hash).first()
            if not token:
                return {"success": False, "message": "Token 未找到"}

            session.delete(token)
            session.commit()

            return {"success": True, "message": "Token 已吊销"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"吊销 Token 失败: {e}")
            return {"success": False, "message": f"吊销 Token 失败: {str(e)}"}
        finally:
            self.close_session(session)
