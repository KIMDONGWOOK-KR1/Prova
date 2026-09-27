"""요소마다 필수 문구가 따로 있을 때 — 2-1 절에서 코드가 읽는다.

## 왜 (2026-09-23 외부 사이트 실측, parabank 회원가입)

Confirm 칸 하나에 문구가 둘이다 — 비었을 때 "Password confirmation is required.",
다를 때 "Passwords did not match.". 요소에는 error_message 자리가 하나뿐이라 뒤의
것만 담겼고, 화면 공통 필수 문구가 없자 필수 케이스가 **일치 검증 문구를 빌려 썼다.**
사이트는 옳은 문구를 냈는데 FAIL — 오탐이다.

1. 규칙이 있는 요소는 에러 문구를 필수 케이스에 빌려 쓰지 않는다. 모르면 격하.
2. 2-1 절의 '비어 있으면 "…"' 을 코드가 읽어 요소의 required_message 로 둔다.
   LLM 스키마에는 넣지 않는다 — 표·본문에 그대로 적힌 사실은 코드가 읽는다.
"""

from __future__ import annotations

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.extractor import (
    _apply_declared_element_required,
    _apply_declared_required_message,
)
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable
from prova.s2_case_generator.generator import generate_cases

ELEMENT_TABLE = [
    ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
    ["password", "입력", "Password", "필수", "-", "-", "Password is required."],
    ["confirm", "입력", "Confirm", "필수", "Password 와 같아야 함", "-",
     "Passwords did not match."],
    ["agree", "체크박스", "약관 동의", "필수", "-", "-", "-"],
    ["register_btn", "버튼", "Register", "-", "-", "-", "-"],
]

# 실물 PDF 에서 읽힌 모양 그대로다 — 굵은 라벨은 한 줄, 규칙은 '•' 글머리.
LINES = [
    ("2. UI 요소 정의", 100.0),
    ("2-1. 입력 검증 규칙 상세", 300.0),
    ("Confirm", 320.0),
    ('• 필수 입력이다. 비어 있으면 "Password confirmation is required." 를 노출한다.', 340.0),
    ('• Password 와 같은 값이어야 한다. 다르면 "Passwords did not match." 를 노출한다.', 360.0),
    ("3. 성공 조건", 400.0),
    ('비어 있으면 "섞이면 안 된다." 를 노출한다.', 420.0),
]


def _doc(lines=LINES):
    return ParsedDocument(source="x", pages=[ParsedPage(
        page_no=1, tables=[ParsedTable(rows=ELEMENT_TABLE)], body_lines=list(lines),
    )])


class TestDeclared:
    def test_비었을_때_문구만_읽는다(self):
        assert _doc().declared_element_required_messages() == {
            "Confirm": "Password confirmation is required.",
        }

    def test_줄이_나뉘어도_읽는다(self):
        lines = LINES[:3] + [
            ('• 필수 입력이다. 비어 있으면 "Password confirmation', 340.0),
            ('is required." 를 노출한다.', 350.0),
        ] + LINES[4:]
        assert _doc(lines).declared_element_required_messages() == {
            "Confirm": "Password confirmation is required.",
        }

    def test_선택_체크하지_않으면도_같은_뜻이다(self):
        lines = LINES[:2] + [
            ("약관 동의", 320.0),
            ('• 필수 항목이다. 체크하지 않으면 "약관에 동의해야 합니다." 를 노출한다.', 340.0),
        ] + LINES[5:]
        assert _doc(lines).declared_element_required_messages() == {
            "약관 동의": "약관에 동의해야 합니다.",
        }

    def test_따옴표가_없으면_답하지_않는다(self):
        """우리 픽스처 모양 — '비어 있으면 에러 메시지를 노출한다.' 는 문구가 아니다."""
        lines = LINES[:3] + [
            ("• 필수 입력이다. 비어 있으면 에러 메시지를 노출한다.", 340.0),
        ] + LINES[5:]
        assert _doc(lines).declared_element_required_messages() == {}

    def test_절이_없으면_빈손(self):
        assert _doc(LINES[:1]).declared_element_required_messages() == {}


def _failure_doc(condition: str, message: str, element_rows):
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[
        ParsedTable(rows=[ELEMENT_TABLE[0], *element_rows]),
        ParsedTable(rows=[["상황", "처리"], [condition, f'"{message}" 노출']]),
    ])])


USERNAME = ["username", "입력", "Username", "필수", "-", "-", "-"]
PASSWORD = ["password", "입력", "Password", "필수", "-", "-", "-"]
QUERY = ["query", "입력", "검색어", "필수", "-", "-", "-"]


class TestFailureTableRow:
    """실패 조건 표의 '비어 있음' 한 행 — 화면 공통인가, 한 칸의 것인가 (saucedemo, 2026-09-27)."""

    def test_일반_문장은_화면_공통이다(self):
        d = _failure_doc("필수 입력값이 비어 있음", "필수 입력 항목입니다.", [USERNAME, PASSWORD])
        assert d.declared_required_message() == "필수 입력 항목입니다."
        assert d.unresolved_required_rows() == []

    def test_라벨을_가리키면_그_요소의_문구다(self):
        d = _failure_doc("Username 이 비어 있음", "Username is required", [USERNAME, PASSWORD])
        assert d.declared_required_message() is None
        assert d.declared_element_required_messages() == {"Username": "Username is required"}

    def test_필수_입력이_하나뿐이면_화면_공통이어도_같다(self):
        """검색어 화면 — 가리킬 수 있는 칸이 하나뿐이다."""
        d = _failure_doc("사용자 입력이 비었음", "검색어를 입력하세요.", [QUERY])
        assert d.declared_required_message() == "검색어를 입력하세요."

    def test_어느_칸인지_모르면_쓰지_않고_알린다(self):
        """'사용자 이름' 은 'Username' 이 아니다 — 추측하면 Password 에도 붙어 오탐이 났다."""
        d = _failure_doc("사용자 이름이 비어 있음", "Epic sadface: Username is required",
                         [USERNAME, PASSWORD])
        assert d.declared_required_message() is None
        assert d.declared_element_required_messages() == {}
        assert d.unresolved_required_rows() == [
            ("사용자 이름이 비어 있음", "Epic sadface: Username is required")]

    def test_모델이_그_문구를_화면_공통으로_내도_지운다(self):
        """파서가 답을 안 하면 모델 값이 남는다 — 같은 오탐이 모델 쪽으로 돌아온다."""
        d = _failure_doc("사용자 이름이 비어 있음", "Epic sadface: Username is required",
                         [USERNAME, PASSWORD])
        spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/",
                          required_message="Epic sadface: Username is required")
        _apply_declared_required_message(spec, d.declared_required_message(),
                                         d.unresolved_required_rows())
        assert spec.required_message is None
        assert any("사용자 이름이 비어 있음" in w for w in spec.warnings)


class TestApply:
    def test_기획서_값으로_채우고_없으면_비운다(self):
        spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/s", elements=[
            UIElement(element_id="confirm", type="input", label="Confirm", required=True),
            UIElement(element_id="password", type="input", label="Password",
                      required=True, required_message="모델이 지어냄"),
        ])
        _apply_declared_element_required(spec, {"Confirm": "Password confirmation is required."})
        assert spec.elements[0].required_message == "Password confirmation is required."
        assert spec.elements[1].required_message is None

    def test_LLM_스키마에는_없다(self):
        """모델이 채울 자리를 주지 않는다 — 7B 출력 모양도 그대로 둔다."""
        schema = ScreenSpec.model_json_schema()
        assert "required_message" not in schema["$defs"]["UIElement"]["properties"]


def _spec(required_message=None, confirm_required=None):
    return ScreenSpec(
        screen_id="reg", screen_name="회원가입", url_path="/register",
        required_message=required_message,
        elements=[
            UIElement(element_id="password", type="input", label="Password", required=True,
                      error_message="Password is required."),
            UIElement(element_id="confirm", type="input", label="Confirm", required=True,
                      constraints={"same_as": "password"},
                      error_message="Passwords did not match.",
                      required_message=confirm_required),
            UIElement(element_id="btn", type="button", label="Register"),
        ],
    )


def _confirm_required(spec):
    return next(c for c in generate_cases(spec)
                if c.violates == "required" and c.target_element == "confirm")


class TestExpectation:
    def test_요소_필수_문구가_가장_먼저다(self):
        case = _confirm_required(_spec("공통 문구", "Password confirmation is required."))
        assert case.expected.value == "Password confirmation is required."

    def test_일치_검증_문구를_필수에_빌려_쓰지_않는다(self):
        """parabank 오탐 — 모르면 '에러가 떴는가' 로 격하한다."""
        case = _confirm_required(_spec())
        assert case.expected.type == "error_shown"
        assert case.expected.value == ""

    def test_일치_위반은_여전히_에러_문구를_쓴다(self):
        case = next(c for c in generate_cases(_spec(confirm_required="x"))
                    if c.violates == "same_as")
        assert case.expected.value == "Passwords did not match."
