"""한 번만 쓸 수 있는 테스트 데이터 — 기획서 예시값의 `{고유}` 를 실행 때 바꾼다.

## 왜 (2026-09-23 외부 사이트 실측, expandtesting 회원가입)

예시 아이디가 매번 같아서 **두 번째 실행부터** 정상 가입이 '이미 있는 계정' 으로
FAIL 했다. 사이트는 멀쩡하다 — 입력 데이터 때문에 난 오탐이다.

실행 직전(S4)에 바꾼다. 계획(plan.json)에 값을 박으면 `--resume` 이 같은 값을 다시 쓴다.
케이스 하나 안에서는 같은 값이다 — 흐름 케이스가 가입한 아이디로 다음 화면에 로그인한다.
"""

from __future__ import annotations

import re

from prova.models import Expectation, SpecDocument, TestCase, TestStep
from prova.unique_token import UNIQUE_TOKEN, fill_unique


def _case(case_id="signup-valid-001"):
    return TestCase(
        case_id=case_id, screen_id="signup", title="정상 가입", type="positive",
        setup_steps=[TestStep(seq=1, action="fill", target="아이디", value="pre-{고유}")],
        steps=[
            TestStep(seq=1, action="fill", target="아이디", value="prova-{고유}"),
            TestStep(seq=2, action="fill", target="이메일", value="p-{고유}@test.com"),
            TestStep(seq=3, action="click", target="가입하기"),
        ],
        expected=Expectation(type="toast_or_redirect", value="환영합니다, prova-{고유}"),
    )


def _values(case):
    return [s.value for s in case.setup_steps + case.steps if s.value]


class TestFillUnique:
    def test_케이스_안에서는_같은_값이다(self):
        filled = fill_unique(_case())
        stamps = {re.search(r"prova-(\w+)", filled.steps[0].value).group(1),
                  re.search(r"p-(\w+)@", filled.steps[1].value).group(1),
                  re.search(r"pre-(\w+)", filled.setup_steps[0].value).group(1),
                  re.search(r"prova-(\w+)", filled.expected.value).group(1)}
        assert len(stamps) == 1
        stamp = stamps.pop()
        assert re.fullmatch(r"[0-9a-z]{8}", stamp)

    def test_토큰이_남지_않는다(self):
        filled = fill_unique(_case())
        assert not any(UNIQUE_TOKEN in v for v in _values(filled) + [filled.expected.value])

    def test_부를_때마다_다른_값이다(self):
        assert fill_unique(_case()).steps[0].value != fill_unique(_case()).steps[0].value

    def test_원본은_그대로다(self):
        """계획에 남은 케이스가 바뀌면 다음 실행이 같은 값을 쓴다."""
        case = _case()
        fill_unique(case)
        assert case.steps[0].value == "prova-{고유}"

    def test_토큰이_없으면_같은_객체를_돌려준다(self):
        case = TestCase(case_id="c", screen_id="s", title="t", type="positive",
                        steps=[TestStep(seq=1, action="fill", target="a", value="x")],
                        expected=Expectation(type="error_shown"))
        assert fill_unique(case) is case


class _Page:
    class context:
        @staticmethod
        def clear_cookies():
            pass

    def on(self, *_):
        pass


def test_run_cases_가_바꾼_값으로_실행하고_판정한다(monkeypatch, tmp_path):
    import prova.nodes as nodes

    seen = {}

    def fake_steps(ctx, case):
        seen["run"] = case
        return [], None

    def fake_verify(state, case, *a, **k):
        seen["verify"] = case
        return "verdict"

    monkeypatch.setattr(nodes, "_run_case_steps", fake_steps)
    monkeypatch.setattr(nodes, "_verify_when_ready", fake_verify)
    monkeypatch.setattr(nodes, "_specs_for", lambda state, case: [])

    state = nodes.AgentState(pdf_path="", base_url="http://x", run_id="t", run_dir=tmp_path,
                             page=_Page(), doc=SpecDocument(source="x", screens=[]),
                             cases=[_case()])
    nodes.run_cases(state)

    assert UNIQUE_TOKEN not in seen["run"].steps[0].value
    assert seen["verify"] is seen["run"]
    assert state.cases[0].steps[0].value == "prova-{고유}"
