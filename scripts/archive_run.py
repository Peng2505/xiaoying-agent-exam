"""把一次 runs/<run_id> 产物归档到 examples/<scenario>/。不改写 Trace。"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from content_agent.config import load_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    run_dir = root / "runs" / args.run_id
    out = root / "examples" / args.scenario
    out.mkdir(parents=True, exist_ok=True)

    for name in ("report.json", "trace.jsonl", "state.json"):
        src = run_dir / name
        if src.is_file():
            shutil.copy2(src, out / name)

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    settings = load_settings()
    meta = {
        "scenario": args.scenario,
        "formal_acceptance": bool(args.formal),
        "llm_mode": report.get("llm_mode") or "real",
        "model": report.get("model") or settings.llm_model,
        "base_url_host": urlparse(settings.llm_base_url).netloc,
        "thinking": settings.llm_thinking,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": args.command,
        "run_id": args.run_id,
        "note": args.note,
        "status": report.get("status"),
        "reason": report.get("reason"),
        "total_cost": report.get("total_cost"),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    saved = report.get("saved_plan")
    if saved and saved.get("path"):
        plan_path = Path(saved["path"])
        if not plan_path.is_file():
            plan_path = root / saved["path"]
        if plan_path.is_file():
            shutil.copy2(plan_path, out / "saved_plan.json")

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
