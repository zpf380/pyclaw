# pyclaw

pyclaw 是一个用 Python 从零实现的开源个人 AI 智能体助手框架（OpenClaw 迷你版），采用全栈架构：基于工具调用的 LLM 智能体循环 + WebSocket JSON-RPC 网关 + React 单页前端。内置聊天、技能管理、自定义工具、敏感词过滤（拦截/替换/掩码）、定时任务、子代理、消息日志与连接配置；通过 litellm 对接 DeepSeek、OpenAI、Gemini 等模型；认证基于 scrypt 密码哈希与 token 会话，区分管理员/成员角色。开箱即用，便于二次开发。

## 功能特性

- **智能体循环**：基于工具调用的多轮对话，支持 `spawn` 子代理并行执行子任务
- **多模型提供商**：经 litellm 统一接入 DeepSeek、OpenAI、Gemini、OpenRouter 等
- **技能系统**：`pyclaw/skills/` 与 `workspace/workspace/skills/` 技能文件自动加载，可启停
- **自定义工具**：管理后台一键创建脚本/命令模式工具，内置文件读写/编辑/列目录（工作区边界保护）
- **敏感词过滤**：拦截 / 替换 / 掩码三种动作，命中自动告警并留痕
- **定时任务**：cron 表达式调度，支持一次性与周期任务
- **认证与会话**：scrypt 密码哈希 + token 会话，管理员/成员角色权限分离
- **渠道接入**：飞书 WebSocket 渠道；Web UI 通过网关实时交互
- **消息持久化**：SQLAlchemy 存储会话消息与日志，Web UI 可回溯

## 技术架构

```
┌────────────────────────────────────────────────────┐
│  React Web UI（聊天/能力中心/敏感词/日志/设置）      │
└──────────────────────┬─────────────────────────────┘
                       │ WebSocket JSON-RPC 2.0
┌──────────────────────▼─────────────────────────────┐
│  GatewayServer（:18790）— 鉴权 / 路由 / 消息推送     │
└──────────────────────┬─────────────────────────────┘
                       │ MessageBus（入站/出站/WS 队列）
┌──────────────────────▼─────────────────────────────┐
│  AgentLoop（LLM 工具调用循环，litellm 多提供商）      │
│   ├─ 内置工具：read_file / write_file / exec / …    │
│   ├─ 自定义工具：脚本 / 命令模式                     │
│   ├─ 子代理：spawn / announce                        │
│   └─ 技能 / 定时任务 / 记忆                           │
└────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python ≥ 3.11（推荐 3.13）
- Node.js ≥ 18（前端构建）
- 一个 LLM API Key（默认 DeepSeek，可换其它提供商）

### 1. 安装后端

```bash
pip install -e .
pip install .[dev]      # 如需运行测试
```

### 2. 配置

```bash
# 首次运行前生成配置（含 DeepSeek / 飞书等凭据）
python -m pyclaw onboard

# 或手动复制示例配置后填入 API Key
cp workspace/pyclaw.json.example workspace/pyclaw.json
```

`workspace/pyclaw.json.example` 为脱敏模板，请勿把含真实密钥的 `workspace/pyclaw.json` 提交到仓库（已加入 `.gitignore`）。

### 3. 启动后端网关

```bash
python -m pyclaw gateway --port 18790
```

首次启动会自动创建种子管理员 **admin / admin123**（请尽快修改）。

### 4. 启动前端

```bash
cd webui
npm install
npm start        # http://localhost:3000
```

浏览器打开 http://localhost:3000 登录后即可使用。未登录时 WebSocket 不建立连接，登录后才与网关保持连接。

### CLI 命令

```bash
python -m pyclaw onboard     # 生成配置文件
python -m pyclaw gateway     # 启动 WebSocket 网关
python -m pyclaw agent       # 命令行与智能体对话
python -m pyclaw status      # 查看运行状态
```

## 测试

```bash
pytest                          # 后端测试
cd webui && npm test            # 前端测试
```

## 目录结构

```
pyclaw/            # 核心包
├── agent/         # Agent 循环、子代理、工具、技能
├── auth/          # 认证服务（scrypt + token）
├── bus/           # 消息总线（入站/出站/WS 队列）
├── channels/      # 渠道（飞书）
├── cli/           # 命令行（onboard/gateway/agent/status）
├── config/        # 配置加载与 schema
├── cron/          # 定时任务
├── database/      # SQLAlchemy 数据层（用户/消息/敏感词/技能/工具）
├── gateway/       # WebSocket JSON-RPC 网关
├── heartbeat/     # 心跳服务
├── providers/     # LLM Provider（litellm）
├── session/       # 会话管理
├── skills/        # 内置技能
└── utils/         # 工具函数
webui/             # React 前端
workspace/         # 运行时数据（配置/会话/Agent 工作区，敏感内容不入库）
tests/             # 后端测试
scripts/           # 调试与维护脚本
```

## 许可证

[MIT](LICENSE) © 2026 zpf380
