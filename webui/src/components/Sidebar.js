import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Sidebar.css';

const Sidebar = ({ isConnected, wsUrl }) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  return (
    <div className="sidebar">
      {/* 侧边栏头部 */}
      <div className="sidebar-header">
        <h2>WebSocket 客户端</h2>
      </div>

      {/* 连接状态卡片 */}
      <div className="connection-status-card">
        <h3>连接状态</h3>
        <div className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
          <span className="dot"></span>
          {/*{isConnected ? '已连接' : '未连接'}*/}
        </div>
        {isConnected && (
          <div className="connected-url">
            <span>地址：</span>
            <span className="url-text">{wsUrl}</span>
          </div>
        )}
      </div>

      {/* 导航菜单 - 集成路由 */}
      <div className="sidebar-menu">
        <h3>功能菜单</h3>
        <ul>
        <li>
            <NavLink 
              to="/" 
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
              end
            >
              <span className="menu-icon">🏠</span>
              <span className="menu-text">控制台首页</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/chat" 
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
              end
            >
              <span className="menu-icon">💬</span>
              <span className="menu-text">消息中心</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/settings" 
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <span className="menu-icon">⚙️</span>
              <span className="menu-text">连接设置</span>
            </NavLink>
          </li>
          {isAdmin && (
          <li>
            <NavLink
              to="/capabilities"
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <span className="menu-icon">🧩</span>
              <span className="menu-text">能力中心</span>
            </NavLink>
          </li>
          )}
          {isAdmin && (
          <li>
            <NavLink
              to="/sensitive-words"
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <span className="menu-icon">🚫</span>
              <span className="menu-text">敏感词管理</span>
            </NavLink>
          </li>
          )}
          <li>
            <NavLink 
              to="/logs" 
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <span className="menu-icon">📜</span>
              <span className="menu-text">消息日志</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/about" 
              className={({ isActive }) => `menu-item ${isActive ? 'active' : ''}`}
            >
              <span className="menu-icon">ℹ️</span>
              <span className="menu-text">关于</span>
            </NavLink>
          </li>
        </ul>
      </div>

      {/* 侧边栏底部 */}
      <div className="sidebar-footer">
        <p>React WebSocket Client</p>
        <p className="version">v1.0.0</p>
      </div>
    </div>
  );
};

export default Sidebar;