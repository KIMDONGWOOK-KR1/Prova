"""기획서 근거 — 케이스의 기대가 기획서 몇 쪽 어느 줄에서 왔는지 찾는다.

## 왜 있는가

리포트는 '기획서와 다름' 이라고만 했다. 개발자가 "기획서 어디에 그런 말이 있느냐" 고 물으면
사용자가 PDF 를 다시 뒤져야 했다. 이 도구의 첫 실패가 오탐이었던 적이 있으므로(외부 사이트
세 곳, 실물 기획서 1차), **사용자가 판정을 스스로 확인할 수단**이 리포트 안에 있어야 한다.

## 모델이 아니라 코드가 찾는다

추출 모델에게 쪽 번호를 물으면 프롬프트·스키마가 바뀌고(2026-11-12 동결), 모델은 쪽 번호를
지어낼 수 있다. 여기서는 PDF 파서가 이미 갖고 있는 표 행과 본문 줄을 쪽 번호와 함께 보관해
두고(`ScreenSpec.source_lines`), 글자 대조로 찾는다. **못 찾으면 붙이지 않는다** — 근거를
지어내지 않는다.

## 무엇을 근거로 치는가

- 케이스가 겨냥한 요소(`target_element`)가 적힌 표 행 — 규칙과 에러 문구가 대개 그 행에 있다.
- 기대 문구(`expected.value`)가 적힌 줄 — 요소 없는 케이스(성공 조건·시나리오)의 근거.

근거는 판정에 관여하지 않는다. 판정이 정해진 뒤 읽는 사람에게 보여 주는 자료다.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from prova.models import ScreenSpec, SourceLine, SpecDocument, SpecSource, TestCase

#: 근거 한 줄의 최대 길이. 긴 표 행은 잘라서 보여 준다 — 근거는 위치를 가리키는 것이지 원문 전체가 아니다.
QUOTE_LIMIT = 200
#: 이보다 짧은 문구는 글자 대조로 찾지 않는다 — '확인' 같은 낱말은 아무 줄에나 걸린다.
MIN_PHRASE = 4
#: 케이스 하나에 붙이는 근거의 수. 많으면 읽지 않는다.
MAX_SOURCES = 2
_CELL_SEP = " | "
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def _squeeze(text: str) -> str:
    """공백을 모두 뺀 꼴 — PDF 는 칸 안에서 줄을 바꾸고 낱말을 띄어 쓴다('특수문 자')."""
    return _WS.sub("", text or "").casefold()


def index_lines(parsed) -> list[SourceLine]:
    """파싱한 기획서(ParsedDocument)의 표 행과 본문 줄을 쪽 번호와 함께 모은다."""
    lines: list[SourceLine] = []
    for page in parsed.pages:
        for table in page.tables:
            for row in table.rows[1:]:  # 머리글 행은 근거가 아니다
                cells = [_clean(c) for c in row if _clean(c)]
                if cells:
                    lines.append(SourceLine(page=page.page_no, text=_CELL_SEP.join(cells),
                                            table=True))
        for text, _top in page.body_lines:
            if _clean(text):
                lines.append(SourceLine(page=page.page_no, text=_clean(text)))
    return lines


def _source(line: SourceLine, extra: str = "") -> SpecSource:
    quote = line.text + (" " + extra if extra else "")
    if len(quote) > QUOTE_LIMIT:
        quote = quote[:QUOTE_LIMIT].rstrip() + "…"
    return SpecSource(page=line.page, quote=quote, table=line.table)


def find_element(lines: Iterable[SourceLine], element_id: Optional[str],
                 label: Optional[str]) -> Optional[SpecSource]:
    """요소가 적힌 표 행. 식별자가 칸과 정확히 같은 행을 먼저, 없으면 이름이 같은 행."""
    lines = list(lines)
    for key in (element_id, label):
        want = _squeeze(key or "")
        if not want:
            continue
        for line in lines:
            if line.table and want in {_squeeze(c) for c in line.text.split(_CELL_SEP)}:
                return _source(line)
    return None


def find_text(lines: Iterable[SourceLine], phrase: Optional[str]) -> Optional[SpecSource]:
    """문구가 적힌 줄. 본문은 줄이 바뀌어 끊길 수 있어 이웃한 두 줄을 이어서도 본다."""
    want = _squeeze(phrase or "")
    if len(want) < MIN_PHRASE:
        return None
    lines = list(lines)
    for line in lines:
        if want in _squeeze(line.text):
            return _source(line)
    for first, second in zip(lines, lines[1:]):
        if first.table or second.table or first.page != second.page:
            continue
        if want in _squeeze(first.text + second.text):
            return _source(first, second.text)
    return None


def _clues(case: TestCase) -> tuple[list[str], list[str]]:
    """기대에서 뽑은 단서 — (표 칸과 정확히 맞춰 볼 이름들, 줄 안에서 찾을 문구들).

    기대 유형마다 기획서에 적힌 꼴이 다르다. 문구를 기대하면 그 문구가, 목록·정렬·합계를
    기대하면 그 대상의 이름이, 이동을 기대하면 그 경로가 기획서에 적혀 있다.
    """
    e = case.expected
    names = [e.count_target, e.option_target, e.order_target, e.sum_total_target,
             e.sum_row_target, *e.labels[:1], *list(e.placeholders)[:1]]
    phrases = [e.value, *list(e.placeholders.values())[:1], e.url_contains]
    return [n for n in names if n], [p for p in phrases if p]


def sources_for_case(spec: ScreenSpec, case: TestCase) -> list[SpecSource]:
    """이 케이스의 기대가 기획서 어디에 적혀 있는가 (최대 두 곳, 못 찾으면 빈 목록)."""
    lines = spec.source_lines
    if not lines:
        return []
    names, phrases = _clues(case)
    found: list[Optional[SpecSource]] = []
    if case.target_element:
        # 요소 표가 없는 기획서(화면 그림 + 설명)에서는 이름이 적힌 줄이라도 가리킨다.
        found.append(find_element(lines, case.target_element, case.target_label)
                     or find_text(lines, case.target_label))
    found += [find_text(lines, phrase) for phrase in phrases]
    found += [find_element(lines, None, name) for name in names]
    unique: list[SpecSource] = []
    for source in found:
        if source is not None and source not in unique:
            unique.append(source)
    return unique[:MAX_SOURCES]


def attach_sources(doc: SpecDocument, cases: Iterable[TestCase]) -> None:
    """케이스마다 근거를 붙인다. 흐름 케이스는 마지막 화면(case.screen_id)의 기획서에서 찾는다."""
    screens = {s.screen_id: s for s in doc.screens}
    for case in cases:
        spec = screens.get(case.screen_id)
        if spec is not None:
            case.spec_sources = sources_for_case(spec, case)
