"""일부러 심은 결함 — 로그인 5회 실패 안내 문구 누락 (2026-10-16 멘토 제안).

값의 규칙이 아니라 **누적된 상태**에 대한 요구라, 한 번 제출하는 케이스로는 잡히지
않는다. 기획서 예시 표의 '시도 횟수' 열이 반복 제출 케이스가 된다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.models import Scenario, ScreenSpec, UIElement
from prova.pipeline import run_pipeline
from prova.s1_spec_extractor.extractor import _apply_declared_scenarios, extract_document
from prova.s1_spec_extractor.pdf_parser import parse_pdf
from prova.s2_case_generator.generator import generate_cases

PDF = "fixtures/specs/lockout_spec.pdf"
LOCKED = "로그인 5회 실패로 계정이 잠겼습니다."


def test_표의_시도_횟수를_읽는다():
    rows = parse_pdf(PDF).declared_scenarios()
    assert [r.get("repeat", 1) for r in rows] == [1, 5]


def test_시도_횟수를_결과_건수로_읽지_않는다():
    assert all(r["expect_count"] is None for r in parse_pdf(PDF).declared_scenarios())


def test_모델이_모르는_칸이라_경고하지_않는다():
    spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/s", scenarios=[
        Scenario(given={"email": "a"}, expect_text="문구")])
    _apply_declared_scenarios(spec, [{"given": {"email": "a"}, "expect_text": "문구",
                                      "expect_count": None, "expect_absent": None, "repeat": 5}])
    assert spec.warnings == []
    assert spec.scenarios[0].repeat == 5


def test_횟수를_적지_않은_표는_한_번이다():
    spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/s")
    _apply_declared_scenarios(spec, [{"given": {"email": "a"}, "expect_text": "문구"}])
    assert spec.scenarios[0].repeat == 1


def _spec(repeat: int) -> ScreenSpec:
    return ScreenSpec(
        screen_id="login", screen_name="로그인", url_path="/login",
        elements=[UIElement(element_id="email", type="input", label="이메일"),
                  UIElement(element_id="go", type="button", label="로그인")],
        scenarios=[Scenario(given={"email": "a@b.c"}, expect_text="문구", repeat=repeat)],
    )


def _scenario_case(repeat: int):
    return next(c for c in generate_cases(_spec(repeat)) if "scenario" in c.case_id)


def test_제출을_횟수만큼_잇고_매번_화면을_새로_연다():
    case = _scenario_case(3)
    assert [s.action for s in case.steps].count("click") == 3
    assert [s.action for s in case.steps].count("navigate") == 3


def test_스텝_번호가_겹치지_않는다():
    # 스크린샷 파일 이름이 번호로 정해진다 — 겹치면 증거가 덮어써진다
    seqs = [s.seq for s in _scenario_case(3).steps]
    assert seqs == list(range(1, len(seqs) + 1))


def test_제목에_횟수를_적는다():
    assert "3회" in _scenario_case(3).title


def test_한_번짜리는_그대로다():
    assert [s.action for s in _scenario_case(1).steps].count("click") == 1


def _lock_verdict(sut_base, variant, tmp_path):
    report, _ = run_pipeline(PDF, f"{sut_base}/{variant}", MockLLM.for_document(PDF),
                             run_id=variant, runs_root=tmp_path, only="scenario")
    return next(v for v in report.cases if "잠겼" in v.title)


def test_안내가_있는_구현은_통과한다(sut_base, tmp_path):
    assert _lock_verdict(sut_base, "good", tmp_path).verdict == "PASS"


def test_안내가_없는_구현은_기획서와_다름으로_실패한다(sut_base, tmp_path):
    verdict = _lock_verdict(sut_base, "bad", tmp_path)
    assert (verdict.verdict, verdict.failure_category) == ("FAIL", "assertion_mismatch")
    assert LOCKED in verdict.failure_detail


def test_두_번_돌려도_첫_실패에_잠기지_않는다(sut_base, tmp_path):
    # {고유} 가 실행마다 바뀌어 앞 실행의 누적이 다음 판정을 바꾸지 않는다
    assert _lock_verdict(sut_base, "good", tmp_path).verdict == "PASS"
    assert _lock_verdict(sut_base, "good", tmp_path / "two").verdict == "PASS"


def test_문서_추출_뒤에도_횟수가_남는다():
    doc = extract_document(PDF, MockLLM.for_document(PDF))
    assert [s.repeat for s in doc.screens[0].scenarios] == [1, 5]


@pytest.mark.parametrize("header", ["시도 횟수", "반복 횟수", "제출 횟수", "attempts"])
def test_횟수_열_이름(header):
    from prova.s1_spec_extractor.pdf_parser import _REPEAT_HEADER_RE

    assert _REPEAT_HEADER_RE.search(header)


@pytest.mark.parametrize("header", ["결과 건수", "개수", "건수"])
def test_건수_열은_횟수가_아니다(header):
    from prova.s1_spec_extractor.pdf_parser import _REPEAT_HEADER_RE

    assert not _REPEAT_HEADER_RE.search(header)
