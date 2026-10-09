"""
自动日报：汇总大盘 + 自选，逐标的给出多角色(AI)简版结论 + 风险清单 + 共识，
输出结构化数据 + HTML（可独立打开/下载）+ Markdown（可复制）。
"""
from datetime import datetime

from backend.data import market
from backend.indicators import mytt
from backend.ai import analyst
from backend.db import store


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _chg_color(v):
    if v is None:
        return "#6b7280"
    return "#e5372a" if v > 0 else ("#10a674" if v < 0 else "#6b7280")


def _stance_color(s):
    return {"偏多": "#e5372a", "偏空": "#10a674"}.get(s, "#6b7280")


def _role_short(card):
    r = card.get("role", {})
    return {"emoji": r.get("emoji", ""), "name": r.get("name", ""),
            "stance": card.get("stance", "中性"), "conclusion": card.get("conclusion", "")}


def build_daily_report():
    now = datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    idx = market.get_index_overview()
    watches = store.list_watch()
    items, risks = [], []
    for w in watches:
        code = w["code"]
        name = w.get("name") or code
        atype = w["type"]
        grp = w.get("grp", "默认")
        try:
            q = market.get_quote(code, atype)
            if q.get("error"):
                items.append({"code": code, "name": name, "type": atype, "group": grp,
                              "error": q["error"]})
                continue
            kl = market.get_kline(code, atype, limit=60)
            rows = kl.get("rows", [])
            ind = mytt.compute_all(rows) if len(rows) >= 20 else {"latest": {}, "signals": []}
            news = market.get_news(code) if atype != "fund" else []
            multi = analyst.analyze_multi(q, ind, news)
        except Exception as e:  # noqa
            items.append({"code": code, "name": name, "type": atype, "group": grp, "error": str(e)})
            continue

        disc = []
        for c in multi.get("cards", []):
            disc.extend(c.get("discipline", []) or [])
        disc = list(dict.fromkeys(disc))
        if disc:
            risks.append({"code": code, "name": name, "type": atype, "warnings": disc})

        items.append({
            "code": code, "name": name, "type": atype, "group": grp,
            "price": q.get("price"), "change_pct": q.get("change_pct"),
            "consensus": multi.get("consensus"),
            "bull": multi.get("bull"), "bear": multi.get("bear"),
            "roles": [_role_short(c) for c in multi.get("cards", [])],
            "first_warning": (disc[0] if disc else None),
        })

    html = _render_html(generated_at, idx, items, risks)
    markdown = _render_md(generated_at, idx, items, risks)
    return {"generated_at": generated_at, "index": idx, "items": items,
            "risks": risks, "html": html, "markdown": markdown, "count": len(items)}


# ---------------------------------------------------------------- 渲染
_CSS = """
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #1f2937; margin: 0; padding: 28px; }
.wrap { max-width: 960px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0 0 4px; }
.meta { color: #6b7280; font-size: 13px; margin-bottom: 18px; }
h2 { font-size: 17px; margin: 26px 0 12px; border-left: 4px solid #2563eb; padding-left: 10px; }
.idxrow { display: flex; gap: 12px; flex-wrap: wrap; }
.idx { background: #fff; border: 1px solid #e3e8ef; border-radius: 12px; padding: 12px 18px; min-width: 150px; }
.idx .n { font-size: 12px; color: #6b7280; }
.idx .p { font-size: 20px; font-weight: 700; margin-top: 3px; }
.card { background: #fff; border: 1px solid #e3e8ef; border-radius: 14px; padding: 16px; margin-bottom: 12px; }
.chead { display: flex; align-items: baseline; gap: 12px; }
.chead .nm { font-size: 18px; font-weight: 700; }
.chead .code { color: #6b7280; font-size: 12px; }
.chead .px { font-size: 20px; font-weight: 700; margin-left: auto; }
.consensus { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 6px; background: #eef2f7; color: #374151; margin: 6px 0 10px; }
.roles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.role { border: 1px solid #e3e8ef; border-radius: 10px; padding: 10px; }
.role .rn { font-weight: 600; font-size: 13px; }
.role .rc { font-size: 12px; color: #374151; margin-top: 3px; }
.badge { font-size: 11px; padding: 1px 7px; border-radius: 5px; margin-left: 6px; }
.warn { background: #fff4f2; border: 1px solid #ffd9d2; color: #e5372a; padding: 10px 12px; border-radius: 9px; margin: 6px 0; font-size: 13px; }
.warns { background: #fff4f2; border: 1px solid #ffd9d2; border-radius: 12px; padding: 14px 18px; }
.warns li { margin: 6px 0; color: #374151; font-size: 13px; }
.err { color: #b45309; font-size: 13px; }
.footer { color: #9ca3af; font-size: 12px; margin-top: 30px; text-align: center; }
"""


def _render_html(generated_at, idx, items, risks):
    parts = [f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
             f'<title>StockPilot 每日投资日报 {generated_at[:10]}</title><style>{_CSS}</style></head><body><div class="wrap">'
             f'<h1>📈 StockPilot 每日投资日报</h1>'
             f'<div class="meta">生成时间：{_esc(generated_at)}　·　覆盖 {len(items)} 个自选标的　·　数据仅供参考，不构成投资建议</div>']

    parts.append('<h2>大盘概览</h2><div class="idxrow">')
    for i in idx:
        parts.append(f'<div class="idx"><div class="n">{_esc(i["name"])}</div>'
                     f'<div class="p" style="color:{_chg_color(i.get("change_pct"))}">{_esc(i.get("price"))}</div>'
                     f'<div style="color:{_chg_color(i.get("change_pct"))}">'
                     f'{(i.get("change_pct") or 0) > 0 and "+" or ""}{_esc(i.get("change_pct"))}%</div></div>')
    parts.append('</div>')

    parts.append(f'<h2>自选快照（{len(items)}）</h2>')
    for it in items:
        if it.get("error"):
            parts.append(f'<div class="card"><div class="chead"><span class="nm">{_esc(it["name"])}</span>'
                         f'<span class="code">{_esc(it["code"])}</span></div>'
                         f'<div class="err">数据获取失败：{_esc(it["error"])}</div></div>')
            continue
        c = it.get("change_pct")
        parts.append('<div class="card">')
        parts.append(f'<div class="chead"><span class="nm">{_esc(it["name"])}</span>'
                     f'<span class="code">{_esc(it["code"])}</span>'
                     f'<span class="px" style="color:{_chg_color(c)}">'
                     f'{(c or 0) > 0 and "+" or ""}{_esc(c)}%</span></div>')
        parts.append(f'<div class="consensus">共识：{_esc(it.get("consensus"))}'
                     f'　🟢多 {it.get("bull", 0)} / 🔴空 {it.get("bear", 0)}</div>')
        parts.append('<div class="roles">')
        for r in it.get("roles", []):
            parts.append(f'<div class="role"><span class="rn">{r["emoji"]} {_esc(r["name"])}'
                         f'<span class="badge" style="background:{_stance_color(r["stance"])}22;color:{_stance_color(r["stance"])}">'
                         f'{_esc(r["stance"])}</span></span>'
                         f'<div class="rc">{_esc(r["conclusion"])}</div></div>')
        parts.append('</div>')
        if it.get("first_warning"):
            parts.append(f'<div class="warn">⛔ {_esc(it["first_warning"])}</div>')
        parts.append('</div>')

    parts.append('<h2>⚠️ 风险与纪律提醒</h2>')
    if risks:
        parts.append('<ul class="warns">')
        for r in risks:
            for w in r["warnings"]:
                parts.append(f'<li><b>{_esc(r["name"])}</b>（{_esc(r["code"])}）：{_esc(w)}</li>')
        parts.append('</ul>')
    else:
        parts.append('<div class="card">暂无追高/重大风险提醒 ✅</div>')

    parts.append('<div class="footer">StockPilot · 个人 AI 投资助手　|　所有 AI 建议仅供参考，投资有风险，决策需谨慎。</div>')
    parts.append('</div></body></html>')
    return "".join(parts)


def _render_md(generated_at, idx, items, risks):
    L = [f"# 📈 StockPilot 每日投资日报", f"生成时间：{generated_at}　覆盖 {len(items)} 个自选标的", ""]
    L.append("## 大盘概览")
    for i in idx:
        L.append(f"- {i['name']}：{i.get('price')}（{(i.get('change_pct') or 0)>0 and '+' or ''}{i.get('change_pct')}%）")
    L.append("")
    L.append(f"## 自选快照（{len(items)}）")
    for it in items:
        if it.get("error"):
            L.append(f"### {it['name']}（{it['code']}）\n- 数据获取失败：{it['error']}")
            continue
        c = it.get("change_pct")
        L.append(f"### {it['name']}（{it['code']}）　{c}%")
        L.append(f"- 共识：{it.get('consensus')}（多 {it.get('bull')} / 空 {it.get('bear')}）")
        for r in it.get("roles", []):
            L.append(f"  - {r['emoji']} {r['name']}（{r['stance']}）：{r['conclusion']}")
        if it.get("first_warning"):
            L.append(f"  - ⛔ {it['first_warning']}")
        L.append("")
    L.append("## ⚠️ 风险与纪律提醒")
    if risks:
        for r in risks:
            for w in r["warnings"]:
                L.append(f"- **{r['name']}**（{r['code']}）：{w}")
    else:
        L.append("- 暂无追高/重大风险提醒 ✅")
    L.append("")
    L.append("> 所有 AI 建议仅供参考，投资有风险，决策需谨慎。")
    return "\n".join(L)
