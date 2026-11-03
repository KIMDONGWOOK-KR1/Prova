"""화면 경로의 자리표시자(`/pets/:petId`)를 글자 그대로 열지 않는다.

## 2026-11-03 WebTestBench 2차 측정에서 잡은 구멍

상세 화면의 경로는 `/pets/:petId` 처럼 자리표시자를 갖는다. Prova 는 그 글자를 그대로
열었고, SPA 는 200 으로 '없는 동물' 화면을 그렸다. 그 화면에서 `Your Name` 칸을 찾다가
**요소 못 찾음** 으로 끝났다 — 0037 B 상세 화면 케이스 전부. 라벨이 틀린 것처럼 보이지만
실제로는 엉뚱한 화면에 있었다.

기획서에는 `예시 경로 | /pets/luna` 가 적혀 있었다. 그 값으로 연다. 값이 없으면 열지 않고
'확인 불가' 로 멈춘다 — 없는 화면에서 찾은 결과는 결함도 통과도 아니다.
"""

from __future__ import annotations

import pytest

from prova.models import ScreenSpec, StepResult, TestCase, TestStep, Expectation
from prova.route_params import arrival_fragment, entry_path, has_placeholder
from prova.s1_spec_extractor.extractor import _extraction_schema, extract_screen_spec
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, ParsedPage, ParsedTable
from prova.s2_case_generator.generator import generate_cases
from prova.s4_executor.playwright_driver import ExecutionContext, execute_step
from prova.s5_verifier.assertion_engine import PageState, verify


def _spec(url_path, example_path=None):
    return ScreenSpec(screen_id="pet_detail", screen_name="상세", url_path=url_path,
                      example_path=example_path)


class TestHasPlaceholder:
    @pytest.mark.parametrize("path", ["/pets/:petId", "/pets/{petId}", "/a/:id/edit",
                                      "/pets/[petId]"])
    def test_자리표시자를_알아본다(self, path):
        assert has_placeholder(path)

    @pytest.mark.parametrize("path", ["/pets", "/", "/pets/luna", "/search?q=a:b",
                                      "https://x.test:8080/a"])
    def test_보통_경로는_아니다(self, path):
        # 쿼리의 ':' 와 호스트의 포트는 자리표시자가 아니다.
        assert not has_placeholder(path)


class TestEntryPath:
    def test_예시_경로로_채운다(self):
        assert entry_path(_spec("/pets/:petId", "/pets/luna")) == "/pets/luna"

    def test_중괄호_자리표시자도_채운다(self):
        assert entry_path(_spec("/jobs/{jobId}/apply", "/jobs/j101/apply")) == "/jobs/j101/apply"

    def test_자리표시자가_없으면_화면_경로_그대로(self):
        assert entry_path(_spec("/pets", "/pets?species=dog")) == "/pets"

    def test_예시가_모양이_다르면_쓰지_않는다(self):
        # 다른 화면의 예시를 잘못 읽었을 수 있다. 맞지 않는 값으로 열면 또 엉뚱한 화면이다.
        assert entry_path(_spec("/pets/:petId", "/favorites")) == "/pets/:petId"

    def test_예시가_없으면_화면_경로_그대로(self):
        assert entry_path(_spec("/pets/:petId")) == "/pets/:petId"


class TestArrivalFragment:
    """흐름의 도착 확인은 주소에 이 글자가 들어 있는지 본다."""

    def test_자리표시자_앞까지만_본다(self):
        # '/pets/:petId' 를 그대로 찾으면 /pets/luna 에 제대로 도착해도 '기획서와 다름'
        # 이 된다 — 오탐이다.
        assert arrival_fragment("/pets/:petId") == "/pets/"
        assert arrival_fragment("/jobs/{id}/apply") == "/jobs/"

    def test_자리표시자가_없으면_경로_그대로(self):
        assert arrival_fragment("/favorites") == "/favorites"


class TestFlowArrival:
    def test_자리표시자_화면에_도착하는_흐름은_앞부분으로_확인한다(self):
        from prova.models import Flow, SpecDocument, UIElement
        from prova.s2_case_generator.generator import generate_flow_cases

        pets = ScreenSpec(screen_id="pets", screen_name="목록", url_path="/pets",
                          elements=[UIElement(element_id="card", type="link", label="Luna")])
        detail = _spec("/pets/:petId", "/pets/luna")
        flow = Flow(flow_id="f", screen_ids=["pets", "pet_detail"], via=["Luna"])
        cases = generate_flow_cases(SpecDocument(screens=[pets, detail], flows=[flow]))
        arrivals = [s.expected.url_contains for c in cases for s in c.steps
                    if s.action == "assert" and s.target.endswith("도착")]
        assert arrivals == ["/pets/"]


def _meta_doc(rows):
    table = ParsedTable(rows=[["항목", "내용"], *rows])
    return ParsedDocument(source="x", pages=[ParsedPage(
        page_no=1, body_lines=[("본문", 10.0)], tables=[table])])


class TestDeclaredExamplePath:
    def test_화면_표의_예시_경로를_읽는다(self):
        doc = _meta_doc([["화면 ID", "pet_detail"], ["화면 경로", "/pets/:petId"],
                         ["예시 경로", "/pets/luna"]])
        assert doc.declared_example_path() == "/pets/luna"

    def test_예시_경로는_화면_경로로_읽히지_않는다(self):
        doc = _meta_doc([["예시 경로", "/pets/luna"], ["화면 경로", "/pets/:petId"]])
        assert doc.declared_screen_meta()["url_path"] == "/pets/:petId"

    def test_없으면_None(self):
        assert _meta_doc([["화면 경로", "/pets"]]).declared_example_path() is None


class _Fixed:
    def complete_json(self, *, system, user, schema, max_tokens=2048, temperature=0.0):
        return {"screen_id": "pet_detail", "screen_name": "상세", "url_path": "/pets/:petId",
                "elements": [], "success_condition": "", "failure_conditions": []}


class TestExtraction:
    def test_S1_이_예시_경로를_코드로_채운다(self):
        doc = _meta_doc([["화면 경로", "/pets/:petId"], ["예시 경로", "/pets/luna"]])
        assert extract_screen_spec(doc, _Fixed()).example_path == "/pets/luna"

    def test_모델에게_보내는_스키마에는_없다(self):
        # 스키마가 바뀌면 캐시가 빗나가고, 모델이 그 값을 지어낼 자리가 생긴다.
        assert "example_path" not in _extraction_schema()["properties"]


class TestGeneratedCases:
    def test_케이스는_예시_경로로_연다(self):
        from prova.models import UIElement

        spec = _spec("/pets/:petId", "/pets/luna")
        spec.elements = [UIElement(element_id="name", type="input", label="Your Name",
                                   required=True, sample_value="Kim")]
        spec.success_condition = "Inquiry sent"
        cases = generate_cases(spec)
        navs = {s.target for c in cases for s in c.steps if s.action == "navigate"}
        assert cases and navs == {"/pets/luna"}


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page()
        browser.close()


class TestFlowDirectEntry:
    def test_주소로_들어가는_흐름도_예시_경로로_연다(self):
        from prova.models import Flow, SpecDocument
        from prova.s2_case_generator.generator import generate_flow_cases

        pets = ScreenSpec(screen_id="pets", screen_name="목록", url_path="/pets")
        detail = _spec("/pets/:petId", "/pets/luna")
        flow = Flow(flow_id="f", screen_ids=["pet_detail", "pets"])
        cases = generate_flow_cases(SpecDocument(screens=[pets, detail], flows=[flow]))
        navs = [s.target for c in cases for s in c.steps if s.action == "navigate"]
        assert navs == ["/pets/luna", "/pets"]


class TestExecutionGuard:
    def test_채우지_못한_자리표시자는_열지_않고_확인_불가다(self, page, tmp_path):
        page.set_content("<p>start</p>")
        before = page.url
        ctx = ExecutionContext(page=page, base_url="http://127.0.0.1:1", specs=[],
                               run_dir=tmp_path, case_id="c", screenshot_every_step=False)
        result = execute_step(ctx, TestStep(seq=1, action="navigate", target="/pets/:petId"))
        assert result.status == "error"
        assert result.error_code == "unverifiable"
        assert "예시 경로" in (result.error_detail or "")
        assert page.url == before  # 열지 않았다

    def test_판정도_확인_불가다(self):
        case = TestCase(case_id="c", screen_id="s", title="t", type="positive",
                        steps=[TestStep(seq=1, action="navigate", target="/pets/:petId")],
                        expected=Expectation(type="toast_or_redirect", value="ok"))
        steps = [StepResult(seq=1, action="navigate", target="/pets/:petId", status="error",
                            error_code="unverifiable", error_detail="자리표시자")]
        v = verify(case, steps, PageState(url="about:blank", text=""))
        assert v.failure_category == "unverifiable"
