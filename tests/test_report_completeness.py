"""리포트 완결성 채점기 — 좋은 소식만 낼 수 있는 지표가 아닌지 확인한다.

## 왜 이 테스트가 먼저인가

이 채점기는 명세서 §9 의 목표가 **100%** 인 지표를 잰다. 늘 100% 를 내는 채점기는
아무것도 재지 않는 것과 같은데, 눈으로는 구분이 안 된다 — 둘 다 초록불이다.

그래서 **일부러 필드를 뺀 리포트**를 먹여 점수가 실제로 내려가는지 본다.
`scripts/eval_selector_speed.py` 가 오탐 집계에 같은 장치를 둔 이유와 같다.

## n/a 를 분모에서 빼는 것도 여기서 지킨다

입력 스텝이 없는 케이스에 '입력 데이터' 를 요구하면 통과율이 케이스 구성에 따라
흔들린다. PASS 에 '실패 원인' 을 요구하면 통과율이 실패 비율을 따라 움직인다.
둘 다 지표를 무의미하게 만든다.
"""

from __future__ import annotations

from tests.conftest import load_script

mod = load_script("scripts/eval_report_completeness.py")


def case(**over) -> dict:
    """다섯 필드가 다 찬 케이스. 테스트마다 필요한 것만 덜어낸다."""
    base = {
        "case_id": "login-required-001",
        "verdict": "PASS",
        "evidence": {"expected": "에러 문구 노출", "actual": "문구 확인"},
        "failure_category": None,
        "failure_detail": None,
        "step_results": [
            {"seq": 1, "action": "navigate", "target": "/login", "status": "ok"},
            {"seq": 2, "action": "fill", "target": "이메일", "status": "ok",
             "value": "a@b.com"},
        ],
    }
    base.update(over)
    return base


def report(*cases: dict) -> dict:
    return {"run_id": "t", "cases": list(cases)}


class TestCheckCase:
    def test_다_있으면_전부_ok(self):
        r = mod.check_case(case())
        assert r["log"] == "ok"
        assert r["input"] == "ok"
        assert r["expected"] == "ok"
        assert r["actual"] == "ok"

    def test_입력값이_없으면_missing(self):
        """이 저장소가 실제로 겪은 모양이다 — fill 스텝은 있는데 값이 안 남았다."""
        steps = [
            {"seq": 1, "action": "fill", "target": "이메일", "status": "ok"},
        ]
        r = mod.check_case(case(step_results=steps))
        assert r["input"] == "missing"

    def test_빈_문자열은_값이다(self):
        """필수 입력 검증 케이스가 넣는 값이 정확히 빈 문자열이다. 이걸 누락으로
        세면 그 케이스들이 통째로 빠진다 — 2026-09-23 에 32건 그랬다."""
        steps = [{"seq": 1, "action": "fill", "target": "이메일", "status": "ok",
                  "value": ""}]
        assert mod.check_case(case(step_results=steps))["input"] == "ok"

    def test_값이_기록되지_않으면_missing(self):
        """빈 문자열(넣었다)과 None(기록이 없다)은 다르다."""
        steps = [{"seq": 1, "action": "fill", "target": "이메일", "status": "ok",
                  "value": None}]
        assert mod.check_case(case(step_results=steps))["input"] == "missing"

    def test_입력_스텝이_없으면_n_a(self):
        """화면을 열어 보기만 하는 케이스. 없는 것을 누락으로 세지 않는다."""
        steps = [{"seq": 1, "action": "navigate", "target": "/orders", "status": "ok"}]
        r = mod.check_case(case(step_results=steps))
        assert r["input"] == "n/a"

    def test_스텝이_하나도_없으면_로그_missing(self):
        r = mod.check_case(case(step_results=[]))
        assert r["log"] == "missing"

    def test_기대와_실제는_따로_센다(self):
        r = mod.check_case(case(evidence={"expected": "무언가"}))
        assert r["expected"] == "ok" and r["actual"] == "missing"

    def test_PASS_에는_실패_원인을_요구하지_않는다(self):
        assert mod.check_case(case(verdict="PASS"))["cause"] == "n/a"

    def test_FAIL_인데_원인이_없으면_missing(self):
        r = mod.check_case(case(verdict="FAIL"))
        assert r["cause"] == "missing"

    def test_FAIL_에_분류와_설명이_다_있어야_ok(self):
        r = mod.check_case(case(verdict="FAIL",
                                failure_category="assertion_mismatch",
                                failure_detail="대문자 검증이 없습니다"))
        assert r["cause"] == "ok"

    def test_분류만_있고_설명이_없으면_missing(self):
        """분류만으로는 무엇을 고쳐야 하는지 모른다."""
        r = mod.check_case(case(verdict="FAIL",
                                failure_category="assertion_mismatch"))
        assert r["cause"] == "missing"

    def test_elapsed_0_은_값이다(self):
        """빠른 스텝이 벌을 받으면 안 된다 — 0 과 없음은 다르다."""
        steps = [{"seq": 1, "action": "navigate", "target": "/x", "status": "ok",
                  "elapsed_ms": 0}]
        assert mod.check_case(case(step_results=steps))["log"] == "ok"


class TestEvaluate:
    def test_다_찬_리포트는_100퍼센트(self):
        r = mod.evaluate([report(case(), case())])
        assert r["total"]["rate"] == 100.0
        assert r["cases"] == 2

    def test_필드를_빼면_점수가_내려간다(self):
        """이 테스트가 이 파일의 이유다 — 채점기가 나쁜 소식을 낼 수 있는가."""
        broken = case(evidence={"expected": "무언가"})     # actual 없음
        r = mod.evaluate([report(case(), broken)])
        assert r["total"]["rate"] < 100.0
        assert r["fields"]["actual"]["missing"] == 1
        assert r["fields"]["actual"]["rate"] == 50.0

    def test_n_a_는_분모에서_뺀다(self):
        """입력 스텝이 없는 케이스만 있으면 '입력 데이터' 는 비율이 없다."""
        steps = [{"seq": 1, "action": "navigate", "target": "/x", "status": "ok"}]
        r = mod.evaluate([report(case(step_results=steps))])
        assert r["fields"]["input"]["required"] == 0
        assert r["fields"]["input"]["rate"] is None
        assert r["total"]["rate"] == 100.0, "해당 없는 칸이 통과율을 깎으면 안 된다"

    def test_빠진_케이스를_이름으로_남긴다(self):
        """숫자만 주면 어디를 고쳐야 하는지 다시 찾아야 한다."""
        broken = case(case_id="search-count-003", evidence={"expected": "x"})
        r = mod.evaluate([report(broken)])
        assert "search-count-003" in r["examples"]["actual"]

    def test_리포트_여러개를_합산한다(self):
        r = mod.evaluate([report(case()), report(case(), case())])
        assert r["reports"] == 2 and r["cases"] == 3
