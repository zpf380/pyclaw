import './LogsPage.css';

const LogsPage = ({ messages }) => {
    // 清空日志
    const clearLogs = () => {
      if (window.confirm('确定要清空所有消息日志吗？')) {
        // 这里会通过父组件回调清空，实际逻辑在App中
        window.dispatchEvent(new CustomEvent('clearLogs'));
      }
    };
  
    return (
      <div className="logs-page">
        <div className="logs-header">
          <h1>消息日志</h1>
          <button onClick={clearLogs} className="btn clear-btn">清空日志</button>
        </div>
        
        <div className="logs-container">
          {messages.length === 0 ? (
            <div className="empty-logs">暂无消息日志</div>
          ) : (
            <div className="logs-list">
              {messages.map(msg => (
                <div key={msg.id} className={`log-item ${msg.type}`}>
                  <div className="log-meta">
                    <span className="log-time">{msg.time}</span>
                    <span className={`log-type ${msg.type}`}>
                      {msg.type === 'sent' ? '发送' : msg.type === 'received' ? '接收' : '系统'}
                    </span>
                  </div>
                  <div className="log-content">{msg.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };
  
  export default LogsPage;