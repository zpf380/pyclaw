import React from 'react';
import { useAuth } from '../context/AuthContext';
import './HomePage.css';

const HomePage = ({ isConnected }) => {
  const { user, logout, refreshSession } = useAuth();
  return (
    <div className="home-page">
      <div className="page-header">
        <h1>控制台首页</h1>
        <p>Websocket 智能体</p>
      </div>
      <div className="home-welcome">
        <h2>欢迎回来，{user?.username}！</h2>
        <div className="home-actions">
          <button onClick={refreshSession} className="btn primary-btn">
            刷新会话
          </button>
          <button onClick={logout} className="btn danger-btn">
            安全退出
          </button>
        </div>
      </div>
      <div>
           
      
    </div>
      {/* 智能体状态卡片 */}
      <div className="agent-status-card">
        <div className="card-title">
          <h2>智能体运行状态</h2>
        </div>

        <div className="agent-status">
          <div className={`status-indicator ${isConnected ? 'online' : 'offline'}`}>
            <span className="status-dot"></span>
            <span className="status-text">
              {/*{isConnected ? '已连接 · 运行中' : '未连接 · 已停止'}*/}
            </span>
          </div>
        </div>

        <div className="agent-info">
          <div className="info-item">
            <label>连接状态</label>
            <span className={isConnected ? 'text-success' : 'text-danger'}>
              {isConnected ? '正常' : '断开'}
            </span>
          </div>
          <div className="info-item">
            <label>服务类型</label>
            <span>WebSocket 智能代理</span>
          </div>
          <div className="info-item">
            <label>运行模式</label>
            <span>客户端模式</span>
          </div>
          <div className="info-item">
            <label>当前版本</label>
            <span>v1.0.0</span>
          </div>
        </div>
      </div>

      {/*/!* 快捷入口 *!/*/}
      {/*<div className="quick-entry">*/}
      {/*  <h3>快捷操作</h3>*/}
      {/*  <div className="entry-grid">*/}
      {/*    <div className="entry-item">*/}
      {/*      <div className="icon">💬</div>*/}
      {/*      <p>消息中心</p>*/}
      {/*    </div>*/}
      {/*    <div className="entry-item">*/}
      {/*      <div className="icon">🔧</div>*/}
      {/*      <p>工具管理</p>*/}
      {/*    </div>*/}
      {/*    <div className="entry-item">*/}
      {/*      <div className="icon">🧩</div>*/}
      {/*      <p>技能管理</p>*/}
      {/*    </div>*/}
      {/*    <div className="entry-item">*/}
      {/*      <div className="icon">⚙️</div>*/}
      {/*      <p>连接设置</p>*/}
      {/*    </div>*/}
      {/*  </div>*/}
      {/*</div>*/}
    </div>
  );
};

export default HomePage;