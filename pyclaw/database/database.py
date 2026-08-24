"""数据库管理类
DatabaseManager类，CRUD操作，敏感词过滤逻辑，事务管理

实现按业务域拆分到 repos/ 下的仓储 mixin，DatabaseManager 组合它们并
统一提供会话生命周期（get_session/close_session）与建表/迁移/清理。
"""

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from .models import Base
from .repos import (
    ConnectionsMixin,
    MessagesMixin,
    SensitiveRulesMixin,
    SkillsMixin,
    ToolsMixin,
    UsersMixin,
)


class DatabaseManager(
    SkillsMixin,
    SensitiveRulesMixin,
    ToolsMixin,
    MessagesMixin,
    ConnectionsMixin,
    UsersMixin,
):
    """数据库管理器（组合各域仓储 mixin）"""

    def __init__(self, db_url: str = None):
        """初始化数据库管理器

        Args:
            db_url: 数据库连接URL，如果为None则使用默认的SQLite数据库
        """
        if db_url is None:
            # 默认使用SQLite数据库
            db_path = Path("pyclaw.db")
            db_url = f"sqlite:///{db_path.absolute()}"

        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # 创建表
        self.create_tables()

        logger.info(f"数据库初始化完成: {db_url}")

    def create_tables(self):
        """创建数据库表（含旧版 users 表兼容迁移、新增列迁移与测试脏数据清理）"""
        try:
            self._migrate_legacy_users()
            Base.metadata.create_all(bind=self.engine)
            self._migrate_add_columns()
            self._cleanup_fake_data()
            logger.info("数据库表创建成功")
        except Exception as e:
            logger.error(f"创建数据库表失败: {e}")
            raise

    def _migrate_add_columns(self) -> None:
        """为已有 SQLite 表补齐新增列（create_all 不会修改已存在的表）.

        幂等：用 inspect 检查列是否存在，缺失才 ALTER。SQLite 的 ADD COLUMN
        不能带 NOT NULL 无默认值，故裸加可空列，由 to_dict() 兜底 NULL。
        """
        try:
            inspector = inspect(self.engine)
            tables = set(inspector.get_table_names())
            # tool_registry.builtin：标记内置工具（保护删除/改名）
            if "tool_registry" in tables:
                cols = {c["name"] for c in inspector.get_columns("tool_registry")}
                if "builtin" not in cols:
                    with self.engine.begin() as conn:
                        conn.execute(text("ALTER TABLE tool_registry ADD COLUMN builtin BOOLEAN"))
                    logger.info("已为 tool_registry 补加 builtin 列")
        except Exception as e:
            logger.error(f"新增列迁移失败（跳过，继续启动）: {e}")

    def _cleanup_fake_data(self) -> None:
        """清理历史测试/脏数据（幂等，只删明确标记的假数据，保留 admin 与有效 token）."""
        try:
            tables = set(inspect(self.engine).get_table_names())
            with self.engine.begin() as conn:
                # 1. 假用户（password_hash='x' 无法登录）及其 token
                if "users" in tables:
                    fake_ids = conn.execute(
                        text("SELECT id FROM users WHERE password_hash = 'x'")
                    ).fetchall()
                    if fake_ids:
                        if "api_tokens" in tables:
                            conn.execute(text(
                                "DELETE FROM api_tokens WHERE user_id IN "
                                "(SELECT id FROM users WHERE password_hash = 'x')"
                            ))
                        conn.execute(text("DELETE FROM users WHERE password_hash = 'x'"))
                        logger.info(f"已清理假用户: {[r[0] for r in fake_ids]}")
                # 2. 假技能
                if "skills" in tables:
                    conn.execute(text("DELETE FROM skills WHERE code IN ('SS','ss') OR name = 'ss'"))
                # 3. 假敏感词规则
                if "sensitive_word_rules" in tables:
                    conn.execute(text("DELETE FROM sensitive_word_rules WHERE keyword IN ('sas','A')"))
                # 4. 遗留旧表（旧 schema 用户，含 aaaa）
                if "users_legacy" in tables:
                    conn.execute(text("DROP TABLE users_legacy"))
                    logger.info("已删除遗留旧表 users_legacy")
        except Exception as e:
            logger.error(f"清理脏数据失败（跳过，继续启动）: {e}")

    def _migrate_legacy_users(self) -> None:
        """迁移旧版 users 表（若存在）.

        旧版 users 表使用 password/email 列，新模型需要 password_hash/salt/role/
        display_name。SQLite create_all 不会修改已存在的表，因此检测到不兼容的旧表时
        先重命名以保留数据，再让 create_all 按新模型重建。幂等：迁移后新表结构符合
        要求，不再触发。SQLite 默认未开启外键约束，重命名不会改写 api_tokens 的外键。
        """
        try:
            inspector = inspect(self.engine)
            if "users" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("users")}
            # 新模型必需列存在即视为已兼容
            if "password_hash" in columns:
                return
            # 选择一个不冲突的备份表名
            existing = set(inspector.get_table_names())
            candidate = "users_legacy"
            n = 0
            while candidate in existing:
                n += 1
                candidate = f"users_legacy_{n}"
            with self.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE users RENAME TO "{candidate}"'))
            logger.warning(
                f"检测到旧版 users 表（不兼容列），已重命名为 {candidate} 以保留数据，"
                "将由新模型重建 users 表"
            )
        except Exception as e:
            logger.error(f"旧版 users 表迁移失败（跳过，继续启动）: {e}")

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()

    def close_session(self, session: Session):
        """关闭数据库会话"""
        session.close()
