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
from typing import Optional

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

    def _element_table(self) -> Optional[ParsedTable]:
        """UI 요소 정의 표. '요소 ID' 와 '유형' 열이 함께 있는 표로 판별한다.

        둘 중 하나만 보면 다른 표(실패 조건 등)와 구분되지 않는다.
        """
        for table in self.all_tables:
            header = [normalize_ws(h) for h in table.header]
            if not header:
                continue
            has_id = any("요소" in h and "ID" in h.upper() for h in header)
            has_type = any("유형" in h for h in header)
            if has_id and has_type:
                return table
        return None

    def _column(self, table: ParsedTable, match) -> list[str]:
        header = [normalize_ws(h) for h in table.header]
        col = next((i for i, h in enumerate(header) if match(h)), None)
        if col is None:
            return []
        return [row[col].strip() for row in table.rows[1:]
                if len(row) > col and row[col].strip()]

    def declared_element_ids(self) -> list[str]:
        """UI 요소 표의 '요소 ID' 열에 적힌 값들. LLM 을 쓰지 않는다.

        왜 필요한가: LLM 이 표의 행 하나를 조용히 빠뜨릴 수 있다. 실측에서 7행
        표에서 버튼 행이 누락된 일이 있었는데, 제출 버튼이 없으면 테스트가
        아무것도 제출하지 못해 **구현이 멀쩡해도 전 케이스가 실패로 보고된다.**
        경고 없이 그런 리포트가 나오는 것이 이 도구에서 가장 위험한 결과다.

        표에 ID 열이 없으면 빈 목록을 돌려준다 — 대조할 근거가 없으면 검사하지
        않는 것이 맞다. 있는 것처럼 추측하면 없는 누락을 경고하게 된다.
        """
        table = self._element_table()
        if table is None:
            return []
        return [v.replace(" ", "")
                for v in self._column(table, lambda h: "요소" in h and "ID" in h.upper())]

    def declared_labels(self) -> list[str]:
        """UI 요소 표의 '라벨' 열. 예시값 표의 열 제목과 맞춰 보는 데 쓴다."""
        table = self._element_table()
        if table is None:
            return []
        return self._column(table, lambda h: "라벨" in h)

    def declared_screen_meta(self) -> dict[str, str]:
        """화면 개요 표('항목 | 내용' 2열)에서 화면 ID 와 경로를 읽는다.

        왜 필요한가: 실측에서 7B 가 '화면 ID | search' 라고 적힌 표를 두고도
        화면명('상품 검색')에서 screen_id 를 'product_search' 로 새로 만들었다.
        screen_id 는 case_id 의 접두사이자 스크린샷 저장 경로에 쓰이므로, 골든
        데이터와 대조할 때도 어긋난다.
        """
        meta: dict[str, str] = {}
        for table in self.all_tables:
            if len(table.header) != 2:
                continue
            for row in table.rows[1:]:
                if len(row) < 2:
                    continue
                key, value = normalize_ws(row[0]), row[1].strip()
                if not value:
                    continue
                if "화면" in key and "ID" in key.upper():
                    meta.setdefault("screen_id", value.replace(" ", ""))
                elif "화면" in key and ("경로" in key or "URL" in key.upper()):
                    meta.setdefault("url_path", value)
        return meta

    def declared_sample_values(self) -> dict[str, str]:
        """예시 데이터 표에서 '라벨 -> 예시값' 을 읽는다. 라벨 -> 값 이다.

        표를 고르는 기준이 캡션이 아니라 **열 제목**이다. 열 제목이 모두 UI 요소의
        라벨이면 그 표는 요소별 예시값 표다. '테스트 계정', '입력 예시 데이터' 처럼
        제목 표현이 기획서마다 달라도 이 기준은 흔들리지 않는다.

        이 기준이 예시 시나리오 표를 걸러내기도 한다. 검색 기획서의 '예시 검색' 표는
        열 제목이 '검색어 | 노출돼야 하는 문구' 인데 뒤쪽이 라벨이 아니므로 제외된다
        — 그 표는 scenarios 로 가야 하고 sample_value 가 아니다.

        왜 필요한가: 실측에서 few-shot 예시의 표 제목을 바꾼 것만으로 로그인의
        sample_value 추출이 두 번 깨졌다. 예시값이 빠지면 정상 케이스가 등록되지
        않은 값을 쓰게 되어 **구현 결함 없이 실패한다**(오탐).
        """
        labels = set(self.declared_labels())
        if not labels:
            return {}

        element_table = self._element_table()
        found: dict[str, str] = {}
        for table in self.all_tables:
            if table is element_table or len(table.rows) < 2:
                continue
            header = [normalize_ws(h) for h in table.header]
            if not header or not all(h in labels for h in header):
                continue
            for i, label in enumerate(header):
                value = table.rows[1][i].strip() if i < len(table.rows[1]) else ""
                if value:
                    found.setdefault(label, value)
        return found

    def declared_label_to_id(self) -> dict[str, str]:
        """UI 요소 표에서 '라벨 -> 요소 ID'. 행 단위로 짝지어 어긋나지 않게 한다."""
        table = self._element_table()
        if table is None:
            return {}
        header = [normalize_ws(h) for h in table.header]
        id_col = next((i for i, h in enumerate(header)
                       if "요소" in h and "ID" in h.upper()), None)
        label_col = next((i for i, h in enumerate(header) if "라벨" in h), None)
        if id_col is None or label_col is None:
            return {}

        mapping: dict[str, str] = {}
        for row in table.rows[1:]:
            if len(row) <= max(id_col, label_col):
                continue
            label, element_id = row[label_col].strip(), row[id_col].strip()
            if label and element_id:
                mapping[label] = element_id.replace(" ", "")
        return mapping

    def declared_scenarios(self) -> Optional[list[dict]]:
        """입력-결과 예시 표를 그대로 시나리오로 옮긴다. LLM 을 쓰지 않는다.

        ## 왜 이걸 LLM 에 맡기지 않는가

        여기에는 추론할 것이 없다. 열 제목 -> 라벨 -> 요소 ID 는 표를 보고 하는
        조회이고, 셀 값은 그대로 옮기면 된다. '8자 이상' 을 min_length: 8 로
        바꾸는 것과는 성질이 다르다.

        실측에서 LLM 에 맡긴 대가를 두 번 치렀다. 회원가입에서는 **기획서에 없는
        시나리오를 만들어냈고**(성공 조건과 예시 데이터를 조합해 지어냈다.
        체크박스 값으로 'checked' 라는 규약까지 창작했다), 검색에서는 표 대신
        **실패 조건 표의 행을 가져왔다**(빈 검색어). 지어낸 기대 문구는 화면에
        없는 문구를 요구해 오탐이 되고, 규칙 위반을 시나리오로 들여오면 같은 것을
        두 번 검증한다.

        ## 표를 고르는 기준

        열 제목 중 **일부만** UI 요소의 라벨인 표다. 나머지 열이 기대 결과다.

            열 제목이 전부 라벨      -> 요소별 예시값 표 (sample_value)
            열 제목이 일부만 라벨    -> 입력-결과 짝 표 (여기)
            라벨이 하나도 없음       -> 개요·실패 조건 등 다른 표

        Returns:
            None  판별할 근거가 없다 (라벨을 못 읽었다). 이때만 LLM 결과를 쓴다.
            []    그런 표가 없다. 시나리오가 없는 것이 정답이다.
            [...] 표에서 읽은 시나리오.
        """
        label_to_id = self.declared_label_to_id()
        if not label_to_id:
            return None

        element_table = self._element_table()
        for table in self.all_tables:
            if table is element_table or len(table.rows) < 2:
                continue
            header = [normalize_ws(h) for h in table.header]
            if len(header) < 2:
                continue
            input_cols = [i for i, h in enumerate(header) if h in label_to_id]
            other_cols = [i for i, h in enumerate(header) if h not in label_to_id]
            if not input_cols or not other_cols:
                continue

            # 기대 결과 열은 라벨이 아닌 첫 열로 본다. 기획서가 열을 더 두면
            # (비고 등) 첫 열만 쓰고 나머지는 무시한다 — 억측하지 않는다.
            expect_col = other_cols[0]
            scenarios: list[dict] = []
            for row in table.rows[1:]:
                if len(row) <= expect_col:
                    continue
                given = {
                    label_to_id[header[i]]: row[i].strip()
                    for i in input_cols
                    if i < len(row) and row[i].strip()
                }
                expect_text = row[expect_col].strip()
                if given and expect_text:
                    scenarios.append({"given": given, "expect_text": expect_text})
            return scenarios
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
