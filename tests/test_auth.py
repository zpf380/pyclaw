# -*- coding: utf-8 -*-
"""认证服务与密码哈希测试."""
import pytest
from datetime import datetime, timedelta

from pyclaw.auth.service import (
    AuthService,
    AuthError,
    hash_password,
    verify_password,
    hash_token,
)
from pyclaw.config.schema import AuthConfig


def test_hash_verify_password():
    salt, pw_hash = hash_password("secret123")
    assert verify_password("secret123", salt, pw_hash)
    assert not verify_password("wrong", salt, pw_hash)


def test_hash_password_random_salt():
    s1, h1 = hash_password("same")
    s2, h2 = hash_password("same")
    assert s1 != s2 and h1 != h2  # 随机盐


def test_hash_token():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")


@pytest.fixture()
def auth(db_manager):
    config = AuthConfig(admin_username="admin", admin_password="admin123")
    return AuthService(db_manager, config)


@pytest.mark.asyncio
async def test_ensure_admin_idempotent(auth):
    auth.ensure_admin()
    auth.ensure_admin()
    users = [u["username"] for u in auth.db.list_users()]
    assert users.count("admin") == 1


@pytest.mark.asyncio
async def test_handle_login_success(auth):
    auth.ensure_admin()
    result = await auth.handle_login({"username": "admin", "password": "admin123"})
    assert result["success"]
    assert result["token"]
    assert result["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_handle_login_wrong_password(auth):
    auth.ensure_admin()
    with pytest.raises(AuthError):
        await auth.handle_login({"username": "admin", "password": "nope"})


@pytest.mark.asyncio
async def test_handle_login_missing_fields(auth):
    auth.ensure_admin()
    with pytest.raises(AuthError):
        await auth.handle_login({"username": "", "password": ""})


@pytest.mark.asyncio
async def test_authenticate_valid_and_invalid(auth):
    auth.ensure_admin()
    result = await auth.handle_login({"username": "admin", "password": "admin123"})
    token = result["token"]

    user = auth.authenticate(token)
    assert user is not None and user["role"] == "admin"

    assert auth.authenticate("bad-token") is None
    assert auth.authenticate("") is None


@pytest.mark.asyncio
async def test_logout_revokes(auth):
    auth.ensure_admin()
    result = await auth.handle_login({"username": "admin", "password": "admin123"})
    token = result["token"]
    assert auth.authenticate(token) is not None
    await auth.handle_logout({"token": token})
    assert auth.authenticate(token) is None


def test_expired_token(db_manager):
    auth = AuthService(db_manager, AuthConfig())
    auth.ensure_admin()
    uid = db_manager.get_user_by_username("admin")["id"]
    db_manager.issue_token(uid, hash_token("old"), datetime.utcnow() - timedelta(hours=1))
    assert auth.authenticate("old") is None
