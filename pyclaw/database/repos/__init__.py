"""数据访问仓储（mixin 组合）

按业务域拆分 DatabaseManager 的实现，DatabaseManager 通过多继承组合各 mixin，
外部调用接口保持不变。每个 mixin 依赖宿主提供 get_session()/close_session()。
"""

from pyclaw.database.repos.connections import ConnectionsMixin
from pyclaw.database.repos.messages import MessagesMixin
from pyclaw.database.repos.sensitive_rules import SensitiveRulesMixin
from pyclaw.database.repos.skills import SkillsMixin
from pyclaw.database.repos.tools import ToolsMixin
from pyclaw.database.repos.users import UsersMixin

__all__ = [
    "ConnectionsMixin",
    "MessagesMixin",
    "SensitiveRulesMixin",
    "SkillsMixin",
    "ToolsMixin",
    "UsersMixin",
]
