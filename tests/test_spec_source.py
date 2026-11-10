"""기획서 근거 — 케이스의 기대가 기획서 몇 쪽 어느 줄에 적혀 있는지 (2026-11-11).

리포트가 '기획서와 다름' 이라고만 하면, "기획서 어디에 그런 말이 있느냐" 는 물음에 사용자가
PDF 를 다시 뒤져야 한다. 근거는 **모델이 아니라 코드가** 찾는다 — PDF 파서가 가진 표 행·본문
줄을 쪽 번호와 함께 두고 글자 대조로. 못 찾으면 붙이지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prova.models import (
    Expectation, ScreenSpec, SourceLine, SpecDocument, SpecSource, TestCase, Verdict,
)
from prova.s1_spec_extractor.pdf_parser import parse_pdf
from prova.s2_case_generator.generator import generate_cases
from prova.s6_report.report_builder import _case_html
from prova.spec_source import (
    QUOTE_LIMIT, attach_sources, find_element, find_text, index_lines, sources_for_case,
)
from prova.wording import source_sentence

SPEC_DIR = Path("fixtures/specs")


def _spec(stem: str) -> ScreenSpec:
    spec = ScreenSpec.model_validate(
        json.loads((SPEC_DIR / f"{stem}_spec.golden.json").read_text(encoding="utf-8")))
    spec.source_lines = index_lines(parse_pdf(str(SPEC_DIR / f"{stem}_spec.pdf")))
    return spec


@pytest.fixture(scope="module")
def signup() -> ScreenSpec:
    return _spec("signup")


# ── 줄 색인 ──────────────────────────────────────────────────────────────────

def test_표_행과_본문_줄을_쪽_번호와_함께_모은다(signup):
    lines = signup.source_lines
    assert {line.page for line in lines} >= {1, 2}
    row = next(line for line in lines if line.table and line.text.startswith("nickname"))
    assert row.page == 1 and "2자 이상 10자 이하" in row.text
    assert any(not line.table and "가입이 완료되었습니다" in line.text for line in lines)


def test_표_머리글_행은_근거가_아니다(signup):
    assert not any(line.table and line.text.startswith("요소 ID") for line in signup.source_lines)


def test_줄_색인은_모델_스키마에_들어가지_않는다():
    """모델에게 묻지 않는다 — 스키마가 바뀌면 동결한 응답 캐시의 키가 달라진다."""
    assert "source_lines" not in ScreenSpec.model_json_schema()["properties"]


# ── 찾기 ─────────────────────────────────────────────────────────────────────

def test_요소는_식별자나_이름이_칸과_같은_행에서_찾는다(signup):
    by_id = find_element(signup.source_lines, "nickname", None)
    by_label = find_element(signup.source_lines, None, "닉네임")
    assert by_id == by_label and by_id.table and by_id.page == 1


def test_칸_안에서_줄이_바뀐_식별자도_찾는다(signup):
    """PDF 는 좁은 칸에서 'password_con firm' 처럼 끊어 적는다."""
    source = find_element(signup.source_lines, "password_confirm", None)
    assert source is not None and "비밀번호 확인" in source.quote


def test_문구는_줄이_바뀌어_끊겨도_찾는다():
    lines = [SourceLine(page=3, text="모든 규칙을 만족하면 가입이"),
             SourceLine(page=3, text="완료되었습니다 문구를 노출한다.")]
    source = find_text(lines, "가입이 완료되었습니다")
    assert source is not None and source.page == 3
    assert "가입이" in source.quote and "완료되었습니다" in source.quote


def test_짧은_문구와_없는_문구는_근거를_지어내지_않는다(signup):
    assert find_text(signup.source_lines, "확인") is None       # 아무 줄에나 걸리는 낱말
    assert find_text(signup.source_lines, "이 문서에 없는 문구입니다") is None
    assert find_element(signup.source_lines, "no_such_id", "없는 이름") is None


def test_긴_행은_잘라서_보여_준다():
    source = find_text([SourceLine(page=1, text="가나다라마" * 100, table=True)], "가나다라마")
    assert len(source.quote) == QUOTE_LIMIT + 1 and source.quote.endswith("…")


# ── 케이스에 붙이기 ──────────────────────────────────────────────────────────

def test_규칙_위반_케이스는_그_요소의_표_행을_근거로_갖는다(signup):
    case = next(c for c in generate_cases(signup) if c.violates == "max_length")
    sources = sources_for_case(signup, case)
    assert sources and sources[0].table and sources[0].quote.startswith("nickname")
    assert source_sentence(sources[0]).startswith("1쪽 표 — nickname")


def test_필수_케이스는_요소_행과_공통_문구가_적힌_곳을_함께_갖는다(signup):
    case = next(c for c in generate_cases(signup)
                if c.violates == "required" and c.target_element == "email")
    quotes = [s.quote for s in sources_for_case(signup, case)]
    assert len(quotes) == 2
    assert quotes[0].startswith("email") and "필수 입력 항목입니다." in quotes[1]


def test_요소_없는_케이스는_기대_문구가_적힌_줄을_근거로_갖는다(signup):
    case = next(c for c in generate_cases(signup) if c.case_id.startswith("signup-valid"))
    sources = sources_for_case(signup, case)
    assert sources and not sources[0].table and "가입이 완료되었습니다" in sources[0].quote


@pytest.mark.parametrize("stem", ["login", "signup", "search", "find_account", "product",
                                  "orders"])
def test_픽스처_기획서의_케이스_대부분에_근거가_붙는다(stem):
    """근거가 갑자기 사라지는 회귀를 잡는다. 전부를 요구하지는 않는다 — 못 찾으면 안 붙인다."""
    spec = _spec(stem)
    cases = generate_cases(spec)
    missing = [c.case_id for c in cases if not sources_for_case(spec, c)]
    assert len(missing) <= 1, missing


def test_줄_색인이_없으면_근거도_없다():
    """Figma 에서 온 화면, 예전에 저장한 계획 — 지어내지 않는다."""
    spec = ScreenSpec.model_validate(
        json.loads((SPEC_DIR / "signup_spec.golden.json").read_text(encoding="utf-8")))
    cases = generate_cases(spec)
    attach_sources(SpecDocument(screens=[spec]), cases)
    assert all(c.spec_sources == [] for c in cases)


def test_attach_sources_는_화면별_기획서에서_찾는다(signup):
    cases = generate_cases(signup)
    attach_sources(SpecDocument(screens=[signup]), cases)
    assert sum(1 for c in cases if c.spec_sources) >= len(cases) - 1


# ── 리포트 ───────────────────────────────────────────────────────────────────

def test_리포트_실패_카드에_기획서_근거가_나온다():
    verdict = Verdict(case_id="c", verdict="FAIL", failure_category="assertion_mismatch",
                      spec_sources=[SpecSource(page=1, quote="nickname | 입력 | 닉네임", table=True),
                                    SpecSource(page=3, quote="필수 입력 항목입니다.")])
    html = _case_html(verdict, open_by_default=True)
    assert "기획서 근거" in html
    assert "1쪽 표 — nickname | 입력 | 닉네임" in html and "3쪽 본문 — 필수 입력 항목입니다." in html


def test_근거가_없으면_그_줄을_그리지_않는다():
    html = _case_html(Verdict(case_id="c", verdict="FAIL"), open_by_default=True)
    assert "기획서 근거" not in html


def test_케이스의_근거가_판정까지_이어진다():
    from prova.s5_verifier.assertion_engine import PageState, verify

    source = SpecSource(page=2, quote="가입이 완료되었습니다", table=False)
    case = TestCase(case_id="c", screen_id="s", title="t", type="positive",
                    spec_sources=[source],
                    expected=Expectation(type="text_visible", value="가입이 완료되었습니다"))
    verdict = verify(case, [], PageState(url="http://x/", text="다른 화면"))
    assert verdict.spec_sources == [source]
