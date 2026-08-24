import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import styles from './LoginPage.module.css';

const LoginPage = () => {
  // 客户端路由跳转（不用 window.location 整页刷新，避免丢失已拉取的历史消息与 WebSocket 状态）
  const navigate = useNavigate();
  // 从上下文获取登录方法
  const { login } = useAuth();
  
  // 表单状态管理
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  
  // 错误提示状态
  const [errors, setErrors] = useState({});
  
  // 加载状态
  const [isLoading, setIsLoading] = useState(false);
  
  // 表单输入变化处理
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    
    // 输入时清除对应字段的错误提示
    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: ''
      }));
    }
  };
  
  // 表单验证
  const validateForm = () => {
    const newErrors = {};
    
    // 用户名验证
    if (!formData.username.trim()) {
      newErrors.username = '用户名不能为空';
    } else if (formData.username.length < 4) {
      newErrors.username = '用户名至少4个字符';
    }
    
    // 密码验证
    if (!formData.password.trim()) {
      newErrors.password = '密码不能为空';
    } else if (formData.password.length < 6) {
      newErrors.password = '密码至少6个字符';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };
  
  // 表单提交处理
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // 表单验证
    const isValid = validateForm();
    if (!isValid) return;
    
    try {
      setIsLoading(true);
      
      // 调用上下文的登录方法（成功后派发 auth:loggedIn，App 据此拉取历史消息）
      await login(formData.username, formData.password);

      // 登录成功客户端跳转首页（保留 WebSocket 连接与已加载的历史消息）
      navigate('/', { replace: true });
      
    } catch (error) {
      // 登录失败处理
      setErrors({
        submit: error.message
      });
    } finally {
      setIsLoading(false);
    }
  };
  
  return (
    <div className={styles.loginContainer}>
      <div className={styles.loginCard}>
        <h2 className={styles.loginTitle}>用户登录</h2>
        
        <form onSubmit={handleSubmit} className={styles.loginForm}>
          {/* 用户名输入框 */}
          <div className={styles.formGroup}>
            <label htmlFor="username">用户名</label>
            <input
              type="text"
              id="username"
              name="username"
              value={formData.username}
              onChange={handleChange}
              className={`${styles.formControl} ${errors.username ? styles.errorInput : ''}`}
              disabled={isLoading}
            />
            {errors.username && <span className={styles.errorText}>{errors.username}</span>}
          </div>
          
          {/* 密码输入框 */}
          <div className={styles.formGroup}>
            <label htmlFor="password">密码</label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              className={`${styles.formControl} ${errors.password ? styles.errorInput : ''}`}
              disabled={isLoading}
            />
            {errors.password && <span className={styles.errorText}>{errors.password}</span>}
          </div>
          
          {/* 提交错误提示 */}
          {errors.submit && <div className={styles.submitError}>{errors.submit}</div>}
          
          {/* 登录按钮 */}
          <button
            type="submit"
            className={styles.loginButton}
            disabled={isLoading}
          >
            {isLoading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;