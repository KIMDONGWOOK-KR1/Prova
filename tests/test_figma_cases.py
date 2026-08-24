"""S2 — figma 출처 스펙은 정적 대조 3종만 만든다 (specs/2026-08-25).

figma 스펙에는 성공 조건·검증 규칙·테스트 계정이 없다. 그 근거 없이 valid
케이스를 만들면 임의 값 제출 → 에러 노출 → FAIL, 즉 구현이 옳아도 오탐이다.
흐름 케이스도 같다 — 도착을 판정할 근거(문구·경로)가 없다. 추출은 하되
케이스는 만들지 않는다.
"""

from pathlib import Path

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.nodes import AgentState, generate_test_cases
from prova.s2_case_generator.generator import generate_cases


def figma_login_spec(url_path: str = "/login") -> ScreenSpec:
    return ScreenSpec(
        screen_id="login", screen_name="로그인", url_path=url_path,
        source_kind="figma",
        elements=[
            UIElement(element_id="n1_3", type="input", label="이메일",
                      placeholder="이메일을 입력하세요"),
            UIElement(element_id="n1_6", type="input", label="비밀번호",
                      placeholder="비밀번호를 입력하세요"),
            UIElement(element_id="n1_9", type="button", label="로그인"),
        ],
    )


class TestFigmaCases:
    def test_정적_대조_케이스만_만든다(self):
        cases = generate_cases(figma_login_spec())
        kinds = sorted(c.case_id for c in cases)
        assert kinds == ["login-labels-001", "login-placeholders-001"]

    def test_valid_케이스를_만들지_않는다(self):
        assert not any("-valid-" in c.case_id for c in generate_cases(figma_login_spec()))

    def test_select_가_있으면_options_케이스도_만든다(self):
        spec = figma_login_spec()
        spec.elements.append(UIElement(
            element_id="n2_1", type="select", label="가입 경로",
            options=["검색", "지인 추천", "광고"]))
        cases = generate_cases(spec)
        assert any(c.expected.type == "options_present" for c in cases)

    def test_경로_매핑이_없으면_케이스를_만들지_않는다(self):
        assert generate_cases(figma_login_spec(url_path="")) == []

    def test_figma_문서는_흐름_케이스를_만들지_않는다(self):
        doc = SpecDocument(
            source="fixtures/figma/x.json",
            screens=[figma_login_spec()],
            flows=[Flow(flow_id="signup_to_login", screen_ids=["signup", "login"])],
        )
        state = AgentState(pdf_path="", base_url="", run_id="t",
                           run_dir=Path("."), doc=doc)
        state = generate_test_cases(state)
        assert not any(c.flow_id for c in state.cases)

    def test_document_출처는_기존_그대로다(self):
        spec = figma_login_spec()
        spec.source_kind = "document"
        assert any("-valid-" in c.case_id for c in generate_cases(spec))
