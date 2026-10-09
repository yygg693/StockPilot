"""Suitability assessment and risk warning endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.core.logging import get_logger
from backend.app.core.risk_warning import generate_warnings, get_trade_confirmation_warning
from backend.app.core.suitability import (
    PRODUCT_GRADES,
    QUESTIONNAIRE,
    RISK_LEVELS,
    build_profile,
    check_product_suitability,
    get_product_grade,
    load_profile,
    save_profile,
)
from backend.app.deps import get_current_user

logger = get_logger("suitability.router")

router = APIRouter(dependencies=[Depends(get_current_user)])


# ---- Models ----

class AssessmentAnswers(BaseModel):
    answers: list[int] | dict[str, str]


class ProductCheckRequest(BaseModel):
    code: str
    name: str = ""


class TradeWarningRequest(BaseModel):
    action: str  # "buy" or "sell"
    code: str
    name: str = ""
    amount: float = 0.0


# ---- Endpoints ----

@router.get("/suitability/questionnaire")
async def get_questionnaire():
    """Get the suitability assessment questionnaire."""
    return {"data": {"questions": QUESTIONNAIRE, "risk_levels": RISK_LEVELS}}


@router.post("/suitability/assess")
async def assess_suitability(req: AssessmentAnswers):
    """Submit questionnaire answers and get risk assessment."""
    profile = build_profile(req.answers)
    await save_profile(profile)
    logger.info("suitability.assessed", level=profile.risk_level, score=profile.score)
    return {"data": {
        "risk_level": profile.risk_level,
        "level_name": profile.level_name,
        "level_desc": profile.level_desc,
        "score": profile.score,
        "max_product_grade": profile.max_product_grade,
        "assessed_at": profile.assessed_at,
    }}


@router.get("/suitability/profile")
async def get_profile():
    """Get current suitability profile."""
    profile = await load_profile()
    if not profile:
        return {"data": {"assessed": False, "message": "尚未完成风险测评"}}
    return {"data": {
        "assessed": True,
        "risk_level": profile.risk_level,
        "level_name": profile.level_name,
        "level_desc": profile.level_desc,
        "score": profile.score,
        "max_product_grade": profile.max_product_grade,
        "assessed_at": profile.assessed_at,
    }}


@router.get("/suitability/product-grades")
async def get_product_grades():
    """Get product risk grade definitions."""
    return {"data": PRODUCT_GRADES}


@router.post("/suitability/check-product")
async def check_product(req: ProductCheckRequest):
    """Check if current investor can invest in a specific product."""
    profile = await load_profile()
    if not profile:
        return {"data": {"suitable": True, "warning": "", "message": "未完成风险测评，默认允许"}}

    grade = get_product_grade(req.code, req.name)
    result = check_product_suitability(profile.risk_level, grade)
    return {"data": result}


@router.get("/risk-warnings")
async def get_risk_warnings():
    """Get all active risk warnings for the current portfolio."""
    from backend.app.services.ai_context import get_trade_db
    db = await get_trade_db()
    warnings = await generate_warnings(db)
    return {"data": warnings}


@router.post("/risk-warnings/trade-check")
async def trade_warning_check(req: TradeWarningRequest):
    """Get a risk warning string for a specific trade confirmation."""
    warning = get_trade_confirmation_warning(req.action, req.code, req.name, req.amount)
    return {"data": {"warning": warning}}
