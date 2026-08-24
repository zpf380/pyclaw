import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import SettingsPage from './pages/SettingsPage';
import LogsPage from './pages/LogsPage';
import AboutPage from './pages/AboutPage';
import HomePage from './pages/HomePage';
import CapabilityCenterPage from './pages/CapabilityCenterPage';
import SensitiveWordManagementPage from './pages/SensitiveWordManagementPage';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import PrivateRoute from './components/PrivateRoute';
import sessionService from './api/sessionService';
import useWebSocket from './hooks/useWebSocket';
import './App.css';

// 管理员路由守卫：非 admin 角色跳回首页（管理页仅管理员可用）
function RequireAdmin({ children }) {
  const { user } = useAuth();
  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />;
  }
  return children;
}

function App() {
  // 全局状态管理
  const [messages, setMessages] = useState([]);
  const [initialSkills, setInitialSkills] = useState([]);
  const [initialTools, setInitialTools] = useState([]);
  const [inputMessage, setInputMessage] = useState('');

  // 收到 WebSocket 消息的统一分发（id 'sys' 由 hook 注入系统提示，其余为各 RPC 请求 id）
  const handleMessage = (recvMsg) => {
    if (recvMsg.id === 'sys' && recvMsg.systemMessage) {
      addMessage(recvMsg.systemMessage, 'system');
      return;
    }
    if (recvMsg.id === '1001') {
      if (recvMsg.result != null) {
        addMessage(recvMsg.result, 'received');
      }
      return;
    }
    if (recvMsg.id === '2001') {
      setInitialSkills(recvMsg.result);
      return;
    }
    if (recvMsg.id === '3001') {
      setInitialTools(recvMsg.result);
      return;
    }
    if (recvMsg.id === '4002') {
      // 处理历史消息
      if (recvMsg.result && Array.isArray(recvMsg.result)) {
        const historyMessages = recvMsg.result;
        console.log('获取到历史消息:', historyMessages.length, '条');

        // 将历史消息转换为前端需要的格式
        const formattedMessages = historyMessages.map((msg) => ({
          id: msg.id,
          content: msg.content,
          type: msg.type,
          time: msg.time,
          timestamp: msg.timestamp,
        }));

        // 一次性设置所有历史消息
        setMessages(formattedMessages);
      }
    }
  };

  const {
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
  } = useWebSocket(handleMessage);

  // 拉取历史消息（登录成功后调用；需携带 token）
  const loadHistory = (targetWs = wsRef.current) => {
    if (!targetWs || targetWs.readyState !== WebSocket.OPEN) return;
    try {
      targetWs.send(JSON.stringify({
        id: '4002',
        jsonrpc: '2.0',
        method: 'system.listMessages',
        params: withAuth({ session_id: 'default', limit: 100 }),
      }));
    } catch (error) {
      console.error('获取历史消息失败', error);
    }
  };

  // 发送消息（带敏感词过滤）
  const sendMessage = async () => {
    if (!isConnected) {
      addMessage('系统消息：未连接到服务器，无法发送消息', 'system');
      return;
    }

    if (!inputMessage.trim()) {
      addMessage('系统消息：消息内容不能为空', 'system');
      return;
    }

    // 先进行敏感词过滤
    let passed = true;
    let actionTaken = 'pass';

    const sock = wsRef.current;
    if (isConnected && sock) {
      try {
        // 发送敏感词过滤请求（用 Promise 版 sendRequest：基于 addEventListener，
        // 不覆盖主 onmessage，避免超时/响应错位时丢失整个消息管道）
        const filterResp = await sendRequest('system.filterMessageContent', { content: inputMessage }, 4000);
        if (filterResp.error) {
          passed = true;
          actionTaken = 'error';
        } else {
          // passed 缺省时默认放行，避免后端异常响应导致消息被误拦截
          passed = filterResp.result?.passed ?? true;
          actionTaken = filterResp.result?.action_taken || 'pass';
        }
      } catch (error) {
        console.error('敏感词过滤失败:', error);
        // 出错时默认通过
        passed = true;
        actionTaken = 'error';
      }
    }

    // 根据过滤结果处理
    if (!passed) {
      // 消息被拦截，不发送给智能体
      const blockedMessage = {
        id: Date.now(),
        content: `[消息包含敏感词，已被拦截] ${inputMessage}`,
        type: 'system', // 显示为系统消息
        time: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, blockedMessage]);

      // 保存拦截日志到数据库（fire-and-forget，用唯一 id 避免占用 4002 历史管道）
      if (isConnected && sock) {
        try {
          sock.send(JSON.stringify({
            id: 'log_' + Date.now(),
            jsonrpc: '2.0',
            method: 'system.addMessage',
            params: withAuth({
              session_id: 'default',
              content: `[消息被拦截] ${inputMessage}`,
              message_type: 'system',
              sender: 'system',
              receiver: 'user',
            }),
          }));
        } catch (error) {
          console.error('保存拦截消息到数据库失败:', error);
        }
      }

      setInputMessage(''); // 清空输入框
      return; // 停止处理，不发送给智能体
    }

    // 消息通过过滤，正常发送给智能体
    try {
      sock.send(JSON.stringify({
        id: '1001',
        jsonrpc: '2.0',
        method: 'agent.run',
        params: withAuth({
          id: 'user-' + (sessionService.getUserInfo()?.id ?? 'anon'),
          agent: 'AgentLoop',
          message: inputMessage,
        }),
      }));
      addMessage(inputMessage, 'sent');
      setInputMessage(''); // 清空输入框
    } catch (error) {
      console.error('发送消息失败', error);
      addMessage(`系统消息：发送消息失败 - ${error.message}`, 'system');
    }
  };

  // 获取skills列表
  const getSkills = () => {
    const sock = wsRef.current;
    if (!sock || !isConnected) {
      addMessage('系统消息：未连接到服务器，无法获取技能列表', 'system');
      return;
    }
    try {
      sock.send(JSON.stringify({
        id: '2001',
        jsonrpc: '2.0',
        method: 'system.listSkills',
        params: withAuth({}),
      }));
    } catch (error) {
      console.error('获取技能列表失败', error);
      addMessage('系统消息：获取技能列表失败', 'system');
    }
  };

  // 获取tools列表
  const getTools = () => {
    const sock = wsRef.current;
    if (!sock || !isConnected) {
      addMessage('系统消息：未连接到服务器，无法获取工具列表', 'system');
      return;
    }
    try {
      sock.send(JSON.stringify({
        id: '3001',
        jsonrpc: '2.0',
        method: 'agent.listTools',
        params: withAuth({
          id: 'user-' + (sessionService.getUserInfo()?.id ?? 'anon'),
          agent: 'AgentLoop',
          message: '',
        }),
      }));
    } catch (error) {
      console.error('获取工具列表失败', error);
      addMessage('系统消息：获取工具列表失败', 'system');
    }
  };

  // 添加消息（带敏感词过滤）
  const addMessage = async (content, type) => {
    if (content === '') {
      return;
    }

    // 先进行敏感词过滤
    let filteredContent = content;
    let passed = true;
    let actionTaken = 'pass';

    const sock = wsRef.current;
    if (isConnected && sock) {
      try {
        // 发送敏感词过滤请求（用 Promise 版 sendRequest：不覆盖主 onmessage，
        // 避免超时/响应错位时丢失整个消息管道）
        const filterResp = await sendRequest('system.filterMessageContent', { content }, 4000);
        if (filterResp.error) {
          passed = true;
          filteredContent = content;
          actionTaken = 'error';
        } else {
          // passed 缺省时默认放行，避免后端异常响应导致消息被误拦截
          passed = filterResp.result?.passed ?? true;
          filteredContent = filterResp.result?.filtered_content || content;
          actionTaken = filterResp.result?.action_taken || 'pass';
        }
      } catch (error) {
        console.error('敏感词过滤失败:', error);
        // 出错时默认通过
        passed = true;
        filteredContent = content;
        actionTaken = 'error';
      }
    }

    // 根据过滤结果处理
    if (!passed) {
      // 消息被拦截
      const blockedMessage = {
        id: Date.now(),
        content: filteredContent,
        type: 'system', // 显示为系统消息
        time: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, blockedMessage]);

      // 保存拦截日志到数据库（fire-and-forget，用唯一 id 避免占用 4002 历史管道）
      if (isConnected && sock) {
        try {
          sock.send(JSON.stringify({
            id: 'log_' + Date.now(),
            jsonrpc: '2.0',
            method: 'system.addMessage',
            params: withAuth({
              session_id: 'default',
              content: `[消息被拦截] ${content}`,
              message_type: 'system',
              sender: 'system',
              receiver: 'user',
            }),
          }));
        } catch (error) {
          console.error('保存拦截消息到数据库失败:', error);
        }
      }

      return; // 停止处理
    }

    // 消息通过过滤，正常显示
    const newMessage = {
      id: Date.now(),
      content: filteredContent,
      type, // sent:发送, received:接收, system:系统
      time: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, newMessage]);

    // 将消息保存到数据库（fire-and-forget，用唯一 id，不占用 4001/4002 响应管道）
    if (isConnected && sock) {
      try {
        sock.send(JSON.stringify({
          id: 'save_' + Date.now(),
          jsonrpc: '2.0',
          method: 'system.addMessage',
          params: withAuth({
            session_id: 'default',
            content: filteredContent,
            message_type: type,
            sender: type === 'sent' ? 'user' : 'system',
            receiver: type === 'sent' ? 'system' : 'user',
          }),
        }));
      } catch (error) {
        console.error('保存消息到数据库失败:', error);
      }
    }
  };

  // 清空日志
  const clearLogs = () => {
    setMessages([]);
  };

  // 监听清空日志事件
  useEffect(() => {
    const handleClearLogs = () => clearLogs();
    window.addEventListener('clearLogs', handleClearLogs);
    return () => window.removeEventListener('clearLogs', handleClearLogs);
  }, []);

  // 登录成功后拉取历史消息
  useEffect(() => {
    const onLoggedIn = () => loadHistory(wsRef.current);
    window.addEventListener('auth:loggedIn', onLoggedIn);
    return () => window.removeEventListener('auth:loggedIn', onLoggedIn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthProvider
      sendRequest={sendRequest}
      ensureConnected={ensureConnected}
      disconnectWebSocket={disconnectWebSocket}
    >
      <Router>
        <div className="app-wrapper">
          {/* 侧边栏 - 全局共享 */}
          <Sidebar
            isConnected={isConnected}
            wsUrl={wsUrl}
          />

          {/* 主内容区域 - 路由容器 */}
          <div className="main-content">
            <div className="app-container">
              <Routes>
                {/* 登录页 */}
                <Route path="/login" element={<LoginPage />} />
                {/* 控制台首页（显示智能体状态） */}
                <Route
                  path="/"
                  element={
                    <PrivateRoute><HomePage isConnected={isConnected} /></PrivateRoute>
                  }
                />
                {/* 消息中心放到 /chat */}
                <Route
                  path="/chat"
                  element={
                    <PrivateRoute>
                      <ChatPage
                        isConnected={isConnected}
                        sendMessage={sendMessage}
                        messages={messages}
                        inputMessage={inputMessage}
                        setInputMessage={setInputMessage}
                      />
                    </PrivateRoute>
                  }
                />
                {/* 连接设置 */}
                <Route
                  path="/settings"
                  element={
                    <PrivateRoute>
                      <SettingsPage
                        wsUrl={wsUrl}
                        setWsUrl={setWsUrl}
                        isConnected={isConnected}
                        connectWebSocket={connectWebSocket}
                        disconnectWebSocket={disconnectWebSocket}
                      />
                    </PrivateRoute>
                  }
                />
                {/* 能力中心：技能 + 工具统一管理入口 */}
                <Route path="/capabilities" element={<PrivateRoute><RequireAdmin><CapabilityCenterPage sendWebSocketRequest={sendWebSocketRequest} sendRequest={sendRequest} isConnected={isConnected} /></RequireAdmin></PrivateRoute>} />
                {/* 旧路由重定向到能力中心 */}
                <Route path="/skills" element={<Navigate to="/capabilities" replace />} />
                <Route path="/tools" element={<Navigate to="/capabilities" replace />} />
                <Route path="/sensitive-words" element={<PrivateRoute><RequireAdmin><SensitiveWordManagementPage sendWebSocketRequest={sendWebSocketRequest} isConnected={isConnected} /></RequireAdmin></PrivateRoute>} />
                {/* 消息日志 */}
                <Route
                  path="/logs"
                  element={<PrivateRoute><LogsPage messages={messages} /></PrivateRoute>}
                />

                {/* 关于页面 */}
                <Route
                  path="/about"
                  element={<AboutPage />}
                />
              </Routes>
            </div>
          </div>
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;
