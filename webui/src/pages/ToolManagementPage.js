import { useState, useEffect, useRef } from 'react';
import './ToolManagementPage.css';

// 分类展示名（仅 UI 映射，分类本身来自后端真实数据）
const CATEGORY_LABELS = {
  system: '系统工具',
  web: '网络工具',
  message: '消息工具',
  custom: '自定义工具'
};

const ToolManagementPage = ({sendWebSocketRequest, sendRequest, isConnected}) => {
  // 核心状态
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [modalVisible, setModalVisible] = useState(false);
  const [configModalVisible, setConfigModalVisible] = useState(false);
  const [currentTool, setCurrentTool] = useState(null);
  const [isEditMode, setIsEditMode] = useState(false);
  // 试运行弹窗状态
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testArgsText, setTestArgsText] = useState('{}');
  const [testResult, setTestResult] = useState(null);
  const [testRunning, setTestRunning] = useState(false);
  const [aiPrompt, setAiPrompt] = useState(''); // AI 生成的需求描述
  const [aiGenerating, setAiGenerating] = useState(false); // AI 生成中

  // 获取工具列表
  const getTools = () => {
    if (!isConnected) return;

    setLoading(true);
    sendWebSocketRequest('agent.listTools', {}, (response) => {
      setLoading(false);
      if (response.result) {
        setTools(response.result);
      } else {
        console.error('获取工具列表失败:', response.error);
        setTools([]);
      }
    });
  };

  // 分类来源：从真实工具数据推导（无数据时仅 UI 兜底选项）
  const categories = Array.isArray(tools)
    ? [...new Set(tools.map(t => t.category).filter(Boolean))]
    : [];
  const allCategories = categories.length > 0
    ? categories
    : ['system', 'web', 'message', 'custom'];

  // 是否为内置工具（不可删除/改名，只能启停/改描述/看配置）
  const isBuiltin = (tool) => tool && tool.builtin === true;

  // 页面加载时获取工具列表
  useEffect(() => {
    getTools();
  }, [isConnected]);

  // 表单数据
  const [formData, setFormData] = useState({
    name: '',
    category: 'custom',
    version: '1.0.0',
    description: '',
    author: '自定义',
    config: {}
  });

  // 配置表单（command/script/parameters 分字段）
  const [configForm, setConfigForm] = useState({
    command: '',
    script: '',
    parametersText: ''
  });

  const modalRef = useRef(null);
  const configModalRef = useRef(null);
  const testModalRef = useRef(null);

  // 筛选工具列表
  const filteredTools = Array.isArray(tools) ? tools.filter(tool => {
    const matchesSearch = tool.name.toLowerCase().includes(searchText.toLowerCase()) ||
                          tool.description.toLowerCase().includes(searchText.toLowerCase()) ||
                          tool.version.includes(searchText);
    const matchesCategory = categoryFilter === 'all' || tool.category === categoryFilter;
    const matchesStatus = statusFilter === 'all' || tool.status === statusFilter;
    return matchesSearch && matchesCategory && matchesStatus;
  }) : [];

  // 打开新增工具弹窗
  const openAddModal = () => {
    setIsEditMode(false);
    setFormData({
      name: '',
      category: 'custom',
      version: '1.0.0',
      description: '',
      author: '自定义',
      config: {}
    });
    setModalVisible(true);
  };

  // 打开编辑工具弹窗（内置工具仅允许改描述，name 禁改）
  const openEditModal = (tool) => {
    setIsEditMode(true);
    setCurrentTool(tool);
    setFormData({
      name: tool.name,
      category: tool.category,
      version: tool.version,
      description: tool.description,
      author: tool.author,
      config: { ...tool.config }
    });
    setModalVisible(true);
  };

  // 打开配置编辑弹窗（内置只读展示 parameters，自定义三字段）
  const openConfigModal = (tool) => {
    setCurrentTool(tool);
    setAiPrompt('');
    const cfg = (tool.config && typeof tool.config === 'object') ? tool.config : {};
    setConfigForm({
      command: typeof cfg.command === 'string' ? cfg.command : '',
      script: typeof cfg.script === 'string' ? cfg.script : '',
      parametersText: cfg.parameters ? JSON.stringify(cfg.parameters, null, 2) : ''
    });
    setConfigModalVisible(true);
  };

  // 打开试运行弹窗
  const openTestModal = (tool) => {
    setCurrentTool(tool);
    setTestArgsText('{}');
    setTestResult(null);
    setTestRunning(false);
    setTestModalVisible(true);
  };

  // 关闭弹窗
  const closeModal = () => {
    setModalVisible(false);
    setCurrentTool(null);
  };

  const closeConfigModal = () => {
    setConfigModalVisible(false);
    setCurrentTool(null);
    setAiGenerating(false);
  };

  const closeTestModal = () => {
    setTestModalVisible(false);
    setCurrentTool(null);
    setTestResult(null);
    setTestRunning(false);
  };

  // 处理工具表单提交（真实 RPC：新增/编辑）
  const handleSubmit = () => {
    if (isEditMode && isBuiltin(currentTool)) {
      // 内置工具保护：仅允许改描述（后端同样仅放行 description/status）
      if (!formData.description.trim()) {
        alert('工具描述不能为空');
        return;
      }
      sendWebSocketRequest('agent.updateTool', {
        id: currentTool.id,
        description: formData.description
      }, (response) => {
        if (response.result?.success) {
          getTools();
          closeModal();
        } else {
          alert(response.result?.message || response.error?.message || '操作失败');
        }
      });
      return;
    }

    if (!formData.name.trim()) {
      alert('工具名称不能为空');
      return;
    }

    const payload = {
      name: formData.name.trim(),
      category: formData.category,
      version: formData.version,
      description: formData.description,
      author: formData.author,
      config: formData.config || {}
    };

    const method = isEditMode ? 'agent.updateTool' : 'agent.addTool';
    if (isEditMode) payload.id = currentTool.id;

    sendWebSocketRequest(method, payload, (response) => {
      if (response.result?.success) {
        getTools();
        closeModal();
      } else {
        alert(response.result?.message || response.error?.message || '操作失败');
      }
    });
  };

  // AI 生成工具配置（结果填回 configForm，由人工确认后再保存）
  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) {
      alert('请先描述你想要的工具需求');
      return;
    }
    setAiGenerating(true);
    try {
      const response = await sendRequest('system.generateTool', {
        prompt: aiPrompt,
        toolName: currentTool?.name || '',
        toolDescription: currentTool?.description || ''
      }, 60000);
      const data = response.result;
      if (response.error || (data && data.success === false)) {
        alert(data?.message || response.error?.message || 'AI 生成失败');
        return;
      }
      if (data && data.success && data.tool) {
        const { command, script, parameters } = data.tool;
        setConfigForm((prev) => ({
          ...prev,
          command: command || prev.command,
          script: script || prev.script,
          parametersText: parameters
            ? JSON.stringify(parameters, null, 2)
            : prev.parametersText
        }));
      } else {
        alert('AI 生成失败，请稍后重试');
      }
    } catch (err) {
      console.error('AI 生成工具配置失败:', err);
      alert('AI 生成工具配置失败，请稍后重试');
    } finally {
      setAiGenerating(false);
    }
  };

  // 保存工具配置（command/script/parameters 三字段组装 config）
  const saveConfig = () => {
    // 参数 Schema 必须是合法 JSON
    let parameters = null;
    if (configForm.parametersText.trim()) {
      try {
        parameters = JSON.parse(configForm.parametersText);
      } catch (e) {
        alert('参数 Schema 不是合法的 JSON，请检查格式');
        return;
      }
    }

    // 至少需要 command 或 script 之一
    const command = configForm.command.trim();
    const script = configForm.script.trim();
    if (!command && !script) {
      alert('请至少填写「命令模板」或「脚本」之一');
      return;
    }

    // 组装 config：保留未在三字段中的既有键（避免误删额外配置）
    const prev = (currentTool.config && typeof currentTool.config === 'object')
      ? { ...currentTool.config } : {};
    delete prev.command;
    delete prev.script;
    delete prev.parameters;
    if (command) prev.command = command;
    if (script) prev.script = script;
    if (parameters !== null) prev.parameters = parameters;

    sendWebSocketRequest('agent.updateTool', {
      id: currentTool.id,
      config: prev
    }, (response) => {
      if (response.result?.success) {
        getTools();
        closeConfigModal();
      } else {
        alert(response.result?.message || response.error?.message || '保存失败');
      }
    });
  };

  // 切换工具状态（真实 RPC：仅更新 status，启停持久化到 DB）
  const toggleToolStatus = (tool) => {
    const nextStatus = tool.status === 'active' ? 'inactive' : 'active';
    sendWebSocketRequest('agent.updateTool', {
      id: tool.id,
      status: nextStatus
    }, (response) => {
      if (response.result?.success) {
        getTools();
      } else {
        alert(response.result?.message || response.error?.message || '操作失败');
      }
    });
  };

  // 删除工具（真实 RPC；内置工具后端拒绝，前端也隐藏按钮）
  const deleteTool = (id) => {
    if (window.confirm('确定要删除该工具吗？此操作不可恢复！')) {
      sendWebSocketRequest('agent.deleteTool', { id }, (response) => {
        if (response.result?.success) {
          getTools();
        } else {
          alert(response.result?.message || response.error?.message || '删除失败');
        }
      });
    }
  };

  // 试运行工具（agent.testTool；exec 类可能运行较久，用 30s 超时）
  const runTest = async () => {
    let args;
    try {
      args = JSON.parse(testArgsText);
    } catch (e) {
      alert('参数必须是合法的 JSON 对象，如 {"path": "README.md"}');
      return;
    }
    if (typeof args !== 'object' || args === null || Array.isArray(args)) {
      alert('参数必须是 JSON 对象');
      return;
    }

    setTestRunning(true);
    setTestResult(null);
    const resp = await sendRequest('agent.testTool', { id: currentTool.id, args }, 30000);
    setTestRunning(false);
    if (resp.error) {
      setTestResult({ success: false, output: resp.error.message || '请求失败', duration_ms: 0 });
    } else {
      setTestResult(resp.result || { success: false, output: '无返回结果', duration_ms: 0 });
    }
  };

  // 点击弹窗外部关闭
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (modalRef.current && !modalRef.current.contains(e.target)) {
        closeModal();
      }
      if (configModalRef.current && !configModalRef.current.contains(e.target)) {
        closeConfigModal();
      }
      if (testModalRef.current && !testModalRef.current.contains(e.target)) {
        closeTestModal();
      }
    };

    if (modalVisible || configModalVisible || testModalVisible) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [modalVisible, configModalVisible, testModalVisible]);

  return (
    <div className="tool-management-page">
      {/* 页面头部 */}
      <div className="page-header">
        <h1>工具管理</h1>
        <button onClick={openAddModal} className="btn add-btn">
          <span className="icon">+</span> 新增工具
        </button>
      </div>

      {/* 筛选和搜索区域 */}
      <div className="filter-section">
        <div className="search-box">
          <input
            type="text"
            placeholder="搜索工具名称/版本/描述..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <span className="search-icon">🔍</span>
        </div>

        <div className="category-filter">
          <label>分类筛选：</label>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">全部分类</option>
            {allCategories.map(category => (
              <option key={category} value={category}>
                {CATEGORY_LABELS[category] || category}
              </option>
            ))}
          </select>
        </div>

        <div className="status-filter">
          <label>状态筛选：</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">全部状态</option>
            <option value="active">已启用</option>
            <option value="inactive">已禁用</option>
          </select>
        </div>
      </div>

      {/* 工具列表 */}
      <div className="tools-list">
        {loading ? (
          <div className="loading-state">
            <div className="loading-icon">⏳</div>
            <div className="loading-text">加载中...</div>
          </div>
        ) : filteredTools.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🔧</div>
            <div className="empty-text">暂无工具数据</div>
            <button onClick={openAddModal} className="btn empty-add-btn">
              立即创建第一个工具
            </button>
          </div>
        ) : (
          <div className="tools-grid">
            {filteredTools.map(tool => {
              const categoryName = CATEGORY_LABELS[tool.category] || tool.category || '未分类';
              const builtin = isBuiltin(tool);
              return (
                <div key={tool.id} className="tool-card">
                  <div className="card-header">
                    <div className="tool-name">
                      {tool.name}
                      {builtin && (
                        <span className="source-tag builtin">内置</span>
                      )}
                    </div>
                    <span className={`status-tag ${tool.status}`}>
                      {tool.status === 'active' ? '已启用' : '已禁用'}
                    </span>
                  </div>

                  <div className="card-body">
                    <div className="tool-meta">
                      <div className="meta-item">
                        <span className="label">分类：</span>
                        <span className="value">{categoryName}</span>
                      </div>
                      <div className="meta-item">
                        <span className="label">版本：</span>
                        <span className="value version">{tool.version}</span>
                      </div>
                      <div className="meta-item">
                        <span className="label">作者：</span>
                        <span className="value">{tool.author}</span>
                      </div>
                      <div className="meta-item full-width">
                        <span className="label">描述：</span>
                        <span className="value">{tool.description}</span>
                      </div>
                      <div className="meta-item full-width">
                        <span className="label">更新时间：</span>
                        <span className="value time">{tool.updateTime}</span>
                      </div>
                    </div>

                    <div className="config-preview">
                      <div className="config-label">配置项：</div>
                      <div className="config-content">
                        {Object.keys(tool.config || {}).length === 0 ? (
                          <span className="no-config">暂无配置</span>
                        ) : (
                          <pre>{JSON.stringify(tool.config, null, 2)}</pre>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="card-footer">
                    <button
                      onClick={() => toggleToolStatus(tool)}
                      className={`action-btn status-btn ${tool.status}`}
                    >
                      {tool.status === 'active' ? '禁用' : '启用'}
                    </button>
                    <button
                      onClick={() => openTestModal(tool)}
                      className="action-btn test-btn"
                    >
                      试运行
                    </button>
                    <button
                      onClick={() => openConfigModal(tool)}
                      className="action-btn config-btn"
                    >
                      配置
                    </button>
                    <button
                      onClick={() => openEditModal(tool)}
                      className="action-btn edit-btn"
                    >
                      编辑
                    </button>
                    {!builtin && (
                      <button
                        onClick={() => deleteTool(tool.id)}
                        className="action-btn delete-btn"
                      >
                        删除
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 新增/编辑工具弹窗 */}
      {modalVisible && (
        <div className="modal-overlay">
          <div className="modal-content" ref={modalRef}>
            <div className="modal-header">
              <h2>{isEditMode ? '编辑工具' : '新增工具'}</h2>
              <button onClick={closeModal} className="close-btn">×</button>
            </div>
            <div className="modal-body">
              {isEditMode && isBuiltin(currentTool) && (
                <div className="config-tip read-only-tip">
                  内置工具仅允许修改描述（名称/分类/版本不可改动）
                </div>
              )}
              <div className="form-row">
                <div className="form-group">
                  <label>工具名称 *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    placeholder="请输入工具名称"
                    disabled={isEditMode && isBuiltin(currentTool)}
                  />
                </div>
                <div className="form-group">
                  <label>工具版本 *</label>
                  <input
                    type="text"
                    value={formData.version}
                    onChange={(e) => setFormData({...formData, version: e.target.value})}
                    placeholder="例如：1.0.0"
                    disabled={isEditMode && isBuiltin(currentTool)}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>工具分类 *</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({...formData, category: e.target.value})}
                    disabled={isEditMode && isBuiltin(currentTool)}
                  >
                    {allCategories.map(category => (
                      <option key={category} value={category}>
                        {CATEGORY_LABELS[category] || category}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>作者</label>
                  <input
                    type="text"
                    value={formData.author}
                    onChange={(e) => setFormData({...formData, author: e.target.value})}
                    placeholder="请输入作者名称"
                    disabled={isEditMode && isBuiltin(currentTool)}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>工具描述</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({...formData, description: e.target.value})}
                  placeholder="请输入工具详细描述"
                  rows={4}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={closeModal} className="btn cancel-btn">取消</button>
              <button onClick={handleSubmit} className="btn confirm-btn">
                {isEditMode ? '保存修改' : '创建工具'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 配置编辑弹窗（内置只读 / 自定义三字段） */}
      {configModalVisible && currentTool && (
        <div className="modal-overlay">
          <div className="modal-content config-modal" ref={configModalRef}>
            <div className="modal-header">
              <h2>配置工具：{currentTool.name}</h2>
              <button onClick={closeConfigModal} className="close-btn">×</button>
            </div>
            <div className="modal-body">
              {isBuiltin(currentTool) ? (
                <>
                  <div className="config-tip read-only-tip">
                    内置工具配置由运行时参数 Schema 决定，只读展示，不可修改
                  </div>
                  <div className="config-editor">
                    <pre className="readonly-config">
                      {JSON.stringify(currentTool.config || {}, null, 2)}
                    </pre>
                  </div>
                </>
              ) : (
                <>
                  <div className="ai-gen-section">
                    <div className="ai-gen-header">
                      <span className="ai-gen-title">✨ AI 生成</span>
                      <span className="ai-gen-hint">描述需求，AI 生成配置并填回表单，确认后再保存</span>
                    </div>
                    <div className="ai-gen-body">
                      <textarea
                        value={aiPrompt}
                        onChange={(e) => setAiPrompt(e.target.value)}
                        placeholder="例如：生成一个在 Windows 下搜索工作区文件的工具，支持按文件名/内容关键字过滤"
                        rows={3}
                        disabled={aiGenerating}
                      />
                      <button
                        onClick={handleAiGenerate}
                        className="btn ai-gen-btn"
                        disabled={aiGenerating}
                      >
                        {aiGenerating ? 'AI 生成中...' : '✨ 生成配置'}
                      </button>
                    </div>
                  </div>
                  <div className="form-group">
                    <label>命令模板</label>
                    <input
                      type="text"
                      value={configForm.command}
                      onChange={(e) => setConfigForm({...configForm, command: e.target.value})}
                      placeholder="如 echo {arg}，{arg} 会被 LLM 实参替换"
                    />
                    <div className="config-tip">支持 {"{arg}"} 占位符，由 LLM 传入的实参按名替换</div>
                  </div>
                  <div className="form-group">
                    <label>Python 脚本</label>
                    <textarea
                      value={configForm.script}
                      onChange={(e) => setConfigForm({...configForm, script: e.target.value})}
                      placeholder="写入临时文件后由解释器执行；与命令模板二选一"
                      rows={8}
                      className="script-editor"
                    />
                    <div className="config-tip">未配置命令模板时执行此脚本</div>
                  </div>
                  <div className="form-group">
                    <label>参数 JSON Schema</label>
                    <div className="config-editor">
                      <textarea
                        value={configForm.parametersText}
                        onChange={(e) => setConfigForm({...configForm, parametersText: e.target.value})}
                        placeholder='{"type": "object", "properties": {"arg": {"type": "string", "description": "..."}}}'
                        rows={10}
                      />
                    </div>
                    <div className="config-tip">可选；非法 JSON 无法保存</div>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={closeConfigModal} className="btn cancel-btn">取消</button>
              {!isBuiltin(currentTool) && (
                <button onClick={saveConfig} className="btn confirm-btn">
                  保存配置
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 试运行弹窗 */}
      {testModalVisible && currentTool && (
        <div className="modal-overlay">
          <div className="modal-content config-modal" ref={testModalRef}>
            <div className="modal-header">
              <h2>试运行：{currentTool.name}</h2>
              <button onClick={closeTestModal} className="close-btn">×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>参数（JSON 对象）</label>
                <div className="config-editor">
                  <textarea
                    value={testArgsText}
                    onChange={(e) => setTestArgsText(e.target.value)}
                    placeholder='{"arg": "值"}'
                    rows={6}
                  />
                </div>
                <div className="config-tip">不改变工具注册状态，仅临时执行一次</div>
              </div>

              {testResult && (
                <div className="form-group">
                  <label>执行结果</label>
                  <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
                    <div className="test-result-head">
                      <span className={`status-tag ${testResult.success ? 'active' : 'inactive'}`}>
                        {testResult.success ? '执行成功' : '执行失败'}
                      </span>
                      {testResult.duration_ms != null && (
                        <span className="test-duration">耗时 {testResult.duration_ms} ms</span>
                      )}
                    </div>
                    <pre className="test-output">{testResult.output}</pre>
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={closeTestModal} className="btn cancel-btn">关闭</button>
              <button
                onClick={runTest}
                className="btn confirm-btn"
                disabled={testRunning}
              >
                {testRunning ? '运行中...' : '运行'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ToolManagementPage;
