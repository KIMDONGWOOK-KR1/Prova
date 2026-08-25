"""기획서+Figma 병합 — 어긋남은 판정이 아니라 발견이다 (specs/2026-08-25 2단계).

겹치는 정보가 어긋나면 그 항목을 검증에서 빼고 불일치로 보고한다. 틀린
근거로 판정하는 것보다, 입력끼리의 모순을 사람에게 보이는 것이 먼저다.
"""

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.s1_merge import merge_documents


def pdf_login(**over):
    base = dict(
        screen_id="login", screen_name="로그인", url_path="/login",
        success_condition="`/dashboard` 로 이동하고 \"환영합니다\" 문구를 노출한다",
        elements=[
            UIElement(element_id="email", type="input", label="이메일",
                      placeholder="이메일을 입력하세요",
                      constraints={"format": "email"}),
            UIElement(element_id="login_btn", type="button", label="로그인"),
        ],
    )
    base.update(over)
    return ScreenSpec(**base)


def figma_login(**over):
    base = dict(
        screen_id="로그인", screen_name="로그인", url_path="",
        source_kind="figma",
        elements=[
            UIElement(element_id="n1_3", type="input", label="이메일",
                      placeholder="이메일을 입력하세요"),
            UIElement(element_id="n1_9", type="button", label="로그인"),
        ],
    )
    base.update(over)
    return ScreenSpec(**base)


def docs(pdf_screens, figma_screens, pdf_flows=(), figma_flows=()):
    return (SpecDocument(source="p.pdf", screens=pdf_screens, flows=list(pdf_flows)),
            SpecDocument(source="f.json", screens=figma_screens, flows=list(figma_flows)))


class TestScreens:
    def test_이름이_같으면_기획서_기반으로_병합된다(self):
        merged, findings = merge_documents(*docs([pdf_login()], [figma_login()]))
        screen = merged.screens[0]
        assert screen.screen_id == "login"          # 기획서 정체성 유지
        assert screen.source_kind == "document"     # 규칙이 있으므로 full 생성
        assert screen.elements[0].constraints == {"format": "email"}
        assert findings == []                       # 전부 일치 — 발견 없음

    def test_기획서에만_있는_화면은_그대로_두고_발견(self):
        merged, findings = merge_documents(*docs([pdf_login()], []))
        assert merged.screens[0].screen_id == "login"
        assert any("디자인에 없" in f for f in findings)

    def test_디자인에만_있는_화면은_figma_모드_그대로_발견(self):
        merged, findings = merge_documents(*docs([], [figma_login()]))
        assert merged.screens[0].source_kind == "figma"
        assert any("기획서에 없" in f for f in findings)


class TestElements:
    def test_placeholder_가_어긋나면_검증에서_빼고_발견(self):
        fig = figma_login()
        fig.elements[0].placeholder = "아이디를 입력하세요"
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].elements[0].placeholder is None
        assert any("안내 문구" in f and "이메일을 입력하세요" in f
                   and "아이디를 입력하세요" in f for f in findings)

    def test_placeholder_는_공백_무시_비교다(self):
        fig = figma_login()
        fig.elements[0].placeholder = "이메일을  입력하세요"
        _, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert findings == []

    def test_유형이_어긋나면_기획서_유형을_유지하고_발견(self):
        fig = figma_login()
        fig.elements[1] = UIElement(element_id="n1_9", type="link", label="로그인")
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].element_by_id("login_btn").type == "button"
        assert any("유형" in f for f in findings)

    def test_디자인에만_있는_요소는_추가되고_발견(self):
        fig = figma_login()
        fig.elements.append(UIElement(element_id="n1_20", type="input", label="OTP"))
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].element_by_id("n1_20") is not None
        assert any("OTP" in f and "기획서에 없" in f for f in findings)

    def test_기획서에만_있는_요소는_유지되고_발견(self):
        fig = figma_login()
        fig.elements = fig.elements[:1]  # 로그인 버튼이 디자인에 없다
        merged, findings = merge_documents(*docs([pdf_login()], [fig]))
        assert merged.screens[0].element_by_id("login_btn") is not None
        assert any("로그인" in f and "디자인에 없" in f for f in findings)

    def test_options_가_어긋나면_기획서_것을_유지하고_발견(self):
        pdf = pdf_login()
        pdf.elements.append(UIElement(element_id="path", type="select",
                                      label="가입 경로", options=["검색", "광고"]))
        fig = figma_login()
        fig.elements.append(UIElement(element_id="n1_30", type="select",
                                      label="가입 경로", options=["검색"]))
        merged, findings = merge_documents(*docs([pdf], [fig]))
        assert merged.screens[0].element_by_id("path").options == ["검색", "광고"]
        assert any("선택 항목" in f for f in findings)

    def test_입력_불변이다(self):
        pdf_doc, fig_doc = docs([pdf_login()], [figma_login()])
        before = pdf_doc.model_dump_json()
        merge_documents(pdf_doc, fig_doc)
        assert pdf_doc.model_dump_json() == before
