"""흐름 표의 '이동 방법' 칸이 누를 이름이 아닐 때.

## 2026-11-04 WebTestBench 6개 기획서에서 잡은 구멍

흐름의 이동 방법은 도구가 누를 버튼·링크 이름이어야 한다. GPT 가 쓴 기획서는 그 칸에
다른 것을 많이 적었다.

- 주소로 들어간다는 말: `/pets/luna 직접 접속`, `주소로 /pets/pet-1001 진입`
- 일어나는 일이나 여러 동작: `검색 성공`, `사용자 검색 성공`, `입력 후 저장 완료`,
  `저장 성공 후 브라우저 재시작`

도구는 그 글자를 버튼 이름으로 찾았고, 못 찾으면 VLM 까지 불러 화면에서 그 '이름' 을
찾게 했다. 결과는 '요소 못 찾음' — 구현 결함처럼 읽힌다(0094 B 흐름 9건이 '검색 성공'
에서 멈춤). VLM 이 문장과 비슷한 버튼을 골라 누를 위험도 있었다.

## 지키는 것

- 주소로 들어간다는 말에 경로가 있고 그 경로가 다음 화면의 모양이면 그 경로로 연다.
  모양이 다르면 다음 화면의 경로로 연다(이동 방법을 안 적은 흐름과 같다).
- 일어나는 일처럼 보이는 문장도 **먼저 화면에서 그 이름을 정확히 찾는다** — '새로고침'
  '작성 완료' 같은 진짜 버튼일 수 있다. 있으면 누른다. 없을 때만 VLM 을 부르지 않고
  '확인 불가' 로 멈추고 사유를 적는다.
- 버튼 이름처럼 보이는 것(`Save Search`, `검색`)은 그대로다.
"""

from __future__ import annotations

import pytest

from prova.models import Flow, ScreenSpec, SpecDocument, TestStep, UIElement
from prova.s2_case_generator.generator import generate_flow_cases, via_phrase_reason
from prova.s4_executor.playwright_driver import ExecutionContext, execute_step


def _flow_steps(via, dst_path="/pets/:petId", example="/pets/luna"):
    src = ScreenSpec(screen_id="list", screen_name="목록", url_path="/pets",
                     elements=[UIElement(element_id="q", type="input", label="Search")])
    dst = ScreenSpec(screen_id="detail", screen_name="상세", url_path=dst_path,
                     example_path=example)
    flow = Flow(flow_id="f", screen_ids=["list", "detail"], via=[via])
    [case] = generate_flow_cases(SpecDocument(screens=[src, dst], flows=[flow]))
    return case.steps


class TestDirectEntry:
    @pytest.mark.parametrize("via, path", [("/pets/luna 직접 접속", "/pets/luna"),
                                           ("주소로 /pets/pet-1001 진입", "/pets/pet-1001")])
    def test_적힌_경로로_연다(self, via, path):
        steps = _flow_steps(via)
        assert not [s for s in steps if s.action == "click"]
        assert [s.target for s in steps if s.action == "navigate"] == ["/pets", path]

    def test_다음_화면_모양이_아니면_화면_경로로_연다(self):
        steps = _flow_steps("/favorites 직접 접속")
        assert [s.target for s in steps if s.action == "navigate"] == ["/pets", "/pets/luna"]

    def test_경로_없는_직접_접속은_사건이다(self):
        steps = _flow_steps("조건 URL 직접 접속")
        [click] = [s for s in steps if s.action == "click"]
        assert click.via_phrase


class TestPhrase:
    @pytest.mark.parametrize("via", ["검색 성공", "사용자 검색 성공", "조회 실패",
                                     "입력 후 저장 완료", "저장 성공 후 브라우저 재시작",
                                     "승인 이벤트 수신", "zzzz 검색", "job-009 선택"])
    def test_일어나는_일은_사유를_단다(self, via):
        assert via_phrase_reason(via)

    @pytest.mark.parametrize("via", ["Save Search", "검색", "History", "Compare (2)",
                                     "Write a Review", "새로고침", "My Reviews의 More options"])
    def test_이름처럼_보이면_그대로다(self, via):
        assert via_phrase_reason(via) is None

    def test_생성된_클릭_스텝에_사유가_실린다(self):
        steps = _flow_steps("검색 성공")
        [click] = [s for s in steps if s.action == "click"]
        assert click.target == "검색 성공" and click.via_phrase

    def test_이름이면_사유가_없다(self):
        steps = _flow_steps("Save Search")
        [click] = [s for s in steps if s.action == "click"]
        assert click.via_phrase is None


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page()
        browser.close()


class _NeverCalled:
    name = "never"

    def locate(self, **kw):
        raise AssertionError("문장 이동 방법으로 VLM 을 부르면 안 된다")


def _ctx(page, tmp_path):
    return ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                            case_id="flow-f", vlm=_NeverCalled(), screenshot_every_step=False)


class TestExecution:
    def test_없으면_VLM_없이_확인_불가다(self, page, tmp_path):
        page.set_content("<button>Search</button>")
        step = TestStep(seq=1, action="click", target="검색 성공",
                        via_phrase=via_phrase_reason("검색 성공"))
        result = execute_step(_ctx(page, tmp_path), step)
        assert result.error_code == "unverifiable"
        assert "이동 방법" in (result.error_detail or "")

    def test_같은_이름의_버튼이_있으면_누른다(self, page, tmp_path):
        page.set_content("<button onclick=\"this.textContent='done'\">작성 완료</button>")
        step = TestStep(seq=1, action="click", target="작성 완료",
                        via_phrase=via_phrase_reason("작성 완료"))
        assert step.via_phrase
        result = execute_step(_ctx(page, tmp_path), step)
        assert result.status == "ok"
        assert page.locator("button").inner_text() == "done"
