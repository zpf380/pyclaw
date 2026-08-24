"""Gateway RPC 协议定义

定义 JSON-RPC 2.0 风格的请求和响应格式。
定义RPC请求/响应格式，JSON-RPC 2.0协议实现，GatewayRequest、GatewayResponse类
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import IntEnum
import json
import uuid


class GatewayErrorCode(IntEnum):
    """Gateway RPC 错误码.

    参考 JSON-RPC 2.0 规范：
    -32700: Parse error
    -32600: Invalid Request
    -32601: Method not found
    -32602: Invalid params
    -32603: Internal error
    """
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # 自定义错误码
    AGENT_NOT_FOUND = -32001
    AGENT_EXECUTION_ERROR = -32002
    SESSION_NOT_FOUND = -32003
    CONFIG_ERROR = -32004

    # 鉴权错误码
    AUTH_REQUIRED = -32005
    AUTH_INVALID = -32006
    AUTH_FORBIDDEN = -32007


class GatewayException(Exception):
    """Gateway 异常类.

    用于在 RPC 处理过程中抛出真正的异常。
    """
    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        """初始化异常.

        Args:
            code: 错误码
            message: 错误消息
            data: 额外数据
        """
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)

    def to_error(self) -> "GatewayError":
        """转换为 GatewayError 对象."""
        return GatewayError(code=self.code, message=self.message, data=self.data)

    @classmethod
    def agent_not_found(cls, agent_name: str) -> "GatewayException":
        """创建 'Agent 未找到' 异常（可 raise 的真实异常）."""
        return cls(
            code=GatewayErrorCode.AGENT_NOT_FOUND,
            message=f"Agent not found: {agent_name}"
        )


@dataclass
class GatewayRequest:
    """Gateway RPC 请求.

    遵循 JSON-RPC 2.0 规范：

    Attributes:
        id: 请求 ID（用于关联响应）
        method: 方法名（如 "agent.run", "agent.getInfo"）
        params: 方法参数（字典）
        jsonrpc: JSON-RPC 版本（默认 "2.0"）
    """
    id: str
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"

    def to_json(self) -> str:
        """转换为 JSON 字符串."""
        return json.dumps({
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params
        })

    @classmethod
    def from_json(cls, json_str: str) -> "GatewayRequest":
        """从 JSON 字符串解析请求.

        Args:
            json_str: JSON 字符串

        Returns:
            GatewayRequest 对象

        Raises:
            ValueError: 如果 JSON 格式无效
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        # 验证必需字段
        if "id" not in data:
            raise ValueError("Missing required field: id")
        if "method" not in data:
            raise ValueError("Missing required field: method")

        return cls(
            id=str(data["id"]),
            method=data["method"],
            params=data.get("params", {}),
            jsonrpc=data.get("jsonrpc", "2.0")
        )

    @classmethod
    def create(cls, method: str, params: Optional[Dict[str, Any]] = None) -> "GatewayRequest":
        """创建新请求（自动生成 ID）.

        Args:
            method: 方法名
            params: 参数字典

        Returns:
            新的 GatewayRequest 对象
        """
        return cls(
            id=str(uuid.uuid4()),
            method=method,
            params=params or {}
        )


@dataclass
class GatewayError:
    """Gateway RPC 错误.

    Attributes:
        code: 错误码
        message: 错误消息
        data: 额外错误数据（可选）
    """
    code: int
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        error_dict = {
            "code": self.code,
            "message": self.message
        }
        if self.data is not None:
            error_dict["data"] = self.data
        return error_dict

    @classmethod
    def method_not_found(cls, method: str) -> "GatewayError":
        """创建 '方法未找到' 错误."""
        return cls(
            code=GatewayErrorCode.METHOD_NOT_FOUND,
            message=f"Method not found: {method}"
        )

    @classmethod
    def invalid_params(cls, message: str = "Invalid parameters", data: Optional[Any] = None) -> "GatewayError":
        """创建 '无效参数' 错误."""
        return cls(
            code=GatewayErrorCode.INVALID_PARAMS,
            message=message,
            data=data
        )

    @classmethod
    def internal_error(cls, message: str = "Internal error") -> "GatewayError":
        """创建 '内部错误'."""
        return cls(
            code=GatewayErrorCode.INTERNAL_ERROR,
            message=message
        )

    @classmethod
    def agent_not_found(cls, agent_name: str) -> "GatewayError":
        """创建 'Agent 未找到' 错误."""
        return cls(
            code=GatewayErrorCode.AGENT_NOT_FOUND,
            message=f"Agent not found: {agent_name}"
        )

    @classmethod
    def agent_execution_error(cls, message: str) -> "GatewayError":
        """创建 'Agent 执行错误'."""
        return cls(
            code=GatewayErrorCode.AGENT_EXECUTION_ERROR,
            message=f"Agent execution error: {message}"
        )

    @classmethod
    def auth_required(cls, message: str = "Authentication required") -> "GatewayError":
        """创建 '需要认证' 错误."""
        return cls(
            code=GatewayErrorCode.AUTH_REQUIRED,
            message=message
        )

    @classmethod
    def auth_invalid(cls, message: str = "Invalid or expired token") -> "GatewayError":
        """创建 '认证无效' 错误."""
        return cls(
            code=GatewayErrorCode.AUTH_INVALID,
            message=message
        )

    @classmethod
    def auth_forbidden(cls, message: str = "Permission denied") -> "GatewayError":
        """创建 '权限不足' 错误."""
        return cls(
            code=GatewayErrorCode.AUTH_FORBIDDEN,
            message=message
        )


@dataclass
class GatewayResponse:
    """Gateway RPC 响应.

    遵循 JSON-RPC 2.0 规范：

    Attributes:
        id: 请求 ID（与请求对应）
        result: 结果数据（如果成功）
        error_obj: 错误信息（如果失败，命名为 error_obj 避免与方法冲突）
        jsonrpc: JSON-RPC 版本（默认 "2.0"）
    """
    id: str
    result: Optional[Any] = None
    error_obj: Optional[GatewayError] = None
    jsonrpc: str = "2.0"

    @property
    def error(self) -> Optional[GatewayError]:
        """获取错误对象（属性访问器）."""
        return self.error_obj

    def to_json(self) -> str:
        """转换为 JSON 字符串."""
        response_dict = {
            "jsonrpc": self.jsonrpc,
            "id": self.id
        }

        if self.error_obj is not None:
            response_dict["error"] = self.error_obj.to_dict()
        else:
            response_dict["result"] = self.result

        return json.dumps(response_dict)

    @classmethod
    def from_json(cls, json_str: str) -> "GatewayResponse":
        """从 JSON 字符串解析响应.

        Args:
            json_str: JSON 字符串

        Returns:
            GatewayResponse 对象

        Raises:
            ValueError: 如果 JSON 格式无效
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        # 验证必需字段
        if "id" not in data:
            raise ValueError("Missing required field: id")

        # 解析 error（如果存在）
        error = None
        if "error" in data:
            error_data = data["error"]
            error = GatewayError(
                code=error_data["code"],
                message=error_data["message"],
                data=error_data.get("data")
            )

        return cls(
            id=str(data["id"]),
            result=data.get("result"),
            error_obj=error,
            jsonrpc=data.get("jsonrpc", "2.0")
        )

    @classmethod
    def success(cls, request_id: str, result: Any) -> "GatewayResponse":
        """创建成功响应.

        Args:
            request_id: 请求 ID
            result: 结果数据

        Returns:
            GatewayResponse 对象
        """
        return cls(id=request_id, result=result)

    @classmethod
    def make_error(cls, request_id: str, error: GatewayError) -> "GatewayResponse":
        """创建错误响应.

        Args:
            request_id: 请求 ID
            error: 错误对象

        Returns:
            GatewayResponse 对象
        """
        return cls(id=request_id, error_obj=error)

    def is_success(self) -> bool:
        """检查是否成功."""
        return self.error_obj is None


@dataclass
class GatewayNotification:
    """Gateway 通知（服务器主动推送）.

    通知不需要响应 ID，用于服务器主动推送消息。

    Attributes:
        method: 通知方法名（如 "agent.message", "agent.status"）
        params: 通知参数
        jsonrpc: JSON-RPC 版本（默认 "2.0"）
    """
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"

    def to_json(self) -> str:
        """转换为 JSON 字符串."""
        return json.dumps({
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params
        })

    @classmethod
    def agent_message(cls, agent_name: str, message: str) -> "GatewayNotification":
        """创建 Agent 消息通知."""
        return cls(
            method="agent.message",
            params={
                "agent": agent_name,
                "message": message
            }
        )

    @classmethod
    def agent_status(cls, agent_name: str, status: str) -> "GatewayNotification":
        """创建 Agent 状态通知."""
        return cls(
            method="agent.status",
            params={
                "agent": agent_name,
                "status": status
            }
        )


# 类型别名
JSONType = Dict[str, Any]