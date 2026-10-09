"""命令行工具：生成每日投资日报。

用法（在项目根目录 D:\\StockPilot 下）：
    python -m backend.cli daily            # 仅打印到控制台
    python -m backend.cli daily --save     # 额外保存 HTML/Markdown 到 data/
可放入 Windows 任务计划程序 / cron 实现每日自动生成。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.config import DATA_DIR  # noqa: E402
from backend.report import build_daily_report  # noqa: E402


def cmd_daily(save: bool = False):
    rep = build_daily_report()
    print(f"📋 日报生成于 {rep['generated_at']}，覆盖 {rep['count']} 个自选标的\n")
    for it in rep["items"]:
        if it.get("error"):
            print(f"  ⚠️ {it['name']}（{it['code']}）：{it['error']}")
            continue
        c = it.get("change_pct") or 0
        print(f"  {it['name']}（{it['code']}） {('+' if c > 0 else '')}{c}%  →  {it['consensus']}")
    if rep["risks"]:
        print("\n⚠️ 风险提醒：")
        for r in rep["risks"]:
            for w in r["warnings"]:
                print(f"  [{r['name']}] {w}")
    else:
        print("\n✅ 暂无追高/重大风险提醒")
    if save:
        from datetime import datetime as _dt
        d = _dt.now().strftime("%Y%m%d")
        html_path = os.path.join(DATA_DIR, f"daily_report_{d}.html")
        md_path = os.path.join(DATA_DIR, f"daily_report_{d}.md")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(rep["html"])
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(rep["markdown"])
        print(f"\n💾 已保存：\n  {html_path}\n  {md_path}")


if __name__ == "__main__":
    cmd_daily(save="--save" in sys.argv)
