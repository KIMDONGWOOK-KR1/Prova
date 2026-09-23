"""방문 예약 화면 — 날짜 요소가 **필수**인 첫 화면, 그리고 아이콘 종류를 가르는 화면.

## 이 화면이 새로 확인하는 것 둘

### 1) 필수 선택 요소가 **둘** 인 화면

지금까지 필수 선택(select) 요소는 화면마다 하나뿐이었다(회원가입의 가입 경로,
문의하기의 문의 유형). 둘이면 **순서**가 드러난다 — 앞의 것이 비었을 때 뒤의
문구가 뜨면 기획서와 다르고, 고칠 곳을 사람이 잘못 찾는다.

> 처음에는 방문 날짜를 `date` 유형으로 썼다가 **도구의 한계를 만났다.**
> `models.py` 가 적어 둔 대로 date 요소는 값을 자동으로 채우지 않는다 —
> `input[type=date]` 는 ISO 날짜만 받아 견본값이 통하지 않아서다. 그래서 필수
> 날짜가 있는 기획서는 정상 케이스가 값을 비운 채 제출해 통과할 수 없다.
> 이 픽스처는 선택 목록으로 돌아갔고, 그 한계는 `docs/lessons.md` 에 남겼다.

### 2) 아이콘의 종류 — 이모지 vs SVG

`icons` 변형은 이모지(👤✉)를 쓰고 `svgicons` 변형은 인라인 SVG 를 쓴다.
**둘은 2차 경로 입장에서 다르다.**

    이모지  글꼴 안의 그림이다. 색과 모양이 표준적이고 어느 앱에서나 같다.
    SVG     직접 그린 선이다. 앱마다 다르고, 실물 웹사이트가 쓰는 모양이다.

1차 경로에는 차이가 없어야 한다 — 둘 다 접근성 이름이 없으니 똑같이 못 찾는다.
그 '똑같음' 을 여기서 못 박아 둔다. 그래야 나중에 2차 경로를 켰을 때 생기는
차이가 **아이콘 종류 때문이라고 말할 수 있다.** 1차에서 이미 달랐다면 그 비교는
성립하지 않는다.

## 심어 둔 결함

    K1  인원수 숫자 검증 없음        자릿수는 보면서 숫자 여부를 안 본다
    K2  방문 시간 선택 목록에서 한 항목 누락
    K3  예약 문구가 기획서와 다름
"""

from __future__ import annotations

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/booking_spec.pdf"


def _run(variant: str, sut_base: str, tmp_path):
    report, _ = run_pipeline(
        pdf_path=SPEC_PDF,
        base_url=f"{sut_base}/{variant}",
        llm=MockLLM.for_spec(SPEC_PDF),
        run_id=f"test-booking-{variant}",
        runs_root=tmp_path,
    )
    return report


@pytest.fixture(scope="module")
def good_run(sut_base, tmp_path_factory):
    return _run("good", sut_base, tmp_path_factory.mktemp("booking-good"))


@pytest.fixture(scope="module")
def bad_run(sut_base, tmp_path_factory):
    return _run("bad", sut_base, tmp_path_factory.mktemp("booking-bad"))


@pytest.fixture(scope="module")
def icons_run(sut_base, tmp_path_factory):
    return _run("icons", sut_base, tmp_path_factory.mktemp("booking-icons"))


@pytest.fixture(scope="module")
def svgicons_run(sut_base, tmp_path_factory):
    return _run("svgicons", sut_base, tmp_path_factory.mktemp("booking-svg"))


class TestTwoRequiredSelects:
    """이 화면을 만든 이유 하나. 필수 선택 요소가 둘인 화면이 없었다."""

    def test_선택_요소마다_필수_케이스가_생긴다(self, good_run):
        made = {v.target_element for v in good_run.cases if v.violates == "required"}
        assert {"visit_date", "visit_time"} <= made, (
            "선택 요소의 required 케이스가 빠졌다: " + str(sorted(made))
        )

    def test_요소별_문구를_기대한다(self, good_run):
        """공통 문구('필수 입력 항목입니다.')가 아니라 기획서가 그 요소에 적은
        문구를 본다. 공통 문구로 뭉개면 어느 칸이 비었는지 화면이 말하지 않는다."""
        v = next(v for v in good_run.cases
                 if v.violates == "required" and v.target_element == "visit_date")
        assert "방문 날짜를 선택하세요." in v.evidence["expected"]

    def test_정상_케이스가_둘_다_고른다(self, good_run):
        v = next(v for v in good_run.cases if v.case_id.endswith("valid-001"))
        picked = {s.target: s.value for s in v.step_results if s.action == "select"}
        assert picked.get("방문 날짜") and picked.get("방문 시간"), picked


class TestGoodVariant:
    def test_전_케이스_통과(self, good_run):
        failures = [v for v in good_run.cases if v.verdict == "FAIL"]
        assert not failures, (
            "기획서 준수 구현에서 실패가 났다 — 오탐이다:\n"
            + "\n".join(f"  {v.title}: {v.failure_detail}" for v in failures)
        )

    def test_선택_항목에는_필수_케이스를_만들지_않는다(self, good_run):
        """요청사항은 임의 항목이다 (배송지 화면과 같은 규칙)."""
        wrong = [v.case_id for v in good_run.cases
                 if v.violates == "required" and v.target_element == "memo"]
        assert not wrong, wrong


class TestBadVariant:
    def test_심은_결함만_잡는다(self, bad_run):
        rules = {v.violates for v in bad_run.cases if v.verdict == "FAIL" and v.violates}
        assert rules == {"numeric"}, (
            "K1(숫자)만 규칙 위반으로 잡혀야 한다: " + str(sorted(rules))
        )

    def test_어느_목록이_빠졌는지_가른다(self, bad_run):
        """선택 요소가 둘이라 목록 케이스도 둘이다. 빠진 쪽만 FAIL 이어야
        개발자가 고칠 곳을 바로 안다 — 둘을 묶으면 어느 목록인지 모른다."""
        by_el = {v.target_element: v.verdict
                 for v in bad_run.cases if "-options-" in v.case_id}
        assert by_el == {"visit_date": "PASS", "visit_time": "FAIL"}, by_el

    def test_자릿수는_구현돼_있어_통과한다(self, bad_run):
        """인원수에 numeric 과 자릿수가 함께 걸려 있고 numeric 만 빠졌다.

        min_length=1 은 케이스가 생기지 않는다 — 1자 미만은 '비어 있음' 이고
        그건 required 케이스가 이미 본다. 같은 입력을 두 케이스가 보면 어느
        규칙이 빠졌는지 판정이 갈리지 않는다."""
        made = {v.violates for v in bad_run.cases if v.target_element == "people"}
        assert made == {"required", "numeric", "max_length"}, sorted(made)
        v = next(v for v in bad_run.cases
                 if v.violates == "max_length" and v.target_element == "people")
        assert v.verdict == "PASS", "인원수 최대 자릿수는 bad 에도 구현돼 있다"


class TestIconKinds:
    """이 화면을 만든 이유 둘. 1차 경로에는 아이콘 종류의 차이가 없어야 한다."""

    def test_이모지도_SVG도_1차로는_못_찾는다(self, icons_run, svgicons_run):
        assert icons_run.summary["pass"] == 0
        assert svgicons_run.summary["pass"] == 0

    def test_두_변형의_판정이_같다(self, icons_run, svgicons_run):
        """여기서 이미 다르면, 2차 경로를 켠 뒤의 차이를 아이콘 종류 탓으로
        돌릴 수 없다 — 비교의 전제가 깨진다."""
        a = {v.case_id: v.verdict for v in icons_run.cases}
        b = {v.case_id: v.verdict for v in svgicons_run.cases}
        assert a == b

    def test_검증_로직은_good_과_같다(self, icons_run, svgicons_run, good_run):
        for run in (icons_run, svgicons_run):
            assert run.summary["total"] == good_run.summary["total"]
