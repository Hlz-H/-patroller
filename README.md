# 巡查者 (Patroller)

**PC 安全监控与控制系统** — 多设备集中管控、AI 异常检测、沙箱分析、自动响应。

```
Agent (Python) ──► Backend (Node.js) ◄── Commander (Electron)
     │                    │                      │
     ▼                    ▼                      ▼
  监控/检测/沙箱      消息中继/持久化         实时看板/策略/告警
```

## 快速开始

### 前置条件

- **Windows 10/11** (Agent 仅支持 Windows)
- **Python 3.9+** + **Node.js 18+**
- **Ollama**（可选，用于 LLM 分析）

### 1. 启动 Backend

```powershell
cd backend
npm install
npm run dev        # http://localhost:3099
```

### 2. 启动 Agent

```powershell
cd agent
pip install -r requirements.txt
python run.py      # http://localhost:8099
```

### 3. 启动 Commander

```powershell
cd commander
npm install
npm run dev        # http://localhost:5173
```

一键启动（开发环境）：

```powershell
scripts\start-all.ps1
```

### 构建

```powershell
scripts\build-all.ps1
```

| 组件 | 构建输出 | 命令 |
|------|---------|------|
| Agent | `agent/dist/patroller-agent/` | `scripts\build-agent.ps1` |
| Commander | `commander/release/` 安装包 | `cd commander && npm run build:dist` |
| Backend | `backend/dist/` | `cd backend && npm run build` |

## 目录结构

```
E:\OpenWorkspace\
├── agent/                  # Python Agent（监控 + 检测 + 沙箱）
│   ├── agent/
│   │   ├── api/           # FastAPI REST + WebSocket
│   │   ├── monitors/      # 6 个系统监控器
│   │   ├── detectors/     # YARA / ML / LLM 检测
│   │   ├── controllers/   # AI 智能调控引擎
│   │   ├── sandbox/       # Windows Sandbox 集成
│   │   └── config.py      # 配置加载
│   ├── tests/             # 345 个测试
│   └── run.py
├── backend/                # Node.js Backend
│   ├── src/
│   │   ├── api/           # 路由 (devices/alerts/sandbox/relay)
│   │   ├── ws/            # WebSocket 实时通信
│   │   └── db/            # SQLite
│   └── ecosystem.config.js  # PM2 配置
├── commander/              # Electron Commander (管理面板)
│   ├── src/
│   │   ├── pages/         # 仪表盘/进程/USB/沙箱/告警/设置
│   │   ├── store/         # Zustand 状态管理
│   │   └── api/           # HTTP + WebSocket 客户端
│   └── electron-builder.yml
├── mobile/                 # React Native App (手机端)
├── scripts/                # 构建/启动/停止脚本
│   ├── start-all.ps1
│   ├── stop-all.ps1
│   ├── build-all.ps1
│   └── build-agent.ps1
└── docs/                   # 设计文档
    ├── 架构设计/
    ├── AI检测/
    ├── 系统加固/
    ├── 沙箱集成/
    ├── 移动端App/
    └── features/AI智能调控引擎/
```

## 功能

| 模块 | 说明 |
|------|------|
| **系统监控** | CPU/内存/磁盘/网络/进程/USB/注册表/服务/目录完整性 |
| **AI 检测** | YARA 规则匹配、ML 异常检测 (Isolation Forest)、LLM 日志分析 (Ollama) |
| **沙箱分析** | Windows Sandbox 隔离执行 + 行为报告 + AI 自动分类 |
| **智能调控** | 自适应调优监控参数、告警自动响应、基线学习 |
| **USB 管控** | VID:PID 黑名单封禁、热插拔事件记录 |
| **实时看板** | Commander 桌面端 / 手机 App 多设备状态、告警、趋势图 |
| **WebSocket** | 指标推送、告警推送、远程命令下发 |
| **Tailscale** | 零配置身份认证、端到端加密组网 |

## 测试

```powershell
# Agent 测试
cd agent && python -m pytest tests/ -v     # 345 passed

# Backend 测试
cd backend && npm test                     # 32 passed

# 全链路集成验证
# 启动 Agent + Backend → 访问 http://localhost:3099/api/v1/health
```

## 许可证

MIT
