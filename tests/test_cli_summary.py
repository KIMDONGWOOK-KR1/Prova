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


def test_약한_확인_통과도_한_줄로_알린다(capsys):
    from prova.s5_verifier.assertion_engine import WEAK_PASS_REASON

    weak = SimpleNamespace(verdict="PASS", failure_category=None, title="정상 검색",
                           violates=None, failure_detail="",
                           evidence={"actual": WEAK_PASS_REASON})
    _print_summary(_report(weak), Path("runs/x"))
    assert "'에러 없음'만 확인한 정상 케이스 1건" in capsys.readouterr().out


def _dry_report(blocked: int, passed: int, other_fails=()):
    cases = ([_case("unverifiable", f"제출 {i}") for i in range(blocked)]
             + [SimpleNamespace(verdict="PASS", failure_category=None, title=f"통과 {i}",
                                violates=None, failure_detail="", evidence={}) for i in range(passed)]
             + list(other_fails))
    report = _report(*cases)
    total = len(cases)
    report.summary["pass_rate"] = round(passed / total * 100, 1)
    report.summary["dry_run"] = {"cases_blocked": blocked, "requests_blocked": blocked,
                                 "setup_allowed": 0}
    return report


def test_dry_run_으로_막은_케이스는_결과_줄_바로_아래에서_결함이_아니라고_말한다(capsys):
    # 11-10 리허설: '실패 14 · 통과율 17.6%' 만 보면 구현이 엉망인 것처럼 읽힌다.
    _print_summary(_dry_report(blocked=14, passed=3), Path("runs/x"))
    out = capsys.readouterr().out
    lines = out.splitlines()
    head = next(i for i, l in enumerate(lines) if "결과: 전체" in l)
    note = lines[head + 1]
    assert "dry-run" in note and "14" in note and "구현 결함이 아닙니다" in note
    # 막지 않은 케이스만 본 결과를 함께 — 3건 중 3건 통과
    assert "막지 않은 3건 중 통과 3" in note


def test_dry_run_막지_않은_케이스의_실패도_그대로_센다(capsys):
    _print_summary(_dry_report(blocked=2, passed=1,
                               other_fails=[_case("assertion_mismatch", "형식", "format")]),
                   Path("runs/x"))
    out = capsys.readouterr().out
    assert "막지 않은 2건 중 통과 1" in out
    assert "기획서와 다름 1건" in out


def test_dry_run_이_아니면_그_줄이_없다(capsys):
    _print_summary(_report(_case("unverifiable", "확인 불가")), Path("runs/x"))
    assert "dry-run" not in capsys.readouterr().out
