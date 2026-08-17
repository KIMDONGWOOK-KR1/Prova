"""라벨을 못 찾는 화면을 파이프라인이 어떻게 다루는가 — 보정 켠 경우와 끈 경우.

## 이 파일이 지키는 가장 중요한 성질

**보정이 사실을 지우지 않는다.**

2차 경로를 켜면 라벨로 못 찾은 요소도 이미지로 찾아 케이스가 통과한다. 그런데 '기획서의
라벨로 요소를 지목할 수 없다' 는 것은 그 자체로 기획-구현 불일치이면서 접근성 결함이다.
그 사실이 리포트에서 사라지면 보정은 검증을 약화시킨 것이 된다.

그래서 보정을 켜도 라벨 탐지 케이스는 FAIL 로 남아야 한다. 이 파일이 그것을 못 박는다.

## 왜 별도 파일인가

test_vlm_healing.py 는 모듈 범위로 브라우저를 하나 띄워 두고 단위 수준을 확인한다.
run_pipeline 은 자기 sync_playwright() 컨텍스트를 여는데, 같은 스레드에서 겹치면
Playwright 가 거부한다. 그래서 브라우저 픽스처가 없는 이 파일에서 돌린다.

## MockVLM 이 증명하지 않는 것

정확도다. MockVLM 은 CSS selector 로 정답을 실측한다 — '완벽한 VLM' 시뮬레이션이다.
실제 모델이 아이콘만 있는 버튼을 '검색' 으로 알아보는지는 실물 모델로 따로 측정해야 한다.
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/search_spec.pdf"

# 아이콘 버튼의 CSS selector. MockVLM 이 이걸로 위치를 실측한다.
SEARCH_BUTTON_SELECTOR = "button[type=submit]"


def _run(variant: str, sut_base: str, tmp_path, vlm=None, run_id: str = ""):
    return run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        vlm=vlm,
        run_id=run_id or f"test-nolabel-{variant}",
        runs_root=tmp_path,
    )


@pytest.fixture(scope="module")
def report_off(sut_base, tmp_path_factory):
    """보정을 끈 실행. 모듈 범위 — 파이프라인 실행이 비싸다."""
    r, _ = _run("nolabel", sut_base, tmp_path_factory.mktemp("nolabel-off"),
                run_id="test-nolabel-off")
    return r


@pytest.fixture(scope="module")
def report_on(sut_base, tmp_path_factory):
    """보정을 켜고 **실측 좌표**로 돌린 실행."""
    r, _ = _run("nolabel", sut_base, tmp_path_factory.mktemp("nolabel-on"),
                vlm=vlm_for(sut_base), run_id="test-nolabel-on")
    return r


@pytest.fixture(scope="module")
def report_wrong(sut_base, tmp_path_factory):
    """보정을 켜고 **버튼을 비켜 가는 좌표**로 돌린 실행 (폼 안 빈 여백)."""
    r, _ = _run("nolabel", sut_base, tmp_path_factory.mktemp("nolabel-wrong"),
                vlm=vlm_for(sut_base, bbox=(0.36, 0.235, 0.64, 0.28)),
                run_id="test-nolabel-wrong")
    return r


class TestHealingOff:
    """기본 동작 — 보정은 선택 기능이고 기본은 꺼져 있다."""


    def test_라벨을_못_찾는_화면은_실패한다(self, report_off):
        """통과하면 검증이 무력하다는 뜻이다."""
        failed = [v for v in report_off.cases if v.verdict == "FAIL"]
        assert failed
        assert any(v.failure_category == "element_not_found" for v in failed)

    def test_보정한_케이스가_없다(self, report_off):
        assert report_off.summary["healed"] == 0

    def test_라벨_탐지_케이스가_실패한다(self, report_off):
        case = next(v for v in report_off.cases if "-labels-" in v.case_id)
        assert case.verdict == "FAIL"
        assert "검색" in case.failure_detail


def measure(sut_base: str, path: str, selector: str) -> tuple[float, ...]:
    """화면에서 요소의 상대 좌표를 실측한다 ('완벽한 VLM' 시뮬레이션).

    좌표를 손으로 적지 않는 이유는 겪어서 안다. 어림잡은 값이 버튼을 살짝 비켜 갔고,
    Playwright 는 빈 여백을 조용히 눌렀다. 폼이 제출되지 않았으니 판정은 그것을 구현
    결함으로 읽어 **없는 결함 7건을 보고했다.** 그때 테스트는 통과했다 — 'healed > 0'
    만 봤기 때문이다.

    실측하면 그 위험이 없고, 좌표가 틀렸을 때 도구가 어떻게 행동하는지는
    TestWrongCoordinates 가 따로 확인한다.

    브라우저를 여기서 열고 바로 닫는다. run_pipeline 이 자기 sync_playwright()
    컨텍스트를 열므로 겹쳐 두면 Playwright 가 거부한다.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{sut_base}{path}")
        box = page.locator(selector).bounding_box()
        browser.close()
    w, h = 1280, 800
    return (box["x"] / w, box["y"] / h,
            (box["x"] + box["width"]) / w, (box["y"] + box["height"]) / h)


def vlm_for(sut_base: str, bbox=None):
    from prova.vlm.mock_backend import MockVLM

    vlm = MockVLM()
    vlm.register("검색", bbox or measure(sut_base, "/nolabel/search",
                                        SEARCH_BUTTON_SELECTOR))
    return vlm


class TestHealingOn:
    """보정을 켜면 케이스가 살아난다 — 그리고 지적은 남는다."""


    def test_보정한_케이스가_있다(self, report_on):
        assert report_on.summary["healed"] > 0, (
            "보정이 한 번도 일어나지 않았다면 이 파일은 아무것도 확인하지 않는다"
        )

    def test_기능_검증이_good과_같아진다(self, report_on):
        """**이게 보정의 목적이다.** nolabel 은 검증 로직이 good 과 완전히 같고
        버튼 마크업만 다르다. 보정이 제대로 되면 기능 판정도 good 과 같아야 한다 —
        유일한 FAIL 은 라벨 탐지 케이스뿐이다.

        이 확인이 없으면 '보정했다' 만 보고 넘어가게 된다. 실제로 그렇게 넘어갔고,
        좌표가 버튼을 비켜 가 없는 결함 7건을 보고하고 있었다."""
        failed = [v for v in report_on.cases if v.verdict == "FAIL"]
        assert len(failed) == 1, "\n".join(
            f"  {v.title}: {v.evidence['actual'][:80]}" for v in failed)
        assert "-labels-" in failed[0].case_id

    def test_보정된_케이스는_판정까지_간다(self, report_on):
        healed = [v for v in report_on.cases if v.healed]
        assert healed
        assert all(v.failure_category != "element_not_found" for v in healed)

    def test_보정해도_라벨_탐지는_실패로_남는다(self, report_on):
        """**이 파일의 핵심.** 보정은 케이스를 살리는 장치이고, '기획서의 라벨로
        요소를 지목할 수 없다' 는 지적은 그대로 남아야 한다. 사라지면 보정이
        검증을 약화시킨 것이 된다."""
        case = next(v for v in report_on.cases if "-labels-" in v.case_id)
        assert case.verdict == "FAIL", "보정이 접근성 결함을 지웠다"
        assert case.healed is False, "라벨 탐지 확인 자체는 보정을 쓰지 않는다"

    def test_보정_상한을_넘지_않는다(self, report_on):
        """라벨 연결이 통째로 깨진 화면에서 모든 스텝이 보정되면, 그 케이스는
        '화면을 확인한 것' 이 아니라 '이미지로 조작한 것' 이 된다."""
        for verdict in report_on.cases:
            healed_steps = [r for r in verdict.step_results
                            if r.location and r.location.healed]
            assert len(healed_steps) <= 2, verdict.case_id

    def test_근거에_보정_사실이_남는다(self, report_on):
        """리포트를 읽는 사람이 '이 PASS 는 이미지로 찾아서 나온 것' 을 알아야 한다."""
        healed = next(v for v in report_on.cases if v.healed)
        marks = [r.location.method for r in healed.step_results if r.location]
        assert "vlm" in marks


class TestWrongCoordinates:
    """좌표가 틀렸을 때 — 이 도구가 낼 수 있는 최악의 리포트를 막는다.

    실제로 겪었다. 어림잡은 좌표가 버튼을 살짝 비켜 갔고, Playwright 는 빈 여백을
    조용히 눌렀다. 폼이 제출되지 않았으니 에러 문구도 결과도 나오지 않았고, 판정은
    그것을 구현 결함으로 읽어 **없는 결함 7건을 보고했다.**

    그래서 누르기 전에 그 좌표에 조작할 수 있는 요소가 있는지 본다. 없으면 누르지 않고
    탐지 실패로 되돌린다 — 살릴 수 없는 것을 살린 척하면 그 뒤의 판정이 전부 거짓이 된다.
    """


    def test_없는_결함을_만들어내지_않는다(self, report_wrong):
        """구현 결함(assertion_mismatch)으로 보고하면 개발자가 없는 버그를 찾는다.
        탐지 실패로 보고해야 '도구가 요소를 못 찾았다' 로 읽힌다."""
        fabricated = [v for v in report_wrong.cases
                      if v.verdict == "FAIL" and v.type == "negative"
                      and v.failure_category == "assertion_mismatch"]
        assert not fabricated, "\n".join(
            f"  {v.title}: {v.evidence['actual'][:80]}" for v in fabricated)

    def test_탐지_실패로_보고한다(self, report_wrong):
        failed = [v for v in report_wrong.cases if v.verdict == "FAIL"]
        assert any(v.failure_category == "element_not_found" for v in failed)

    def test_진행하지_못했으므로_healed가_아니다(self, report_wrong):
        """시도만 하고 막힌 것을 healed 로 세면, 리포트가 '이미지로 찾아 진행했다' 고
        말하는데 실제로는 아무것도 진행되지 않은 상태가 된다."""
        assert report_wrong.summary["healed"] == 0

    def test_사유에_좌표를_남긴다(self, report_wrong):
        """개발자가 보정이 어디를 눌렀는지 확인할 수 있어야 한다."""
        failed = next(v for v in report_wrong.cases
                      if v.failure_category == "element_not_found")
        assert "검색" in failed.failure_detail


class TestGoodVariantUnaffected:
    def test_보정을_켜도_good은_그대로다(self, sut_base, tmp_path):
        """보정은 탐지가 실패했을 때만 진입한다. 켜는 것만으로 기존 판정이
        달라지면 그건 확장이 아니라 회귀다."""
        report, _ = _run("good", sut_base, tmp_path, vlm=vlm_for(sut_base),
                         run_id="test-good-vlm")
        assert report.summary["healed"] == 0
        assert report.summary["fail"] == 0
