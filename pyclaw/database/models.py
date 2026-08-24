"""数据库模型定义
SQLAlchemy模型类：Skill(技能)、Message(消息)、Agent(智能体)、Connection(连接)、SensitiveWordRule(敏感词规则)、MessageFilterLog(过滤日志)
"""

import json
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Skill(Base):
    """技能表"""
    __tablename__ = "skills"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="技能名称")
    code = Column(String(50), unique=True, nullable=False, comment="技能编码")
    description = Column(Text, comment="技能描述")
    status = Column(String(20), default="active", comment="技能状态: active/inactive")
    category = Column(String(50), default="custom", comment="技能类别")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description or "",
            "status": self.status,
            "category": self.category,
            "createTime": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
            "updateTime": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else ""
        }


class ToolRegistry(Base):
    """工具注册表"""
    __tablename__ = "tool_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="工具名称")
    description = Column(Text, comment="工具描述")
    category = Column(String(50), default="system", comment="工具类别: system/web/message/custom")
    version = Column(String(20), default="1.0.0", comment="工具版本")
    status = Column(String(20), default="active", comment="工具状态: active/inactive")
    author = Column(String(50), default="pyclaw", comment="作者")
    config = Column(Text, comment="工具配置(JSON格式)")
    builtin = Column(Boolean, default=False, comment="是否内置工具（内置不可删除/改名）")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def to_dict(self):
        """转换为字典格式（config 解析为对象，字段与前端 ToolManagementPage 对齐）"""
        try:
            config = json.loads(self.config) if self.config else {}
        except (json.JSONDecodeError, TypeError):
            config = {}
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "version": self.version,
            "status": self.status,
            "description": self.description or "",
            "config": config,
            "builtin": bool(self.builtin),
            "createTime": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
            "updateTime": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else "",
            "author": self.author or "",
        }


class Message(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, comment="会话ID")
    content = Column(Text, nullable=False, comment="消息内容")
    message_type = Column(String(20), nullable=False, comment="消息类型: sent/received/system")
    sender = Column(String(100), comment="发送者")
    receiver = Column(String(100), comment="接收者")
    timestamp = Column(DateTime, default=datetime.utcnow, comment="消息时间戳")
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "content": self.content,
            "type": self.message_type,
            "sender": self.sender or "",
            "receiver": self.receiver or "",
            "time": self.timestamp.strftime("%H:%M:%S") if self.timestamp else "",
            "timestamp": self.timestamp.isoformat() if self.timestamp else ""
        }


class Agent(Base):
    """智能体表"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="智能体名称")
    description = Column(Text, comment="智能体描述")
    status = Column(String(20), default="active", comment="智能体状态")
    config = Column(Text, comment="智能体配置(JSON格式)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "status": self.status,
            "config": self.config or "{}",
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else ""
        }


class Connection(Base):
    """连接表"""
    __tablename__ = "connections"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(100), unique=True, nullable=False, comment="客户端ID")
    remote_address = Column(String(100), comment="远程地址")
    connected_at = Column(DateTime, default=datetime.utcnow, comment="连接时间")
    disconnected_at = Column(DateTime, nullable=True, comment="断开时间")
    status = Column(String(20), default="connected", comment="连接状态")
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "remote_address": self.remote_address or "",
            "connected_at": self.connected_at.isoformat() if self.connected_at else "",
            "disconnected_at": self.disconnected_at.isoformat() if self.disconnected_at else "",
            "status": self.status
        }


class SensitiveWordRule(Base):
    """敏感词规则表"""
    __tablename__ = "sensitive_word_rules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(100), nullable=False, comment="敏感词")
    action = Column(String(20), default="block", comment="处理动作: block/replace/review")
    replacement = Column(String(100), comment="替换词（当action为replace时使用）")
    category = Column(String(50), default="general", comment="分类")
    severity = Column(String(20), default="medium", comment="严重程度: low/medium/high")
    description = Column(Text, comment="规则描述")
    status = Column(String(20), default="active", comment="规则状态: active/inactive")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "keyword": self.keyword,
            "action": self.action,
            "replacement": self.replacement or "",
            "category": self.category,
            "severity": self.severity,
            "description": self.description or "",
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else ""
        }


class MessageFilterLog(Base):
    """消息过滤日志表"""
    __tablename__ = "message_filter_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, comment="消息ID")
    rule_id = Column(Integer, ForeignKey("sensitive_word_rules.id"), nullable=False, comment="规则ID")
    matched_word = Column(String(100), nullable=False, comment="匹配到的敏感词")
    action_taken = Column(String(20), nullable=False, comment="采取的动作")
    original_content = Column(Text, comment="原始内容")
    filtered_content = Column(Text, comment="过滤后的内容")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关系
    message = relationship("Message", backref="filter_logs")
    rule = relationship("SensitiveWordRule", backref="filter_logs")

    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "message_id": self.message_id,
            "rule_id": self.rule_id,
            "matched_word": self.matched_word,
            "action_taken": self.action_taken,
            "original_content": self.original_content or "",
            "filtered_content": self.filtered_content or "",
            "created_at": self.created_at.isoformat() if self.created_at else ""
        }


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(256), nullable=False, comment="密码哈希(scrypt)")
    salt = Column(String(64), nullable=False, comment="密码盐值")
    role = Column(String(20), default="member", comment="角色: admin/operator/member")
    status = Column(String(20), default="active", comment="状态: active/inactive")
    display_name = Column(String(100), comment="显示名称")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    tokens = relationship("ApiToken", backref="user", cascade="all, delete-orphan")

    def to_dict(self):
        """转换为字典格式（不包含密码哈希与盐值）"""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "status": self.status,
            "display_name": self.display_name or "",
            "createTime": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
            "updateTime": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else ""
        }


class ApiToken(Base):
    """API Token表（存 SHA-256 哈希，不存明文）"""
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户ID")
    token_hash = Column(String(64), unique=True, nullable=False, comment="Token SHA-256 哈希")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    last_used_at = Column(DateTime, nullable=True, comment="最后使用时间")

    def to_dict(self):
        """转换为字典格式（不包含 token 哈希明文）"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "expires_at": self.expires_at.isoformat() if self.expires_at else "",
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else ""
        }