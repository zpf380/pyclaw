"""智能体/连接数据访问 mixin - 供 DatabaseManager 组合"""
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from ..models import Agent, Connection


class ConnectionsMixin:
    """智能体与连接相关数据库操作"""

    def get_all_agents(self) -> list[dict]:
        """获取所有智能体"""
        session = self.get_session()
        try:
            agents = session.query(Agent).order_by(Agent.updated_at.desc()).all()
            return [agent.to_dict() for agent in agents]
        except SQLAlchemyError as e:
            logger.error(f"获取智能体列表失败: {e}")
            return []
        finally:
            self.close_session(session)

    def add_connection(self, client_id: str, remote_address: str) -> dict:
        """添加连接记录"""
        session = self.get_session()
        try:
            new_connection = Connection(
                client_id=client_id,
                remote_address=remote_address,
                status="connected"
            )

            session.add(new_connection)
            session.commit()
            session.refresh(new_connection)

            return {"success": True, "connection": new_connection.to_dict()}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"添加连接记录失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

    def update_connection_status(self, client_id: str, status: str, disconnected_at: str = None) -> dict:
        """更新连接状态"""
        session = self.get_session()
        try:
            connection = session.query(Connection).filter(Connection.client_id == client_id).first()
            if connection:
                connection.status = status
                if disconnected_at:
                    connection.disconnected_at = disconnected_at
                session.commit()

            return {"success": True}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新连接状态失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

    def get_active_connections(self) -> list[dict]:
        """获取活跃连接"""
        session = self.get_session()
        try:
            connections = session.query(Connection).filter(
                Connection.status == "connected"
            ).order_by(Connection.connected_at.desc()).all()

            return [conn.to_dict() for conn in connections]
        except SQLAlchemyError as e:
            logger.error(f"获取连接列表失败: {e}")
            return []
        finally:
            self.close_session(session)
