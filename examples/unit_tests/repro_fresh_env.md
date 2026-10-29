# 全新环境复现记录（阶段 F）

日期：2026-10-29

## 做法

1. 复制项目到独立目录（本机临时复现目录，路径已脱敏，不写入公开交付）
2. **排除**：`.venv`、`runs/`、`saved_plans/`、`.env`、`.git`、缓存  
3. 在新目录：`python -m venv .venv` → `pip install -r requirements.txt`  
4. **未复制密钥**；`llm_configured=False`

## 结果

| 检查项 | 结果 |
| --- | --- |
| 包安装 | 成功，`content-agent` 可用 |
| 数据路径 | `...\xiaoying-agent-exam-repro-f\data` 存在 |
| 不依赖原 runs/saved_plans | 安装前不存在；mock 运行才新建 runs |
| `pytest -q` | **61 passed** |
| 缺 budget（无 Key） | `missing_constraints`，退出码 2（修复校验顺序后） |
| `--llm mock` | 可运行；`llm_mode=mock`（非决策证据） |
| 真实 LLM | 需本地自备 `.env`，复现目录未放置密钥 |

## 复现中发现并已修复

无 `.env` 时，原先先检查 LLM 配置，导致缺预算被误报为「未配置密钥」。已改为：**先校验约束，再检查 LLM 配置**。原仓库与复现目录均已验证 pytest 61 passed。

