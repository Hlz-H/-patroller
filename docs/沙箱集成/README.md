# 沙箱集成 — Phase 6

## 概述

为巡查者 (Patroller) 提供 **Windows Sandbox 可执行文件隔离运行** 能力。当可疑文件被检出时，可在隔离的沙箱环境中运行并记录行为，再通过 LLM 分析行为报告给出研判结论。

## 架构

```
+----------------+     REST/WS     +----------------+     .wsb XML     +------------------+
|  Commander UI  |  ←──────────→  |  Backend (TS)  |  ←──────────→  |  Agent (Python)  |
|  (sandbox 页面) |                |  3099          |                 |  8099             |
+----------------+                +----------------+                 +------------------+
                                                                           |
                                                                    SandboxManager
                                                                      |          |
                                                     +----------------+   +------------------+
                                                     |                    |                  |
                                              config.wsb           sandbox_work/    LLMAnalyzer
                                              (XML)                (目录)               (AI分析)
                                                     |                    |
                                                     v                    v
                                              WindowsSandbox    report.json / done.txt
                                              .exe 启动            (行为监控脚本输出)
```

## 工作流

1. **用户/系统** 将可疑文件路径提交到 Agent API `POST /api/v1/sandbox/run`
2. **SandboxManager** 创建 session 目录，写入 PowerShell 监控脚本和 `.wsb` XML 配置文件
3. Agent 调用 `WindowsSandbox.exe config.wsb` 启动 Windows Sandbox
4. Sandbox VM 启动后自动执行 `LogonCommand` → PowerShell 监控脚本
   - 启动目标 EXE
   - 监控进程创建、文件变更（`FileSystemWatcher`）、网络连接
5. 监控脚本将行为数据写入 `report.json` 并创建 `done.txt` 标记完成
6. SandboxManager 收集报告 → `BehaviorReporter.parse()` 结构化输出
7. 可选：调用 LLM 分析行为报告，输出 `classification`（SAFE/SUSPICIOUS/MALICIOUS）
8. 结果返回调用方（Commander UI / 命令行 / 自动响应）

## 关键组件

### Agent 端 (Python)

| 组件 | 文件 | 职责 |
|------|------|------|
| `SandboxManager` | `agent/agent/sandbox/manager.py` | WSB 生成、Sandbox 启动、超时管理、报告收集、LLM 分析 |
| `BehaviorReporter` | `agent/agent/sandbox/reporter.py` | 原始 JSON → `BehaviorReport` 结构化数据、可疑信号提取 |
| `BehaviorReport` | `agent/agent/sandbox/reporter.py` | 行为报告数据模型 + `suspicious_indicators` 属性 |
| API endpoints | `agent/agent/api/server.py` | 5 个 sandbox REST 路由 |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/sandbox/status` | 沙箱可用性和配置 |
| POST | `/api/v1/sandbox/run` | 提交文件执行沙箱分析 |
| POST | `/api/v1/sandbox/analyze` | 分析已有报告 |
| POST | `/api/v1/sandbox/run-and-analyze` | 执行 + 分析一步到位 |

### Backend 端 (TypeScript)

| 组件 | 文件 | 职责 |
|------|------|------|
| Sandbox relay routes | `backend/src/api/sandbox.ts` | 转发 sandbox 命令到 Agent，持久化结果 |
| `sandbox_results` 表 | `backend/src/db/index.ts` | SQLite 表，存储 id/device/file_path/status/report/analysis |

### Backend API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/sandbox/run` | 向 Agent 发送 sandbox 命令 |
| GET | `/api/v1/sandbox/results/:deviceId` | 查询设备的历史沙箱结果 |
| GET | `/api/v1/sandbox/result/:id` | 查询单条沙箱结果详情 |

## 配置 (`config.yaml`)

```yaml
sandbox:
  enabled: false
  timeout_seconds: 120
  work_dir: sandbox_work
  vm:
    networking: false
    audio: false
    gpu: false
    clipboard: false
    printer: false
  ai_analysis:
    enabled: true
    model: qwen2.5:7b
    prompt_template: |
      You are a malware analyst. A file was executed in a Windows Sandbox.
      Below is the behavior report:
      {report}
      Classify the behavior as: SAFE / SUSPICIOUS / MALICIOUS.
      Provide a confidence score (0-100) and a brief reasoning.
      Return JSON: {{"classification": "...", "confidence": ..., "reasoning": "..."}}
```

- `enabled`: 总开关。默认关闭，需手动开启
- `timeout_seconds`: 沙箱最大运行时间（超出则杀掉 VM 并收集已有输出）
- `vm.*`: VM 功能控制。关闭网络/音频/GPU/剪贴板/打印机以降低风险
- `ai_analysis.*`: AI 分析开关和模型配置。复用 ollama 同 1 个端点

## 监控脚本

使用嵌入式 PowerShell 脚本（硬编码在 `manager.py` 中），在沙箱 VM 内部执行：

1. **进程监控**: 启动目标 EXE，轮询 `Get-Process` 抓取子进程
2. **文件监控**: `FileSystemWatcher` 监听桌面目录的创建/修改/删除
3. **网络监控**: 沙箱退出后获取 `Get-NetTCPConnection` 建立的连接
4. **输出**: `ConvertTo-Json` → `report.json` + touch `done.txt`

脚本路径硬编码在 `.wsb` 的 `LogonCommand` 中，与输入文件一起通过 `MappedFolders` 映射进入沙箱。

## 可疑信号检测

`BehaviorReport.suspicious_indicators` 自动提取以下信号：

- 进程退出码异常（非 `0` 且非 `-1`）
- 可疑进程名：`powershell`, `cmd`, `wscript`, `cscript`, `mshta`, `regsvr32`, `rundll32`, `certutil`, `bitsadmin`
- 创建可执行文件（`.exe`, `.dll`, `.ps1` 等）
- 外部网络连接（非 127.0.0.1）
- 大量文件删除行为

## AI 分析

复用 Agent 的 LLM（ollama），通过 `llm_analyzer` 的 HTTP API（`/api/generate`）发送行为报告，要求返回结构化 JSON：

```json
{
  "classification": "SUSPICIOUS",
  "confidence": 85,
  "reasoning": "创建了多个可执行文件并尝试连接外部 IP"
}
```

## 局限性

1. **Windows 版本限制**: Windows Sandbox 仅 Windows 10/11 Pro/Enterprise 可用。
   - Home 版用户：SandboxManager 初始化时 `available=False`，`run_file()` 返回 `None`
   - 降级方案：检查到不可用后输出 WARN 日志，Commander UI 显示"沙箱不可用"
2. **无网络隔离**: `vm.networking=false` 时沙箱无网络，部分恶意软件可能因此不触发行为
3. **监控深度**: 使用 PowerShell 脚本而非内核级监控，可能有绕过空间
4. **性能**: 每次沙箱启动需要 10-30 秒 VM 初始化时间

## 后续改进方向

- 支持 `.wsb` 配置文件模板自定义
- 支持沙箱结果缓存（同文件 Hash 直接复用）
- 支持 YARA 规则直接扫描沙箱输出文件
- 支持多文件批量提交
