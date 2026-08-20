"""S1 의 조용한 실패를 막는 장치들. LLM 없이 검증한다.

## 여기서 지키려는 것

S1 이 요소를 빠뜨리면 리포트에는 '구현 결함' 처럼 보인다. 원인은 추출인데
개발자는 자기 코드를 뒤진다. 특히 **제출 버튼이 빠지면 폼이 제출되지 않아
구현이 옳아도 모든 케이스가 실패로 나온다.** 실측에서 로컬 7B 가 7행 표의 버튼
행을 빠뜨린 일이 있었으므로, 가정이 아니라 관측된 실패다.

프롬프트에 요소 ID 목록을 넣어 예방하고, 그래도 빠지면 경고로 알린다. 예방과
검출을 둘 다 두는 이유는 프롬프트가 모델·버전에 따라 흔들리기 때문이다.
"""

from __future__ import annotations

from prova.models import Precondition, ScreenSpec, UIElement
from prova.s1_spec_extractor.extractor import (
    _apply_declared_precondition,
    _apply_declared_required_message,
    _apply_declared_scenarios,
    _apply_declared_types,
    _document_warnings,
    _normalize_element_ids,
    build_user_prompt,
    structural_warnings,
)
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable


def element_table(*ids: str) -> ParsedDocument:
    rows = [["요소 ID", "유형", "라벨"]] + [[i, "입력", i] for i in ids]
    return ParsedDocument(
        source="x", pages=[ParsedPage(page_no=1, tables=[ParsedTable(rows=rows)])]
    )


def spec_with(*elements: UIElement) -> ScreenSpec:
    return ScreenSpec(screen_id="s", screen_name="화면", url_path="/s",
                      elements=list(elements))


def button(element_id: str = "submit") -> UIElement:
    return UIElement(element_id=element_id, type="button", label="확인")


class TestBuildUserPrompt:
    def test_요소_ID_목록을_프롬프트에_박는다(self):
        """코드가 확실히 아는 사실을 추론에 맡기지 않는다. 표의 몇 번째 열이
        ID 인지는 괘선으로 정해지므로 추론할 여지가 없다."""
        prompt = build_user_prompt("본문", ["email", "password", "login_btn"])
        assert "정확히 3개" in prompt
        assert "email, password, login_btn" in prompt

    def test_목록이_없으면_지시를_넣지_않는다(self):
        """ID 열이 없는 기획서도 있다. 없는 사실을 지어내 지시하면 LLM 이
        존재하지 않는 요소를 만들어 낸다."""
        assert "반드시 지킬 것" not in build_user_prompt("본문", [])
        assert "반드시 지킬 것" not in build_user_prompt("본문", None)


class TestStructuralWarnings:
    def test_표에_있는_요소가_빠지면_경고한다(self):
        doc = element_table("email", "password", "login_btn")
        spec = spec_with(
            UIElement(element_id="email", type="input", label="이메일"),
            button("login_btn"),
        )
        warnings = structural_warnings(spec, doc)
        assert any("password" in w for w in warnings)
        assert any("구현 결함이 아닙니다" in w for w in warnings), (
            "원인이 추출이라는 사실을 알려야 개발자가 자기 코드를 뒤지지 않는다"
        )

    def test_버튼이_없으면_경고한다(self):
        """제출 버튼이 없으면 폼이 제출되지 않아 전 케이스가 실패로 나온다."""
        doc = element_table("email")
        spec = spec_with(UIElement(element_id="email", type="input", label="이메일"))
        assert any("버튼" in w for w in structural_warnings(spec, doc))

    def test_표시_전용_화면은_버튼_경고를_내지_않는다(self):
        """주문조회처럼 입력이 없는 화면에는 제출할 폼이 없다. 2026-08-20
        실모델 관통에서 15/15 통과한 화면에 '모든 케이스가 실패로 나옵니다'
        경고가 떴다 — 사실과 다른 경고는 진짜 경고를 묻는다(늑대 소리)."""
        rows = [["요소 ID", "유형", "라벨"],
                ["order_list", "목록", "주문 목록"],
                ["order_total", "텍스트", "합계"]]
        doc = ParsedDocument(
            source="x",
            pages=[ParsedPage(page_no=1, tables=[ParsedTable(rows=rows)])])
        spec = spec_with(
            UIElement(element_id="order_list", type="list", label="주문 목록"),
            UIElement(element_id="order_total", type="text", label="합계"))
        assert not any("버튼" in w for w in structural_warnings(spec, doc))

    def test_채울_수_있는_요소가_있으면_버튼_경고를_낸다(self):
        """select·checkbox 도 제출이 필요한 폼이다."""
        doc = element_table("agree")
        spec = spec_with(
            UIElement(element_id="agree", type="checkbox", label="약관 동의"))
        assert any("버튼" in w for w in structural_warnings(spec, doc))

    def test_모두_추출되면_경고가_없다(self):
        doc = element_table("email", "login_btn")
        spec = spec_with(
            UIElement(element_id="email", type="input", label="이메일",
                      constraints={"format": "email"}),
            button("login_btn"),
        )
        assert structural_warnings(spec, doc) == []


class TestConstraintsWarning:
    """'규칙이 하나도 추출되지 않았다' 경고 — 표가 답을 아는 경우는 침묵한다.

    2026-08-20 실모델 관통에서 주문조회 화면(규칙 열이 전부 '-')에 'S1 추출
    실패를 의심하세요' 가 떴다. 파서가 표에서 '규칙이 없다' 를 이미 읽을 수
    있는데도 의심하라고 말하면 늑대 소리가 된다.
    """

    def _doc(self, rules_cell: str | None) -> ParsedDocument:
        if rules_cell is None:
            rows = [["요소 ID", "유형", "라벨"], ["a", "입력", "가"]]
        else:
            rows = [["요소 ID", "유형", "라벨", "입력 검증 규칙"],
                    ["a", "입력", "가", rules_cell]]
        return ParsedDocument(
            source="x",
            pages=[ParsedPage(page_no=1, tables=[ParsedTable(rows=rows)])])

    def _spec(self) -> ScreenSpec:
        return spec_with(UIElement(element_id="a", type="input", label="가"),
                         button())

    def test_표가_규칙_없음을_말하면_경고하지_않는다(self):
        warnings = structural_warnings(self._spec(), self._doc("-"))
        assert not any("constraints" in w for w in warnings)

    def test_표에_규칙이_적혀_있는데_비면_경고한다(self):
        warnings = structural_warnings(self._spec(), self._doc("8자 이상"))
        assert any("constraints" in w for w in warnings)

    def test_규칙_열이_없으면_경고한다(self):
        """열이 없으면 표가 '규칙 없음' 을 말해 준 것이 아니다 — 규칙이 본문
        서술에만 있을 수 있으므로 의심을 유지한다."""
        warnings = structural_warnings(self._spec(), self._doc(None))
        assert any("constraints" in w for w in warnings)

    def test_요소_표가_아예_없어도_경고한다(self):
        doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1)])
        warnings = structural_warnings(self._spec(), doc)
        assert any("constraints" in w for w in warnings)

    def test_규칙이_추출됐으면_경고하지_않는다(self):
        spec = spec_with(
            UIElement(element_id="a", type="input", label="가",
                      constraints={"min_length": 8}),
            button())
        warnings = structural_warnings(spec, self._doc("8자 이상"))
        assert not any("constraints" in w for w in warnings)


class TestMissingTable:
    """대조할 표 자체가 없는 기획서의 처리."""

    def test_대조할_표가_없으면_없는_누락을_경고하지_않는다(self):
        """ID 열이 없는 기획서에서 '요소가 빠졌다' 고 하면 안 된다.

        빠진 것이 아니라 대조할 근거가 없는 것이고, 둘은 개발자가 할 일이 다르다.
        """
        doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1)])
        spec = spec_with(UIElement(element_id="email", type="input", label="이메일"),
                         button())
        assert not any("빠진 요소" in w for w in structural_warnings(spec, doc))

    def test_대조할_표가_없다는_사실은_경고한다(self):
        """**이 테스트는 원래 반대를 못 박고 있었다** — 표가 없으면 경고 0건이라고.

        훼손된 기획서로 실측하면서 그 전제가 틀렸음이 드러났다. 열 이름을
        '요소 ID' -> '항목' 으로 바꾸자 표를 못 찾았고, 그러면

            declared_* 여덟 개가 전부 빈손
            _apply_declared_* 들은 조용히 반환 (if not declared: return)
            위의 행 누락 검사도 건너뜀

        이 되어 **LLM 답을 대조할 근거가 하나도 남지 않는다.** 그런데 리포트는
        정상으로 보였다. 그 실행은 우연히 결과가 맞았지만, 틀렸다면 아무것도
        잡지 못했다.

        '검증망이 없다' 는 결과가 맞았을 때도 알려야 하는 사실이다 —
        확인하지 않은 것과 확인해서 통과한 것은 다르다.
        """
        doc = ParsedDocument(source="x", pages=[ParsedPage(page_no=1)])
        spec = spec_with(UIElement(element_id="email", type="input", label="이메일"),
                         button())
        warnings = structural_warnings(spec, doc)
        assert any("UI 요소 정의 표를 찾지 못했습니다" in w for w in warnings)
        assert any("검증이 모두 비활성화" in w for w in warnings)


class TestNormalizeElementIds:
    """실측에서 7B 가 password_confirm 을 'password_confir m' 으로 냈다.

    element_id 는 슬러그라서 공백이 들어갈 여지가 없고, 고칠 방법도 하나뿐이다.
    판정 강도를 낮추는 보정이 아니라 표기 복원이므로 조용히 처리한다.
    """

    def test_ID의_공백을_지운다(self):
        spec = spec_with(
            UIElement(element_id="password_confir m", type="input", label="확인")
        )
        _normalize_element_ids(spec)
        assert spec.elements[0].element_id == "password_confirm"

    def test_same_as_참조도_함께_고친다(self):
        """참조가 어긋나면 교차 필드 위반 케이스가 생성되지 않아, 구현에 일치
        검증이 없어도 조용히 넘어간다."""
        spec = spec_with(
            UIElement(element_id="pass word", type="input", label="비밀번호"),
            UIElement(element_id="confirm", type="input", label="비밀번호 확인",
                      constraints={"same_as": "pass word"}),
        )
        _normalize_element_ids(spec)
        assert spec.elements[0].element_id == "password"
        assert spec.elements[1].constraints["same_as"] == "password"

    def test_정상_ID는_건드리지_않는다(self):
        spec = spec_with(UIElement(element_id="login_btn", type="button", label="로그인"))
        _normalize_element_ids(spec)
        assert spec.elements[0].element_id == "login_btn"


class TestApplyDeclaredTypes:
    """유형은 표에 적힌 사실이므로 LLM 결과를 덮어쓴다.

    다만 _normalize_element_ids 와 달리 경고를 남긴다. 공백 제거는 표기 복원이지만,
    유형이 달랐다는 것은 모델이 표를 잘못 읽었다는 뜻이고 그건 프롬프트가
    나빠지고 있다는 신호다.
    """

    def test_표의_유형으로_맞춘다(self):
        spec = spec_with(UIElement(element_id="r", type="text", label="검색 결과 목록"))
        _apply_declared_types(spec, {"검색 결과 목록": "list"})
        assert spec.elements[0].type == "list"

    def test_바꿨으면_경고를_남긴다(self):
        spec = spec_with(UIElement(element_id="r", type="text", label="검색 결과 목록"))
        _apply_declared_types(spec, {"검색 결과 목록": "list"})
        assert any("검색 결과 목록" in w and "list" in w for w in spec.warnings)

    def test_같으면_경고하지_않는다(self):
        """매 실행마다 뜨는 경고는 정작 중요한 경고를 묻는다."""
        spec = spec_with(UIElement(element_id="e", type="input", label="이메일"))
        _apply_declared_types(spec, {"이메일": "input"})
        assert spec.warnings == []

    def test_표에_없는_라벨은_건드리지_않는다(self):
        spec = spec_with(UIElement(element_id="x", type="input", label="없는 것"))
        _apply_declared_types(spec, {"이메일": "input"})
        assert spec.elements[0].type == "input"
        assert spec.warnings == []


class TestApplyDeclaredScenarios:
    def test_건수까지_표의_값으로_바꾼다(self):
        spec = spec_with(button())
        _apply_declared_scenarios(spec, [
            {"given": {"q": "notebook"}, "expect_text": "검색 결과 3건", "expect_count": 3}])
        assert spec.scenarios[0].expect_count == 3

    def test_값이_같으면_경고하지_않는다(self):
        """표에서 읽은 dict 에 expect_count 키가 없고 모델 쪽에는 None 이 있을 때,
        비교 형태를 맞추지 않으면 값이 같은데도 매 실행마다 경고가 뜬다."""
        from prova.models import Scenario

        spec = spec_with(button())
        spec.scenarios = [Scenario(given={"q": "a"}, expect_text="문구")]
        _apply_declared_scenarios(spec, [{"given": {"q": "a"}, "expect_text": "문구"}])
        assert spec.warnings == []


class TestApplyDeclaredRequiredMessage:
    """필수 입력 문구도 표에 그대로 적혀 있다.

    화면 세 개를 한 문서에 담자 7B 가 검색 화면의 이 값을 few-shot 예시의 문구로
    채웠다. 구현이 올바른 문구를 노출하는데 기대 문구가 달라 FAIL 이 되는 오탐이다.
    """

    def test_표의_문구로_맞춘다(self):
        spec = spec_with(button())
        spec.required_message = "필수 항목을 입력하세요."
        _apply_declared_required_message(spec, "검색어를 입력하세요.")
        assert spec.required_message == "검색어를 입력하세요."

    def test_바꿨으면_경고를_남긴다(self):
        spec = spec_with(button())
        spec.required_message = "필수 항목을 입력하세요."
        _apply_declared_required_message(spec, "검색어를 입력하세요.")
        assert any("필수 입력 문구" in w for w in spec.warnings)

    def test_같으면_경고하지_않는다(self):
        spec = spec_with(button())
        spec.required_message = "검색어를 입력하세요."
        _apply_declared_required_message(spec, "검색어를 입력하세요.")
        assert spec.warnings == []

    def test_판별하지_못하면_손대지_않는다(self):
        """표에서 후보를 하나로 특정하지 못하면 LLM 의 판단을 남긴다."""
        spec = spec_with(button())
        spec.required_message = "모델이 낸 문구"
        _apply_declared_required_message(spec, None)
        assert spec.required_message == "모델이 낸 문구"
        assert spec.warnings == []


class TestPreconditionCorrection:
    """전제 계정은 표가 이긴다 (스펙 §3-1·§8) — 모델이 옮겨 적다 틀려도
    기획서 표의 값으로 덮어쓴다. 옮겨적기 실패는 실측된 실패 모양이다."""

    def test_전제_표의_계정으로_덮어쓴다(self):
        spec = ScreenSpec(screen_id="product", screen_name="상품 등록",
                          url_path="/product",
                          precondition=Precondition(requires_login=True,
                                                    account_email="wrong@x.com",
                                                    account_password="wrong"))
        # '전제' 절의 계정 표 (§5 테스트 계정과 같은 2열 형식)
        table = [["이메일", "비밀번호"], ["seller@test.com", "Seller1!"]]
        _apply_declared_precondition(spec, table)
        assert spec.precondition.account_email == "seller@test.com"
        assert spec.precondition.account_password == "Seller1!"

    def test_경고가_달라진_필드를_모두_밝힌다(self):
        """이메일만 언급하면(과거 버그) 비밀번호가 함께 틀렸다는 사실이
        경고에서 사라진다 — 어느 필드가 달랐는지 둘 다 남겨야 한다."""
        spec = ScreenSpec(screen_id="product", screen_name="상품 등록",
                          url_path="/product",
                          precondition=Precondition(requires_login=True,
                                                    account_email="wrong@x.com",
                                                    account_password="wrong"))
        table = [["이메일", "비밀번호"], ["seller@test.com", "Seller1!"]]
        _apply_declared_precondition(spec, table)
        warning = spec.warnings[0]
        assert "이메일" in warning and "wrong@x.com" in warning and "seller@test.com" in warning
        assert "비밀번호" in warning and "wrong" in warning and "Seller1!" in warning

    def test_이메일만_같으면_비밀번호_차이만_밝힌다(self):
        spec = ScreenSpec(screen_id="product", screen_name="상품 등록",
                          url_path="/product",
                          precondition=Precondition(requires_login=True,
                                                    account_email="seller@test.com",
                                                    account_password="wrong"))
        table = [["이메일", "비밀번호"], ["seller@test.com", "Seller1!"]]
        _apply_declared_precondition(spec, table)
        warning = spec.warnings[0]
        assert "비밀번호" in warning
        assert "이메일" not in warning

    def test_전제_절이_없으면_건드리지_않는다(self):
        spec = ScreenSpec(screen_id="login", screen_name="로그인",
                          url_path="/login")
        _apply_declared_precondition(spec, None)
        assert spec.precondition is None


class TestDocumentWarnings:
    """화면 하나만 봐서는 알 수 없는 어긋남."""

    def doc(self, screens, flows=()):
        from prova.models import SpecDocument

        return SpecDocument(screens=list(screens), flows=list(flows))

    def screen(self, screen_id):
        return ScreenSpec(screen_id=screen_id, screen_name=screen_id,
                          url_path=f"/{screen_id}", elements=[button()])

    def test_화면_ID_중복을_경고한다(self):
        """겹치면 case_id 접두사가 같아져 스크린샷이 서로를 덮어쓴다 — 리포트는
        정상으로 보이는데 증거가 사라진다."""
        doc = self.doc([self.screen("login"), self.screen("login")])
        assert any("중복" in w for w in _document_warnings(doc))

    def test_없는_화면을_가리키는_흐름을_경고한다(self):
        """그 흐름은 케이스가 만들어지지 않는다. 경고가 없으면 검증한 줄 알았는데
        아무것도 확인하지 않은 상태가 된다."""
        from prova.models import Flow

        doc = self.doc([self.screen("login")],
                       [Flow(flow_id="f", screen_ids=["login", "없는화면"])])
        warnings = _document_warnings(doc)
        assert any("없는화면" in w for w in warnings)

    def test_정상_문서에는_경고가_없다(self):
        from prova.models import Flow

        doc = self.doc([self.screen("signup"), self.screen("login")],
                       [Flow(flow_id="f", screen_ids=["signup", "login"])])
        assert _document_warnings(doc) == []


class TestAllWarnings:
    def test_화면이_여럿이면_화면_ID를_붙인다(self):
        """어디를 고쳐야 하는지가 경고의 위치로 드러나야 한다."""
        from prova.models import SpecDocument

        a = ScreenSpec(screen_id="login", screen_name="로그인", url_path="/login",
                       warnings=["문제 하나"])
        b = ScreenSpec(screen_id="signup", screen_name="회원가입", url_path="/signup")
        doc = SpecDocument(screens=[a, b], warnings=["문서 경고"])
        assert doc.all_warnings == ["문서 경고", "[login] 문제 하나"]

    def test_화면이_하나면_접두사를_붙이지_않는다(self):
        """접두사가 매번 붙으면 화면당 PDF 하나인 기존 리포트의 경고 문장이
        괜히 길어진다."""
        from prova.models import SpecDocument

        a = ScreenSpec(screen_id="login", screen_name="로그인", url_path="/login",
                       warnings=["문제 하나"])
        assert SpecDocument(screens=[a]).all_warnings == ["문제 하나"]
