"""消息数据访问 mixin - 供 DatabaseManager 组合"""
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from ..models import Message


class MessagesMixin:
    """消息相关数据库操作"""

    def add_message(self, session_id: str, content: str, message_type: str,
                   sender: str = None, receiver: str = None) -> dict:
        """添加消息

        Returns:
            {"success": bool, "message": dict, "error": str}
        """
        session = self.get_session()
        try:
            new_message = Message(
                session_id=session_id,
                content=content,
                message_type=message_type,
                sender=sender,
                receiver=receiver
            )

            session.add(new_message)
            session.commit()
            session.refresh(new_message)

            return {"success": True, "message": new_message.to_dict()}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"添加消息失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

    def get_messages_by_session(self, session_id: str, limit: int = 100) -> list[dict]:
        """根据会话ID获取消息"""
        session = self.get_session()
        try:
            messages = session.query(Message).filter(
                Message.session_id == session_id
            ).order_by(Message.timestamp.desc()).limit(limit).all()

            return [msg.to_dict() for msg in reversed(messages)]  # 按时间正序排列
        except SQLAlchemyError as e:
            logger.error(f"获取消息失败: {e}")
            return []
        finally:
            self.close_session(session)

    def clear_session_messages(self, session_id: str) -> dict:
        """清空会话消息

        Returns:
            {"success": bool, "message": str}
        """
        session = self.get_session()
        try:
            session.query(Message).filter(Message.session_id == session_id).delete()
            session.commit()

            return {"success": True, "message": "消息清空成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"清空消息失败: {e}")
            return {"success": False, "message": f"清空消息失败: {str(e)}"}
        finally:
            self.close_session(session)
