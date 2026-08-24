import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const PrivateRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  
  // 加载中显示占位
  if (loading) {
    return <div className="loading">加载中...</div>;
  }
  
  if (!isAuthenticated) {
    // 未登录则跳转到登录页
    return <Navigate to="/login" replace />;
  }
  
  // 已登录则渲染受保护的组件
  return children;
};

export default PrivateRoute;