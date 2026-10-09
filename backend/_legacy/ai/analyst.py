"""
AI 分析模块：多角色投资分析师。支持：
  - 单角色综合卡片（analyze，向后兼容旧接口/前端）
  - 多角色卡片（analyze_multi）：技术派 / 价值派 / 风控派 / 激进派
未配置 DeepSeek API Key 时自动降级为"纯规则分析"，按角色侧重给出不同结论。
"""
import json

from backend.config import CONFIG

# 多角色定义（顺序即前端展示顺序）
ROLES = [
    {"id": "tech", "name": "技术派", "emoji": "📊",
     "focus": "趋势 / 均线 / MACD / 量价",
     "hint": "重点关注技术面：均线排列、MACD 金叉死叉、RSI 超买超卖、量价配合。给出明确的趋势判断与买卖参考。"},
    {"id": "value", "name": "价值派", "emoji": "💡",
     "focus": "估值 / PE / PB / 安全边际",
     "hint": "重点关注估值：PE/PB 水平与历史分位、估值安全边际、与行业/大盘对比。判断当前价格是否便宜、有没有安全边际。"},
    {"id": "risk", "name": "风控派", "emoji": "🛡️",
     "focus": "止损 / 追高 / 仓位",
     "hint": "重点关注风险：追高纪律、止损位设置、最大回撤控制、仓位建议。宁可错过，不可做错。"},
    {"id": "momentum", "name": "激进派", "emoji": "🚀",
     "focus": "动量 / 突破 / 弹性",
     "hint": "重点关注动量与弹性：短期涨幅、突破形态、资金热度、上行空间。敢于在强趋势中持有、在突破时跟进。"},
]


def _discipline_check(quote, indicators):
    """投资纪律：追高判断（来自 config 参数）。"""
    disc = CONFIG.get("discipline", {})
    chase_limit = disc.get("chase_high_pct", 10)
    warnings = []
    latest = (indicators or {}).get("latest", {})
    recent5 = latest.get("recent5_pct")
    if recent5 is not None and recent5 > chase_limit:
        warnings.append(f"近5日涨幅 {recent5}% 已超 {chase_limit}%，⛔ 严禁追高")
    return warnings


def _stance_from_text(text):
    t = (text or "")
    if any(k in t for k in ("买入", "偏多", "关注", "持有", "低吸", "加仓", "参与")):
        return "偏多"
    if any(k in t for k in ("减仓", "偏空", "谨慎", "卖出", "回避", "离场", "严禁", "退场")):
        return "偏空"
    return "中性"


def _rule_based_card(quote, indicators, news, role=None):
    """无 AI 时按角色侧重的规则决策卡片。role=None 为综合视角。"""
    signals = (indicators or {}).get("signals", [])
    latest = (indicators or {}).get("latest", {})
    role_id = role["id"] if role else None

    # ---- 角色侧重计分 ----
    if role_id == "value":
        pe = quote.get("pe"); pb = quote.get("pb")
        reasons = []
        score = 0
        if pe is not None:
            if pe < 15:
                score += 1; reasons.append(f"PE={pe} 偏低，估值有安全边际")
            elif pe > 40:
                score -= 1; reasons.append(f"PE={pe} 偏高，注意估值泡沫")
            else:
                reasons.append(f"PE={pe} 中性")
        if pb is not None:
            if pb < 2:
                score += 0.5; reasons.append(f"PB={pb} 较低")
            elif pb > 8:
                score -= 0.5; reasons.append(f"PB={pb} 偏高")
        bull = 1 if score > 0 else (0 if score == 0 else -1)
        bear = -bull
        checklist = [{"item": r, "status": "✅" if score > 0 else ("❌" if score < 0 else "⚠️")}
                     for r in reasons] or [{"item": "无可用估值数据，退回技术面", "status": "⚠️"}]
        reasoning = "（价值派·规则）" + ("；".join(reasons) if reasons else "暂无估值数据，建议结合技术面。")

    elif role_id == "risk":
        warnings = _discipline_check(quote, indicators)
        chase = latest.get("recent5_pct") or 0
        bull = 0
        bear = 1 if (warnings or chase > 5) else 0
        checklist = [
            {"item": f"追高检查：近5日 {chase}%", "status": "❌" if chase > 5 else "✅"},
            {"item": f"止损纪律：按 config 止损 {CONFIG['discipline']['stop_loss_pct']}%", "status": "⚠️"},
        ]
        reasoning = "（风控派·规则）" + ("；".join(warnings) if warnings else "未见明显追高，但须严守止损位与仓位上限。")

    elif role_id == "momentum":
        recent5 = latest.get("recent5_pct") or 0
        rsi = latest.get("RSI14") or 50
        bull = 1 if (recent5 > 0 and rsi > 50) else (0 if recent5 >= 0 else -1)
        bear = -bull
        checklist = [
            {"item": f"短期动量：近5日 {recent5}%", "status": "✅" if recent5 > 0 else "❌"},
            {"item": f"RSI14={rsi}", "status": "✅" if rsi > 50 else "⚠️"},
        ]
        reasoning = f"（激进派·规则）近期动能 {'向上' if recent5 > 0 else '偏弱'}，RSI={rsi}，{'可顺势参与' if recent5 > 0 and rsi > 50 else '暂观望'}。"

    else:  # tech / 综合
        bull = sum(1 for s in signals if s[2] == "偏多")
        bear = sum(1 for s in signals if s[2] == "偏空")
        checklist = [{"item": f"{s[0]}：{s[1]}",
                      "status": "✅" if s[2] == "偏多" else ("❌" if s[2] == "偏空" else "⚠️")}
                     for s in signals] or [{"item": "数据不足，无法判断", "status": "⚠️"}]
        reasoning = "（技术派·规则）综合均线/MACD/RSI/KDJ 信号。"

    # ---- 结论与倾向 ----
    if role_id == "risk":
        if _discipline_check(quote, indicators):
            conclusion, confidence, stance = "偏空，严禁追高", "高", "偏空"
        else:
            stance = "偏空" if bear > bull else ("偏多" if bull > bear else "中性")
            conclusion = "中性偏谨慎，控仓观望" if stance == "偏空" else "可小仓参与，严守止损"
            confidence = "中"
    else:
        if bull > bear:
            stance = "偏多"
            conclusion = "偏多，可关注" if role_id != "momentum" else "动能向上，顺势参与"
            confidence = "中"
        elif bear > bull:
            stance = "偏空"
            conclusion = "偏空，谨慎" if role_id != "momentum" else "动能走弱，注意退场"
            confidence = "中"
        else:
            stance = "中性"
            conclusion = "方向不明，观望"
            confidence = "低"

    price = latest.get("price") or quote.get("price")
    stop = round(price * (1 - CONFIG["discipline"]["stop_loss_pct"] / 100), 2) if price else None
    return {
        "engine": "rule",
        "conclusion": conclusion,
        "confidence": confidence,
        "stance": stance,
        "key_levels": {"buy_ref": price, "stop_loss": stop, "target": None},
        "checklist": checklist,
        "discipline": _discipline_check(quote, indicators),
        "reasoning": reasoning + ("" if role else "（未配置 DeepSeek API Key，当前为规则引擎结论。填入 key 后可获得 AI 深度分析。）"),
    }


def _build_prompt(quote, indicators, news, role=None):
    latest = (indicators or {}).get("latest", {})
    signals = (indicators or {}).get("signals", [])
    news_titles = [n.get("title", "") for n in (news or [])][:6]
    asset_type = quote.get("type", "stock")
    type_cn = {"stock": "A股股票", "etf": "ETF基金", "fund": "场外基金"}.get(asset_type, "标的")
    role_part = ""
    if role:
        role_part = (f"\n你当前的分析师角色是【{role['name']}】（{role['focus']}）。{role['hint']}\n"
                     "请站在该角色视角给出结论，与其他角色形成互补。")
    return f"""你是一位严谨的中国市场投资分析师{('，当前扮演' + role['name'] + '角色') if role else ''}。请基于以下数据，对该{type_cn}给出结构化的投资决策建议。
{role_part}
【标的】{quote.get('name')}（{quote.get('code')}）
【最新价/净值】{quote.get('price')}　涨跌幅 {quote.get('change_pct')}%
【技术指标】{json.dumps(latest, ensure_ascii=False)}
【技术信号】{json.dumps([{'类型': s[0], '解读': s[1], '倾向': s[2]} for s in signals], ensure_ascii=False)}
【近期新闻标题】{json.dumps(news_titles, ensure_ascii=False)}

请严格按以下 JSON 格式输出（不要有多余文字）：
{{
  "conclusion": "一句话核心结论，含 买入/持有/减仓 倾向",
  "confidence": "高/中/低",
  "stance": "偏多/偏空/中性",
  "key_levels": {{"buy_ref": 买入参考价数字或null, "stop_loss": 止损价数字或null, "target": 目标价数字或null}},
  "checklist": [{{"item": "检查项描述", "status": "✅或⚠️或❌"}}],
  "reasoning": "150字以内的分析逻辑，说明你的角色视角下的综合判断"
}}

投资纪律要求：短期涨幅过大时务必提示追高风险；结论必须客观，不得承诺收益。"""


def _analyze_one(quote, indicators, news, role=None):
    """单角色分析主入口：优先 AI（带角色），失败降级规则。"""
    ai_cfg = CONFIG.get("ai", {})
    api_key = (ai_cfg.get("api_key") or "").strip()
    if not ai_cfg.get("enabled", True) or not api_key:
        return _rule_based_card(quote, indicators, news, role)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=ai_cfg.get("base_url"))
        prompt = _build_prompt(quote, indicators, news, role)
        resp = client.chat.completions.create(
            model=ai_cfg.get("model", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        card = json.loads(content)
        card["engine"] = "deepseek"
        card["discipline"] = _discipline_check(quote, indicators)
        card.setdefault("stance", _stance_from_text(card.get("conclusion", "")))
        return card
    except Exception as e:  # noqa
        fallback = _rule_based_card(quote, indicators, news, role)
        fallback["reasoning"] += f"\n（AI 调用失败，已降级为规则引擎：{e}）"
        return fallback


def analyze(quote, indicators, news):
    """单角色综合卡片（向后兼容 /api/analyze）。"""
    return _analyze_one(quote, indicators, news, role=None)


def analyze_multi(quote, indicators, news):
    """多角色卡片：4 角色并行调用，返回各角色卡片 + 共识汇总。
    用线程池并行，把"串行等 4 次 LLM"缩短到最慢那一次（约 1/4 耗时）。"""
    from concurrent.futures import ThreadPoolExecutor

    def _run(role):
        c = _analyze_one(quote, indicators, news, role=role)
        c["role"] = {"id": role["id"], "name": role["name"],
                     "emoji": role["emoji"], "focus": role["focus"]}
        if "stance" not in c:
            c["stance"] = _stance_from_text(c.get("conclusion", ""))
        return c

    with ThreadPoolExecutor(max_workers=4) as ex:
        cards = list(ex.map(_run, ROLES))
    bull = sum(1 for c in cards if c["stance"] == "偏多")
    bear = sum(1 for c in cards if c["stance"] == "偏空")
    if bull > bear:
        consensus = "整体偏多，多数角色看好"
    elif bear > bull:
        consensus = "整体偏空，多数角色谨慎"
    else:
        consensus = "多空分歧，建议观望"
    return {"cards": cards, "consensus": consensus,
            "bull": bull, "bear": bear, "neutral": len(cards) - bull - bear}
