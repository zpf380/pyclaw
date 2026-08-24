import React, { createContext, useContext, useState, useEffect } from 'react';
import sessionService from '../api/sessionService';

// 创建上下文
const AuthContext = createContext();

// 自定义Hook，方便组件使用
export const useAuth = () => {
  return useContext(AuthContext);
};

// 上下文提供者组件
// ensureConnected：登录前按需建立 WebSocket 连接（未登录不常驻连接）
// disconnectWebSocket：登出/强制登出后断开连接
export const AuthProvider = ({ children, sendRequest, ensureConnected, disconnectWebSocket }) => {
  // 登录状态
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  // 用户信息
  const [user, setUser] = useState(null);
  // 加载状态
  const [loading, setLoading] = useState(true);

  // 初始化检查登录状态
  useEffect(() => {
    const initAuth = () => {
      try {
        const isAuth = sessionService.isAuthenticated();
        setIsAuthenticated(isAuth);

        if (isAuth) {
          setUser(sessionService.getUserInfo());
        }
      } catch (error) {
        console.error('初始化认证状态失败:', error);
        setIsAuthenticated(false);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();

    // 定时检查Session是否过期（每分钟检查一次）
    const interval = setInterval(() => {
      const currentAuth = sessionService.isAuthenticated();
      if (currentAuth !== isAuthenticated) {
        setIsAuthenticated(currentAuth);
        setUser(currentAuth ? sessionService.getUserInfo() : null);
      }
    }, 60 * 1000);

    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // 监听后端返回的鉴权错误（token 缺失/无效/权限不足）触发的强制登出
  useEffect(() => {
    const onForceLogout = () => {
      sessionService.clearSession();
      setIsAuthenticated(false);
      setUser(null);
      // token 失效强制登出：断开连接
      if (disconnectWebSocket) disconnectWebSocket();
      window.location.href = '/login';
    };
    window.addEventListener('auth:forceLogout', onForceLogout);
    return () => window.removeEventListener('auth:forceLogout', onForceLogout);
    // disconnectWebSocket 由 useWebSocket 的 useCallback([]) 提供，引用稳定
  }, [disconnectWebSocket]);

  // 登录：调用后端 system.login，成功后保存真实 token 与用户信息
  // 未登录时不保持 WebSocket 连接；仅在本登录请求期间按需临时建连
  const login = async (username, password) => {
    if (!sendRequest) {
      throw new Error('WebSocket 未连接，无法登录');
    }

    // 登录请求需要一条 WebSocket 连接承载
    if (ensureConnected) {
      try {
        await ensureConnected();
      } catch (e) {
        throw new Error(`无法连接服务器：${e.message}`);
      }
    }

    const response = await sendRequest('system.login', { username, password });
    if (response.error) {
      // 登录失败：关闭本次临时连接，回到"未登录不连接"状态
      if (disconnectWebSocket) disconnectWebSocket();
      throw new Error(response.error.message || '用户名或密码错误');
    }

    const { token, user: userInfo } = response.result;
    sessionService.setSession(userInfo, token);

    // 更新状态
    setIsAuthenticated(true);
    setUser(userInfo);

    // 通知 App 登录成功，以便拉取历史消息等
    window.dispatchEvent(new Event('auth:loggedIn'));

    return { success: true, userInfo, token };
  };

  // 登出：best-effort 调用后端吊销 token，然后清理本地会话
  const logout = async () => {
    try {
      const token = sessionService.getToken();
      if (sendRequest && token) {
        await sendRequest('system.logout', { token });
      }
    } catch (error) {
      console.warn('调用 system.logout 失败（忽略）:', error);
    }

    // 清除Session
    sessionService.clearSession();
    // 更新状态
    setIsAuthenticated(false);
    setUser(null);
    // 登出后断开 WebSocket，恢复"未登录不连接"状态
    if (disconnectWebSocket) disconnectWebSocket();
    // 跳转到登录页
    window.location.href = '/login';
  };

  // 刷新Session
  const refreshSession = () => {
    sessionService.refreshSession();
  };

  // 上下文值
  const authValue = {
    isAuthenticated,
    user,
    loading,
    login,
    logout,
    refreshSession
  };

  return (
    <AuthContext.Provider value={authValue}>
      {!loading && children}
    </AuthContext.Provider>
  );
};
