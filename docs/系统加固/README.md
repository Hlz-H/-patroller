# 系统加固 — Phase 7

## 概述

为巡查者 (Patroller) 提供 Windows 系统层面的加固监控能力。在已有的进程/USB/沙箱基础上，增加对**注册表**、**服务**、**关键目录**三方面的持续监控，覆盖常见持久化、权限提升和篡改攻击面。

## 架构

三个独立 monitor 模块，遵循与其他 monitor 一致的模式（async polling + AlertStore + REST API）：

```
+-------------------+
|  PatrollerAgent   |
+-------------------+
  |    |        |
  v    v        v
+------+ +-------+ +-------------------+
|Registry|Service| DirectoryIntegrity |
|Monitor|Monitor|     Monitor        |
+------+ +-------+ +-------------------+
  |        |        |
  v        v        v
+--------------------------------------+
|           AlertStore                 |
|  (AlertType.SYSTEM + 分类 group_key) |
+--------------------------------------+
  |
  v
+--------------------------------------+
|  API Server (3 GET endpoints)        |
+--------------------------------------+
```

## 模块详情

### 1. RegistryMonitor — 注册表防护

**文件**: `agent/agent/monitors/registry_monitor.py`

监控关键注册表项的添加、删除、值修改。使用 Python 内置 `winreg` 模块，零额外依赖。

**监控范围（默认配置）**：

| 注册表路径 | 说明 |
|------------|------|
| `HKLM\Software\Microsoft\Windows\CurrentVersion\Run` | 系统级开机自启动 |
| `HKLM\...\RunOnce` | 单次启动项 |
| `HKLM\...\ShellServiceObjectDelayLoad` | 浏览器辅助对象（BHO） |
| `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` | 用户级开机自启动 |
| `HKLM\System\CurrentControlSet\Services` | 服务注册项 |

**实现机制**：
- 轮询读取每个 key 下的所有 value name + data
- 与上一周期快照做 diff：新增 → `warn`，删除 → `warn`，修改 → `warn`
- 所有 alert 附带 `registry_key`、`value_name`、`old_value`/`new_value` 等详情

**平台兼容**：
- Windows：正常使用 `winreg`
- 非 Windows：`_REG_AVAILABLE = False`，`run()` 直接 return

### 2. ServiceMonitor — 服务状态监控

**文件**: `agent/agent/monitors/service_monitor.py`

监控 Windows 服务的**创建**、**删除**、**状态变更**（running ↔ stopped）。

**实现机制**：
- 首选 WMI：`Win32_Service` 查询（pywin32）
- 降级：`subprocess.run(["sc", "query"])` 解析输出
- 按 name 做 key 做快照 diff，检测三类变化
- 支持 `monitored_names` 白名单过滤（空 = 监控全部）

**Alert 级别**：
| 事件 | 级别 | group_key 格式 |
|------|------|---------------|
| 新服务创建 | INFO | `service:new:{name}` |
| 服务删除 | WARN | `service:removed:{name}` |
| 状态变更 | WARN | `service:state:{name}` |

### 3. DirectoryIntegrityMonitor — 关键目录防篡改

**文件**: `agent/agent/monitors/directory_integrity.py`

监控关键目录下的文件创建、删除、修改。使用轮询 + stat 对比，可选 SHA-256 哈希校验。

**监控路径（默认配置）**：

| 目录 | 说明 |
|------|------|
| `C:\Windows\System32\drivers\etc` | hosts 文件篡改 |
| `C:\Program Files` | 程序安装/卸载 |

**检测能力**：
| 变化 | 检测依据 | Alert 级别 |
|------|----------|-----------|
| 文件创建 | 路径不在上一快照中 | WARN |
| 文件删除 | 路径在上一快照但不在当前 | CRITICAL |
| 文件修改 | size 变化 / mtime 变化 / hash 不匹配 | WARN |

**性能考虑**：
- `check_hash: false`（默认）→ 只对比 stat（size + mtime），开销极小
- `check_hash: true` → 计算 SHA-256 前 16 字节，适合小目录精确检测
- 监控大目录（如 C:\Windows）时建议调大 `interval_seconds` 或缩小路径范围

## 配置参考

```yaml
monitors:
  registry:
    enabled: true
    interval_seconds: 30      # 注册表变化不频繁，30s 足够
  service:
    enabled: true
    interval_seconds: 15
  directory_integrity:
    enabled: true
    interval_seconds: 60

registry:
  monitored_keys:
    - "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    - "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    # ...

service:
  monitored_names: []          # 空 = 监控全部
  alert_on_state_change: true
  alert_on_new_service: true

directory_integrity:
  monitored_paths:
    - "C:\\Windows\\System32\\drivers\\etc"
  watch_recursive: true
  check_hash: false
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/registry` | 当前注册表快照 + monitor 状态 |
| GET | `/api/v1/services` | 当前服务列表 + monitor 状态 |
| GET | `/api/v1/directory-integrity` | 当前目录快照 + monitor 状态 |

## 后续改进

- 注册表支持值数据类型的完整解析（DWORD/QWORD/REG_EXPAND_SZ）
- 服务监控增加启动类型变更告警（auto→disabled）
- 目录监控支持文件权限（ACL）变化检测
- 支持 Windows Event Log 订阅替代轮询（减少开销）
