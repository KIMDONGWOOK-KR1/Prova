"""이메일이 아닌 아이디로 로그인하는 화면의 전제 (2026-09-28, 스파이크 3 saucedemo).

saucedemo 상품 목록 기획서의 전제가 **경고 없이** 빠졌다. 세 군데가 이메일 로그인에
묶여 있었다 — 계정 표 머리글이 정확히 '이메일|비밀번호', 로그인 화면 ID 가 'login',
아이디 칸을 '이메일' 낱말·형식으로만 찾았다. 넓히되 **후보가 정확히 하나일 때만** —
틀린 칸에 값을 넣고 '전제 실패' 로 보고하면 원인이 숨는다.
"""

from __future__ import annotations

from prova.models import Precondition, ScreenSpec, SpecDocument, UIElement
from prova.s1_spec_extractor.extractor import _apply_declared_precondition
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable
from prova.s2_case_generator.precondition import expand_precondition, guard_case

SD_LOGIN = ScreenSpec(
    screen_id="sd_login", screen_name="로그인", url_path="/",
    elements=[UIElement(element_id="username", type="input", label="Username"),
              UIElement(element_id="password", type="input", label="Password"),
              UIElement(element_id="login_btn", type="button", label="Login")])
PRE = Precondition(requires_login=True, account_email="standard_user",
                   account_password="secret_sauce")
INVENTORY = ScreenSpec(screen_id="sd_inventory", screen_name="상품 목록",
                       url_path="/inventory.html", precondition=PRE)


class TestAccountTable:
    def _doc(self, header):
        return ParsedDocument(source="x", pages=[ParsedPage(
            page_no=1, body_lines=[("4. 전제", 10.0)],
            tables=[ParsedTable(rows=[header, ["standard_user", "secret_sauce"]], top=30.0)])])

    def test_아이디_비밀번호_머리글도_계정_표다(self):
        table = self._doc(["Username", "Password"]).declared_precondition_account()
        spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/s")
        _apply_declared_precondition(spec, table)
        assert spec.precondition.account_email == "standard_user"
        assert spec.precondition.account_password == "secret_sauce"

    def test_둘째_열이_비밀번호가_아니면_계정_표가_아니다(self):
        assert self._doc(["상품명", "가격"]).declared_precondition_account() is None


class TestLoginScreen:
    def test_ID_가_login_이_아니어도_비밀번호_칸이_있는_유일한_화면을_쓴다(self):
        steps, warns = expand_precondition(PRE, SpecDocument(screens=[SD_LOGIN, INVENTORY]))
        assert [(s.action, s.target) for s in steps][:4] == [
            ("navigate", "/"), ("fill", "Username"), ("fill", "Password"), ("click", "Login")]
        assert steps[1].value == "standard_user"
        assert warns == []

    def test_가드_케이스도_같은_로그인_화면을_쓴다(self):
        case = guard_case(INVENTORY, PRE, SpecDocument(screens=[SD_LOGIN, INVENTORY]), 1)
        assert case is not None and case.expected.url_contains == "/"

    def test_비밀번호_칸이_있는_화면이_둘이면_고르지_않는다(self):
        other = SD_LOGIN.model_copy(update={"screen_id": "admin_login", "url_path": "/admin"})
        steps, warns = expand_precondition(
            PRE, SpecDocument(screens=[SD_LOGIN, other, INVENTORY]))
        assert steps == [] and warns


def test_전제_스텝은_로그인_화면의_요소_힌트로_찾는다():
    """전제 스텝을 상품 목록 화면의 명세만으로 찾았다. 'Login' 이 버튼이라는 힌트가 없어
    라벨 전략이 <form aria-label="Login"> 을 잡아 눌렀고, 제출이 안 돼 전제가 실패했다
    (saucedemo, 2026-09-28). 우리 SUT 는 마크업이 깔끔해 힌트 없이도 우연히 맞았다."""
    from prova.models import Expectation, TestCase, TestStep
    from prova.nodes import AgentState, _specs_for

    case = TestCase(case_id="c", screen_id="sd_inventory", title="t", type="positive",
                    setup_steps=[TestStep(seq=1, action="click", target="Login")],
                    expected=Expectation(type="error_shown"))
    state = AgentState(pdf_path="", base_url="http://x", run_id="t", run_dir=None,
                       doc=SpecDocument(screens=[SD_LOGIN, INVENTORY]))
    assert [s.screen_id for s in _specs_for(state, case)] == ["sd_inventory", "sd_login"]


class TestIdField:
    def test_아이디_칸이_둘이면_고르지_않는다(self):
        login = SD_LOGIN.model_copy(update={"elements": [
            *SD_LOGIN.elements, UIElement(element_id="company", type="input", label="Company")]})
        steps, warns = expand_precondition(PRE, SpecDocument(screens=[login, INVENTORY]))
        assert steps == [] and any("후보" in w or "입력란" in w for w in warns)
