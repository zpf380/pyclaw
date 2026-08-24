import React, { useState, useEffect } from 'react';
import './SensitiveWordManagementPage.css';

const SensitiveWordManagementPage = ({ sendWebSocketRequest, isConnected }) => {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [formData, setFormData] = useState({
    keyword: '',
    action: 'block',
    replacement: '',
    category: 'general',
    severity: 'medium',
    description: '',
    status: 'active'
  });

  // 获取敏感词规则列表
  const getRules = () => {
    if (!isConnected) return;
    
    setLoading(true);
    sendWebSocketRequest('system.listSensitiveRules', {}, (response) => {
      setLoading(false);
      if (response.result) {
        setRules(response.result);
      } else {
        console.error('获取敏感词规则失败:', response.error);
      }
    });
  };

  useEffect(() => {
    getRules();
  }, [isConnected]);

  // 打开添加/编辑模态框
  const openModal = (rule = null) => {
    if (rule) {
      // 编辑模式
      setEditingRule(rule);
      setFormData({
        keyword: rule.keyword,
        action: rule.action,
        replacement: rule.replacement || '',
        category: rule.category,
        severity: rule.severity,
        description: rule.description || '',
        status: rule.status
      });
    } else {
      // 添加模式
      setEditingRule(null);
      setFormData({
        keyword: '',
        action: 'block',
        replacement: '',
        category: 'general',
        severity: 'medium',
        description: '',
        status: 'active'
      });
    }
    setShowModal(true);
  };

  // 关闭模态框
  const closeModal = () => {
    setShowModal(false);
    setEditingRule(null);
    setFormData({
      keyword: '',
      action: 'block',
      replacement: '',
      category: 'general',
      severity: 'medium',
      description: '',
      status: 'active'
    });
  };

  // 处理表单提交
  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!formData.keyword.trim()) {
      alert('敏感词不能为空');
      return;
    }

    setLoading(true);
    
    if (editingRule) {
      // 更新规则
      const params = {
        id: editingRule.id,
        ...formData
      };
      
      sendWebSocketRequest('system.updateSensitiveRule', params, (response) => {
        setLoading(false);
        if (response.result && response.result.success) {
          getRules();
          closeModal();
        } else {
          alert(response.result?.message || '更新敏感词规则失败');
        }
      });
    } else {
      // 添加规则
      sendWebSocketRequest('system.addSensitiveRule', formData, (response) => {
        setLoading(false);
        if (response.result && response.result.success) {
          getRules();
          closeModal();
        } else {
          alert(response.result?.message || '添加敏感词规则失败');
        }
      });
    }
  };

  // 删除规则
  const deleteRule = (id) => {
    if (window.confirm('确定要删除该敏感词规则吗？此操作不可恢复！')) {
      sendWebSocketRequest('system.deleteSensitiveRule', { id }, (response) => {
        if (response.result && response.result.success) {
          getRules();
        } else {
          alert(response.result?.message || '删除敏感词规则失败');
        }
      });
    }
  };

  // 切换规则状态
  const toggleRuleStatus = (rule) => {
    const newStatus = rule.status === 'active' ? 'inactive' : 'active';
    const params = {
      id: rule.id,
      status: newStatus
    };
    
    sendWebSocketRequest('system.updateSensitiveRule', params, (response) => {
      if (response.result && response.result.success) {
        getRules();
      } else {
        alert(response.result?.message || '更新规则状态失败');
      }
    });
  };

  // 获取动作显示文本
  const getActionText = (action) => {
    const actions = {
      'block': '拦截',
      'replace': '替换',
      'review': '审核'
    };
    return actions[action] || action;
  };

  // 获取严重程度显示文本
  const getSeverityText = (severity) => {
    const severities = {
      'low': '低',
      'medium': '中',
      'high': '高'
    };
    return severities[severity] || severity;
  };

  return (
    <div className="sensitive-word-management">
      <div className="page-header">
        <h1>敏感词规则管理</h1>
        <button 
          className="btn btn-primary"
          onClick={() => openModal()}
          disabled={loading}
        >
          添加规则
        </button>
      </div>

      <div className="rules-container">
        {loading ? (
          <div className="loading">加载中...</div>
        ) : (
          <div className="rules-list">
            {rules.length === 0 ? (
              <div className="no-data">暂无敏感词规则</div>
            ) : (
              rules.map((rule) => (
                <div key={rule.id} className="rule-card">
                  <div className="rule-header">
                    <span className={`status-badge ${rule.status}`}>
                      {rule.status === 'active' ? '启用' : '禁用'}
                    </span>
                    <span className="severity-badge">
                      {getSeverityText(rule.severity)}
                    </span>
                    <span className="action-badge">
                      {getActionText(rule.action)}
                    </span>
                  </div>
                  
                  <div className="rule-content">
                    <h3 className="keyword">{rule.keyword}</h3>
                    {rule.description && (
                      <p className="description">{rule.description}</p>
                    )}
                    {rule.action === 'replace' && rule.replacement && (
                      <p className="replacement">替换为: {rule.replacement}</p>
                    )}
                    <p className="category">分类: {rule.category}</p>
                    <p className="time">
                      创建: {rule.created_at} | 更新: {rule.updated_at}
                    </p>
                  </div>
                  
                  <div className="rule-actions">
                    <button 
                      className="btn btn-small btn-secondary"
                      onClick={() => toggleRuleStatus(rule)}
                    >
                      {rule.status === 'active' ? '禁用' : '启用'}
                    </button>
                    <button 
                      className="btn btn-small btn-primary"
                      onClick={() => openModal(rule)}
                    >
                      编辑
                    </button>
                    <button 
                      className="btn btn-small btn-danger"
                      onClick={() => deleteRule(rule.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 添加/编辑模态框 */}
      {showModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h2>{editingRule ? '编辑敏感词规则' : '添加敏感词规则'}</h2>
              <button className="close-btn" onClick={closeModal}>×</button>
            </div>
            
            <form onSubmit={handleSubmit} className="modal-body">
              <div className="form-group">
                <label>敏感词 *</label>
                <input
                  type="text"
                  value={formData.keyword}
                  onChange={(e) => setFormData({...formData, keyword: e.target.value})}
                  placeholder="请输入敏感词"
                  required
                />
              </div>
              
              <div className="form-group">
                <label>处理动作 *</label>
                <select
                  value={formData.action}
                  onChange={(e) => setFormData({...formData, action: e.target.value})}
                >
                  <option value="block">拦截</option>
                  <option value="replace">替换</option>
                  <option value="review">审核</option>
                </select>
              </div>
              
              {formData.action === 'replace' && (
                <div className="form-group">
                  <label>替换词 *</label>
                  <input
                    type="text"
                    value={formData.replacement}
                    onChange={(e) => setFormData({...formData, replacement: e.target.value})}
                    placeholder="请输入替换词"
                    required
                  />
                </div>
              )}
              
              <div className="form-group">
                <label>分类</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({...formData, category: e.target.value})}
                >
                  <option value="general">通用</option>
                  <option value="political">政治</option>
                  <option value="violence">暴力</option>
                  <option value="porn">色情</option>
                  <option value="ad">广告</option>
                  <option value="custom">自定义</option>
                </select>
              </div>
              
              <div className="form-group">
                <label>严重程度</label>
                <select
                  value={formData.severity}
                  onChange={(e) => setFormData({...formData, severity: e.target.value})}
                >
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                </select>
              </div>
              
              <div className="form-group">
                <label>描述</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({...formData, description: e.target.value})}
                  placeholder="请输入规则描述"
                  rows="3"
                />
              </div>
              
              {editingRule && (
                <div className="form-group">
                  <label>状态</label>
                  <select
                    value={formData.status}
                    onChange={(e) => setFormData({...formData, status: e.target.value})}
                  >
                    <option value="active">启用</option>
                    <option value="inactive">禁用</option>
                  </select>
                </div>
              )}
              
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                  取消
                </button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? '处理中...' : (editingRule ? '更新' : '添加')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default SensitiveWordManagementPage;