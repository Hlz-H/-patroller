# 移动端 App（Phase 5）

**状态：** 已完成

## 设计结论

**React Native (Expo) + expo-router + Zustand + Axios。** 只连 Backend（3099），不做直连 Agent。跟 Commander 共享同一套 Backend API 契约，TypeScript 类型保持一致。

## 动机

手机端需要随时查看 PC 安全状态、接收告警推送、远程执行基本管控。桌面端（Commander）不能随身带，移动端是必备的补充入口。

## 网络拓扑

```
┌──────────┐    REST/WS    ┌──────────┐
│  Mobile   │◄───────────►│ Backend  │
│   App     │   port 3099  │  Node.js │
└──────────┘              └────┬─────┘
                               │ REST/WS
                          ┌────▼─────┐
                          │  Agent   │
                          │ (monitored PC)
                          └──────────┘
```

**移动端不直连 Agent**：Agent 跑在被监控电脑上，手机从外部网络访问，只能通过 Backend 中继。

## 设计决策

### 1. Expo (managed) + expo-router

**推荐：Expo SDK 52+，expo-router v4（file-based routing）**

理由：
- Expo managed workflow 零原生配置，`npx create-expo-app` 就能跑
- expo-router 的文件路由跟 Commander 的 react-router 心智模型一致，页面结构一目了然
- OTA 更新（expo-updates）可以直接推补丁，不用走 App Store 审核
- 对比：React Native CLI 需要配置 Xcode/Android Studio，对于这种纯 HTTP API 的 App 属于过度工程

### 2. 状态管理：Zustand

与 Commander 保持一致。三个 Store：
- **deviceStore** — 设备列表、在线状态、metrics 缓存
- **alertStore** — 告警列表、筛选、未读数
- **appStore** — 连接配置（Backend URL）、通知设置

### 3. 网络层：Axios + 自定义 WebSocket hook

Axios 跟 Commander 一致。WebSocket 封装成 React hook（`useWebSocket`），在 App 根组件挂载，自动重连。

### 4. 只用 Backend API，不做直接 Agent 调用

Commander 同时连 Agent 和 Backend，因为它跟 Agent 在同一局域网。手机端只连 Backend（3099），所有 Relay 命令通过 `POST /relay/command` 发送。

### 5. UI 风格：简洁、暗色、信息密度适中

安全监控 App 需要一眼看到状态，不需要花里胡哨。配色跟 Commander 整体一致：暗色背景，绿/黄/红状态指示。

### 6. 不推荐的方案

| 方案 | 理由 |
|------|------|
| React Native CLI（bare） | 需要 Xcode/Android Studio 配置，managed Expo 就够用 |
| Flutter | 跟 Commander（React）不共享代码，两套维护成本 |
| 纯 PWA | 通知能力弱，后台 WebSocket 不可靠，原生体验差 |
| Commander 直接打包成 PWA | Electron 绑了 native API，不能直接跑在手机上 |

## 目录结构

```
mobile/
├── app/                      # expo-router pages
│   ├── _layout.tsx           # Root layout (Stack + register WS)
│   ├── (tabs)/
│   │   ├── _layout.tsx       # Tab navigation
│   │   ├── index.tsx         # Dashboard
│   │   ├── devices.tsx       # Device list
│   │   ├── alerts.tsx        # Alert list
│   │   └── settings.tsx      # Settings
│   ├── devices/
│   │   └── [id].tsx          # Device detail
│   └── alerts/
│       └── [id].tsx          # Alert detail
├── src/
│   ├── services/
│   │   ├── api.ts            # Axios client + all API methods
│   │   ├── ws.ts             # WebSocket hook
│   │   └── notifications.ts  # Push notification setup
│   ├── stores/
│   │   ├── deviceStore.ts    # Zustand: devices + metrics
│   │   ├── alertStore.ts     # Zustand: alerts + filters
│   │   └── appStore.ts       # Zustand: settings + config
│   ├── types/
│   │   └── index.ts          # TypeScript types (mirrors backend)
│   └── components/
│       ├── DeviceCard.tsx     # Device summary card
│       ├── StatusBadge.tsx    # Online/offline/paused indicator
│       ├── AlertRow.tsx       # Single alert list item
│       ├── MetricCard.tsx     # CPU/Mem/Disk gauge
│       └── EmptyState.tsx     # Empty list placeholder
├── app.json
├── package.json
├── tsconfig.json
├── babel.config.js
└── assets/                   # Icons, splash, etc.
```

## 组件树

```
App (_layout.tsx)
└── WebSocketProvider (挂载 ws 连接)
    └── TabNavigator ((tabs)/_layout.tsx)
        ├── Dashboard (index.tsx)
        │   ├── StatusSummary (设备总数/在线/告警)
        │   └── RecentAlerts (最近 5 条告警)
        ├── Devices (devices.tsx)
        │   └── DeviceCard[] (设备列表)
        │       └── DeviceDetail (devices/[id].tsx)
        │           ├── StatusBadge
        │           ├── MetricCard[] (CPU/Mem/Disk/Network)
        │           └── RecentAlerts (该设备告警)
        ├── Alerts (alerts.tsx)
        │   ├── FilterBar (type/severity/device)
        │   └── AlertRow[] (告警列表)
        │       └── AlertDetail (alerts/[id].tsx)
        └── Settings (settings.tsx)
            ├── ServerConfig (Backend URL)
            ├── NotificationsToggle
            └── About
```

## 数据流

```
[App Start]
  ├── appStore.loadConfig() → 读取本地存储的 Backend URL
  ├── WebSocket.connect(backendUrl) → /ws
  ├── deviceStore.fetchDevices() → GET /api/v1/devices
  └── alertStore.fetchAlerts() → GET /api/v1/alerts

[WebSocket Events]
  ├── device:online → deviceStore.setOnline(id)
  ├── device:offline → deviceStore.setOffline(id)
  ├── device:metrics → deviceStore.updateMetrics(id, data)
  └── device:alert → alertStore.addAlert(alert) + 通知

[User Actions]
  ├── Pull-to-refresh → re-fetch current screen data
  ├── Acknowledge alert → POST /api/v1/alerts/:id/acknowledge
  ├── Remote command → POST /api/v1/relay/command
  └── Change settings → appStore.saveConfig() → 重启 WS 连接
```

## 实施任务

> 使用 子代理协调 逐任务实施。每个任务是一个批次，任务内可并行子代理。

### 批次 1：项目脚手架 + 基础设施

**文件：** 创建 `mobile/package.json`、`mobile/app.json`、`mobile/tsconfig.json`、`mobile/babel.config.js`、`mobile/src/types/index.ts`、`mobile/src/services/api.ts`

**意图：** 搭起 Expo 项目骨架，类型定义和 API 客户端就绪

- [x] 创建 package.json（Expo SDK 52, react-native, expo-router, zustand, axios, expo-notifications）
- [x] 创建 app.json + tsconfig.json + babel.config.js
- [x] 创建 src/types/index.ts（镜像 backend 的 Device、Alert、SystemMetrics、WsMessage 等）
- [x] 创建 src/services/api.ts（Axios 实例 + 所有 API 方法封装）

### 批次 2：Zustand 状态管理 + WebSocket hook

**文件：** 创建 `mobile/src/stores/deviceStore.ts`、`mobile/src/stores/alertStore.ts`、`mobile/src/stores/appStore.ts`、`mobile/src/services/ws.ts`

**意图：** 三个 Zustand store + WebSocket React hook，数据层完整

- [x] 创建 deviceStore：设备列表 CRUD、metrics 更新、在线状态切换
- [x] 创建 alertStore：告警列表、添加/确认/筛选
- [x] 创建 appStore：Backend URL 存续、通知开关
- [x] 创建 ws.ts：WebSocket hook（自动连接/重连/事件分发到 stores）

### 批次 3：导航 + 共享组件

**文件：** 创建 `mobile/app/_layout.tsx`、`mobile/app/(tabs)/_layout.tsx`、`mobile/src/components/DeviceCard.tsx`、`mobile/src/components/StatusBadge.tsx`、`mobile/src/components/AlertRow.tsx`、`mobile/src/components/MetricCard.tsx`、`mobile/src/components/EmptyState.tsx`、`mobile/assets/` 占位

**意图：** 导航骨架 + 所有复用 UI 组件

- [x] 创建 app/_layout.tsx（root layout：加载配置 → 挂载 WS → Stack navigator）
- [x] 创建 app/(tabs)/_layout.tsx（Tab navigator：Dashboard/Devices/Alerts/Settings）
- [x] 创建 DeviceCard、StatusBadge、AlertRow、MetricCard、EmptyState 组件
- [x] 创建 assets/ 占位

### 批次 4：Dashboard 首页

**文件：** 创建 `mobile/app/(tabs)/index.tsx`

**意图：** 仪表盘显示设备概览和最近告警

- [x] 状态摘要卡（设备总数/在线/告警未读数）
- [x] 最近 5 条告警列表
- [x] Pull-to-refresh
- [x] 数据来自 deviceStore + alertStore

### 批次 5：Devices 列表 + 详情页

**文件：** 创建 `mobile/app/(tabs)/devices.tsx`、`mobile/app/devices/[id].tsx`

**意图：** 设备列表和详情页面

- [x] devices.tsx：FlatList 设备列表、在线/离线筛选、pull-to-refresh
- [x] [id].tsx：设备详情、Metrics 卡片、该设备告警列表、发送命令按钮

### 批次 6：Alerts 列表 + 详情页

**文件：** 创建 `mobile/app/(tabs)/alerts.tsx`、`mobile/app/alerts/[id].tsx`

**意图：** 告警列表和详情页面

- [x] alerts.tsx：FlatList 告警列表、severity/type 筛选、pull-to-refresh、标记已读
- [x] [id].tsx：告警详情（完整信息、上报设备、操作按钮）

### 批次 7：Settings 页面 + 通知

**文件：** 创建 `mobile/app/(tabs)/settings.tsx`、`mobile/src/services/notifications.ts`

**意图：** 设置页面和推送通知设置

- [x] settings.tsx：Backend URL 配置（输入框 + 保存 + 测试连接）、通知开关、关于信息
- [x] notifications.ts：Expo Notifications 设置 + 权限请求

## 变更历史

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-05-30 | 初始设计 | — |

## 坑 / 注意事项

- **WebSocket 重连策略**：Expo 进后台会暂停 JS 执行，回到前台后需要主动检测 WS 断开并重连
- **Backend URL 配置**：用户需要手动输入 Backend 地址（Tailscale IP 或域名），存 AsyncStorage
- **首次加载体验**：API 请求可能慢（VPN/远程连接），需要 skeleton loading 而不是 spinner
- **通知权限**：iOS 需要用户授权，Android 10+ 也需要运行时权限，都要处理拒绝情况
- **Relay 命令**：部分 Agent 操作（杀进程、禁 USB）不可逆，发送前需要确认对话框
- **Expo SDK 版本**：expo-router v4 需要 Expo SDK 52+，`npx expo install` 处理兼容性
- **TypeScript strict**：跟 Commander 一致使用 strict 模式，避免 `as any` 逃生舱

## 待办

- [x] 批次 1：项目脚手架 + 基础设施
- [x] 批次 2：Zustand 状态管理 + WebSocket hook
- [x] 批次 3：导航 + 共享组件
- [x] 批次 4：Dashboard 首页
- [x] 批次 5：Devices 列表 + 详情页
- [x] 批次 6：Alerts 列表 + 详情页
- [x] 批次 7：Settings 页面 + 通知
