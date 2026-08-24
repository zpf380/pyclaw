# pyclaw
pyclaw 是一个用 Python 从零实现的开源个人 AI 智能体助手框架（OpenClaw 迷你版），采用全栈架构：基于工具调用的 LLM 智能体循环 + WebSocket JSON-RPC 网关 + React 单页前端。内置聊天、技能管理、自定义工具、敏感词过滤（拦截/替换/掩码）、定时任务、子代理、消息日志与连接配置；通过 litellm 对接 DeepSeek、OpenAI、Gemini 等模型；认证基于 scrypt 密码哈希与 token 会话，区分管理员/成员角色。开箱即用，便于二次开发。
