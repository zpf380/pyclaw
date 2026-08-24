const SettingsPage = ({ 
    wsUrl, 
    setWsUrl, 
    isConnected, 
    connectWebSocket, 
    disconnectWebSocket
  }) => {
    return (
      <div className="settings-page">
        <h1>连接设置</h1>
        
        <div className="settings-card">
          <h3>WebSocket 服务器配置</h3>
          
          <div className="form-group">
            <label htmlFor="wsUrl">服务器地址：</label>
            <input
              id="wsUrl"
              type="text"
              value={wsUrl}
              onChange={(e) => setWsUrl(e.target.value)}
              placeholder="例如：ws://localhost:18790"
              className="form-input"
              disabled={isConnected}
            />
          </div>
          
          <div className="settings-actions">
            <button 
              onClick={connectWebSocket} 
              disabled={isConnected}
              className="btn connect-btn"
            >
              连接
            </button>
            <button 
              onClick={disconnectWebSocket} 
              disabled={!isConnected}
              className="btn disconnect-btn"
            >
              断开
            </button>
          
          </div>
          
          <div className="connection-status">
            <span className="status-label">当前状态：</span>
            <span className={`status-value ${isConnected ? 'connected' : 'disconnected'}`}>
              {isConnected ? '已连接' : '未连接'}
            </span>
          </div>
        </div>
        
        <div className="settings-card tips-card">
          <h3>使用提示</h3>
          <ul>
            <li>请确保输入正确的 WebSocket 服务器地址</li>
            <li>连接成功后，可在消息中心收发消息</li>
            <li>断开连接后，所有未发送的消息将丢失</li>
          </ul>
        </div>
      </div>
    );
  };
  
  export default SettingsPage;