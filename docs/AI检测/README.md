# AI 检测能力（Phase 4）

**状态：** 已完成

## 设计结论

在 Agent 内部直接集成三种 AI 检测能力：YARA 规则引擎扫描进程/文件、ML 异常检测分析进程行为、LLM 本地模型分析安全日志。三者都是 Agent 的**可选增强模块**，不依赖外部云服务，默认关闭，用户手动开启。

## 动机

现有的监控系统只能做规则匹配（黑名单进程、USB VID/PID 封锁），对未知威胁无能为力。AI 检测的目标：

1. 用 YARA 规则匹配已知恶意软件特征（内存扫描、文件扫描）
2. 用 ML 模型识别异常的进程行为（挖矿行为、横向移动、数据窃取）
3. 用 LLM 聚合分析告警，去重、定级、给出处置建议

## 设计决策

### 总体架构

```
Agent main loop
  ├── Monitors (existing)
  │   ├── SystemResourceMonitor
  │   ├── ProcessMonitor
  │   └── USBMonitor
  ├── AI Detectors (new)
  │   ├── YaraDetector     ─ 扫描新进程/内存/文件
  │   ├── MLAnomalyDetector ─ 进程行为异常评分
  │   └── LLMAnalyzer      ─ 告警聚合分析
  ├── Alert Engine (existing)
  ├── API Server (existing)
  └── BackendClient (existing)
```

三个检测器相互独立，各自产生告警，通过 AlertStore 统一上报。

### YARA 规则引擎

**推荐方案：** `yara-python`（直接调用 yara C 库）

- 规则管理：从 `rules/` 目录加载 `.yar` 文件，支持热加载
- 扫描对象：
  - 新进程启动时扫描其可执行文件（`exe` 路径）
  - 定期扫描高危进程的内存（可选，CPU 开销大）
  - 新文件创建事件（通过 Windows 通知或轮询）
- 规则来源：内置基础规则集 + 用户自定义
- 匹配到规则 → 产生 `AlertType.YARA` 告警

### ML 异常检测

**推荐方案：** `scikit-learn` Isolation Forest（离线训练 + 在线推理）

- 特征工程（从 SystemResourceMonitor + ProcessMonitor 提取）：
  - 进程维度：CPU%、Mem%、线程数、句柄数、网络连接数
  - 系统维度：全局 CPU 负载、内存压力、网络吞吐变化率
  - 父子进程关系：子进程创建速率、非常规父进程（如 word.exe 启动 powershell.exe）
- 训练模式：
  - 初始：收集 24 小时正常基线 → 训练 Isolation Forest 模型
  - 持续更新：每 N 小时滚动重训练，只保留正常样本
- 推理模式：
  - 每轮 poll 对活跃进程评分，异常分 > 阈值 → `AlertType.ANOMALY`
- 模型持久化：`joblib` 存到磁盘 `models/anomaly_detector.joblib`

### LLM 日志分析

**推荐方案：** 直接 HTTP 调用 `ollama` API（`http://localhost:11434/api/generate`）

- 不引入额外包，直接用 `requests` 或 `httpx`
- 推荐模型：`qwen2.5:7b`（中文好、体积适中、7B 能在消费级 GPU/CPU 运行）
- 分析模式：
  - **聚合分析**（默认）：每 30 分钟或 50 条告警，批处理 → LLM 总结趋势、去重、定级
  - **实时分析**（可选）：单条高危告警 → LLM 判断是否需要立即处置
- Prompt 结构：
  - 系统提示：设定安全分析专家角色 + 输出格式（JSON）
  - 用户消息：时间范围内的告警列表
  - 输出：分类/去重后的告警摘要 + 风险等级 + 处置建议
- LLM 输出作为告警 enrichment，不阻塞主流程

### 配置文件

```yaml
ai:
  enabled: false  # 总开关

  yara:
    enabled: false
    rules_dir: "rules/"
    scan_new_processes: true
    scan_process_memory: false
    scan_interval_seconds: 30

  ml_anomaly:
    enabled: false
    model_path: "models/anomaly_detector.joblib"
    contamination: 0.01  # 预期异常比例
    training_hours: 24    # 初始训练需要的小时数
    retrain_interval_hours: 4

  llm:
    enabled: false
    endpoint: "http://localhost:11434"
    model: "qwen2.5:7b"
    batch_interval_minutes: 30
    batch_size: 50
```

### 依赖变更

```txt
# AI 检测（Phase 4）
yara-python>=4.5.0
scikit-learn>=1.3.0
joblib>=1.3.0
```

`ollama` 不引入 Python 包，直接 HTTP 调用。

### 调研结论

**YARA 规则来源：** [YARA Forge](https://github.com/YARAHQ/yara-forge) 三级策略 — Core（~5K 条，低误报）→ Extended（~10K）→ Full（~11K）。生产环境用 Core 起步。yara-python 4.1.3+ 支持 Python 3.12，用预编译 wheel 避免 MSVC 编译。

**ML 升级路径：** sklearn Isolation Forest 起步 → 需要流式更新时切换到 [River](https://github.com/online-ml/river) 的 HalfSpaceTrees（6K⭐），逐样本增量更新无需批重训练。

**LLM 模型确认：** Qwen2.5 7B 中文能力最强（SSlogs、ForensIQ 等项目均验证），推荐用 `ollama` Python 官方包 + Pydantic schema 约束结构化输出。

### 不推荐的方案

- **TensorFlow/PyTorch 做异常检测**：太重了，杀鸡用牛刀，Isolation Forest / River 足够
- **云 LLM API（OpenAI/Claude）**：违反本地优先约束
- **端上实时训练深度学习模型**：训练计算开销不适合后台 Agent，推理可以但训练不行
- **把 LLM 放在 Agent 进程内**：ollama 是独立进程，Agent 只做 API 调用

## 实施任务

> 使用 子代理协调 逐任务实施。

### 任务 1：YARA 检测器

**文件：** 创建 `agent/agent/detectors/__init__.py`、`agent/agent/detectors/yara_detector.py`、`rules/` 目录；修改 `agent/agent/config.py`、`agent/agent/config.yaml`、`agent/agent/main.py`

**意图：** 集成 yara-python 扫描新进程的可执行文件，命中规则产生告警

- [x] 创建 YaraDetector 类：加载规则目录、扫描文件/进程内存、回调上报告警
- [x] 创建基础规则集（几条示例规则：powershell 加密执行、可疑 rundll32）
- [x] 修改 config.py/yaml 添加 ai.yara 配置段
- [x] 修改 main.py 集成 YaraDetector
- [x] 验证：放置测试规则文件 → 启动进程 → 触发告警

### 任务 2：ML 异常检测器

**文件：** 创建 `agent/agent/detectors/ml_anomaly.py`；修改 `agent/agent/config.py`、`agent/agent/config.yaml`、`agent/agent/main.py`

**意图：** 基于进程行为做 Isolation Forest 异常检测

- [x] 创建 MLAnomalyDetector 类：特征提取、模型训练/加载、在线推理
- [x] 集成到 main.py（从现有 monitors 获取进程数据）
- [x] 添加配置项
- [x] 验证：模拟异常进程行为 → 触发告警

### 任务 3：LLM 告警分析器

**文件：** 创建 `agent/agent/detectors/llm_analyzer.py`；修改 `agent/agent/config.py`、`agent/agent/config.yaml`、`agent/agent/main.py`

**意图：** 批处理告警，通过本地 ollama 模型分析并 enrichment

- [x] 创建 LLMAnalyzer 类：告警缓冲、批量请求 LLM、输出解析
- [x] 设计 prompt 模板
- [x] 集成到 AlertStore（监听告警事件，攒批）
- [x] 验证：制造多条告警 → 等待批处理 → 检查 enrichment 结果

### 任务 4：安装依赖 & 集成测试

**文件：** `agent/requirements.txt`

**意图：** 确保新依赖正确安装，全模块可导入

- [x] 添加 yara-python、scikit-learn、joblib 到 requirements.txt
- [x] `pip install` 验证安装成功
- [x] `python -c "from agent.detectors.yara_detector import YaraDetector; ..."` 验证导入

## 变更历史

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-05-29 | 初始设计 | — |

## 坑 / 注意事项

- **yara-python Windows 编译**：需要 MSVC 或预编译 wheel，建议 `pip install yara-python` 时确保有 VC++ 运行时。如果编译失败，考虑使用 `pip install yara-python==4.5.0` 的预编译版本
- **ollama 不存在时不阻塞**：LLMAnalyzer 必须优雅降级，ollama 服务未启动时只记 WARN 不报错
- **ML 模型冷启动**：初始 24 小时内没有训练数据时，MLAnomalyDetector 应记录状态但不产生误报
- **性能开销**：YARA 扫描大文件会卡主循环，扫描必须在独立线程/进程中运行，通过队列返回结果
- **规则更新**：YARA 规则变更需要热加载，不重启 Agent（监测 `rules/` 目录 mtime）
