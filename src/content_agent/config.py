"""从环境变量读取配置。不在代码中写死任何密钥。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BUSINESS_TOOLS = ("search_materials", "generate_script", "estimate_cost", "save_plan")

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    repo_data = _REPO_ROOT / "data"
    return repo_data if repo_data.is_dir() else Path.cwd() / "data"


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值：{raw!r}") from exc
    if value <= 0:
        raise ValueError(f"环境变量 {name} 必须大于 0，当前值：{value}")
    return value


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_thinking: str
    max_steps: int
    max_attempts_per_step: int
    max_cumulative_steps: int
    data_dir: Path
    runs_dir: Path
    plans_dir: Path

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)


def load_settings() -> Settings:
    load_dotenv()
    thinking = os.getenv("LLM_THINKING", "disabled").strip().lower() or "disabled"
    if thinking not in {"disabled", "enabled"}:
        raise ValueError("环境变量 LLM_THINKING 只能是 disabled 或 enabled")
    return Settings(
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip() or "https://api.deepseek.com",
        llm_model=os.getenv("LLM_MODEL", "").strip() or "deepseek-flash",
        llm_thinking=thinking,
        max_steps=_int_env("MAX_STEPS", 12),
        max_attempts_per_step=_int_env("MAX_ATTEMPTS_PER_STEP", 3),
        # 跨续跑会话的全局决策步上限，防止反复新建步骤绕过单步重试上限
        max_cumulative_steps=_int_env("MAX_CUMULATIVE_STEPS", 36),
        data_dir=Path(os.getenv("CONTENT_AGENT_DATA_DIR") or _default_data_dir()),
        runs_dir=Path(os.getenv("CONTENT_AGENT_RUNS_DIR") or "runs"),
        plans_dir=Path(os.getenv("CONTENT_AGENT_PLANS_DIR") or "saved_plans"),
    )
