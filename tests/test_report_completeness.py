"""리포트 완결성 채점기 — 실패 케이스의 다섯 칸을 제대로 세는가 (2026-11-11).

채점기(scripts/score_report_completeness.py)는 실행 폴더의 report.json 만 읽는다. 여기서는
칸이 빠진 기록을 '찼다' 고 세지 않는지, 그리고 실제 판정 코드가 만든 실패 기록이 다섯 칸을
모두 채우는지 본다.
"""

from __future__ import annotations

import json

from prova.models import Expectation, StepResult, TestCase
from prova.s5_verifier.assertion_engine import PageState, verify
from tests.conftest import load_script

rc = load_script("scripts/score_report_completeness.py")


def _case(**over) -> dict:
    case = {
        "case_id": "c-1", "verdict": "FAIL",
        "failure_category": "assertion_mismatch", "failure_detail": "문구가 다릅니다.",
        "spec_sources": [{"page": 1, "quote": "email | 입력", "table": True}],
        "evidence": {"expected": "오류 문구가 나타난다", "actual": "문구 없음",
                     "url": "http://x/login", "screenshot": None},
        "step_results": [
            {"seq": 1, "action": "navigate", "target": "/login", "value": None, "status": "ok"},
            {"seq": 2, "action": "fill", "target": "이메일", "value": "a@b.c", "status": "ok"},
            {"seq": 3, "action": "click", "target": "로그인", "value": None, "status": "ok"},
        ],
    }
    case.update(over)
    return case


def test_다섯_칸이_찬_케이스():
    assert all(rc.score_case(_case()).values())


def test_넣은_값이_기록되지_않으면_입력_데이터가_비었다():
    steps = _case()["step_results"]
    steps[1]["value"] = None
    fields = rc.score_case(_case(step_results=steps))
    assert not fields["입력 데이터"] and fields["실행 로그"]


def test_빈_칸으로_둔_입력은_기록된_것이다():
    """필수 항목 케이스는 칸을 비워 둔다 — 빈 글자는 '비웠다' 는 기록이다."""
    steps = _case()["step_results"]
    steps[1]["value"] = ""
    assert rc.score_case(_case(step_results=steps))["입력 데이터"]


def test_클릭과_이동은_값이_없어도_된다():
    steps = [s for s in _case()["step_results"] if s["action"] != "fill"]
    case = _case(step_results=steps)
    assert rc.score_case(case)["입력 데이터"] and not rc.has_inputs(case)


def test_빠진_칸을_찼다고_세지_않는다():
    assert not rc.score_case(_case(step_results=[]))["실행 로그"]
    assert not rc.score_case(_case(failure_detail=""))["실패 원인"]
    assert not rc.score_case(_case(failure_category=None))["실패 원인"]
    evidence = dict(_case()["evidence"], expected="  ")
    assert not rc.score_case(_case(evidence=evidence))["기대 결과"]
    evidence = dict(_case()["evidence"], url=None)
    assert not rc.score_case(_case(evidence=evidence))["실제 결과"]


def test_폴더를_훑어_집계한다(tmp_path):
    bad = _case(case_id="c-2", failure_detail=None)
    lost = _case(case_id="c-3")
    lost["evidence"]["screenshot"] = "c-3/step1.png"  # 파일은 만들지 않는다
    passed = _case(case_id="c-4", verdict="PASS", failure_category=None, failure_detail=None)
    run = tmp_path / "run-a"
    run.mkdir()
    (run / "report.json").write_text(
        json.dumps({"cases": [_case(), bad, lost, passed]}, ensure_ascii=False), encoding="utf-8")

    result = rc.score(tmp_path)
    assert (result["runs"], result["fail"], result["pass"]) == (1, 3, 1)
    assert result["fail_complete"] == 2
    assert result["incomplete"] == ["run-a/c-2: 실패 원인"]
    assert result["fail_files_ok"] == 2 and result["missing_files"] == ["run-a/c-3: c-3/step1.png"]
    assert result["pass_complete"] == 1          # 통과 케이스는 실패 원인을 보지 않는다
    assert result["runs_without_log"] == ["run-a"]
    assert "2/3 (66.7%)" in rc.render(result)


def test_판정_코드가_만든_실패_기록은_다섯_칸이_찬다():
    """채점기가 보는 꼴은 실제 Verdict 를 JSON 으로 내린 것이다."""
    case = TestCase(case_id="c", screen_id="s", title="t", type="positive",
                    expected=Expectation(type="text_visible", value="가입이 완료되었습니다"))
    steps = [StepResult(seq=1, action="navigate", target="/signup", status="ok"),
             StepResult(seq=2, action="fill", target="이메일", value="a@b.c", status="ok")]
    verdict = verify(case, steps, PageState(url="http://x/signup", text="다른 화면"))
    assert verdict.verdict == "FAIL"
    assert all(rc.score_case(verdict.model_dump(mode="json")).values())
