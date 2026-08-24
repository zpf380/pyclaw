import { useState } from 'react';
import SkillManagementPage from './SkillManagementPage';
import ToolManagementPage from './ToolManagementPage';
import './CapabilityCenterPage.css';

/**
 * 能力中心 - 统一管理技能与工具
 *
 * 底层机制保持不变（技能注入 prompt、工具注入 tools schema），仅在此
 * 用 Tab 把两个管理页收拢到同一入口。
 */
const CapabilityCenterPage = ({ sendWebSocketRequest, sendRequest, isConnected }) => {
  const [activeTab, setActiveTab] = useState('skills');

  return (
    <div className="capability-center-page">
      {/* Tab 导航 */}
      <div className="cc-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'skills'}
          className={`cc-tab ${activeTab === 'skills' ? 'active' : ''}`}
          onClick={() => setActiveTab('skills')}
        >
          🧩 技能
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'tools'}
          className={`cc-tab ${activeTab === 'tools' ? 'active' : ''}`}
          onClick={() => setActiveTab('tools')}
        >
          🔧 工具
        </button>
      </div>

      {/* Tab 内容（切换时重新挂载，各自拉取最新列表） */}
      <div className="cc-content">
        {activeTab === 'skills' ? (
          <SkillManagementPage
            sendWebSocketRequest={sendWebSocketRequest}
            sendRequest={sendRequest}
            isConnected={isConnected}
          />
        ) : (
          <ToolManagementPage
            sendWebSocketRequest={sendWebSocketRequest}
            sendRequest={sendRequest}
            isConnected={isConnected}
          />
        )}
      </div>
    </div>
  );
};

export default CapabilityCenterPage;
