import { useState, useEffect, useRef, useCallback } from 'react';
import sessionService from '../api/sessionService';
import { removeControlCharacters, isAuthError } from '../api/rpc';

/**
 * WebSocket 连接管理 Hook
 *
 * 职责：
 *  - 维护连接生命周期（connect/disconnect/自动重连到 wsUrl）
 *  - 解析收到的 JSON-RPC 消息并转交给 onMessage 回调（通过 ref 保持最新，避免闭包过期）
 *  - 注入当前登录 token（withAuth）、统一处理鉴权错误（触发 auth:forceLogout 强制登出）
 *  - 提供两种请求入口：sendRequest（Promise 版，addEventListener 不干扰主 onmessage）
 *                       sendWebSocketRequest（callback 版，覆盖式监听，供管理页使用）
 *
 * @param {Function} onMessage 收到消息（已解析为对象）时回调，通常用于按 id 分发到各页面状态
 */
export default function useWebSocket(onMessage) {
  const [ws, setWs] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [wsUrl, setWsUrl] = useState('ws://localhost:18790');

  // ws 引用（避免闭包过期，供异步请求与事件监听使用）
  const wsRef = useRef(null);
  // 连接代际计数器：废弃连接的事件处理器据此自我失效（见 connectWebSocket）
  const wsSeqRef = useRef(0);
  // 始终持有最新的 onMessage 回调，onopen 建连时不必重复绑定
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  // 为 RPC 参数注入当前登录 token
  const withAuth = useCallback((params = {}) => {
    const token = sessionService.getToken();
    return token ? { ...params, token } : params;
  }, []);

  // 检查响应是否携带鉴权错误，若是则清空会话并广播强制登出事件
  const dispatchAuthError = useCallback((response) => {
    if (isAuthError(response)) {
      sessionService.clearSession();
      window.dispatchEvent(new Event('auth:forceLogout'));
      return true;
    }
    return false;
  }, []);

  // 连接方法
  const connectWebSocket = useCallback(() => {
    // 关闭旧的活跃连接（同步置空，避免 StrictMode 双挂载时旧连接在 onopen
    // 前未被关闭而成为孤儿连接）
    const oldWs = wsRef.current;
    if (oldWs) {
      try {
        oldWs.close(1000, '切换连接');
      } catch (e) {
        // 忽略已关闭的连接
      }
      wsRef.current = null;
    }

    // 连接代际计数：每次 connectWebSocket 递增，用于让废弃连接的事件处理器
    // 自我失效（孤儿连接的 onmessage/onclose 不再污染当前状态）
    const seq = ++wsSeqRef.current;

    try {
      const newWs = new WebSocket(wsUrl);
      // 同步登记为当前连接（onopen 前），后续 connectWebSocket 才能关闭它
      wsRef.current = newWs;
      // 判断该连接是否仍是当前活跃连接（代际 + 引用双重校验）
      const isCurrent = () => wsSeqRef.current === seq && wsRef.current === newWs;

      // 连接成功
      newWs.onopen = () => {
        if (!isCurrent()) {
          // 已被更新的连接取代：自毁，避免孤儿连接存活
          try { newWs.close(); } catch (e) { /* 忽略 */ }
          return;
        }
        console.log('WebSocket 连接成功');
        setIsConnected(true);
        setWs(newWs);
        onMessageRef.current?.({
          id: 'sys',
          systemMessage: '系统消息：已成功连接到服务器',
        });
      };
      // 收到消息
      newWs.onmessage = (event) => {
        // 孤儿连接不再处理消息，避免重复/陈旧数据污染
        if (!isCurrent()) return;
        const jsonString = removeControlCharacters(event.data);
        console.log(jsonString);
        let recvMsg;
        try {
          recvMsg = JSON.parse(jsonString);
        } catch (e) {
          console.error('解析 WebSocket 消息失败', e);
          return;
        }
        // 集中处理鉴权错误：强制登出
        if (dispatchAuthError(recvMsg)) {
          return;
        }
        onMessageRef.current?.(recvMsg);
      };
      // 连接关闭
      newWs.onclose = (event) => {
        // 仅当关闭的是当前活跃连接时才更新状态，
        // 避免 StrictMode 双挂载/切换连接时废弃连接的 onclose 误重置连接状态
        if (!isCurrent()) return;
        console.log('WebSocket 连接关闭', event);
        setIsConnected(false);
        if (wsRef.current === newWs) wsRef.current = null;
        setWs(null);
        onMessageRef.current?.({
          id: 'sys',
          systemMessage: `系统消息：连接已关闭 (${event.code})`,
        });
      };

      newWs.onerror = (error) => {
        if (!isCurrent()) return;
        console.error('WebSocket 错误', error);
        onMessageRef.current?.({
          id: 'sys',
          systemMessage: `系统消息：连接出错 - ${error.message}`,
        });
      };
    } catch (error) {
      console.error('创建 WebSocket 失败', error);
      onMessageRef.current?.({
        id: 'sys',
        systemMessage: `系统消息：创建连接失败 - ${error.message}`,
      });
    }
  }, [wsUrl, dispatchAuthError]);

  // 确保存在一条已打开的 WebSocket 连接（登录前按需建连）
  // 已连接则立即 resolve；未连接则新建连接并等待 open / error / close / 超时
  const ensureConnected = useCallback((timeout = 8000) => {
    const sock = wsRef.current;
    if (sock && sock.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      let settled = false;
      let timer = null;
      connectWebSocket();
      const newWs = wsRef.current;
      if (!newWs) {
        reject(new Error('创建 WebSocket 连接失败'));
        return;
      }
      const cleanup = () => {
        clearTimeout(timer);
        newWs.removeEventListener('open', onOpen);
        newWs.removeEventListener('error', onError);
        newWs.removeEventListener('close', onClose);
      };
      const onOpen = () => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve();
      };
      const onError = () => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(new Error('WebSocket 连接失败'));
      };
      const onClose = () => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(new Error('WebSocket 连接已关闭'));
      };
      newWs.addEventListener('open', onOpen);
      newWs.addEventListener('error', onError);
      newWs.addEventListener('close', onClose);
      timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        cleanup();
        // 关闭可能仍处于 CONNECTING 的残留连接
        try { newWs.close(1000, '连接超时'); } catch (e) { /* 忽略 */ }
        reject(new Error('WebSocket 连接超时'));
      }, timeout);
    });
  }, [connectWebSocket]);

  // 断开连接（防御：连接已关闭/未完成时 close 会抛错，忽略）
  const disconnectWebSocket = useCallback(() => {
    const sock = wsRef.current;
    if (sock) {
      try {
        sock.close(1000, '客户端主动断开');
      } catch (e) {
        // 忽略已关闭/未完成的连接
      }
    }
  }, []);

  // 发送WebSocket请求（Promise 版，供 AuthProvider 真实登录/登出等使用）
  // 使用 addEventListener，不覆盖主 onmessage 处理器
  // timeout 可选（毫秒，默认 8000）：试运行 exec 类工具可能超过默认超时，由调用方传更长的值
  const sendRequest = useCallback(
    (method, params, timeout = 8000) => {
      return new Promise((resolve) => {
        const sock = wsRef.current;
        if (!sock || sock.readyState !== WebSocket.OPEN) {
          resolve({ error: { code: -999, message: 'WebSocket 未连接' } });
          return;
        }
        const requestId = 'req_' + Date.now();
        const onMessage = (event) => {
          try {
            const response = JSON.parse(removeControlCharacters(event.data));
            if (response.id === requestId) {
              clearTimeout(timer);
              sock.removeEventListener('message', onMessage);
              // system.login 失败（密码错误返回 -32006）不应触发强制登出：
              // 否则登录页会整页刷新吞掉错误提示；由 AuthProvider.login 自行处理
              if (method !== 'system.login') {
                dispatchAuthError(response);
              }
              resolve(response);
            }
          } catch (err) {
            // 忽略其他消息
          }
        };
        sock.addEventListener('message', onMessage);
        const timer = setTimeout(() => {
          sock.removeEventListener('message', onMessage);
          resolve({ error: { code: -999, message: '请求超时' } });
        }, timeout);
        try {
          sock.send(JSON.stringify({
            id: requestId,
            jsonrpc: '2.0',
            method,
            params: withAuth(params),
          }));
        } catch (e) {
          sock.removeEventListener('message', onMessage);
          resolve({ error: { code: -999, message: '发送失败: ' + e.message } });
        }
      });
    },
    [withAuth, dispatchAuthError]
  );

  // 发送WebSocket请求（callback 版，供管理页表格等使用）
  // 复用 Promise 版 sendRequest（基于 addEventListener，不覆盖主 onmessage）：
  // 修复并发请求互相覆盖监听器、以及请求期间吞掉主消息管道的问题。
  const sendWebSocketRequest = useCallback(
    (method, params, callback, timeout = 8000) => {
      sendRequest(method, params, timeout).then((response) => {
        if (callback) callback(response);
      });
    },
    [sendRequest]
  );

  // 挂载时仅当本地会话有效（已登录）才建立 WebSocket 连接；
  // 未登录时不连接（登录时由 login 流程按需临时建连，成功后保持）
  useEffect(() => {
    if (sessionService.isAuthenticated()) {
      connectWebSocket();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 组件卸载时关闭连接
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, '组件卸载');
      }
    };
  }, []);

  return {
    ws,
    isConnected,
    wsUrl,
    setWsUrl,
    withAuth,
    wsRef,
    connectWebSocket,
    ensureConnected,
    disconnectWebSocket,
    sendRequest,
    sendWebSocketRequest,
  };
}
