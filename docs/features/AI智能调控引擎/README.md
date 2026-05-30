# AI 智能调控引擎

**状态：** 已完成

## 设计结论

新增一个 `agent/controllers/smart_control.py` 模块，作为 Agent 的"大脑"——周期性评估系统状态，自适应调优监控参数，并对告警做智能响应。不替换现有组件，而是在它们之上加一层协调逻辑。

## 动机

目前 Agent 的监控参数全是静态配置：间隔写死在 config.yaml，阈值靠人工拍脑袋。一个正常工作的系统和被攻击的系统用同一套监控参数，纯属浪费资源。

AI 调控引擎的目标：
1. **自适应调优**：系统空闲时放大监控间隔省资源，检测到异常时收紧间隔抓细节
2. **智能响应**：低危告警自动处理（如杀掉可疑进程），高危告警触发沙箱深度分析
3. **基线学习**：学习系统正常运行时的指标基线，精准识别真正的异常，减少误报

## 设计决策

### 架构：三层循环

```
┌─────────────────────────────────────────────┐
│             SmartControlEngine              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │   Tuner  │  │ Responder│  │ Baseline │  │
│  │ (调参)   │  │ (响应)   │  │ (基线)    │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │              │        │
│  ┌────▼──────────────▼──────────────▼─────┐  │
│  │         State Evaluator               │  │
│  │   (每分钟评估一次系统状态)              │  │
│  └────────────────────────────────────────┘  │
└────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌──────────┐
    │ Monitors│   │Detectors│   │ AlertStore│
    │(6个)    │   │(3个)    │   │          │
    └─────────┘   └─────────┘   └──────────┘
```

**State Evaluator**（核心）：每分钟运行一次，收集所有 monitor 最新指标 + 最近一分钟的告警 → 计算系统健康评分（0-100）→ 生成状态摘要文本 → 喂给三个子模块。

**Tuner**：根据系统评分动态调整：
- 健康分 80+（一切正常）：监控间隔 ×2，降低采样频率
- 健康分 50-80（轻度异常）：恢复正常间隔
- 健康分 <50（明确异常）：监控间隔 ×0.5，开启详细日志
- 健康分 <20（严重异常）：间隔 ×0.25，所有监控全开

**Responder**：根据告警类型和严重度自动响应：
- `critical` + `process`：调用 OS kill 进程 + 触发沙箱分析
- `critical` + `usb`：禁用 USB 端口
- `warning` + `registry`：记录注册表快照，增加监控频率
- `warning` + 重复告警：调用 LLMAnalyzer 做深度分析
- `info`：记录日志，不操作

**Baseline**：在系统"安静期"（连续 2 小时无告警）自动学习：
- CPU/内存/磁盘 IO 的正常范围（均值 ± 2σ）
- 进程白名单
- 注册表修改频率基线
- 基线持久化到 `data/baseline.json`

### 现有的 LLMAnalyzer 怎么用

不重复造 LLM 调用。Responder 在遇到**需要判断**的场景时（如"这个注册表修改是正常的 Windows Update 还是恶意行为？"）调用 LLMAnalyzer 做深度分析。Tuner 和 Baseline 不依赖 LLM，纯数学。

### 配置结构

```yaml
smart_control:
  enabled: true
  evaluation_interval: 60  # 秒，状态评估周期
  tuner:
    enabled: true
    idle_multiplier: 2.0    # 空闲时间隔放大倍数
    stress_multiplier: 0.25 # 高压时间隔缩小倍数
  responder:
    enabled: true
    auto_respond_critical: true   # 自动响应 critical 告警
    auto_respond_warning: false   # warning 需人类确认
    llm_threshold: 3              # 同一告警重复 N 次后调 LLM 分析
  baseline:
    enabled: true
    learning_period: 7200  # 秒，学习基线需要的最小安静期
    storage_path: data/baseline.json
```

### 为什么不用规则引擎

规则引擎（如 Drools、simple-rules）适合确定性逻辑，但这里的调优和响应需要根据系统状态做**连续数值调整**和**概率判断**。数学计算 + 简单阈值比规则引擎更直接，成本更低。

## 文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 创建 | `agent/agent/controllers/__init__.py` | 空 |
| 创建 | `agent/agent/controllers/smart_control.py` | SmartControlEngine 主类 |
| 创建 | `agent/agent/controllers/state.py` | SystemState / StateEvaluator |
| 创建 | `agent/agent/controllers/tuner.py` | AdaptiveTuner |
| 创建 | `agent/agent/controllers/responder.py` | AlertResponder |
| 创建 | `agent/agent/controllers/baseline.py` | BaselineLearner |
| 创建 | `tests/test_smart_control.py` | 测试 |
| 修改 | `agent/agent/config.py` | 加 SmartControlConfig |
| 修改 | `agent/agent/config.yaml` | 加 smart_control 配置段 |
| 修改 | `agent/agent/main.py` | 初始化和启动 SmartControlEngine |
| 修改 | `agent/agent/alert.py` | 添加响应动作字段 (action_taken) |

## 设计决策记录

| 决策 | 选择 | 放弃的方案 | 原因 |
|------|------|-----------|------|
| 调控频率 | 每分钟 | 每5秒/每10分钟 | 太快浪费资源，太慢来不及响应 |
| 基线算法 | 均值+2σ | 滑动窗口/ML模型 | 够用且可解释，ML 训练成本高 |
| 响应模式 | 内置简单动作 | 只依赖 LLM | LLM 有延迟和成本，简单场景直接处理 |
| LLM 调用 | 仅在重复告警时 | 每次告警都调 | 省钱省时间 |

## 变更历史

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-05-30 | 初始设计 | — |

## 坑 / 注意事项

- Tuner 修改的间隔值不能持久化到 config.yaml，否则下次启动就用错值了。修改值存在内存中，每次重启从 config.yaml 重新加载
- 基线文件可能被篡改。Baseline 加载后做简单校验（JSON schema + 值范围合理性检查）
- LLMAnalyzer 如果挂了（Ollama 不通），Responder 必须降级为只记录不分析，不能阻塞
- 状态评估循环不能阻塞主事件循环，必须用 `asyncio.create_task` 跑后台

## 实施任务

### 任务 1：控制器基础 + SystemState

**文件：** 创建 `agent/agent/controllers/__init__.py`、`agent/agent/controllers/smart_control.py`、`agent/agent/controllers/state.py`、修改 `agent/agent/config.py`、`agent/agent/config.yaml`

**意图：** 实现 SmartControlEngine 框架、SystemState 数据类、StateEvaluator 状态评估逻辑，以及配置加载

- [x] 在 config.py 中添加 SmartControlConfig dataclass
- [x] 在 config.yaml 中添加 smart_control 配置段
- [x] 创建 controllers/__init__.py
- [x] 实现 state.py：SystemState dataclass + StateEvaluator（收集 monitor 指标 + 告警 → 计算健康分 → 生成摘要）
- [x] 实现 smart_control.py：SmartControlEngine 主类（启动/停止后台循环，编排各子模块）

### 任务 2：AdaptiveTuner

**文件：** 创建 `agent/agent/controllers/tuner.py`

**意图：** 根据健康分动态调整 monitor 间隔

- [x] 实现 AdaptiveTuner：输入健康分 → 计算每个 monitor 的 multiplier → 调用 monitor 的配置更新方法
- [x] 给 Monitor 基类添加 `update_interval(multiplier)` 方法支持运行时改间隔
- [x] 测试：健康分 90 时间隔放大 2x，健康分 30 时间隔缩小 0.5x

### 任务 3：AlertResponder

**文件：** 创建 `agent/agent/controllers/responder.py`、修改 `agent/agent/alert.py`

**意图：** 根据告警自动执行响应动作

- [x] 在 Alert/AlertStore 中添加 `action_taken` 字段和动作记录
- [x] 实现 AlertResponder：订阅 AlertStore 新告警 → 匹配规则 → 执行动作
- [x] 支持动作：kill_process, disable_usb, trigger_sandbox, increase_monitoring, call_llm
- [x] Responder 调用 LLMAnalyzer 做深度分析的接口（仅重复告警时触发）

### 任务 4：BaselineLearner

**文件：** 创建 `agent/agent/controllers/baseline.py`

**意图：** 学习系统正常运行的基线

- [x] 实现 BaselineLearner：检测安静期 → 收集指标 → 计算均值/标准差 → 持久化
- [x] 基线加载验证（JSON schema + 值范围检查）
- [x] 加载基线后，Tuner 可以使用基线差异度作为健康分的一部分

### 任务 5：集成到 main.py

**文件：** 修改 `agent/agent/main.py`

**意图：** 在 Agent 启动时初始化 SmartControlEngine

- [x] 在 main.py 的初始化流程中添加 SmartControlEngine
- [x] 启停生命周期管理（start/stop）
- [x] 验证：启动 Agent 后 SmartControlEngine 开始周期性输出状态日志

### 任务 6：测试

**文件：** 创建 `tests/test_smart_control.py`

**意图：** 完整测试所有组件

- [x] StateEvaluator：健康分计算逻辑
- [x] AdaptiveTuner：各种健康分下的 multiplier
- [x] AlertResponder：各告警类型触发的动作
- [x] BaselineLearner：基线学习、加载、校验
- [x] SmartControlEngine：启停、循环调度
