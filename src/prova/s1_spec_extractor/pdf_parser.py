"""S1 전반부 — PDF에서 텍스트와 표를 결정적으로 추출한다.

## 왜 LLM 앞에 이 단계를 두는가

명세서 §10-2는 PDF 추출을 'API 후보(강한 멀티모달 추론 필요)'로 분류했다.
그 판단은 이미지와 자유서술이 섞인 실무 기획서를 전제한 것이다. 우리가 만드는
텍스트 레이어 PDF는 사정이 다르다. pdfplumber가 글자와 표 괘선을 정확히 읽어내므로,
LLM에게 남는 일은 '텍스트 -> JSON 구조화' 뿐이다. 그 정도면 로컬 7B로 충분하다.

이렇게 결정적 추출과 LLM 구조화를 분리해두면 이득이 세 가지다.
1) 추출 단계를 LLM 없이 단위 테스트할 수 있다.
2) LLM에 넘기는 입력이 작아져 10GiB VRAM 환경에서도 컨텍스트가 넉넉하다.
3) WITCHES 실물 PDF가 이미지 기반이어도 이 파일만 교체하면 된다.

## 표를 따로 뽑는 이유

extract_text() 는 표 안 글자까지 함께 쏟아낸다. 그러면 "email 입력 이메일 필수
이메일 형식(@ 포함) 올바른 이메일..." 처럼 한 줄로 뭉개져서, 어느 값이 어느
열에 속하는지 알 수 없다. 그래서 표는 find_tables() 로 잡아 마크다운 표로
재구성하고, 본문 텍스트는 표 영역을 제외한 글자만 모아 만든다. LLM이 열 이름을
보고 값의 의미를 판단할 수 있게 하는 것이 목적이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from prova.text_utils import normalize_ws


@dataclass
class ParsedTable:
    """PDF 표 하나. rows[0]을 헤더로 취급한다."""

    rows: list[list[str]] = field(default_factory=list)

    @property
    def header(self) -> list[str]:
        return self.rows[0] if self.rows else []

    def to_markdown(self) -> str:
        if not self.rows:
            return ""
        ncols = max(len(r) for r in self.rows)
        lines = []
        for i, row in enumerate(self.rows):
            padded = list(row) + [""] * (ncols - len(row))
            lines.append("| " + " | ".join(padded) + " |")
            if i == 0:
                lines.append("|" + "---|" * ncols)
        return "\n".join(lines)


@dataclass
class ParsedPage:
    page_no: int
    body_text: str = ""
    tables: list[ParsedTable] = field(default_factory=list)


@dataclass
class ParsedDocument:
    source: str
    pages: list[ParsedPage] = field(default_factory=list)

    @property
    def all_tables(self) -> list[ParsedTable]:
        return [t for p in self.pages for t in p.tables]

    def declared_element_ids(self) -> list[str]:
        """UI 요소 표의 '요소 ID' 열에 적힌 값들. LLM 을 쓰지 않는다.

        왜 필요한가: LLM 이 표의 행 하나를 조용히 빠뜨릴 수 있다. 실측에서 7행
        표에서 버튼 행이 누락된 일이 있었는데, 제출 버튼이 없으면 테스트가
        아무것도 제출하지 못해 **구현이 멀쩡해도 전 케이스가 실패로 보고된다.**
        경고 없이 그런 리포트가 나오는 것이 이 도구에서 가장 위험한 결과다.

        표에 ID 열이 없으면 빈 목록을 돌려준다 — 대조할 근거가 없으면 검사하지
        않는 것이 맞다. 있는 것처럼 추측하면 없는 누락을 경고하게 된다.
        """
        for table in self.all_tables:
            header = [normalize_ws(h) for h in table.header]
            if not header:
                continue
            # '요소 ID' 와 '유형' 이 함께 있는 표를 UI 요소 정의 표로 본다.
            # 둘 중 하나만으로는 다른 표(실패 조건 등)와 구분되지 않는다.
            has_id = any("요소" in h and "ID" in h.upper() for h in header)
            has_type = any("유형" in h for h in header)
            if not (has_id and has_type):
                continue
            col = next(i for i, h in enumerate(header)
                       if "요소" in h and "ID" in h.upper())
            return [row[col].replace(" ", "") for row in table.rows[1:]
                    if len(row) > col and row[col].strip()]
        return []

    def to_llm_text(self) -> str:
        """LLM 프롬프트에 넣을 형태로 직렬화.

        페이지 경계를 남기는 이유: 여러 화면이 담긴 기획서에서 화면 구분의
        단서가 되기 때문이다. 표에는 번호를 붙여 본문에서 참조할 수 있게 한다.
        """
        chunks = []
        for page in self.pages:
            chunks.append(f"=== 페이지 {page.page_no} ===")
            if page.body_text:
                chunks.append(page.body_text)
            for i, table in enumerate(page.tables, 1):
                chunks.append(f"[표 {page.page_no}-{i}]")
                chunks.append(table.to_markdown())
        return "\n\n".join(c for c in chunks if c)


def _clean_cell(cell: str | None) -> str:
    """셀 텍스트 정리.

    셀 안 개행은 PDF 렌더링 폭 때문에 생긴 것이므로 공백으로 바꾼다. 원문의
    공백 배치를 정확히 복원하지는 못한다 — 그래서 문구 비교는 text_utils.loosen
    으로 공백을 무시하고 한다. 자세한 배경은 text_utils 모듈 설명 참고.
    """
    return normalize_ws(cell)


def _extract_tables(page) -> list[ParsedTable]:
    tables: list[ParsedTable] = []
    for raw in page.extract_tables():
        rows = [[_clean_cell(c) for c in row] for row in raw]
        # 완전히 빈 행은 버린다 (괘선만 있는 행이 잡히는 경우)
        rows = [r for r in rows if any(r)]
        if rows:
            tables.append(ParsedTable(rows=rows))
    return tables


def _extract_body_text(page) -> str:
    """표 영역을 제외한 본문 텍스트.

    find_tables() 가 준 bbox 안에 있는 글자를 걸러낸다. 표를 지우고 남은 글자가
    없으면 빈 문자열이 된다(표만 있는 페이지).
    """
    table_boxes = [t.bbox for t in page.find_tables()]
    if not table_boxes:
        return normalize_ws_lines(page.extract_text() or "")

    def outside_tables(obj) -> bool:
        cx = (obj["x0"] + obj["x1"]) / 2
        cy = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= cx <= x1 and top <= cy <= bottom
                       for x0, top, x1, bottom in table_boxes)

    filtered = page.filter(outside_tables)
    return normalize_ws_lines(filtered.extract_text() or "")


def normalize_ws_lines(text: str) -> str:
    """줄 단위로 공백을 정리하고 빈 줄을 압축한다. 줄 구조 자체는 보존한다.

    본문은 문장 단위 줄바꿈에 의미가 있을 수 있어(제목/항목 구분) 줄을 뭉치지
    않는다. 셀 텍스트와 다루는 방식이 다른 이유다.
    """
    lines = [normalize_ws(ln) for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def parse_pdf(path: str | Path) -> ParsedDocument:
    """PDF를 페이지별 본문 텍스트 + 표로 분해한다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {path}")

    doc = ParsedDocument(source=str(path))
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            doc.pages.append(ParsedPage(
                page_no=i,
                body_text=_extract_body_text(page),
                tables=_extract_tables(page),
            ))
    return doc
