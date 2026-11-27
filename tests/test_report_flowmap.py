"""흐름 실패 카드의 화면 흐름 지도 — 어느 화면, 어느 이동에서 끊겼는가.

리포트에는 기획서의 흐름 표가 없어서 케이스 스텝의 화면 경계 이름('signup 성공',
'login 도착')으로 지도를 다시 세운다. 그 이름은 생성기가 짓는다 — 그래서 여기서는
스텝을 손으로 쓰지 않고 generate_flow_cases 가 만든 스텝을 쓴다. 생성기가 이름을
바꾸면 이 테스트가 먼저 깨진다.
"""

from __future__ import annotations

from prova.models import Flow, ScreenSpec, SpecDocument, StepResult, UIElement, Verdict
from prova.s2_case_generator.generator import generate_flow_cases
from prova.s6_report.report_builder import _flow_map_html, flow_route

NAMES = {"signup": "회원가입", "login": "로그인", "product": "상품 등록"}


def _steps(via=("로그인하러 가기",)):
    def screen(sid, path, *labels):
        return ScreenSpec(screen_id=sid, screen_name=NAMES[sid], url_path=path,
                          success_condition="완료 문구가 보인다",
                          elements=[UIElement(element_id=f"{sid}.{i}", type="input", label=l)
                                    for i, l in enumerate(labels)]
                          + [UIElement(element_id=f"{sid}.go", type="button", label="확인")])
    doc = SpecDocument(
        screens=[screen("signup", "/signup", "이메일"), screen("login", "/login", "이메일"),
                 screen("product", "/product", "상품명")],
        flows=[Flow(flow_id="f", screen_ids=["signup", "login", "product"], via=list(via))])
    [case] = generate_flow_cases(doc)
    return case.steps


def _verdict(steps, fail_at=None, verdict=None):
    """fail_at 번째 스텝(0부터)에서 멈춘 판정. None 이면 스텝은 끝까지 지났다."""
    done = steps if fail_at is None else steps[:fail_at + 1]
    results = [StepResult(seq=s.seq, action=s.action, target=s.target,
                          status="error" if i == fail_at else "ok") for i, s in enumerate(done)]
    pending = [{"action": s.action, "target": s.target, "value": s.value, "phase": "test"}
               for s in steps[len(done):]]
    return Verdict(case_id="flow-f-001", screen_id="product", flow_id="f",
                   verdict=verdict or ("PASS" if fail_at is None else "FAIL"),
                   failure_category=None if verdict == "PASS" else "assertion_mismatch",
                   step_results=results, pending_steps=pending)


def _at(steps, target):
    return next(i for i, s in enumerate(steps) if s.target == target)


def test_화면_순서와_이동_방법을_읽는다():
    route = flow_route(_verdict(_steps()))
    assert route == {"screens": ["signup", "login", "product"],
                     "via": ["로그인하러 가기", ""], "broken": None}


def test_통과한_흐름은_모든_화면이_통과():
    html = _flow_map_html(_verdict(_steps()), NAMES)
    assert html.count("data-state='ok'") == 5
    assert "여기서 끊김" not in html and "data-via='click'" in html and "data-via='url'" in html


def test_눌렀는데_다음_화면에_닿지_않으면_이동이_끊긴다():
    steps = _steps()
    v = _verdict(steps, fail_at=_at(steps, "login 도착"))
    assert flow_route(v)["broken"] == ("edge", 0)
    html = _flow_map_html(v, NAMES)
    assert "<li class='fm-node' data-state='ok'><b>회원가입</b><i>통과</i>" in html
    assert "data-state='broken'><span>'로그인하러 가기' 누름</span><i>여기서 끊김</i>" in html
    assert "<b>로그인</b><i>가지 못함</i>" in html and "<b>상품 등록</b><i>가지 못함</i>" in html


def test_누를_요소를_못_찾아도_이동이_끊긴다():
    steps = _steps()
    v = _verdict(steps, fail_at=_at(steps, "로그인하러 가기"))
    assert flow_route(v)["broken"] == ("edge", 0)


def test_중간_화면의_성공_조건이_틀리면_그_화면이_끊긴다():
    steps = _steps(via=())
    v = _verdict(steps, fail_at=_at(steps, "login 성공"))
    assert flow_route(v)["broken"] == ("node", 1)
    html = _flow_map_html(v, NAMES)
    assert "<b>로그인</b><i>여기서 끊김</i>" in html and "<b>상품 등록</b><i>가지 못함</i>" in html


def test_스텝은_다_지났는데_틀렸으면_마지막_화면이다():
    route = flow_route(_verdict(_steps(), verdict="FAIL"))
    assert route["broken"] == ("node", 2)


def test_흐름이_아니거나_모양이_다르면_지도를_그리지_않는다():
    plain = Verdict(case_id="c", screen_id="signup", verdict="FAIL")
    assert flow_route(plain) is None and _flow_map_html(plain, NAMES) == ""
    odd = Verdict(case_id="c", screen_id="login", flow_id="f", verdict="FAIL",
                  step_results=[StepResult(seq=1, action="click", target="가입하기", status="error")])
    assert flow_route(odd) is None
