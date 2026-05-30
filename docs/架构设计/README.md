# 巡查者 - PC 安全监控与控制系统

**状态：** 进行中

## 设计结论

三件套架构：**Python Agent（执行端）+ Electron Commander（管理端）+ React Native App（手机端）**，通过 Tailscale VPN 组网，Backend 可本地运行也可云端部署。本地优先，账户即 Tailscale 身份，零配置设备互认。

## 动机

保护个人多台电脑的安全，集中管控各设备的运行状态、外设接入、进程行为，配合 AI 进行异常检测和自动响应。所有组件都跑在自己的网络里，不经过第三方云服务。

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   Tailscale VPN 网络                      │
│                    (身份层 + 网络层)                      │
└──────────────────────────┬──────────────────────────────┘
                           │
         ┌─────────────────┼──────────────────┐
         │                 │                  │
    ┌────▼────┐      ┌────▼────┐       ┌─────▼─────┐
    │  Agent  │      │Commander│       │  Mobile   │
    │(Windows)│◄────►│Desktop  │◄─────►│   App     │
    │ Python  │ HTTP │Electron │ HTTP  │ React Nat.│
    │  +AI    │      │ +React  │       │           │
    └────┬────┘      └─────────┘       └───────────┘
         │
    ┌────▼────┐
    │ Backend │  (内嵌在 Agent 或独立运行)
    │ Node.js │  REST API + WebSocket
    └─────────┘
```

### 组件职责

| 组件 | 语言 | 职责 |
|------|------|------|
| **Agent** | Python | 每台被保护电脑上运行。监控系统指标、管控外设/USB、查杀恶意进程、AI 检测、沙箱运行可疑文件 |
| **Commander** | TypeScript/Electron | 桌面管理面板。多设备看板、策略配置、AI 调控、告警管理 |
| **Mobile** | TypeScript/React Native | 手机端查看设备状态、接收告警、远程基本操作 |
| **Backend** | TypeScript/Node.js | 消息中继、设备注册、账户认证（委托 Tailscale）、WebSocket 推送 |

### 网络通信

```
Agent ──► Backend:   HTTP POST (状态上报) + WebSocket (实时)
Agent ◄── Backend:   WebSocket (指令下发)
Commander ──► Backend: HTTP (查询) + WebSocket (实时面板)
Mobile ──► Backend:   HTTP + WebSocket
Backend ◄──► Tailscale: 设备身份验证
```

所有通信走 Tailscale 虚拟局域网，端到端加密，不需要公网暴露端口。

## 设计决策

### 1. Agent 使用 Python

Python 拥有最完善的系统监控生态：
- `psutil` — CPU/内存/磁盘/网络/进程
- `pywin32` / `wmi` — Windows 底层操作（注册表、服务、外设、USB）
- `watchdog` — 文件系统监控
- `yara-python` — 恶意软件特征匹配
- `scikit-learn` / `llama-cpp-python` — AI/ML 能力
- `cuckoo` / `sandbox` — 沙箱能力（调用 Windows Sandbox 或自定义）

**不选 Node.js 的理由：** Windows 底层 API 调用能力弱，AI/ML 生态差 Python 太多。

### 2. Commander 使用 Electron + React

用户的现有项目是 TypeScript/Node.js 技术栈，Electron 最匹配。桌面端需要系统托盘、通知、开机自启等原生能力。

### 3. Mobile 使用 React Native

与 Commander 共享 TypeScript 类型定义和 API 层。一套 API client 两端用，保持一致的数据模型。

### 4. Backend 可内嵌也可独立

- **单机模式：** Backend 作为 Agent 的子进程运行，端口复用
- **独立模式：** Backend 单独部署，多 Agent 共用一个 Backend
- 两种模式通过配置切换，代码同一套

### 5. 账户 = Tailscale 身份

不自己搞用户系统。Tailscale 登录即认证，设备通过 Tailscale 网络自动发现。Backend 验证连接来源的 Tailscale IP 即可确认设备身份。

**如果用户坚持不用 Tailscale：** 退回到自建简单账户（用户名 + 密码 + JWT），作为可选模式。

### 6. 本地优先，云端可选

- **纯本地：** 全部跑在局域网 / VPN，数据不出网络
- **云端：** Backend 部署到 VPS，Agent 通过 WireGuard/Tailscale 连接
- **混合：** 本地 Backend + Cloudflare Tunnel 对外暴露，手机外网访问

### 7. AI 智能调控

AI 能力分层：

| 层级 | 实现 | 位置 |
|------|------|------|
| **规则引擎** | 基于 YARA + 静态规则 | Agent (Python) |
| **ML 模型** | 异常检测 (Isolation Forest / One-Class SVM) | Agent (Python) |
| **LLM 分析** | 接入本地 ollama 或云端 API 分析日志 | Commander / Backend |
| **智能调控** | AI 根据安全事件自动决策（杀进程/禁USB/通知） | Commander (配置) → Agent (执行) |

规则引擎始终在线、离线可用。LLM 分析需要联网或本地 ollama。

### 8. 沙箱设计

使用 Windows Sandbox（Windows 10/11 Pro 内置功能）作为隔离执行环境：
- 可疑文件自动或手动发送到沙箱运行
- 记录沙箱内行为（文件操作、网络请求、进程创建）
- 生成行为报告供 AI 分析
- 沙箱用完自动销毁

**备选：** 如果系统不支持 Windows Sandbox，降级为进程隔离（Job Object + 受限 Token）。

## 模块拆分

### Phase 1: Agent 核心（MVP）

- [x] 系统资源监控（CPU/内存/磁盘/网络） — SystemResourceMonitor
- [x] 进程监控（创建/终止事件 + 黑白名单） — ProcessMonitor
- [x] USB 设备管控 — USBMonitor（WMI 查询 VID:PID + 黑名单封禁）
- [x] REST API + WebSocket 上报 — FastAPI + uvicorn + _WSManager
- [x] Windows 系统托盘 + 开机自启 — pystray + electron-tray 互备

### Phase 2: Commander 桌面端

- [x] Electron 壳 + React 面板 — Vite + electron/main.ts + preload.ts
- [x] 多设备实时看板 — Dashboard.tsx + StatusCard.tsx
- [x] 策略配置（白名单/USB/外设规则） — Settings.tsx + Processes.tsx + USB.tsx
- [x] 告警列表 + 通知 — Alerts.tsx + AlertBadge.tsx

### Phase 3: Backend 服务

- [x] Node.js REST API — Express + 设备/告警/relay/sandbox 路由
- [x] WebSocket 实时通信 — ws/ 模块 + 设备状态/指标广播
- [x] 设备注册/发现 — devices.ts + pending_commands relay
- [x] Tailscale 身份集成 — tailscaleAuthMiddleware

### Phase 4: AI 能力

- [x] YARA 规则引擎
- [x] ML 异常检测模型
- [x] 行为分析 + 智能调控
- [x] LLM 日志分析

### Phase 5: Mobile App

- [x] React Native 项目搭建（Expo + expo-router + Zustand + Axios）
- [x] 设备列表 + 状态面板（Dashboard + Devices 列表/详情页）
- [x] 告警查看（Alerts 列表/详情页 + 筛选 + 确认）
- [x] 远程基本管控（Relay command + Settings 服务器配置）
- [x] WebSocket 实时更新（自动重连、事件分发）
- [x] 推送通知基础设施（expo-notifications 权限/注册/通道）

### Phase 6: 沙箱

- [x] Windows Sandbox 集成（SandboxManager + 嵌入式监控脚本）
- [x] 行为报告生成（BehaviorReporter + 结构化数据模型）
- [x] AI 自动分析沙箱结果（复用 LLMAnalyzer 分析 prompt）

### Phase 7: 系统加固

- [x] 注册表防护（RegistryMonitor — HKLM/HKCU Run/RunOnce/Services 快照对比）
- [x] 服务状态监控（ServiceMonitor — WMI + fallback sc query，状态变更 + 新增/删除）
- [x] 关键目录防篡改（DirectoryIntegrityMonitor — 递归 stat/hash 轮询，检测创建/删除/修改）

## 不推荐的方向（已否决）

| 方向 | 否决理由 |
|------|---------|
| 全栈 Rust/Tauri | Rust 学习成本高，开发慢，AI 生态差 |
| 原生 Win32 C++ | 开发效率太低，不适合快速迭代 |
| 全部 Node.js | Windows 底层操作和 AI 能力弱 |
| 云原生/SaaS | 用户要本地运行，数据不出网 |
| Flutter | 与 Electron Commander 不能共享代码 |

## 变更历史

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-05-29 | 初始设计 | — |
| 2026-05-30 | Phase 5 Mobile App 设计文档 + 初始实现 | 新增 docs/移动端App/README.md；24 个源文件 |
| 2026-05-30 | Phase 6 沙箱集成 | 新增 docs/沙箱集成/README.md；sandbox/ 模块、API 路由、Backend relay、SQLite 表 |
| 2026-05-30 | Phase 7 系统加固 | 3 个新 monitor（注册表/服务/目录完整性）、配置、API 端点、docs/系统加固/README.md |

## 坑 / 注意事项

- Windows Sandbox 只在 Pro/Enterprise 版可用，Home 版需要备选方案
- YARA 规则需要持续更新才能保持有效性
- ML 模型需要用户场景数据训练才能准确
- Tailscale 在中国大陆可能不稳定，需要准备备选组网方案（ZeroTier / WireGuard）
- Electron 打包体积较大（~150MB），考虑后期切 Tauri

## 待办

- [x] 确定项目正式名称（巡查者）
- [x] Agent 框架选型 (FastAPI / Quart / aiohttp)
- [x] Commander UI 框架选型 (Ant Design / shadcn/ui)
- [x] 数据库选型 (SQLite / SQLite + PostgreSQL)
