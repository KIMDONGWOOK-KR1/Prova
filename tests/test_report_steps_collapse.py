"""긴 단계는 앞쪽 통과한 단계를 한 줄로 접는다 (2026-11-25).

같은 4단계를 5번 되풀이한 로그인 잠금 케이스가 20줄을 끝까지 늘어놓아, 멈춘 자리를 찾으려면
스크롤해야 했다. 되풀이를 찾아 멈춘 회차 앞을 접고, 멈춘 회차는 펼쳐 둔다. 웹 UI(app.js)와 같은 규칙.
"""

from __future__ import annotations

from prova.models import StepResult, Verdict
from prova.s6_report.report_builder import _trace_html, step_period, step_plan

LOGIN = [("navigate", "/login"), ("fill", "이메일"), ("fill", "비밀번호"), ("click", "로그인")]


def _steps(sig, n, fail_last=True):
    out = []
    for i in range(n):
        a, t = sig[i % len(sig)]
        out.append(StepResult(seq=i + 1, action=a, target=t, value=f"v{i}", elapsed_ms=100,
                              screenshot=f"s{i + 1}.png",
                              status="error" if fail_last and i == n - 1 else "ok"))
    return out


def test_4단계_5회_되풀이_멈춘_회차_앞을_접는다():
    steps = _steps(LOGIN, 20)
    assert step_period(steps) == 4  # 넣은 값(v0, v1…)은 달라도 같은 단계
    plan = step_plan(steps, 19)
    assert plan == {"hide": 16, "period": 4, "label": "1–4회째 · 16단계 모두 통과"}


def test_3단계_2회_더하기_1_중간에_멈춘_회차도_되풀이다():
    sig = [("navigate", "/a"), ("fill", "이름"), ("click", "다음")]
    steps = _steps(sig, 9)[:7]
    steps[-1].status = "error"
    assert step_period(steps) == 3
    # 7개라 8개 이하 — 그대로 둔다
    assert step_plan(steps, 6) is None
    longer = _steps(sig, 10)  # 3 × 3 + 1, 마지막에서 멈춤
    assert step_period(longer) == 3
    assert step_plan(longer, 9) == {"hide": 9, "period": 3, "label": "1–3회째 · 9단계 모두 통과"}


def test_되풀이가_없으면_멈춘_단계_앞_3개만_남긴다():
    sig = [("fill", f"칸{i}") for i in range(12)]
    steps = _steps(sig, 12)
    assert step_period(steps) == 0
    assert step_plan(steps, 11) == {"hide": 8, "period": 0, "label": "앞 단계 8개 통과"}
    # 모두 통과면 마지막 하나만
    assert step_plan(steps, -1)["label"] == "단계 11개 모두 통과"


def test_8개_이하는_그대로():
    assert step_plan(_steps(LOGIN, 8), 7) is None


def test_리포트_실패_카드는_접힌_묶음과_멈춘_회차를_보인다():
    v = Verdict(case_id="login-scenario-009", title="잠금", screen_id="login", verdict="FAIL",
                failure_category="assertion_mismatch", step_results=_steps(LOGIN, 20))
    html = _trace_html(v, "defect")
    grp = html.index("<li class='tr-grp'><details>")
    assert "<details open" not in html  # 인쇄·처음 모습은 접힌 채
    assert "1–4회째 · 16단계 모두 통과" in html[grp:]
    end = html.index("</details>")
    assert "5회째" in html[end:] and "1회째" in html[grp:end]
    # 접힌 단계도 끌기·캡처를 위해 남아 있다 — 20줄 모두
    assert html.count("data-start=") == 20
