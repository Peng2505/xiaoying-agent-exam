# AI 辅助开发记录

本文件只记录已经核实的事实。未执行的开发、测试和无法确认的人工操作，不写成已完成。

记录规范见项目根目录 `AGENTS.md` 第 8 节。后续每个开发阶段结束前在文末追加，不改写已有阶段。
## 开发者职责与技术贡献

本项目采用 AI 辅助开发方式，结合 Cursor、ChatGPT 和 DeepSeek API 完成 Agent 应用的设计、实现与验证。

### 1. 需求理解与技术决策

本人负责确定项目目标、选择业务场景、确认技术方案以及制定阶段性验收要求。

综合项目复杂度、可解释性和工程实现成本，最终选择 Python CLI、单 Agent 架构及基于真实 LLM Tool Calling 的动态决策方案。

### 2. AI 辅助开发与工程协作

使用 Cursor 辅助完成代码实现、调试、测试设计与文档整理；使用 ChatGPT 辅助进行技术方案评估、风险分析与独立代码审查。

本人负责确认关键技术选择、审查 AI 提出的方案，并根据评审反馈安排针对性改进。

### 3. Agent 能力设计与验证

重点关注以下能力：

- 模型根据工具观察结果自主选择下一步动作
- 预算超限后的动态重规划
- 工具执行失败后的恢复策略
- 已成功步骤的结果复用
- 预算、截止时间及状态约束
- 幂等保存、执行上限与异常退出

通过 T01–T08 场景验证上述能力。具体测试执行者、实际结果和证据路径见阶段记录及评估文档。

### 4. 问题分析与持续改进

采用分阶段开发和验收方式，结合 AI 交叉审查发现设计与实现中的潜在问题。

对于发现的问题，确认修复方向，由 Cursor 辅助完成代码修改及回归测试，并根据实际验证结果决定是否进入下一阶段。

### 5. 个人代码理解与独立验证

本节记录本人亲自完成的代码阅读、命令执行、测试结果核对和问题验证。

具体操作、日期、执行命令及观察结果应在完成后据实填写。尚未完成的验证不记录为已完成。

### 6. AI 使用边界

Cursor 主要承担代码生成、调试与测试执行；ChatGPT 主要提供方案评估和独立审查建议；DeepSeek API 是项目运行时的模型决策服务。

个人贡献与 AI 辅助内容明确区分，不虚构人工代码修改或独立测试结果。

## 总览（整合，不替代下文分阶段原文）

| 方面 | 已核实内容 |
| --- | --- |
| AI 工具 | Cursor（本仓库开发/修复会话）；ChatGPT（技术方案评估与独立代码审查反馈，由开发者整理后交 Cursor 修复）；DeepSeek API（运行时真实 Tool Calling） |
| Cursor 主要工作 | 需求分析与设计文档、代码实现（Agent/工具/守卫/续跑）、测试设计与真实场景执行、文档撰写、独立审查缺陷的最小修复与回归 |
| ChatGPT 主要工作 | 方案评估、风险分析、独立终审缺陷清单（superseded / 非法参数崩溃 / 指纹缺 outline / Mock 不完整 / 缺 T02 证据等）；**未直接在本仓库改代码** |
| 开发者已确认决策 | 选题第 2 题；Python+CLI+真实 Tool Calling；不用 LangGraph；T02 CLI 拒识；分阶段验收；确认独立审查修复报告；同意最终 GitHub 提交 |
| 开发者未在对话中亲自粘贴的代码修改 | 标记为「待用户确认」；**不虚构**独立手写编码或未发生的人工测试 |
| 验证 | 单元测试与 T01–T08 及修复后 T04 复跑证据见 `examples/`；详见下文各阶段 |

以下为按时间追加的原始阶段日志（保留不删改）。

## 使用的 AI 工具

| 日期 | 工具 | 本阶段实际做了什么 |
| --- | --- | --- |
| 2026-10-29 | Cursor | 阅读现有文档，核对目录与 Git 状态，创建本文件，并把持续记录规范写入 `AGENTS.md`；后续各阶段实现与修复见下文 |
| 2026-10-29 | ChatGPT | 开发者侧用于技术方案评估与独立代码审查；审查结论由开发者整理为缺陷清单后交 Cursor 最小修复（见「独立审查修复轮」） |
| 2026-10-29 | DeepSeek API | 真实场景 T01–T08 及修复后 T04 复跑的模型决策服务 |

本记录创建之前的文件由谁编写，当前会话无法核实。

## 记录字段

每个阶段使用下表。复制到文末后填写，不要把空表本身当成已完成工作。

| 字段 | 填写要求 |
| --- | --- |
| 阶段 | 日期与阶段名称 |
| AI 辅助内容 | Cursor 实际完成的分析、设计、代码、修改、调试或测试设计 |
| 人工贡献 | 仅写用户已实际做出的决策、修改、检查或验证；无法确认时写「待用户确认」 |
| 验证结果 | 写运行命令、结果和证据路径；未执行则写「未执行」 |
| 未解决问题 | 仍存在的错误、缺口或待确认项；没有则写「无」 |

## 截至 2026-10-29 12:19 已核实的仓库状态

本次记录开始前，项目目录内只有以下文件：

| 路径 | 核实方式 | 内容范围 |
| --- | --- | --- |
| `AGENTS.md` | 直接阅读 | 项目开发规范；第 13 节写明已选第 2 题 |
| `docs/exam-requirements.md` | 直接阅读 | 考试规则与 GitHub 交付规范 |
| `docs/exam-question-2.md` | 直接阅读 | 第 2 题「内容任务规划 Agent」原文 |

同一时刻尚未出现：`README.md`、`requirements.txt`、`.env.example`、`src/`、`tests/`、`examples/`、`data/`，以及 `docs/01-requirements.md`、`docs/02-solution.md`、`docs/03-evaluation.md`、`docs/05-retrospective.md`。

项目目录内没有 `.git`。在该目录执行 `git rev-parse --show-toplevel`，返回的仓库根是 `D:/`，且当前分支没有任何提交。因此本项目还没有可提交的 Commit SHA。

未运行任何测试，也没有运行 Trace。

## 阶段日志

### 2026-10-29 阶段 0：记录建立前已存在的材料

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 无法从本会话核实。不把这三份文件的编写归因于 Cursor。 |
| 人工贡献 | 待用户确认。`AGENTS.md` 第 13 节写有「已选择第 2 题」，但本会话没有看到用户做出该选择的过程。 |
| 验证结果 | 未执行测试。只通过阅读文件和列出目录确认上述三份文件存在，且没有业务代码与测试代码。 |
| 未解决问题 | 见下方「关键问题」1、2、3。 |

### 2026-10-29 阶段 1：建立 AI 使用记录

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 阅读 `AGENTS.md`、`docs/exam-requirements.md`、`docs/exam-question-2.md`；列出项目文件；执行 `git rev-parse --show-toplevel` 核对仓库根。创建 `docs/04-ai-usage.md`。在 `AGENTS.md` 第 8 节写入 8 条持续记录规范，并在第 10 节、第 13.8 节加上更新本文件的要求。 |
| 人工贡献 | 用户在本会话要求建立该记录、规定 8 条记录规则，并要求只填写已核实内容。用户未在本会话修改代码或执行测试。 |
| 验证结果 | 未执行测试。本阶段没有可运行程序。文件写入后的存在性，以本次任务结束时磁盘上的 `docs/04-ai-usage.md` 与更新后的 `AGENTS.md` 为准。 |
| 未解决问题 | 记录规范已写入，业务实现、测试和 Git 提交均未开始。 |

### 2026-10-29 阶段 2：技术设计与设计修订（未写代码）

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | Cursor 阅读三份规范文档，起草技术设计：要求对照、架构、决策循环、四个工具的结构、硬约束、T01–T08 测试方案、目录、分阶段计划、风险。按用户审阅意见修订了以下内容：T07 续跑（按真实执行次数注入失败、`save_plan:always`、默认步数上限、续跑摘要上下文、不重复执行成功步骤）；T04 断言（不暴露价格，验证行为和约束，不规定固定调用顺序）；`pyproject.toml` 打包；`record_attempt` 状态一致性规则；测试真实性规则；README 验收点索引；阶段 A–G 的验收标准。设计文件：`.cursor/plans/内容任务规划agent设计_c79f056e.plan.md`。 |
| 人工贡献 | 用户审阅初版设计，确认以下决定：Python + CLI + 真实 LLM Tool Calling；单 Agent 加四个工具，不用 LangGraph；OpenAI 兼容接口，模型由环境变量配置；T02 由 CLI 校验、不调用 LLM；同意在项目目录 `git init`；继续维护本记录。用户还提出七条修订要求（T07、T04、打包、状态一致性、测试真实性、评审体验、工作顺序）。用户正式确认选择第 2 题。 |
| 验证结果 | 未执行测试。本阶段只有设计文档，没有代码。 |
| 未解决问题 | 1. Cursor 请求切换到执行模式写代码，用户界面拒绝了这次切换，阶段 A 尚未开始。2. 阶段 C 之前需要可用的 LLM 服务和 Key。3. 下方「关键问题」第 1 项（`AGENTS.md` 第 12 节矛盾）计划在阶段 A 修正，现已具备条件：用户已确认选题。 |

### 2026-10-29 阶段 A：骨架、打包和数据

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | Cursor 在项目目录执行了 `git init -b main`（未提交），编写了 `.gitignore`、`pyproject.toml`、`requirements.txt`、`.env.example`，以及包骨架 `src/content_agent/`（`__init__.py`、`__main__.py`、`config.py`、`results.py`、`cli.py`）。`cli.py` 实现了 T02 的确定性校验：缺少预算或截止时间直接拒绝，不调用 LLM。还编写了合成数据 `data/costs.json`（三种格式合计分别为 12、10、8）、`data/materials.json`，测试 `tests/test_cli_validation.py`、`tests/test_data_files.py`。另外修正了 `AGENTS.md` 第 12 节，并排查、修复了 Windows 下的输出乱码。与设计不同的一处：统一结果结构放在新文件 `results.py`，而不是 `tools.py`。 |
| 人工贡献 | 用户在会话中下达「开始阶段A」指令，并确认了阶段 A 的范围（`git init`、T02 由 CLI 校验）。本阶段代码均由 Cursor 编写；用户是否另行审阅代码，待用户确认。 |
| 验证结果 | 全部真实执行。（1）`python -m venv .venv` 后 `.venv\Scripts\python.exe -m pip install -r requirements.txt`：安装成功。（2）`content-agent --help`、`python -m content_agent run --help`：退出码 0。（3）缺 `--budget`、缺 `--deadline`：都输出 `missing_constraints`，`llm_calls=0`，退出码 2。（4）约束齐全：输出「Agent 循环尚未实现」，退出码 3，这是阶段 A 的预期占位。（5）非法 `--inject-failure bad:1`：被拒绝，退出码 2。（6）`python -m pytest -v`：21 passed，证据为 `examples/unit_tests/pytest_phase_a.txt`。（7）在仓库外任意工作目录运行时，数据目录仍正确解析到项目内 `data/`。（8）`git status` 确认 `.venv`、`*.egg-info`、`.pytest_cache` 未被跟踪。 |
| 未解决问题 | Agent 循环、四个工具和续跑尚未实现（阶段 B、C）。尚无 Git 提交（阶段 G）。尚未在全新 clone 目录中复现（计划在阶段 F）。 |

### 2026-10-29 阶段 B：四个工具、硬约束、状态与幂等

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | Cursor 实现了 `state.py`（Step/RunState、`record_attempt`、原子持久化、`resume_summary`）、`store.py`（方案指纹与幂等索引）、`tools.py`（四个业务工具与按真实执行次数的失败注入）、`guards.py`（计划校验、依赖、成功步骤保护、复用、finish、缺口计算）、`executor.py`（守卫→执行/复用→记状态→落盘；失败后不自动重试）。编写并真实运行了阶段 B 单元测试。与设计一致的一点：费用表不向工具描述暴露价格。与设计略有不同：新增 `executor.py` 作为调度入口，便于阶段 C 的 Agent 直接调用。 |
| 人工贡献 | 用户验收阶段 A 后明确下达阶段 B 范围与九条约束（统一返回、禁止代码伪装决策、硬约束复核、真实状态、幂等四类用例、失败注入、单元测试清单、AI 记录、不提前写 Agent 循环）。本阶段代码均由 Cursor 编写；用户是否另行审阅，待用户确认。 |
| 验证结果 | `python -m pytest -v`：**50 passed**。证据：`examples/unit_tests/pytest_phase_b.txt`。覆盖：正常工具链、错误输入、失败注入与 RETRY_EXHAUSTED、预算超限观察与保存拒绝、截止时间拒绝、依赖错误、重复保存（同次/跨次）、不同内容再保存、成功步骤复用、失败历史保留、状态持久化恢复、重规划保留成功步骤。未调用真实 LLM。 |
| 未解决问题 | Agent 循环、真实 LLM Tool Calling、Trace、CLI 接入 executor、续跑会话均未实现（阶段 C–E）。尚无 Git 提交。 |

### 2026-10-29 阶段 C：真实 DeepSeek Agent 循环与 T01

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 先排查阶段 B 三项风险：补强成功步骤复用（比对业务参数，不一致返回 `ARGS_MISMATCH_ON_SUCCEEDED`）；加强 `save_plan` 对 estimate/script 格式一致性校验并加回归测试；在 Agent 中明确三类计数。实现 `llm.py`（RealLLM + MockLLM，DeepSeek `thinking.disabled`）、`prompts.py`、`trace.py`、`agent.py`、`scripts/probe_tool_calling.py`，并接入 CLI。未把价格写入工具描述。 |
| 人工贡献 | 用户验收阶段 B，确认进入阶段 C；本地自行配置 `.env`（DeepSeek Key，对话中未展示密钥）；确认默认模型 deepseek-flash、非思考模式。代码均由 Cursor 编写；用户是否另行审阅待确认。 |
| 验证结果 | （1）回归后单元测试 **54 passed**，证据 `examples/unit_tests/pytest_phase_c.txt`。（2）真实探测 `scripts/probe_tool_calling.py`：**ok=true**，模型返回 `update_plan` tool_call，证据 `examples/unit_tests/probe_tool_calling.json`。（3）T01 真实运行：**status=completed**，steps_used=6，total_cost=10，方案已保存；证据 `examples/T01_normal/`。（4）探索性预算超限运行（非正式 T04）：先估 video_premium=12/`within_budget=false`，再 update_plan 换 video_basic=10 后保存成功；证据 `examples/T04_exploratory/`，`formal_acceptance=false`。 |
| 未解决问题 | 续跑 `--resume` 尚未完整实现（阶段 E）。正式 T03/T04/T05 验收在阶段 D。Mock 默认脚本不完整，仅作 CLI 占位。 |

### 2026-10-29 阶段 D：T03 / T04 / T05 真实场景

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 一致性加固：`compute_gap` 改为综合全部估算、在存在可行估算时返回 None；prompt 区分 retryable 临时故障与约束不可行（不写死换哪种格式）。新增回归 `tests/test_phase_d_consistency.py` 与归档脚本 `scripts/archive_run.py`。用真实 DeepSeek 正式跑通 T03、T04、T05 并落盘 examples。 |
| 人工贡献 | 用户验收阶段 C 后确认进入阶段 D，并规定正式 T03/T04/T05 验收标准。代码与场景运行由 Cursor 执行；用户是否另行审阅 Trace，待用户确认。 |
| 验证结果 | 单元测试 **57 passed**（`examples/unit_tests/pytest_phase_d.txt`）。真实场景：T03 completed（注入失败后改 backup）；T04 completed（premium=12 超限后改 basic=10）；T05 incomplete/infeasible（gap.budget_gap=3，未保存）。证据目录见各 `examples/T0x_*/`，meta 均标记 `formal_acceptance=true`、`llm_mode=real`。 |
| 未解决问题 | 续跑与 T06/T07/T08 在阶段 E。T05 的 `reason` 字段为模型长文本（含 infeasible），缺口以代码计算的 `gap` 为准。T04 保存结果因指纹与探索性运行相同而 `duplicate=true`，费用仍为 10≤预算。 |

### 2026-10-29 阶段 E：T06 幂等 / T07 续跑 / T08 上限

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 核对 T04 duplicate 文件一致性（未改原 Trace）；为 T05 增加全局最低成本证明（`global_min_cost` + `compute_gap` 的 `globally_infeasible_by_budget`）。实现 `prepare_resume` / CLI `--resume`、续跑摘要与 Trace `session` 字段。真实运行 T06（两次同输入）、T07（save 注入失败后续跑）、T08（max_steps=2）。新增 `tests/test_resume.py` 与说明文件 `T04.../idempotency_note.json`、`T05.../feasibility_note.json`。 |
| 人工贡献 | 用户验收阶段 D 后确认进入阶段 E，并规定 T06–T08 与续跑验收标准。代码与真实运行由 Cursor 执行；用户是否另行审阅，待用户确认。 |
| 验证结果 | 单元测试 **59 passed**（`examples/unit_tests/pytest_phase_e.txt`）。T06：run1 新建方案，run2 `duplicate=true` 同 plan_id，文件数 +1。T07：session1 incomplete（save 注入失败×3），session2 completed；search/script/estimate 真实执行次数保持 1；失败历史保留。T08：`incomplete/max_steps_reached`，未保存。 |
| 未解决问题 | 阶段 F 文档与阶段 G 提交。T07 续跑时 s4 已达单步尝试上限，模型新建 s5 完成保存（属合理恢复，已如实记录）。 |

## 关键问题

| 编号 | 现象 | AI 提出的处理 | 实际修复 | 验证 |
| --- | --- | --- | --- | --- |
| 1 | `AGENTS.md` 第 12 节仍写「正式题目尚未录入」，第 13 节已写「已选择第 2 题」，两节矛盾。 | 本阶段不改这两节，避免把未确认的历史改写为既成事实。 | 未修复 | 通过阅读 `AGENTS.md` 确认矛盾仍在 |
| 2 | 项目目录没有独立 Git 仓库，且没有任何提交。考试要求提交 GitHub URL 和最终 Commit SHA。 | 待用户确认是否在项目目录单独初始化仓库。本阶段不执行 `git init`。 | 未修复 | `git rev-parse --show-toplevel` 返回 `D:/`；`git log` 显示当前分支没有提交 |
| 3 | 第 2 题要求的 Agent、四个工具、T01–T08 测试和运行证据都还未实现。 | 不在本文件中把这些写成已完成。 | 未开始 | 目录中无 `src/`、`tests/`、`examples/` |
| 1（阶段 A 更新） | 同第 1 项。 | 用户已确认选题后，把第 12 节改为「选题状态：已确定第 2 题」。 | 已修复 | 阅读修改后的 `AGENTS.md` 第 12 节 |
| 2（阶段 A 更新） | 同第 2 项。 | 用户同意后，在项目目录执行 `git init -b main`。 | 部分修复：已初始化，尚无提交和 SHA | `git rev-parse --show-toplevel` 返回 `D:/xiaoying-agent-exam` |
| 4 | Windows 下 CLI 输出经管道或重定向后中文乱码（help 与 JSON 都受影响）。根因：Python 在非控制台输出时使用系统代码页 GBK（`sys.stdout.encoding=gbk`），而接收端按 UTF-8 解码。 | 在 `cli.main()` 开头把 stdout、stderr 设为 UTF-8；保存证据时改用字节重定向，避免 PowerShell 5 的 `Tee-Object` 写出 UTF-16 文件。 | 已修复 | 重跑 CLI，中文显示正常；`pytest_phase_a.txt` 已用 UTF-8 重新生成 |
| 5 | 阶段 B 首轮测试中 `test_different_plan_content_saves_again` 失败：重规划时删掉了已成功的 s2/s3/s4，触发 `PROTECT_SUCCEEDED`。 | 这是硬约束正确拦截。修正测试：重规划必须保留全部已成功步骤，再追加替代路径。另补充「超预算后保留成功步骤、替代失败保存」用例。 | 已修复 | 全量 pytest 50 passed，见 `examples/unit_tests/pytest_phase_b.txt` |
| 6 | 成功步骤复用未比对业务参数：换 source/limit/format 仍可能复用旧产物。 | 增加 `business_args_for_reuse` 与 `ARGS_MISMATCH_ON_SUCCEEDED`；参数变化时拒绝并要求新建 step_id。 | 已修复 | `test_succeeded_step_rejects_different_args` 等，阶段 C 全量 54 passed |
| 7 | 重规划后若误用旧 `estimate_id` 保存新脚本。 | `save_plan` 校验 script_id 与 format；回归测试覆盖。 | 已确认并加固 | `test_estimate_must_match_current_script_after_replan` |
| 8 | `compute_gap` 只取最近一次估算，可能忽略更接近可行的观察；临时失败与不可行语义需钉死。 | 改为综合全部估算；存在可行估算则无 gap；prompt 区分 retryable 与 CONSTRAINT_VIOLATION；新增阶段 D 回归测试。 | 已修复 | `test_phase_d_consistency.py`；T05 真实 gap.budget_gap=3 |
| 9 | T05 仅凭已观察估算宣称不可行，缺少费用表全局证明。 | 增加 `global_min_cost` 穷举；gap 标记 `globally_infeasible_by_budget`；补充 `feasibility_note.json`（不改原 Trace）。 | 已加固 | 全局最低成本 8 > 预算 5 |
| 10 | `--resume` 未实现。 | 实现 `prepare_resume`、续跑摘要、CLI 接入；真实 T07 验证。 | 已修复 | `examples/T07_resume/` |
| 11 | 续跑时新建 s5 可能反复绕过单步重试上限。 | 增加跨会话 `MAX_CUMULATIVE_STEPS`（默认 36）；达上限拒绝续跑/停止循环。 | 已修复 | `tests/test_resume.py::test_cumulative_steps_block_infinite_resume_new_steps` |

## 明确尚未开始（首次写入时的快照，勿当作当前状态）

以下事项截至本文件**首次写入**时均未发生。其后阶段 A–E 已实际完成实现与测试；阶段 F 完成文档与复现。当前状态见上文总览与各阶段日志，勿把本快照误读为项目仍未开始。

- 内容任务规划 Agent 的架构设计与代码实现
- 素材检索、脚本生成、成本估算、方案保存四个工具
- T01–T08 及考试要求的三组基础场景测试
- 任何运行命令、Trace 或「测试通过」结论
- 除阶段 1 所述文档编辑以外的人工代码修改

### 2026-10-29 阶段 F：文档、验收矩阵与全新环境复现

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 检查 T07 新建步骤绕过风险：增加 `MAX_CUMULATIVE_STEPS` 与续跑拒绝逻辑及回归测试。确认 T05 `global_min_cost` 覆盖费用表与 schema 全部 format。撰写 `README.md`、`docs/01-05`、`docs/acceptance-matrix.md`。在独立目录执行全新 venv 安装、pytest 与 mock CLI。 |
| 人工贡献 | 用户验收阶段 E 后确认进入阶段 F，并规定文档与复现要求。代码/文档由 Cursor 编写；用户是否独立审阅全文，待用户确认。 |
| 验证结果 | 原仓库与独立复现目录（路径已脱敏）：`pytest` **61 passed**。复现目录无 `.env`/原 `runs`；缺 budget 返回 `missing_constraints`；mock CLI 可跑。证据：`examples/unit_tests/pytest_phase_f.txt`、`repro_fresh_env.md`。复现中发现并修复：约束校验须优先于 LLM 配置检查。 |
| 未解决问题 | 阶段 G 首次正式 commit / GitHub URL 仍待用户确认后执行。 |

### 2026-10-29 阶段 G（准备）：独立审查 ZIP、安全扫描、终测（未 push）

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 脱敏文档与历史 pytest 中的本机绝对路径；安全扫描交付树；代码自检 11 项；重新运行全量 pytest 并保存 `pytest_phase_g_final.txt`；在项目目录外生成审查 ZIP（排除 `.env`/`.venv`/`runs`/`saved_plans`）。未执行 git commit / push。 |
| 人工贡献 | 用户确认阶段 F 有条件通过，要求准备独立审查材料且暂不 GitHub 推送。 |
| 验证结果 | `pytest -q`：**61 passed**（`examples/unit_tests/pytest_phase_g_final.txt`）。ZIP：`D:\xiaoying-agent-exam-independent-review.zip`。`.env` 被 gitignore。 |
| 未解决问题 | 正式 commit/push 待独立审查与用户最终确认。建议提交时排除 `.cursor/plans/`。 |

### 2026-10-29 独立审查修复轮（最小范围，未 commit / push）

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | 按独立终审问题做最小修复：（1）`executor` 拒绝 `STEP_SUPERSEDED` 再执行，防止改回 succeeded；（2）`tools._validate_args` 严格校验 + `TOOL_EXCEPTION`/`EXECUTOR_EXCEPTION` 兜底；（3）`compute_fingerprint` 纳入规范化 `outline`，仍排除 script/estimate/run id；（4）默认 `CompletePathMockLLM` 走通 search→generate→estimate→save→finish，明确 `llm_mode=mock`；（5）落盘 `examples/T02_missing_constraints/` 并更新 `docs/03-evaluation.md`、`acceptance-matrix.md`、README；（6）确认交付 `scripts/probe_tool_calling.py`、`scripts/archive_run.py`。新增回归：`test_superseded_guard.py`、`test_tool_arg_validation.py` 及 store/mock 用例。 |
| 人工贡献 | 用户提供独立审查缺陷清单并要求最小修复、禁止 commit/push、完成后暂停待确认。本轮代码与证据由 Cursor 执行；用户是否另行人工复跑，待用户确认。 |
| 验证结果 | 全量 `pytest -q`：**74 passed**（`examples/unit_tests/pytest_independent_review_fix.txt`）。Mock CLI 完整路径 `status=completed`、`llm_mode=mock`（`examples/unit_tests/mock_complete_path_report.json`）。T02：缺 budget/deadline 退出码 2、`llm_calls=0`。历史 `examples/T01`/`T03`–`T08` Trace **未改写**。敏感信息：`.env` 仍忽略；扫描未见新的真实 Key 写入仓库文件。 |
| 未解决问题 | 正式 commit/push 仍待用户最终确认。指纹算法变更后，与审查前旧 `saved_plans/index.json` 混用可能无法命中旧指纹（同进程新 store 内复用已测通）。本轮未要求、也未追加新的真实模型场景 Trace（修复点均由确定性测试覆盖）。 |

问题对照（本轮）：

| # | 审查发现 | 处理 | 状态 | 证据 |
| --- | --- | --- | --- | --- |
| 12 | superseded 步骤仍可执行并改回成功 | `STEP_SUPERSEDED` 守卫拒绝，不写成功 attempt | 已修复 | `tests/test_superseded_guard.py` |
| 13 | `material_ids` 含 dict 导致 TypeError 崩溃 | 参数校验 + 异常兜底 | 已修复 | `tests/test_tool_arg_validation.py` |
| 14 | 指纹不含 outline，不同脚本可同指纹 | 规范化 outline 纳入指纹；随机 id 仍排除 | 已修复 | `tests/test_store_idempotency.py` |
| 15 | 默认 Mock 半途 incomplete | `CompletePathMockLLM` 完整成功路径 | 已修复 | `test_complete_path_mock_finishes_successfully`；mock CLI |
| 16 | 缺 T02 落盘证据 | 新增 `examples/T02_missing_constraints/` | 已修复 | 该目录 + 文档矩阵 |

### 2026-10-29 最终提交前检查与 GitHub 交付

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | Cursor 执行：全量 pytest；真实 DeepSeek 重跑 T04 并归档至 `examples/T04_budget_overrun_post_fix/`（不覆盖历史 T04）；核对非法参数结构化错误与指纹 outline 语义；更新 `docs/03-evaluation.md`（区分历史/修复后证据）、`acceptance-matrix.md`、本文件；敏感信息与交付清单检查；创建最终 commit 并推送 GitHub（按用户授权）。 |
| 人工贡献 | 用户确认独立审查修复报告，原则上同意进入最终 GitHub 提交流程；要求不得替其在招聘考试网站点击提交。本轮仍无核实到用户亲自粘贴/手写业务代码；关键决策与审查确认归用户。用户是否在本地再次独立复跑命令，待用户自行补充第 5 节。 |
| 验证结果 | `pytest -q`：**74 passed**（`examples/unit_tests/pytest_final_pre_commit.txt`）。T04 修复后复跑：`status=completed`，premium=12→basic=10，`llm_mode=real`（`examples/T04_budget_overrun_post_fix/`）。结构化错误与指纹手工核对通过。历史 Trace 未改写。 |
| 未解决问题 | 考试官网最终提交须由用户本人完成。若仓库为私有，须自行添加评审账号可读权限。 |

### 2026-10-29 集中优化（P0 逻辑 + CLI 展示，未 commit）

| 字段 | 内容 |
| --- | --- |
| AI 辅助内容 | Cursor：修复 save 依赖产物血缘与 finish 计划一致性；实现默认中文报告 / `--output json` / `--verbose`；UTF-16→UTF-8 证据规范化；更新文档；全量回归与真实 T01/T04 复跑归档（不覆盖历史）。 |
| ChatGPT | 提出本轮审查建议（save 依赖一致性、finish 状态一致性、CLI 可读性等），由用户整理后交 Cursor 实施。 |
| 人工贡献 | 用户下达集中优化任务、确认约 4 小时用时口径、要求不自动 commit/push、完成后暂停验收。代码实现仍由 Cursor 完成。 |
| 验证结果 | 全量 pytest **84 passed**（`examples/unit_tests/pytest_post_opt.txt`）。Mock 中文报告 / JSON+verbose 样例已落盘。真实 T01：`examples/T01_normal_post_opt/` completed、费用 8（模型选 graphic，与历史 T01 的 10 不同属非确定性）。真实 T04：`examples/T04_budget_overrun_post_opt/` completed，估算路径 premium=12→basic=10。历史 T01–T08 Trace 未覆盖。未 commit/push。 |
| 未解决问题 | 正式二次 push 待用户验收后确认。 |
