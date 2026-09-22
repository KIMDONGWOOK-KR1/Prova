"""테스트 계정·예시 동작 표의 열 제목이 라벨과 조금 달라도 읽고, 못 읽으면 말한다.

## 왜 (2026-09-23 외부 사이트 실측)

공개 연습 사이트용 기획서의 테스트 계정 표를 `사용자 이름 | 비밀번호` 로 적었는데
요소 라벨은 `Username | Password` 였다. 표를 고르는 기준이 '열 제목이 라벨과 글자까지
같다' 여서 두 표가 모두 조용히 빠졌다.

- 테스트 계정 표가 빠지자 정상 케이스는 코드가 지어낸 값(`a1`)을 넣었다. 등록된
  계정이 아니므로 로그인이 실패했고 '기획서와 다름' 으로 보고됐다 — 오탐.
- 예시 동작 표가 빠지자 사이트가 공개한 음성 시나리오 두 건이 한 건도 만들어지지
  않았다. **경고는 없었다.**

고친 것은 셋이다. 확신할 수 있는 범위만 넓힌다 — 대소문자·공백을 무시하고 요소
ID 로도 맞춘다. `사용자 이름` 과 `Username` 처럼 말이 다른 것은 맞추지 않는다(다른
표를 잘못 읽는다). 대신 그때 무슨 일이 일어나는지를 경고로 알린다.
"""

from __future__ import annotations

from prova.models import ScreenSpec, UIElement
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable
from prova.s2_case_generator.rule_expander import spec_defects

ELEMENTS = ParsedTable(rows=[
    ["요소 ID", "유형", "라벨", "필수", "입력 검증 규칙", "안내 문구", "에러 메시지"],
    ["username", "입력", "Username", "-", "-", "-", "-"],
    ["password", "입력", "Password", "-", "-", "-", "-"],
    ["submit", "버튼", "Submit", "-", "-", "-", "-"],
])


def doc(*tables: ParsedTable) -> ParsedDocument:
    return ParsedDocument(source="x", pages=[ParsedPage(page_no=1, tables=[ELEMENTS, *tables])])


class TestTolerantHeaders:
    def test_대소문자와_공백은_무시한다(self):
        d = doc(ParsedTable(rows=[["user name", "PASSWORD"], ["student", "Password123"]]))
        # 'user name' 은 라벨 'Username' 과 공백만 다르다
        assert d.declared_sample_values() == {"Username": "student", "Password": "Password123"}

    def test_요소_ID_로도_맞춘다(self):
        d = doc(ParsedTable(rows=[["username", "password"], ["student", "Password123"]]))
        assert d.declared_sample_values() == {"Username": "student", "Password": "Password123"}

    def test_말이_다르면_맞추지_않는다(self):
        d = doc(ParsedTable(rows=[["사용자 이름", "비밀번호"], ["student", "Password123"]]))
        assert d.declared_sample_values() == {}

    def test_예시_동작_표도_같은_규칙이다(self):
        d = doc(ParsedTable(rows=[
            ["username", "password", "노출돼야 하는 문구"],
            ["incorrectUser", "Password123", "Your username is invalid!"],
        ]))
        assert d.declared_scenarios() == [{
            "given": {"username": "incorrectUser", "password": "Password123"},
            "expect_text": "Your username is invalid!",
            "expect_count": None, "expect_absent": None,
        }]


class TestUnreadExampleTable:
    def test_기대_문구_열이_있는데_요소와_맞는_열이_없으면_알린다(self):
        d = doc(ParsedTable(rows=[
            ["사용자 이름", "비밀번호", "노출돼야 하는 문구"],
            ["incorrectUser", "Password123", "Your username is invalid!"],
        ]))
        unread = d.unread_example_tables()
        assert unread == ["사용자 이름 | 비밀번호 | 노출돼야 하는 문구"]

    def test_읽은_표는_알리지_않는다(self):
        d = doc(ParsedTable(rows=[
            ["Username", "Password", "노출돼야 하는 문구"],
            ["incorrectUser", "Password123", "Your username is invalid!"],
        ]))
        assert d.unread_example_tables() == []

    def test_기대_문구_열이_없는_표는_예시_표가_아니다(self):
        d = doc(ParsedTable(rows=[["상황", "처리"], ["비밀번호가 틀림", "오류 노출"]]))
        assert d.unread_example_tables() == []


class TestInventedValue:
    def _spec(self, **kw):
        el = dict(element_id="username", type="input", label="Username")
        el.update(kw)
        return ScreenSpec(screen_id="s", screen_name="s", url_path="/",
                          elements=[UIElement(**el)])

    def test_규칙도_예시값도_없는_입력란은_지어낸_값을_쓴다고_알린다(self):
        warnings = spec_defects(self._spec())
        assert any("'Username'" in w and "임의 값" in w for w in warnings), warnings

    def test_예시값이_있으면_조용하다(self):
        assert not any("임의 값" in w for w in spec_defects(self._spec(sample_value="student")))

    def test_규칙으로_만든_값은_지어낸_것이_아니다(self):
        """이메일 형식 규칙이 있으면 user@test.com 을 만든다 — 규칙이 정한 값이다."""
        spec = self._spec(constraints={"format": "email"})
        assert not any("임의 값" in w for w in spec_defects(spec))


def test_못_읽은_예시_표는_설계_문서_경고로_나온다():
    from prova.s1_spec_extractor.extractor import structural_warnings

    d = doc(ParsedTable(rows=[
        ["사용자 이름", "비밀번호", "노출돼야 하는 문구"],
        ["incorrectUser", "Password123", "Your username is invalid!"],
    ]))
    spec = ScreenSpec(screen_id="s", screen_name="s", url_path="/", elements=[
        UIElement(element_id="username", type="input", label="Username"),
        UIElement(element_id="password", type="input", label="Password"),
        UIElement(element_id="submit", type="button", label="Submit"),
    ])
    warnings = structural_warnings(spec, d)
    assert any("사용자 이름 | 비밀번호 | 노출돼야 하는 문구" in w and "시나리오를 만들지" in w
               for w in warnings), warnings
