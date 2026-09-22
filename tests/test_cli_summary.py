"""터미널 요약은 '기획서와 다름' 과 '실행 문제' 를 나눠 보여 준다.

이 도구의 첫째 원칙은 탐지·환경 실패를 구현 결함과 섞지 않는 것이다
(assertion_mismatch = 구현을 고쳐라, 나머지 = 도구·환경을 고쳐라). 분류는
처음부터 판정에 있었는데 터미널은 모든 FAIL 을 같은 모양으로 찍어서, 화면만
보는 사람에게는 그 구분이 없었다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from prova.cli import _print_summary


def _case(category, title, violates=None, detail="사유"):
    return SimpleNamespace(verdict="FAIL", failure_category=category, title=title,
                           violates=violates, failure_detail=detail)


def _report(*cases):
    fails = [c for c in cases if c.verdict == "FAIL"]
    return SimpleNamespace(
        summary={"total": len(cases), "pass": len(cases) - len(fails),
                 "fail": len(fails), "pass_rate": 0.0},
        cases=list(cases))


def test_두_묶음으로_나눈다(capsys):
    report = _report(
        _case("assertion_mismatch", "비밀번호 대문자 검증", "require_uppercase"),
        _case("precondition_failed", "가격 숫자 검증"),
        _case("element_not_found", "검색 버튼"),
    )
    _print_summary(report, Path("runs/x"))
    out = capsys.readouterr().out

    assert "기획서와 다름 1건" in out
    assert "실행 문제 2건" in out
    assert "도구·환경" in out
    # 실행 문제 줄에는 원인 이름이 붙는다 — 무엇을 고쳐야 하는지 한눈에
    assert "[전제 미충족]" in out
    assert "[요소 미탐지]" in out
    # 순서: 기획서와 다름이 먼저
    assert out.index("기획서와 다름") < out.index("실행 문제")


def test_실행_문제가_없으면_그_묶음을_찍지_않는다(capsys):
    _print_summary(_report(_case("assertion_mismatch", "형식 검증", "format")),
                   Path("runs/x"))
    out = capsys.readouterr().out
    assert "기획서와 다름 1건" in out
    assert "실행 문제" not in out
