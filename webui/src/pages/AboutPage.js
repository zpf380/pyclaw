import './AboutPage.css';

const AboutPage = () => {
    return (
      <div className="about-page">
        <h1>关于 WebSocket 客户端</h1>
        
        <div className="about-card">
          <h3>版本信息</h3>
          <p>版本号：v1.0.0</p>
          <p>构建时间：{new Date().toLocaleDateString()}</p>
          <p>基于 React + WebSocket 构建</p>
        </div>
        
        <div className="about-card">
          <h3>功能说明</h3>
          <ul>
            <li>支持 WebSocket 连接/断开</li>
            <li>实时消息收发</li>
            <li>消息日志记录</li>
            <li>响应式界面设计</li>
          </ul>
        </div>
        
        <div className="about-card">
          <h3>技术栈</h3>
          <div className="tech-stack">
            <span>React 18</span>
            <span>React Router 6</span>
            <span>WebSocket API</span>
            <span>CSS3</span>
          </div>
        </div>
      </div>
    );
  };
  
  export default AboutPage;