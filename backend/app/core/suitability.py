"""Investor suitability management — risk profiling and product matching.

Implements the standard Chinese securities suitability framework:
- Investor risk levels: C1-C5 (conservative to aggressive)
- Product risk grades: R1-R5 (low to high)
- Matching rule: Investor Cn can invest in products with grade <= Rn
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from backend.app.core.logging import get_logger

logger = get_logger("suitability")


# ---- Risk levels ----

RISK_LEVELS = {
    "C1": {"name": "保守型", "desc": "风险承受能力极低，适合保本型产品", "max_product": "R1"},
    "C2": {"name": "稳健型", "desc": "风险承受能力较低，适合低风险产品", "max_product": "R2"},
    "C3": {"name": "平衡型", "desc": "中等风险承受能力，适合混合型产品", "max_product": "R3"},
    "C4": {"name": "进取型", "desc": "较高风险承受能力，适合股票型产品", "max_product": "R4"},
    "C5": {"name": "激进型", "desc": "高风险承受能力，适合所有产品", "max_product": "R5"},
}

PRODUCT_GRADES = {
    "R1": {"name": "低风险", "desc": "货币基金、国债逆回购等", "examples": ["货币基金", "国债逆回购"]},
    "R2": {"name": "中低风险", "desc": "债券基金、银行理财R2", "examples": ["债券基金", "银行理财"]},
    "R3": {"name": "中风险", "desc": "混合基金、指数基金", "examples": ["混合基金", "指数基金"]},
    "R4": {"name": "中高风险", "desc": "股票基金、个股", "examples": ["股票", "股票基金"]},
    "R5": {"name": "高风险", "desc": "期货、期权、杠杆产品", "examples": ["期货", "期权"]},
}


# ---- Questionnaire ----

QUESTIONNAIRE = [
    {
        "id": "age",
        "question": "您的年龄段是？",
        "options": [
            {"label": "18-30岁", "score": 4},
            {"label": "31-45岁", "score": 5},
            {"label": "46-60岁", "score": 3},
            {"label": "60岁以上", "score": 1},
        ],
    },
    {
        "id": "income",
        "question": "您的家庭年收入大约是？",
        "options": [
            {"label": "10万以下", "score": 1},
            {"label": "10-30万", "score": 2},
            {"label": "30-50万", "score": 3},
            {"label": "50-100万", "score": 4},
            {"label": "100万以上", "score": 5},
        ],
    },
    {
        "id": "assets",
        "question": "您的可投资资产（不含房产）大约是？",
        "options": [
            {"label": "10万以下", "score": 1},
            {"label": "10-50万", "score": 2},
            {"label": "50-200万", "score": 3},
            {"label": "200-500万", "score": 4},
            {"label": "500万以上", "score": 5},
        ],
    },
    {
        "id": "experience",
        "question": "您的投资经验年数？",
        "options": [
            {"label": "无经验", "score": 1},
            {"label": "1-3年", "score": 2},
            {"label": "3-5年", "score": 3},
            {"label": "5-10年", "score": 4},
            {"label": "10年以上", "score": 5},
        ],
    },
    {
        "id": "knowledge",
        "question": "您的金融知识水平？",
        "options": [
            {"label": "基本不了解", "score": 1},
            {"label": "了解一些", "score": 2},
            {"label": "比较了解", "score": 3},
            {"label": "非常熟悉", "score": 4},
            {"label": "专业人士", "score": 5},
        ],
    },
    {
        "id": "loss_tolerance",
        "question": "如果投资亏损20%，您会？",
        "options": [
            {"label": "立即全部卖出", "score": 1},
            {"label": "卖出大部分", "score": 2},
            {"label": "观望不动", "score": 3},
            {"label": "逢低加仓", "score": 4},
            {"label": "大幅加仓", "score": 5},
        ],
    },
    {
        "id": "horizon",
        "question": "您的投资期限预期？",
        "options": [
            {"label": "1年以内", "score": 1},
            {"label": "1-3年", "score": 2},
            {"label": "3-5年", "score": 3},
            {"label": "5-10年", "score": 4},
            {"label": "10年以上", "score": 5},
        ],
    },
    {
        "id": "ratio",
        "question": "股票类资产占您投资总额的比例？",
        "options": [
            {"label": "不投资股票", "score": 1},
            {"label": "10%以下", "score": 2},
            {"label": "10-30%", "score": 3},
            {"label": "30-60%", "score": 4},
            {"label": "60%以上", "score": 5},
        ],
    },
]


@dataclass
class SuitabilityProfile:
    """Investor suitability assessment result."""
    risk_level: str = "C2"       # C1-C5
    score: int = 0               # Total questionnaire score
    level_name: str = "稳健型"
    level_desc: str = ""
    max_product_grade: str = "R2"  # Highest product grade allowed
    assessed_at: str = ""
    questionnaire: dict = field(default_factory=dict)


def assess_risk_level(answers: dict[str, str] | list[int]) -> tuple[int, str]:
    """Score questionnaire answers and determine risk level.

    Args:
        answers: either a dict mapping question id to selected option label,
                 or a list of int scores (one per question, in order).

    Returns:
        (total_score, risk_level)
    """
    if isinstance(answers, list):
        # Frontend sends a list of scores directly
        total = sum(int(s) for s in answers[:len(QUESTIONNAIRE)])
    else:
        total = 0
        for q in QUESTIONNAIRE:
            qid = q["id"]
            selected = answers.get(qid, "")
            for opt in q["options"]:
                if opt["label"] == selected:
                    total += opt["score"]
                    break

    # Score thresholds: 8-15=C1, 16-22=C2, 23-29=C3, 30-36=C4, 37-40=C5
    if total <= 15:
        level = "C1"
    elif total <= 22:
        level = "C2"
    elif total <= 29:
        level = "C3"
    elif total <= 36:
        level = "C4"
    else:
        level = "C5"

    return total, level


def build_profile(answers: dict[str, str] | list[int]) -> SuitabilityProfile:
    """Build a full suitability profile from questionnaire answers."""
    score, level = assess_risk_level(answers)
    info = RISK_LEVELS[level]
    # Store answers in a JSON-serializable format
    questionnaire_data = answers if isinstance(answers, dict) else {"scores": answers}
    return SuitabilityProfile(
        risk_level=level,
        score=score,
        level_name=info["name"],
        level_desc=info["desc"],
        max_product_grade=info["max_product"],
        assessed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        questionnaire=questionnaire_data,
    )


def check_product_suitability(
    investor_level: str,
    product_grade: str,
) -> dict:
    """Check if an investor can invest in a product.

    Returns: {suitable, investor_level, product_grade, warning}
    """
    investor_info = RISK_LEVELS.get(investor_level, RISK_LEVELS["C2"])
    max_grade = investor_info["max_product"]

    # Compare grade numbers
    investor_max_num = int(max_grade[1])
    product_num = int(product_grade[1])
    suitable = product_num <= investor_max_num

    warning = ""
    if not suitable:
        warning = (
            f"您的风险等级为{investor_level}({investor_info['name']})，"
            f"该产品风险等级为{product_grade}({PRODUCT_GRADES.get(product_grade, {}).get('name', '')})，"
            f"超出您的风险承受能力，不建议投资。"
        )

    return {
        "suitable": suitable,
        "investor_level": investor_level,
        "investor_level_name": investor_info["name"],
        "product_grade": product_grade,
        "product_grade_name": PRODUCT_GRADES.get(product_grade, {}).get("name", ""),
        "warning": warning,
    }


def get_product_grade(code: str, name: str = "") -> str:
    """Determine product risk grade from code/name heuristics."""
    # ETF codes: 51xxxx (SH), 15xxxx (SZ) -> usually R3
    # Bond funds: names containing 债 -> R2
    # Money market funds: names containing 货币 -> R1
    # Index funds: names containing 指数 -> R3
    # Individual stocks -> R4
    # Futures/options -> R5

    if "货币" in name:
        return "R1"
    if "债" in name:
        return "R2"
    if "指数" in name or "ETF" in name.upper():
        return "R3"
    if code.startswith(("51", "15", "16")):
        return "R3"
    if "期货" in name or "期权" in name or "杠杆" in name:
        return "R5"
    # Default: individual stock
    return "R4"


# ---- DB persistence ----

async def save_profile(profile: SuitabilityProfile) -> None:
    """Save suitability profile to DB."""
    from backend.app.db.session import get_db
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO suitability_profile
           (id, risk_level, score, questionnaire_json, assessed_at, expires_at)
           VALUES (1, ?, ?, ?, ?, '')""",
        (
            profile.risk_level,
            profile.score,
            json.dumps(profile.questionnaire, ensure_ascii=False),
            profile.assessed_at,
        ),
    )
    await db.commit()
    logger.info("suitability.saved", level=profile.risk_level, score=profile.score)


async def load_profile() -> SuitabilityProfile | None:
    """Load suitability profile from DB."""
    from backend.app.db.session import get_db
    db = await get_db()
    cursor = await db.execute("SELECT * FROM suitability_profile WHERE id = 1")
    row = await cursor.fetchone()
    if not row:
        return None

    level = row["risk_level"]
    info = RISK_LEVELS.get(level, RISK_LEVELS["C2"])
    return SuitabilityProfile(
        risk_level=level,
        score=row["score"],
        level_name=info["name"],
        level_desc=info["desc"],
        max_product_grade=info["max_product"],
        assessed_at=row["assessed_at"],
        questionnaire=json.loads(row["questionnaire_json"]) if row["questionnaire_json"] else {},
    )
