// WebSocket RPC 通用工具（与 socket 实例无关的纯工具函数）

// 后端 GatewayErrorCode 中表示鉴权失败的错误码（缺失/无效 token、权限不足）
export const AUTH_ERROR_CODES = [-32005, -32006, -32007];

// 过滤消息中的控制字符（避免对端返回内容里的控制字符导致 JSON.parse 失败）
export function removeControlCharacters(str) {
  return str.replace(/[\x00-\x1F\x7F\x80-\x9F]/g, '');
}

// 判断 RPC 响应是否携带鉴权错误（调用方应据此触发强制登出）
export function isAuthError(response) {
  return !!(response && response.error && AUTH_ERROR_CODES.includes(response.error.code));
}
