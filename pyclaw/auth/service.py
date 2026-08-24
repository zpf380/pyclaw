"""认证服务 - 用户认证、Token 签发与校验

使用标准库实现：
- 密码哈希: hashlib.scrypt + 随机盐
- Token: secrets.token_urlsafe(32)，数据库仅存 SHA-256 哈希
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from loguru import logger


def hash_password(password: str) -> tuple[str, str]:
    """使用 scrypt 对密码加盐哈希.

    Returns:
        (salt_hex, hash_hex)
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """校验密码是否匹配."""
    try:
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )
        return secrets.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    """将明文 token 哈希为 SHA-256 用于存储."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthError(Exception):
    """认证异常，携带 Gateway 错误对象."""

    def __init__(self, error: GatewayError):
        self.error = error
        super().__init__(error.message)


class AuthService:
    """用户认证与 Token 管理服务.

    Args:
        db_manager: DatabaseManager 实例
        auth_config: AuthConfig 配置对象（enabled/admin_username/admin_password/token_ttl_hours/seed_admin）
    """

    def __init__(self, db_manager, auth_config):
        self.db = db_manager
        self.auth_config = auth_config

    # ------------------------------------------------------------------
    # 种子与初始化
    # ------------------------------------------------------------------
    def ensure_admin(self) -> None:
        """确保种子管理员存在（幂等）."""
        if not self.auth_config.seed_admin:
            return

        username = self.auth_config.admin_username
        existing = self.db.get_user_by_username(username)
        if existing:
            return

        salt, pw_hash = hash_password(self.auth_config.admin_password)
        result = self.db.create_user(
            username=username,
            password_hash=pw_hash,
            salt=salt,
            role="admin",
            display_name="管理员",
        )
        if result["success"]:
            logger.warning(
                "==================================================================\n"
                f"种子管理员已创建: {username} / {self.auth_config.admin_password}\n"
                "⚠️  默认密码仅用于初始化，请尽快在配置中修改 adminPassword 并重新部署！\n"
                "=================================================================="
            )

    # ------------------------------------------------------------------
    # 认证核心
    # ------------------------------------------------------------------
    def authenticate(self, token: str) -> dict | None:
        """校验 token，返回用户字典（不含敏感字段）.

        Returns:
            user dict（id/username/role/display_name），无效或过期返回 None
        """
        if not token:
            return None

        token_hash = hash_token(token)
        token_record = self.db.get_token_record_by_hash(token_hash)
        if not token_record:
            return None

        # 检查过期
        expires_at = token_record["expires_at"]
        if expires_at and expires_at < datetime.utcnow():
            logger.warning("Token 已过期")
            return None

        # 检查用户状态
        user = self.db.get_user_by_id(token_record["user_id"])
        if not user or user.get("status") != "active":
            return None

        # 更新最后使用时间（失败不影响认证）
        self.db.update_token_last_used(token_hash)

        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user.get("display_name", ""),
        }

    # ------------------------------------------------------------------
    # RPC 处理器（由 Gateway 注册）
    # ------------------------------------------------------------------
    async def handle_login(self, params: dict) -> dict:
        """处理 system.login.

        Returns:
            {"success": True, "token": str, "user": dict, "expiresAt": str}
        """
        # 惰性导入，避免 auth -> gateway 包的循环导入（gateway/__init__ 急切导入 server）
        from pyclaw.gateway.rpc import GatewayError

        # 鉴权关闭时返回伪 token + admin 角色（保持老部署可用）
        if not self.auth_config.enabled:
            return {
                "success": True,
                "token": "disabled-auth",
                "user": {"id": 0, "username": "system", "role": "admin", "display_name": "系统"},
                "expiresAt": "",
            }

        username = params.get("username", "")
        password = params.get("password", "")

        if not username or not password:
            raise AuthError(GatewayError.invalid_params("用户名和密码不能为空"))

        record = self.db.get_user_record_by_username(username)
        if not record or record["status"] != "active":
            raise AuthError(GatewayError.auth_invalid("用户名或密码错误"))

        if not verify_password(password, record["salt"], record["password_hash"]):
            raise AuthError(GatewayError.auth_invalid("用户名或密码错误"))

        # 签发 token
        raw_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=self.auth_config.token_ttl_hours)
        result = self.db.issue_token(record["id"], hash_token(raw_token), expires_at)
        if not result["success"]:
            raise AuthError(GatewayError.internal_error("Token 签发失败"))

        user = self.db.get_user_by_id(record["id"])
        return {
            "success": True,
            "token": raw_token,
            "user": user,
            "expiresAt": expires_at.isoformat(),
        }

    async def handle_logout(self, params: dict) -> dict:
        """处理 system.logout — 吊销当前 token."""
        token = params.get("token", "")
        if token:
            self.db.revoke_token(hash_token(token))
        return {"success": True, "message": "已退出登录"}

    async def handle_list_users(self, params: dict) -> list:
        """处理 system.listUsers（admin-only，由 Gateway 集中强制）."""
        return self.db.list_users()

    async def handle_update_user_role(self, params: dict) -> dict:
        """处理 system.updateUserRole（admin-only）.

        params: {"id": int, "role": str}
        """
        user_id = params.get("id")
        role = params.get("role", "")
        if user_id is None:
            return {"success": False, "message": "用户ID不能为空"}
        if role not in ("admin", "member", "operator"):
            return {"success": False, "message": f"无效的角色: {role}"}

        return self.db.update_user_role(user_id, role)
