import { useState, useEffect, useRef } from 'react';
import './SkillManagementPage.css';

const SkillManagementPage = ({sendWebSocketRequest, sendRequest, isConnected}) => {
  // 状态管理
  const [skills, setSkills] = useState([]);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [modalVisible, setModalVisible] = useState(false);
  const [currentSkill, setCurrentSkill] = useState(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [readOnly, setReadOnly] = useState(false); // 内置技能：正文/元数据只读（文件在包目录）
  const [loading, setLoading] = useState(false);
  const [aiPrompt, setAiPrompt] = useState(''); // AI 生成的需求描述
  const [aiGenerating, setAiGenerating] = useState(false); // AI 生成中

  // 获取技能列表
  const getSkills = () => {
    if (!isConnected) return;

    setLoading(true);
    sendWebSocketRequest('system.listSkills', {}, (response) => {
      setLoading(false);
      if (response.result) {
        setSkills(response.result);
      } else {
        console.error('获取技能列表失败:', response.error);
        // 如果获取失败，使用空数组
        setSkills([]);
      }
    });
  };

  // 页面加载时获取技能列表
  useEffect(() => {
    getSkills();
  }, [isConnected]);

  // 表单数据（content 为 SKILL.md 正文，null 表示尚未加载）
  const [formData, setFormData] = useState({
    name: '',
    code: '',
    description: '',
    content: null
  });

  const modalRef = useRef(null);

  // 筛选技能列表
  const filteredSkills = skills.filter(skill => {
    const matchesSearch = skill.name.toLowerCase().includes(searchText.toLowerCase()) ||
                          skill.code.toLowerCase().includes(searchText.toLowerCase()) ||
                          skill.description.toLowerCase().includes(searchText.toLowerCase());
    const matchesStatus = statusFilter === 'all' || skill.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // 是否为内置技能（category=builtin：文件在包目录 pyclaw/skills/，只能启停）
  const isBuiltin = (skill) => skill.category === 'builtin';

  // 打开新增技能弹窗
  const openAddModal = () => {
    setIsEditMode(false);
    setReadOnly(false);
    setAiPrompt('');
    setFormData({
      name: '',
      code: '',
      description: '',
      content: '# 技能说明\n\n在这里编写技能的使用说明与操作步骤...'
    });
    setModalVisible(true);
  };

  const refresh = () => {
    getSkills();
  };

  // 打开编辑技能弹窗（异步拉取 SKILL.md 正文）
  const openEditModal = (skill) => {
    setIsEditMode(true);
    const builtin = isBuiltin(skill);
    setReadOnly(builtin);
    setAiPrompt('');
    setCurrentSkill(skill);
    setFormData({
      name: skill.name,
      code: skill.code,
      description: skill.description,
      content: builtin ? null : '' // 内置技能正文在包目录，不拉取
    });
    setModalVisible(true);

    // 非内置技能：拉取 workspace SKILL.md 正文供编辑
    if (!builtin) {
      sendWebSocketRequest('system.getSkillContent', { code: skill.code }, (response) => {
        const data = response.result;
        if (data && data.success && data.skill) {
          setFormData((prev) => ({ ...prev, content: data.skill.content || '' }));
        }
      });
    }
  };

  // 关闭弹窗
  const closeModal = () => {
    setModalVisible(false);
    setCurrentSkill(null);
    setReadOnly(false);
    setLoading(false);
    setAiGenerating(false);
  };

  // AI 生成技能配置（结果填回表单，由人工确认后再保存落盘）
  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) {
      alert('请先描述你想要的技能需求');
      return;
    }
    setAiGenerating(true);
    try {
      const response = await sendRequest('system.generateSkill', { prompt: aiPrompt }, 60000);
      const data = response.result;
      if (response.error || (data && data.success === false)) {
        alert(data?.message || response.error?.message || 'AI 生成失败');
        return;
      }
      if (data && data.success && data.skill) {
        const { name, description, content } = data.skill;
        setFormData((prev) => ({
          ...prev,
          name: name || prev.name,
          description: description || prev.description,
          content: content || prev.content
        }));
        // 生成的名字建议填入编码（编辑模式编码不可改，忽略）
        if (!isEditMode && name) {
          setFormData((prev) => ({
            ...prev,
            code: (name.toLowerCase().replace(/[^a-z0-9_-]/g, '') || prev.code)
          }));
        }
      } else {
        alert('AI 生成失败，请稍后重试');
      }
    } catch (err) {
      console.error('AI 生成技能失败:', err);
      alert('AI 生成技能失败，请稍后重试');
    } finally {
      setAiGenerating(false);
    }
  };

  // 处理表单提交
  const handleSubmit = () => {
    if (!formData.name.trim() || !formData.code.trim()) {
      alert('技能名称和编码不能为空');
      return;
    }
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(formData.code)) {
      alert('技能编码仅支持小写字母/数字/短横线/下划线（如 file-management）');
      return;
    }

    setLoading(true);

    if (isEditMode) {
      // 编辑模式（内置技能为只读，正常不会走到保存）
      const params = {
        id: currentSkill.id,
        name: formData.name,
        description: formData.description,
        status: currentSkill.status
      };
      // content 仅在有正文时携带（避免 getSkillContent 尚未返回时误清空文件正文）
      if (formData.content !== null && formData.content !== undefined) {
        params.content = formData.content;
      }

      sendWebSocketRequest('system.updateSkill', params, (response) => {
        setLoading(false);
        if (response.result && response.result.success) {
          getSkills();
          closeModal();
        } else {
          alert(response.result?.message || '更新技能成功');
        }
      });
    } else {
      // 新增模式（写文件 + DB，content 为可选正文）
      const params = {
        name: formData.name,
        code: formData.code,
        description: formData.description,
        content: formData.content || ''
      };

      sendWebSocketRequest('system.addSkill', params, (response) => {
        setLoading(false);
        if (response.result && response.result.success) {
          getSkills();
          closeModal();
        } else {
          alert(response.result?.message || '添加技能成功');
        }
      });
    }
  };

  // 切换技能状态
  const toggleSkillStatus = (id) => {
    const skill = skills.find(s => s.id === id);
    if (skill) {
      const newStatus = skill.status === 'active' ? 'inactive' : 'active';

      const params = {
        id: id,
        status: newStatus
      };

      sendWebSocketRequest('system.updateSkill', params, (response) => {
        if (response.result && response.result.success) {
          getSkills();
        } else {
          alert(response.result?.message || '更新技能状态成功');
        }
      });
    }
  };

  // 删除技能（内置技能后端拒绝，前端也隐藏按钮）
  const deleteSkill = (id) => {
    if (window.confirm('确定要删除该技能吗？此操作不可恢复！')) {
      const params = { id: id };

      sendWebSocketRequest('system.deleteSkill', params, (response) => {
        if (response.result && response.result.success) {
          getSkills();
        } else {
          alert(response.result?.message || '删除技能成功');
        }
      });
    }
  };

  // 文件 ↔ DB 双向同步（import: 文件→DB；export: DB→workspace 骨架文件）
  const syncSkills = (direction) => {
    const confirmMsg = direction === 'import'
      ? '将从 workspace 的 SKILL.md 文件导入到数据库（保留启停状态，覆盖 DB 元数据）。继续？'
      : '将把数据库中的技能导出为 workspace 的 SKILL.md 文件（已存在不覆盖）。继续？';
    if (!window.confirm(confirmMsg)) return;

    sendWebSocketRequest('system.syncSkills', { direction }, (response) => {
      if (response.result && response.result.success) {
        alert(response.result.message);
        getSkills();
      } else {
        alert(response.result?.message || response.error?.message || '同步失败');
      }
    });
  };

  // 点击弹窗外部关闭
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (modalRef.current && !modalRef.current.contains(e.target)) {
        closeModal();
      }
    };

    if (modalVisible) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [modalVisible]);

  return (
    <div className="skill-management-page">
      {/* 页面头部 */}
      <div className="page-header">
        <h1>技能管理</h1>
        <div className="header-actions">
          <button onClick={() => syncSkills('import')} className="btn sync-btn">
            ⬇ 从文件导入
          </button>
          <button onClick={() => syncSkills('export')} className="btn sync-btn">
            ⬆ 导出到文件
          </button>
          <button onClick={openAddModal} className="btn add-btn">
            <span className="icon">+</span> 新增技能
          </button>
        </div>
      </div>

      {/* 筛选和搜索区域 */}
      <div className="filter-section">
        <div className="search-box">
          <input
            type="text"
            placeholder="搜索技能名称/编码/描述..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <span className="search-icon">🔍</span>
        </div>
        <div className="status-filter">
          <label>状态筛选：</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">全部</option>
            <option value="active">已启用</option>
            <option value="inactive">已禁用</option>
          </select>
        </div>
        <button onClick={refresh} className='btn empty-add-btn'>刷新</button>
      </div>

      {/* 技能列表 */}
      <div className="skills-list">
        {filteredSkills.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <div className="empty-text">暂无技能数据</div>
            <button onClick={openAddModal} className="btn empty-add-btn">
              立即创建第一个技能
            </button>
          </div>
        ) : (
          <div className="skills-table">
            <div className="table-header">
              <div className="table-cell name-col">技能名称</div>
              <div className="table-cell code-col">技能编码</div>
              <div className="table-cell desc-col">描述</div>
              <div className="table-cell status-col">状态</div>
              <div className="table-cell time-col">更新时间</div>
              <div className="table-cell action-col">操作</div>
            </div>
            <div className="table-body">
              {filteredSkills.map(skill => (
                <div key={skill.id} className="table-row">
                  <div className="table-cell name-col">
                    {skill.name}
                    {isBuiltin(skill) && (
                      <span className="source-tag builtin">内置</span>
                    )}
                  </div>
                  <div className="table-cell code-col">
                    {skill.code}
                    {!isBuiltin(skill) && (
                      <span className="source-tag workspace">工作区</span>
                    )}
                  </div>
                  <div className="table-cell desc-col">{skill.description}</div>
                  <div className="table-cell status-col">
                    <span className={`status-tag ${skill.status}`}>
                      {skill.status === 'active' ? '已启用' : '已禁用'}
                    </span>
                  </div>
                  <div className="table-cell time-col">{skill.updateTime}</div>
                  <div className="table-cell action-col">
                    <button
                      onClick={() => toggleSkillStatus(skill.id)}
                      className={`action-btn status-btn ${skill.status}`}
                    >
                      {skill.status === 'active' ? '禁用' : '启用'}
                    </button>
                    <button
                      onClick={() => openEditModal(skill)}
                      className="action-btn edit-btn"
                    >
                      {isBuiltin(skill) ? '查看' : '编辑'}
                    </button>
                    {!isBuiltin(skill) && (
                      <button
                        onClick={() => deleteSkill(skill.id)}
                        className="action-btn delete-btn"
                      >
                        删除
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 新增/编辑技能弹窗 */}
      {modalVisible && (
        <div className="modal-overlay">
          <div className="modal-content" ref={modalRef}>
            <div className="modal-header">
              <h2>{readOnly ? '查看技能' : (isEditMode ? '编辑技能' : '新增技能')}</h2>
              <button onClick={closeModal} className="close-btn">×</button>
            </div>
            <div className="modal-body">
              {readOnly && (
                <div className="config-tip read-only-tip">
                  内置技能文件位于包目录（pyclaw/skills/），仅支持启停，不可在线编辑正文
                </div>
              )}
              {!readOnly && (
                <div className="ai-gen-section">
                  <div className="ai-gen-header">
                    <span className="ai-gen-title">✨ AI 生成</span>
                    <span className="ai-gen-hint">描述需求，AI 生成配置并填回表单，确认后再保存</span>
                  </div>
                  <div className="ai-gen-body">
                    <textarea
                      value={aiPrompt}
                      onChange={(e) => setAiPrompt(e.target.value)}
                      placeholder="例如：生成一个会议纪要技能，能读取文件、整理要点并保存到 workspace/notes/meeting/"
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
              )}
              <div className="form-group">
                <label>技能名称 *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  placeholder="请输入技能名称"
                  disabled={readOnly}
                />
              </div>
              <div className="form-group">
                <label>技能编码 *</label>
                <input
                  type="text"
                  value={formData.code}
                  onChange={(e) => setFormData({
                    ...formData,
                    code: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '')
                  })}
                  placeholder="请输入技能编码（小写短横线，如 file-management）"
                  disabled={isEditMode} // 编码不可修改
                />
              </div>
              <div className="form-group">
                <label>技能描述</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({...formData, description: e.target.value})}
                  placeholder="请输入技能描述信息"
                  rows={3}
                  disabled={readOnly}
                />
              </div>
              {!readOnly && (
                <div className="form-group">
                  <label>SKILL.md 正文</label>
                  <textarea
                    value={formData.content || ''}
                    onChange={(e) => setFormData({...formData, content: e.target.value})}
                    placeholder="技能正文将写入 workspace/skills/<编码>/SKILL.md"
                    rows={12}
                    className="skill-body-editor"
                  />
                  <div className="config-tip">
                    保存后落盘到 SKILL.md 文件，正文为 LLM 上下文注入内容
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={closeModal} className="btn cancel-btn">取消</button>
              {!readOnly && (
                <button
                  onClick={handleSubmit}
                  className="btn confirm-btn"
                  disabled={loading}
                >
                  {loading ? '处理中...' : (isEditMode ? '保存修改' : '创建技能')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillManagementPage;
