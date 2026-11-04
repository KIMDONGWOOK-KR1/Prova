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


class TestQueryPlaceholder:
    """2026-11-04: 쿼리의 자리표시자(`/search?q={keyword}`)는 경로 조각만 보던 검사를 빠져나갔다.
    글자 그대로 열면 '{keyword}' 로 검색한 화면에서 요소를 찾는다."""

    @pytest.mark.parametrize("path", ["/search?q={keyword}", "/s?page=1&q=:term",
                                      "/s?q=[term]"])
    def test_쿼리_값_자리표시자를_알아본다(self, path):
        assert has_placeholder(path)

    @pytest.mark.parametrize("path", ["/search?q=dog", "/search?q=a:b", "/s?q={a}x"])
    def test_보통_쿼리값은_아니다(self, path):
        assert not has_placeholder(path)

    def test_예시_경로로_채운다(self):
        assert entry_path(_spec("/search?q={keyword}", "/search?q=dog")) == "/search?q=dog"

    def test_예시가_없으면_그_쿼리만_빼고_연다(self):
        # 2026-11-04 0051 A: '/dashboard?tab={tab}&period={period}' 처럼 필터용 선택 값이다.
        # 열지 않으면 그 화면의 케이스 전부가 확인 불가가 된다(65건). 값을 빼면 기본 화면이다.
        assert entry_path(_spec("/search?q={keyword}&type={type}")) == "/search"
        assert entry_path(_spec("/s?q={keyword}&sort=new")) == "/s?sort=new"

    def test_예시에_그_쿼리가_없으면_예시를_쓰지_않는다(self):
        assert entry_path(_spec("/search?q={keyword}", "/search?x=1")) == "/search"

    def test_경로_조각_자리표시자는_빼지_않는다(self):
        assert entry_path(_spec("/topics/{id}?page={page}")) == "/topics/{id}?page={page}"

    def test_도착_확인은_경로까지만_본다(self):
        # '/search/' 를 찾으면 /search?q=dog 에 제대로 와도 '기획서와 다름' 이다.
        assert arrival_fragment("/search?q={keyword}") == "/search"


class TestSeveralPaths:
    """2026-11-04 0051 B: 경로 칸에 '/reviews/new, /reviews/new?itemId={itemId}' 처럼 경로가
    여럿이면 아예 열지 않았다. 모두 경로이면 자리표시자 없는 첫 경로로 연다."""

    def test_깨끗한_첫_경로로_연다(self):
        spec = _spec("/reviews/new, /reviews/new?itemId={itemId}")
        assert entry_path(spec) == "/reviews/new"

    def test_자리표시자_없는_경로를_먼저_고른다(self):
        assert entry_path(_spec("/items/:id, /items")) == "/items"

    def test_모두_자리표시자면_예시가_맞는_것으로(self):
        assert entry_path(_spec("/a/:id, /b/:id", "/b/7")) == "/b/7"

    def test_모두_자리표시자이고_예시가_없으면_열지_못하는_값이다(self):
        from prova.route_params import is_route
        target = entry_path(_spec("/a/:id, /b/:id"))
        assert has_placeholder(target) or not is_route(target)

    def test_세미콜론_뒤는_설명이다(self):
        # 0094 A: '/jobs; 예: /jobs?type=full-time&city=...' 를 통째로 열지 않아 30건이 확인 불가.
        assert entry_path(_spec("/jobs; 예: /jobs?type=full-time&page=1")) == "/jobs"
        assert entry_path(_spec("/jobs/compare?ids=j101,j104; 2~4 개 ID 를 쉼표 구분")) \
            == "/jobs/compare?ids=j101,j104"

    def test_및_도_경로를_나눈다(self):
        assert entry_path(_spec("/ 및 /?type={type}&page={page}")) == "/"

    def test_등호_주변_공백을_지운다(self):
        # S1 이 옮기며 넣은 공백('chart ={chart}', '& page=').
        assert entry_path(_spec("/dashboard?tab={tab}&chart ={chart}& page= {page}")) \
            == "/dashboard"

    def test_세미콜론_앞이_문장이면_그대로다(self):
        url = "마지막 성공한 검색 URL 뒤 #save-search; 예: /jobs?type=a"
        assert entry_path(_spec(url)) == url

    @pytest.mark.parametrize("url_path", ["모든 서비스 경로에 공통 적용",
                                          "새 작성 /topics/new, 수정 /topics/1/edit"])
    def test_문장은_그대로_둔다(self, url_path):
        # 문장 안의 경로를 골라 열면 기획서가 그 화면이라고 하지 않은 곳일 수 있다.
        assert entry_path(_spec(url_path)) == url_path

    def test_도착_확인은_모든_경로에_맞는_앞부분이다(self):
        frag = arrival_fragment("/reviews/new, /reviews/new?itemId={itemId}")
        assert frag == "/reviews/new"
        frag = arrival_fragment("/items, /search?q={keyword}")
        for url in ("/items", "/search?q=dog"):
            assert frag in url


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

    def test_경로가_아닌_문장은_열지_않고_확인_불가다(self, page, tmp_path):
        # 2026-11-04 0051 B: 공통 화면의 경로 칸이 '모든 서비스 경로에 공통 적용'. 그 문장을 주소로
        # 열자 앱이 '없는 페이지' 를 그렸고, 헤더의 'Write Review' 가 없다는 오탐이 났다.
        page.set_content("<p>start</p>")
        before = page.url
        ctx = ExecutionContext(page=page, base_url="http://127.0.0.1:1", specs=[],
                               run_dir=tmp_path, case_id="c", screenshot_every_step=False)
        result = execute_step(ctx, TestStep(seq=1, action="navigate",
                                            target="모든 서비스 경로에 공통 적용"))
        assert result.error_code == "unverifiable"
        assert "경로" in (result.error_detail or "")
        assert page.url == before

    @pytest.mark.parametrize("target", ["/", "/books", "books", "/search?q=x", "http://h:1/a",
                                        "/compare?ids=a,b"])
    def test_경로_모양이면_경로다(self, target):
        # 'books' 처럼 앞 슬래시가 없는 상대 경로도 기준 주소에 붙여 연다(_resolve_url).
        from prova.route_params import is_route
        assert is_route(target)

    @pytest.mark.parametrize("target", ["모든 서비스 경로에 공통 적용", "/a, /b", "/a,/b",
                                        "새 작성 /topics/new", "https://h/a b", ""])
    def test_문장이나_여러_경로는_경로가_아니다(self, target):
        from prova.route_params import is_route
        assert not is_route(target)

    def test_쿼리_자리표시자도_열지_않는다(self, page, tmp_path):
        page.set_content("<p>start</p>")
        before = page.url
        ctx = ExecutionContext(page=page, base_url="http://127.0.0.1:1", specs=[],
                               run_dir=tmp_path, case_id="c", screenshot_every_step=False)
        result = execute_step(ctx, TestStep(seq=1, action="navigate",
                                            target="/search?q={keyword}"))
        assert result.error_code == "unverifiable"
        assert page.url == before

    def test_판정도_확인_불가다(self):
        case = TestCase(case_id="c", screen_id="s", title="t", type="positive",
                        steps=[TestStep(seq=1, action="navigate", target="/pets/:petId")],
                        expected=Expectation(type="toast_or_redirect", value="ok"))
        steps = [StepResult(seq=1, action="navigate", target="/pets/:petId", status="error",
                            error_code="unverifiable", error_detail="자리표시자")]
        v = verify(case, steps, PageState(url="about:blank", text=""))
        assert v.failure_category == "unverifiable"
