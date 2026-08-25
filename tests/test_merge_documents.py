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


class TestFlows:
    """흐름 채택 규칙 — 디자인의 prototype 연결이 기획서 성공 조건과 모순일 수
    있다(실물 사례: 가입하기→로그인 vs 성공 조건 /welcome). 그대로 실행하면
    구현이 옳아도 FAIL(오탐)이므로, 어긋남=발견 원칙을 흐름에도 적용한다."""

    def _pdf_signup(self, success="가입이 완료되면 `/welcome` 로 이동한다"):
        return ScreenSpec(
            screen_id="signup", screen_name="회원가입", url_path="/signup",
            success_condition=success,
            elements=[
                UIElement(element_id="submit", type="button", label="가입하기"),
                UIElement(element_id="to_login", type="link", label="로그인하러 가기"),
            ],
        )

    def _figma_flow(self, via_node="가입하기"):
        return Flow(flow_id="회원가입_to_로그인",
                    screen_ids=["회원가입", "로그인"], via=[via_node])

    def _merge(self, pdf_flows=(), figma_flows=(), success=None):
        pdf_screens = [self._pdf_signup(**({"success": success} if success else {})),
                       pdf_login()]
        figma_screens = [
            ScreenSpec(
                screen_id="회원가입", screen_name="회원가입", url_path="",
                source_kind="figma",
                elements=[
                    UIElement(element_id="n2_1", type="button", label="가입하기"),
                    UIElement(element_id="n2_2", type="link", label="로그인하러 가기"),
                ],
            ),
            figma_login(),
        ]
        return merge_documents(*docs(pdf_screens, figma_screens,
                                     pdf_flows=pdf_flows, figma_flows=figma_flows))

    def test_PDF_흐름은_그대로_남는다(self):
        pdf_flow = Flow(flow_id="signup_then_login",
                        screen_ids=["signup", "login"], via=[])
        merged, _ = self._merge(pdf_flows=[pdf_flow])
        assert any(f.flow_id == "signup_then_login" for f in merged.flows)

    def test_link_via_흐름은_재기입되어_채택된다(self):
        merged, findings = self._merge(
            figma_flows=[self._figma_flow(via_node="로그인하러 가기")])
        adopted = [f for f in merged.flows if f.via == ["로그인하러 가기"]]
        assert adopted and adopted[0].screen_ids == ["signup", "login"]
        assert findings == []

    def test_button_via_가_성공_조건_경로와_어긋나면_발견하고_미채택(self):
        merged, findings = self._merge(figma_flows=[self._figma_flow()])
        assert merged.flows == []
        assert any("가입하기" in f and "/welcome" in f for f in findings)

    def test_button_via_가_성공_조건_경로와_맞으면_채택(self):
        merged, findings = self._merge(
            figma_flows=[Flow(flow_id="회원가입_to_로그인",
                              screen_ids=["회원가입", "로그인"], via=["가입하기"])],
            success="가입이 완료되면 `/login` 으로 이동한다")
        assert [f.via for f in merged.flows] == [["가입하기"]]
        assert findings == []

    def test_성공_조건에_경로가_없으면_판정_불능으로_미채택(self):
        merged, findings = self._merge(
            figma_flows=[self._figma_flow()],
            success="가입이 완료되면 완료 문구를 노출한다")
        assert merged.flows == []
        assert any("확인할 수 없" in f for f in findings)

    def test_같은_흐름이_양쪽에_있으면_한_번만(self):
        pdf_flow = Flow(flow_id="signup_link_to_login",
                        screen_ids=["signup", "login"], via=["로그인하러 가기"])
        merged, _ = self._merge(
            pdf_flows=[pdf_flow],
            figma_flows=[self._figma_flow(via_node="로그인하러 가기")])
        assert len(merged.flows) == 1

    def test_미매칭_화면이_낀_흐름은_발견하고_미채택(self):
        merged, findings = self._merge(
            figma_flows=[Flow(flow_id="회원가입_to_설정",
                              screen_ids=["회원가입", "설정"], via=["설정"])])
        assert merged.flows == []
        assert any("설정" in f for f in findings)

    def test_via_요소가_병합_화면에_없으면_발견하고_미채택(self):
        merged, findings = self._merge(
            figma_flows=[self._figma_flow(via_node="없는 버튼")])
        assert merged.flows == []
        assert any("없는 버튼" in f for f in findings)
