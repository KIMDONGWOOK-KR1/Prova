"""전제 스텝은 코드가 만든다 (스펙 §3-2·§3-3). LLM 은 관여하지 않는다."""
import pytest
from prova.models import Precondition, ScreenSpec, SpecDocument, UIElement
from prova.s2_case_generator.precondition import expand_precondition, guard_case

LOGIN = ScreenSpec(
    screen_id="login", screen_name="로그인", url_path="/login",
    elements=[
        UIElement(element_id="email", type="input", label="이메일"),
        UIElement(element_id="password", type="input", label="비밀번호"),
        UIElement(element_id="submit", type="button", label="로그인"),
    ])
PRODUCT = ScreenSpec(
    screen_id="product", screen_name="상품 등록", url_path="/product",
    precondition=Precondition(requires_login=True,
                              account_email="seller@test.com",
                              account_password="Seller1!"))
DOC = SpecDocument(screens=[LOGIN, PRODUCT])


class TestExpand:
    def test_로그인_스텝_네_개를_라벨로_만든다(self):
        steps, warnings = expand_precondition(PRODUCT.precondition, DOC)
        # ActionType 에는 "input" 이 없다 — 텍스트 입력은 "fill" 이다
        # (generator.py 의 _input_step 과 동일한 규칙).
        assert [(s.action, s.target) for s in steps] == [
            ("navigate", "/login"), ("fill", "이메일"),
            ("fill", "비밀번호"), ("click", "로그인")]
        assert steps[1].value == "seller@test.com"
        assert steps[2].value == "Seller1!"
        assert warnings == []

    def test_로그인_화면이_문서에_없으면_스텝_없이_경고한다(self):
        doc = SpecDocument(screens=[PRODUCT])
        steps, warnings = expand_precondition(PRODUCT.precondition, doc)
        assert steps == [] and any("login" in w for w in warnings)


class TestGuard:
    def test_역방향_케이스는_setup_없이_리다이렉트를_기대한다(self):
        case = guard_case(PRODUCT, PRODUCT.precondition, DOC, seq=16)
        assert case.setup_steps == []
        assert case.case_id == "product-precondition-guard-016"
        assert case.expected.type == "redirect"
        assert case.expected.url_contains == "/login"
        assert [s.action for s in case.steps] == ["navigate"]


class TestGeneratorWiring:
    def test_전제_화면의_모든_케이스에_setup_이_붙는다(self):
        from prova.s2_case_generator.generator import generate_cases
        cases = generate_cases(PRODUCT, doc=DOC)   # 실제 시그니처에 맞춘다
        normal = [c for c in cases if "precondition-guard" not in c.case_id]
        assert normal and all(len(c.setup_steps) == 4 for c in normal)
        guards = [c for c in cases if "precondition-guard" in c.case_id]
        assert len(guards) == 1 and guards[0].setup_steps == []
