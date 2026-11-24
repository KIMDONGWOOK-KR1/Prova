"""리포트 원형차트 — 기획자가 결과의 구성을 한눈에 본다 (2026-10-16 멘토링 요구).

처음에는 원형차트였고, 2026-11-18 에 비율 막대로 바꿨다가 11-24 에 원형차트로 되돌렸다.
웹 UI 결과 화면도 같은 도넛을 쓴다 — 같은 숫자가 화면과 파일에서 다른 그림이면 다른 문서로 읽힌다.

차트가 숫자를 부풀리면 안 된다. 네 조각의 합은 전체 케이스 수와 같아야 하고, '기획서와
다름' 과 '실행 문제' 는 색과 이름 모두 갈린다. 실행하지 않은 것은 조각이 아니라 말로 남긴다.
"""

from __future__ import annotations

from prova.models import TestReport, Verdict
from prova.s5_verifier.assertion_engine import WEAK_PASS_REASON
from prova.s6_report.report_builder import chart_segments, render_html


def _v(case_id: str, verdict: str = "PASS", category=None, actual: str = "ok") -> Verdict:
    return Verdict(case_id=case_id, title=case_id, type="positive", verdict=verdict,
                   failure_category=category, evidence={"actual": actual})


def _report(verdicts: list[Verdict], **summary) -> TestReport:
    s = TestReport.summarize(verdicts)
    s.update(summary)
    return TestReport(run_id="r", target_url="http://x", spec_source="s.pdf", summary=s,
                      cases=verdicts, created_at="2026-11-02T00:00:00+09:00")


MIXED = [_v("a"), _v("b"), _v("c", actual=WEAK_PASS_REASON),
         _v("d", "FAIL", "assertion_mismatch"), _v("e", "FAIL", "assertion_mismatch"),
         _v("f", "FAIL", "element_not_found"), _v("g", "FAIL", "precondition_failed")]


def test_네_조각으로_나누고_합이_전체와_같다():
    got = {s.key: s.count for s in chart_segments(MIXED)}
    assert got == {"pass": 2, "weak": 1, "defect": 2, "infra": 2}
    assert sum(got.values()) == len(MIXED)


def test_없는_조각은_그리지_않는다():
    assert [s.key for s in chart_segments([_v("a")])] == ["pass"]


def test_리포트에_원형차트와_이름표가_함께_있다():
    html = render_html(_report(MIXED))
    chart = html[html.index("<div class='chart'>"):]
    assert "<svg viewBox='0 0 132 132'" in chart and "role='img'" in chart
    assert "<ul class='legend'>" in chart
    # 색만으로 말하지 않는다 — 조각마다 이름과 수가 글자로 있다.
    assert "기획서와 다름 2 · 실행 문제 2 · 통과 3 (약한 확인 1 포함)" in html


def test_조각의_순서는_웹_UI와_같다():
    """결함이 맨 앞, 통과가 맨 뒤 — 화면에서 본 도넛과 파일의 도넛이 같은 그림이다."""
    html = render_html(_report(MIXED))
    svg = html[html.index("<div class='chart'>"):html.index("</svg>", html.index("<div class='chart'>"))]
    order = [svg.index(f"class='seg {k}'") for k in ("defect", "infra", "weak", "pass")]
    assert order == sorted(order)


def test_조각_길이의_합은_고리_한_바퀴다():
    """틈(2)을 빼고 그린 조각 + 틈 = 둘레. 부풀린 조각이 없다."""
    import math
    import re
    html = render_html(_report(MIXED))
    dashes = [float(a) for a in re.findall(r"class='seg \w+'[^>]*stroke-dasharray='([\d.]+) ", html)]
    radius = 132 / 2 - 16 / 2 - 1
    assert abs(sum(dashes) + 2 * len(dashes) - 2 * math.pi * radius) < 0.1


def test_케이스가_없으면_차트를_그리지_않는다():
    assert "<div class='chart'>" not in render_html(_report([]))


def test_확인하지_않은_것이_있으면_차트_옆에_말한다():
    html = render_html(_report(MIXED, coverage_gaps=["x", "y"]))
    assert "차트에 없는 것" in html and "2건" in html
