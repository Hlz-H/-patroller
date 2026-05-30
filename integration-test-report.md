# 全链路集成测试报告

**日期**: 2026-05-30  
**环境**: Windows (localhost)  
**Agent**: FastAPI on :8099 | **Backend**: Express on :3099  

---

## Agent 端点 (10/10 ✅)

| 端点 | 方法 | 结果 | 说明 |
|------|------|------|------|
| `/api/v1/status` | GET | ✅ PASS | `status: running`, uptime 正常 |
| `/api/v1/system` | GET | ✅ PASS | CPU 5%, 内存 58.7%, 3 块磁盘, 网络 224 连接 |
| `/api/v1/processes?limit=3` | GET | ✅ PASS | 342 进程追踪中 |
| `/api/v1/usb` | GET | ✅ PASS | 37 个活跃设备 |
| `/api/v1/alerts` | GET | ✅ PASS | 告警列表正常返回 |
| `/api/v1/registry` | GET | ✅ PASS | **Phase 7** — 注册表快照正常 |
| `/api/v1/services` | GET | ✅ PASS | **Phase 7** — 服务快照正常 |
| `/api/v1/directory-integrity` | GET | ✅ PASS | **Phase 7** — 目录完整性正常 |
| `/api/v1/sandbox/status` | GET | ✅ PASS | **Phase 6** — `enabled: false, available: false`（符合配置预期） |
| `/api/v1/config` | POST | ✅ PASS | 配置热更新正常 (`updated: ["process"]`) |

### WebSocket

| 端点 | 结果 | 说明 |
|------|------|------|
| `ws://127.0.0.1:8099/ws` | ❌ 握手超时 | uvicorn 内部 issue（预存问题，非 Phase 6/7 引入） |
| `ws://127.0.0.1:3099/ws` | ✅ PASS | 正常连接 |

---

## Backend 端点 (7/7 ✅)

| 端点 | 方法 | 结果 | 说明 |
|------|------|------|------|
| `/api/v1/health` | GET | ✅ PASS | `status: ok`, deviceCount: 1 |
| `/api/v1/devices` | GET | ✅ PASS | HLZ 在线（Agent 自动注册） |
| `/api/v1/devices/online` | GET | ✅ PASS | 同上 |
| `/api/v1/alerts` | GET | ✅ PASS | 告警列表正常 |
| `/api/v1/alerts/unacknowledged` | GET | ✅ PASS | 16 条未处理告警 |
| `/api/v1/devices/{id}/heartbeat` | POST | ✅ PASS | 新设备注册成功 |
| `/api/v1/devices/{id}/alerts` | POST | ✅ PASS | 告警创建成功 (201 Created) |

---

## 修复的 Bug

### `agent/agent/config.py` — `_process()` 缺少 return 语句

**症状**: Agent 启动时 `ProcessMonitor.__init__` 报 `AttributeError: 'NoneType' object has no attribute 'whitelist'`

**根因**: `_parse_config()` 内嵌函数 `_process()` 定义时只有 `data = raw.get("process", {})` 没有 `return` 语句，导致返回 `None`。

**修复**: 补全 return 语句：
```python
def _process() -> ProcessConfig:
    data = raw.get("process", {})
    return ProcessConfig(
        whitelist=list(data.get("whitelist", [])),
        blacklist=list(data.get("blacklist", [])),
    )
```

---

## 总结

**17/18 端点通过测试 (94.4%)**，Agent 与 Backend 全链路互通。

- Agent 自动注册到 Backend，心跳正常
- 告警推送正常（Agent 产生 → Backend 存储）
- Phase 6 沙箱接口响应正常（sandbox disabled 返回预期错误）
- Phase 7 系统加固接口（registry/service/directory-integrity）全部正常
- 唯一失败的 Agent WS 是 uvicorn 内部 issue，不影响 REST API
