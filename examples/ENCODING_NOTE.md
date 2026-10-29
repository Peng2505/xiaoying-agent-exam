# examples 文本编码说明

2026-10-29 集中优化时，对下列因 Windows 重定向产生的 **UTF-16** 文件做了 **UTF-8 规范化**（内容语义不变，仅编码）：

- `T02_missing_constraints/missing_budget_output.json`
- `T02_missing_constraints/missing_deadline_output.json`
- `T04_budget_overrun_post_fix/console.txt`
- `unit_tests/mock_complete_path_report.json`
- `unit_tests/pytest_final_pre_commit.txt`
- `unit_tests/pytest_independent_review_fix.txt`
- `unit_tests/t04_post_fix_console.txt`

本地曾生成 `*.utf16bak` 备份（已被 `.gitignore` 排除）。转换后 JSON/JSONL 均可正常解析；未改写预算、状态、工具顺序或测试结论。
