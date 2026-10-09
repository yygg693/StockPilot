"""Tests for backend.app.core.suitability — investor risk profiling."""
from __future__ import annotations

from backend.app.core.suitability import (
    QUESTIONNAIRE,
    RISK_LEVELS,
    PRODUCT_GRADES,
    assess_risk_level,
    build_profile,
    check_product_suitability,
    get_product_grade,
)


class TestQuestionnaire:
    def test_has_8_questions(self):
        assert len(QUESTIONNAIRE) == 8

    def test_each_question_has_options(self):
        for q in QUESTIONNAIRE:
            assert "id" in q
            assert "question" in q
            assert len(q["options"]) >= 4
            for opt in q["options"]:
                assert "label" in opt
                assert "score" in opt
                assert 1 <= opt["score"] <= 5


class TestRiskLevels:
    def test_has_5_levels(self):
        assert set(RISK_LEVELS.keys()) == {"C1", "C2", "C3", "C4", "C5"}

    def test_max_product_mapping(self):
        assert RISK_LEVELS["C1"]["max_product"] == "R1"
        assert RISK_LEVELS["C5"]["max_product"] == "R5"


class TestAssessRiskLevel:
    def _make_answers(self, option_index: int = 0) -> dict:
        """Build answers selecting the option_index-th option for each question."""
        answers = {}
        for q in QUESTIONNAIRE:
            answers[q["id"]] = q["options"][option_index]["label"]
        return answers

    def test_all_low_scores_gives_c1(self):
        answers = self._make_answers(0)  # First option = lowest score
        score, level = assess_risk_level(answers)
        assert level == "C1"
        assert score <= 15

    def test_all_high_scores_gives_c5(self):
        answers = {}
        for q in QUESTIONNAIRE:
            # Select the option with the highest score
            best = max(q["options"], key=lambda o: o["score"])
            answers[q["id"]] = best["label"]
        score, level = assess_risk_level(answers)
        assert level == "C5"
        assert score > 36

    def test_empty_answers_gives_c1(self):
        score, level = assess_risk_level({})
        assert score == 0
        assert level == "C1"


class TestBuildProfile:
    def test_profile_has_all_fields(self):
        answers = {"age": "31-45岁", "income": "10-30万"}
        profile = build_profile(answers)
        assert profile.risk_level in RISK_LEVELS
        assert profile.score > 0
        assert profile.level_name
        assert profile.max_product_grade
        assert profile.assessed_at

    def test_profile_max_product_matches_level(self):
        answers = {}
        for q in QUESTIONNAIRE:
            answers[q["id"]] = q["options"][2]["label"]  # Middle options
        profile = build_profile(answers)
        expected = RISK_LEVELS[profile.risk_level]["max_product"]
        assert profile.max_product_grade == expected


class TestCheckProductSuitability:
    def test_c1_can_buy_r1(self):
        result = check_product_suitability("C1", "R1")
        assert result["suitable"] is True
        assert result["warning"] == ""

    def test_c1_cannot_buy_r4(self):
        result = check_product_suitability("C1", "R4")
        assert result["suitable"] is False
        assert "超出" in result["warning"]

    def test_c5_can_buy_anything(self):
        for grade in ["R1", "R2", "R3", "R4", "R5"]:
            result = check_product_suitability("C5", grade)
            assert result["suitable"] is True

    def test_c3_can_buy_r3_not_r4(self):
        assert check_product_suitability("C3", "R3")["suitable"] is True
        assert check_product_suitability("C3", "R4")["suitable"] is False


class TestGetProductGrade:
    def test_money_fund_is_r1(self):
        assert get_product_grade("001234", "货币基金") == "R1"

    def test_bond_fund_is_r2(self):
        assert get_product_grade("005678", "债券基金A") == "R2"

    def test_etf_is_r3(self):
        assert get_product_grade("510300", "沪深300ETF") == "R3"

    def test_index_fund_is_r3(self):
        assert get_product_grade("161725", "指数基金") == "R3"

    def test_stock_is_r4(self):
        assert get_product_grade("sh600519", "贵州茅台") == "R4"

    def test_futures_is_r5(self):
        assert get_product_grade("IF2401", "沪深300期货") == "R5"
