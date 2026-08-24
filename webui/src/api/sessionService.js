// 定义 Session 常量
const SESSION_KEY = 'user_session';
// Session 过期时间（单位：毫秒），与后端 token TTL（auth.tokenTtlHours，默认 24h）对齐
const SESSION_EXPIRE_TIME = 24 * 60 * 60 * 1000;

// Session 管理工具类
const sessionService = {
  /**
   * 创建/更新 Session
   * @param {Object} userInfo - 用户信息
   * @param {string} token - 登录令牌
   */
  setSession(userInfo, token) {
    const sessionData = {
      userInfo,
      token,
      createTime: Date.now(), // 记录创建时间
      expireTime: Date.now() + SESSION_EXPIRE_TIME // 计算过期时间
    };
    
    localStorage.setItem(SESSION_KEY, JSON.stringify(sessionData));
  },

  /**
   * 获取当前 Session
   * @returns {Object|null} 会话信息或null（过期/不存在）
   */
  getSession() {
    try {
      const sessionStr = localStorage.getItem(SESSION_KEY);
      if (!sessionStr) return null;

      const sessionData = JSON.parse(sessionStr);
      
      // 检查是否过期
      if (Date.now() > sessionData.expireTime) {
        this.clearSession(); // 清理过期会话
        return null;
      }
      
      return sessionData;
    } catch (error) {
      console.error('获取Session失败:', error);
      this.clearSession();
      return null;
    }
  },

  /**
   * 检查是否已登录（Session有效）
   * @returns {boolean}
   */
  isAuthenticated() {
    return !!this.getSession();
  },

  /**
   * 刷新Session（延长过期时间）
   */
  refreshSession() {
    const session = this.getSession();
    if (session) {
      this.setSession(session.userInfo, session.token);
    }
  },

  /**
   * 清除Session
   */
  clearSession() {
    localStorage.removeItem(SESSION_KEY);
  },

  /**
   * 获取用户信息
   * @returns {Object|null}
   */
  getUserInfo() {
    const session = this.getSession();
    return session ? session.userInfo : null;
  },

  /**
   * 获取Token
   * @returns {string|null}
   */
  getToken() {
    const session = this.getSession();
    return session ? session.token : null;
  },

  /**
   * 获取用户角色
   * @returns {string|null} admin/member/operator
   */
  getRole() {
    const userInfo = this.getUserInfo();
    return userInfo ? userInfo.role : null;
  }
};

export default sessionService;