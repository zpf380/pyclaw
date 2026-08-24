# -*- coding: utf-8 -*-
"""Gateway RPC 协议（请求/响应序列化与错误码）测试."""
import json

from pyclaw.gateway.rpc import (
    GatewayRequest,
    GatewayResponse,
    GatewayError,
    GatewayErrorCode,
    GatewayException,
    GatewayNotification,
)


class TestGatewayRequest:
    def test_roundtrip(self):
        req = GatewayRequest.create("system.status", {"a": 1})
        parsed = GatewayRequest.from_json(req.to_json())
        assert parsed.method == "system.status"
        assert parsed.params == {"a": 1}
        assert parsed.id == req.id

    def test_missing_id(self):
        import pytest
        with pytest.raises(ValueError):
            GatewayRequest.from_json(json.dumps({"method": "x"}))

    def test_invalid_json(self):
        import pytest
        with pytest.raises(ValueError):
            GatewayRequest.from_json("{not json")


class TestGatewayResponse:
    def test_success(self):
        resp = GatewayResponse.success("abc", {"ok": True})
        data = json.loads(resp.to_json())
        assert data["result"] == {"ok": True}
        assert "error" not in data
        assert resp.is_success()

    def test_error(self):
        err = GatewayError.internal_error("boom")
        resp = GatewayResponse.make_error("abc", err)
        data = json.loads(resp.to_json())
        assert data["error"]["code"] == GatewayErrorCode.INTERNAL_ERROR
        assert data["error"]["message"] == "boom"
        assert not resp.is_success()

    def test_roundtrip(self):
        resp = GatewayResponse.success("abc", [1, 2])
        parsed = GatewayResponse.from_json(resp.to_json())
        assert parsed.id == "abc" and parsed.result == [1, 2]


class TestGatewayError:
    def test_factories(self):
        assert GatewayError.method_not_found("x").code == GatewayErrorCode.METHOD_NOT_FOUND
        assert GatewayError.auth_required().code == GatewayErrorCode.AUTH_REQUIRED
        assert GatewayError.auth_invalid().code == GatewayErrorCode.AUTH_INVALID
        assert GatewayError.auth_forbidden().code == GatewayErrorCode.AUTH_FORBIDDEN
        assert GatewayError.agent_not_found("a").code == GatewayErrorCode.AGENT_NOT_FOUND


class TestGatewayException:
    def test_to_error(self):
        exc = GatewayException.agent_not_found("AgentLoop")
        err = exc.to_error()
        assert err.code == GatewayErrorCode.AGENT_NOT_FOUND
        assert "AgentLoop" in err.message


class TestGatewayNotification:
    def test_agent_message(self):
        n = GatewayNotification.agent_message("AgentLoop", "hi")
        data = json.loads(n.to_json())
        assert data["method"] == "agent.message"
        assert data["params"] == {"agent": "AgentLoop", "message": "hi"}
