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

## 표에서 읽어 내는 사실이 여덟 가지다

확장 과정에서 같은 실패를 반복해 겪고 얻은 결론이다 — **표에 그대로 적힌 사실은 LLM
에 맡기지 않는다.** 프롬프트로 부탁해 본 것들이 문서가 길어지거나 few-shot 예시를
고칠 때마다 조용히 틀렸다.

    declared_element_ids        요소 ID
    declared_element_types      유형 (목록 -> list)
    declared_screen_meta        화면 ID · 경로
    declared_sample_values      예시값
    declared_scenarios          입력-결과 짝 + 결과 건수
    declared_placeholders       입력 안내 문구
    declared_required_message   필수 입력 문구
    declared_flows              화면 흐름

공통 원칙이 하나 있다. **확신할 수 있을 때만 답한다.** 판별 근거가 없거나 후보가
여럿이면 None/빈 값을 돌려주고 LLM 의 판단을 남긴다. 억측한 값으로 덮어쓰면 오탐이
되고, 오탐은 미탐보다 도구의 신뢰를 빨리 무너뜨린다.

## 표를 따로 뽑는 이유

extract_text() 는 표 안 글자까지 함께 쏟아낸다. 그러면 "email 입력 이메일 필수
이메일 형식(@ 포함) 올바른 이메일..." 처럼 한 줄로 뭉개져서, 어느 값이 어느
열에 속하는지 알 수 없다. 그래서 표는 find_tables() 로 잡아 마크다운 표로
재구성하고, 본문 텍스트는 표 영역을 제외한 글자만 모아 만든다. LLM이 열 이름을
보고 값의 의미를 판단할 수 있게 하는 것이 목적이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

from prova.text_utils import normalize_ws, quoted_re

# 건수 열을 값의 모양으로 찾을 때 쓴다. 음수·소수는 건수가 아니다.
_INT_RE = re.compile(r"\d+")

# 실패 조건 표에서 '값이 없는 상황' 을 가리키는 표현.
#
# 표현을 열거하는 것이 못마땅하지만, 프롬프트에 "표현이 아니라 의미로 찾으세요"
# 라고 적어 둔 것을 코드로 옮긴 것이다. 여기서 못 찾으면 LLM 의 판단을 그대로
# 쓰므로(declared_required_message 참고), 표현을 놓치는 것이 검증을 없애지 않는다.
# '선택하지 않음' · '동의하지 않음' 은 넣지 않는다. 그것들은 요소 하나의 상태에
# 대한 문구이고(가입 경로 미선택, 약관 미동의), required_message 는 **화면 공통**
# 문구다. 넣으면 회원가입 기획서에서 후보가 셋이 되어 판별을 포기하게 된다.
_EMPTY_INPUT_RE = re.compile(r"비어\s*있|비었|입력하지\s*않|미입력|누락|공백")

# 표 칸 안의 인용된 문구. 기획서가 쓰는 인용부호가 여러 가지다.
_QUOTED_RE = quoted_re(60)

# 흐름 표의 '화면 순서'·'이동 방법' 칸에서 항목을 가르는 구분자.
# 화살표 표현이 기획서마다 다르고(->, →, >, 쉼표) PDF 변환에서 모양이 바뀌기도 한다.
_FLOW_SEP = r"→|->|—>|>|,|·"

# '노출되면 안 되는 문구' 열을 찾는 헤더 패턴.
#
# 건수 열은 값의 모양(전부 정수)으로 찾는데 이 열은 그럴 수 없다 — 값이 그냥
# 문구라서 기대 문구 열과 모양이 같다. 그래서 헤더로 찾고, 기획서마다 다르게
# 쓸 표현을 넉넉히 받는다. 못 찾으면 이 검증을 만들지 않는다(억측하지 않는다).
_FORBIDDEN_HEADER_RE = re.compile(
    r"안\s*되는|안\s*됨|안돼|금지|노출되지|없어야|보이지\s*않"
)

# 기획서 '유형' 열의 한국어 표현 -> models.ElementType.
# 여기 없는 표현은 매핑하지 않는다 (declared_element_types 설명 참고).
ELEMENT_TYPE_WORDS = {
    "입력": "input",
    "입력란": "input",
    "버튼": "button",
    "링크": "link",
    "선택": "select",
    "체크박스": "checkbox",
    "텍스트": "text",
    "목록": "list",
    "날짜": "date",
}


@dataclass
class ParsedTable:
    """PDF 표 하나. rows[0]을 헤더로 취급한다.

    top: 페이지 안에서 표가 시작하는 세로 위치(pdfplumber 좌표, 작을수록 위).
    declared_seed_rows·declared_precondition_account 가 '절 제목 다음에 오는
    첫 표' 를 찾을 때, 제목보다 위에 있는 표(같은 페이지에 먼저 오는 다른 절의
    표)를 걸러내는 데 쓴다 — 페이지 단위로만 판별하면 한 페이지에 여러 절이
    들어갈 때 엉뚱한 표를 고르게 된다(예: '화면 개요' 표가 '테스트 주문 데이터'
    표보다 먼저 나오는 경우).
    """

    rows: list[list[str]] = field(default_factory=list)
    top: float = 0.0

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
    # 표 영역을 뺀 본문을 줄 단위로, 각 줄의 세로 위치(top)와 함께 담는다.
    # body_text 는 이 줄들을 이어 붙인 것과 같다 — 절 제목의 위치를 찾을 때만
    # (표 필터링용) body_lines 를 쓴다.
    body_lines: list[tuple[str, float]] = field(default_factory=list)

    def heading_top(self, heading_re: re.Pattern) -> Optional[float]:
        """heading_re 에 맞는 줄의 세로 위치. 이 페이지에 없으면 None.

        declared_precondition_account·declared_seed_rows 가 '절 제목보다
        아래에 있는 표만' 후보로 삼을 때 쓴다(ParsedTable.top 설명 참고).
        """
        for text, top in self.body_lines:
            if heading_re.match(text):
                return top
        return None


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

        ## 페이지를 넘어간 표를 이어 붙인다

        표가 길어 다음 페이지로 넘어가면 PDF 는 헤더를 다시 그린다. pdfplumber 는
        그것을 **별개의 표 두 개**로 읽으므로, 첫 표만 쓰면 넘어간 행이 조용히
        사라진다.

        실제로 겪었다. 요소 표에 '안내 문구' 열을 추가해 표가 넓어지자 회원가입
        기획서의 마지막 행(로그인하러 가기)이 다음 페이지로 밀렸고, `declared_element_ids`
        가 그 요소를 빠뜨렸다. 그러면 프롬프트에도 안 들어가고 누락 경고도 안 뜬다 —
        **행을 빠뜨리지 않기 위해 만든 장치가 같은 이유로 무력해진다.**

        헤더가 같은 표만 이어 붙인다. 다른 표를 잘못 붙이면 없는 요소를 만들어낸다.
        """
        merged: Optional[ParsedTable] = None
        for table in self.all_tables:
            header = [normalize_ws(h) for h in table.header]
            if not header:
                continue
            has_id = any("요소" in h and "ID" in h.upper() for h in header)
            has_type = any("유형" in h for h in header)
            if not (has_id and has_type):
                continue
            if merged is None:
                merged = ParsedTable(rows=[list(r) for r in table.rows])
            elif [normalize_ws(h) for h in merged.header] == header:
                merged.rows.extend(list(r) for r in table.rows[1:])
        return merged

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
        # 행 독해(declared_element_rows)를 쓰지 않는다 — 그쪽은 라벨 열까지
        # 요구하는데, ID 대조는 라벨 없는 표에서도 의미가 있다. 열 찾기 규칙만
        # 공유한다.
        table = self._element_table()
        if table is None:
            return []
        return [v.replace(" ", "")
                for v in self._column(table, self._ELEMENT_COLUMNS["id"])]

    #: UI 요소 표의 열을 찾는 규칙 — **여기 한 곳에만 둔다.** 2026-08-22 까지
    #: 독해 함수 여섯 개가 각자 열을 찾았고 실제로 어긋나 있었다: 안내 문구 열을
    #: 한쪽은 "안내" 로, 다른 쪽은 "안내 or placeholder" 로 찾아, 헤더가
    #: 'Placeholder' 인 기획서에서는 백필한 요소가 곧바로 '모델이 틀렸다' 경고를
    #: 받았다(모델 탓이 아닌데). 열 찾기가 두 벌이면 한쪽만 고쳐진다.
    _ELEMENT_COLUMNS = {
        "id": lambda h: "요소" in h and "ID" in h.upper(),
        "type": lambda h: "유형" in h,
        "label": lambda h: "라벨" in h,
        "required": lambda h: "필수" in h,
        "rules": lambda h: "규칙" in h,
        "placeholder": lambda h: "안내" in h or "placeholder" in h.lower(),
        "error": lambda h: "에러" in h,
    }

    def declared_element_rows(self) -> list[dict]:
        """UI 요소 표를 행 단위로 읽는다 — 결정적 표 독해에 하나를 더한다.

        ## 왜 필요한가 (2026-08-20 실측)

        실모델 7B 가 주문조회 화면의 요소 4개를 두 번 다 0개 추출했다. 로그인·
        상품등록의 입력·버튼 요소는 옮기면서 **표시 전용 요소(목록·텍스트)는
        통째로 빠뜨린다.** 요소가 없으면 정렬·합계·건수 케이스가 생성되지 않아
        심은 결함을 실행조차 못 했다. 그때 경고("표에는 4개, 추출은 0개")가
        말해 주듯 파서는 표를 이미 읽고 있었다 — 대조에서 백필로 올린다.

        열 매핑: 요소 ID·유형·라벨·필수·입력 검증 규칙·안내 문구·에러 메시지.
        '-' 는 기획서의 '없음' 표기이므로 빈 값으로 옮긴다. 유형은
        ELEMENT_TYPE_WORDS 로만 매핑하고 모르는 표현은 None 으로 둔다 —
        억지로 매핑하면 틀린 유형을 확신을 갖고 만들게 된다
        (declared_element_types 와 같은 판단). ID 나 라벨이 빈 행은 버린다.
        규칙 셀은 자유 서술이라 여기서 옮기지 않는다 — 원문을 rules 로 넘겨
        백필 쪽이 '규칙을 못 옮겼다' 를 경고하는 데만 쓴다. 규칙 열 자체가
        없으면 rules 는 None 이다 — 빈 문자열('열은 있는데 셀이 비었다')과
        구분해야 소비자가 "표가 규칙 없음을 말했다" 를 오판하지 않는다.
        """
        table = self._element_table()
        if table is None:
            return []
        header = [normalize_ws(h) for h in table.header]

        def col(name: str) -> Optional[int]:
            match = self._ELEMENT_COLUMNS[name]
            return next((i for i, h in enumerate(header) if match(h)), None)

        def cell(row: list[str], i: Optional[int]) -> str:
            value = normalize_ws(row[i]) if i is not None and i < len(row) else ""
            return "" if value in ("-", "—") else value

        id_col = col("id")
        type_col = col("type")
        label_col = col("label")
        required_col = col("required")
        rules_col = col("rules")
        placeholder_col = col("placeholder")
        error_col = col("error")
        if id_col is None or label_col is None:
            return []

        rows: list[dict] = []
        for row in table.rows[1:]:
            element_id = cell(row, id_col).replace(" ", "")
            label = cell(row, label_col)
            if not element_id or not label:
                continue
            rows.append({
                "element_id": element_id,
                "type": ELEMENT_TYPE_WORDS.get(normalize_ws(cell(row, type_col))),
                "label": label,
                "required": "필수" in cell(row, required_col),
                "rules": cell(row, rules_col) if rules_col is not None else None,
                "placeholder": cell(row, placeholder_col),
                "error_message": cell(row, error_col),
            })
        return rows

    def declared_labels(self) -> list[str]:
        """UI 요소 표의 '라벨' 열. 예시값 표의 열 제목과 맞춰 보는 데 쓴다."""
        return [r["label"] for r in self.declared_element_rows()]

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
        return {r["label"]: r["element_id"] for r in self.declared_element_rows()}

    def declared_placeholders(self) -> dict[str, str]:
        """UI 요소 표의 '안내 문구' 열. 라벨 -> placeholder 다.

        ## 왜 기획서가 이걸 적게 했는가

        SUT 에는 placeholder 가 있는데 **기획서에는 없었다.** 구현에 있는 UI 문구가
        기획서 관할 밖이라는 뜻이고, 그러면 아무도 그 문구를 검증하지 않는다 —
        '아이디를 입력하세요' 로 바뀌어도 통과한다. 입력 안내 문구는 사용자가 가장
        먼저 읽는 글자이므로 기획-구현 대조 대상이 맞다.

        ## '-' 는 해당 없음이다

        버튼·체크박스·목록에는 placeholder 가 없다. '-' 를 값으로 받으면 화면에서
        placeholder="-" 를 찾다 실패해 없는 결함을 보고하게 된다.
        """
        return {r["label"]: r["placeholder"]
                for r in self.declared_element_rows() if r["placeholder"]}

    def declared_required_message(self) -> Optional[str]:
        """실패 조건 표에서 '값이 비어 있을 때' 노출하는 문구를 읽는다.

        ## 왜 이것도 코드가 읽는가

        같은 실패를 또 겪었다. 화면 세 개를 한 문서에 담자 7B 가 검색 화면의
        required_message 를 **few-shot 예시의 문구("필수 항목을 입력하세요.")로**
        채웠다. 기획서에는 "검색어를 입력하세요." 라고 적혀 있었다.

        그 결과가 오탐이다 — 구현은 올바른 문구를 노출하는데 기대 문구가 달라
        FAIL 이 된다. 프롬프트에 "표현이 아니라 의미로 찾으세요" 라고 적어 뒀지만,
        프롬프트는 보장이 아니라 부탁이다. 그리고 이 값도 결국 **표에 그대로 적혀
        있다.**

        ## 확신할 수 있을 때만 답한다

        후보가 정확히 하나일 때만 값을 돌려준다. 여러 행이 '비어 있음' 을 다루면
        (요소별로 다른 문구를 쓰는 기획서) 어느 것이 화면 공통 문구인지 알 수
        없으므로 None 을 돌려주고 LLM 의 판단을 남긴다. 억측한 문구는 오탐이 된다.
        """
        table = self._failure_table()
        if table is None:
            return None
        header = [normalize_ws(h) for h in table.header]
        cond_col = next((i for i, h in enumerate(header)
                         if "상황" in h or "조건" in h), None)
        act_col = next((i for i, h in enumerate(header)
                        if i != cond_col and ("처리" in h or "동작" in h)), None)
        if cond_col is None or act_col is None:
            return None

        found: list[str] = []
        for row in table.rows[1:]:
            if len(row) <= max(cond_col, act_col):
                continue
            if not _EMPTY_INPUT_RE.search(normalize_ws(row[cond_col])):
                continue
            quoted = _QUOTED_RE.search(row[act_col])
            if quoted:
                found.append(normalize_ws(quoted.group(1)))
        return found[0] if len(found) == 1 else None

    def _failure_table(self) -> Optional[ParsedTable]:
        """실패 조건 표. '상황|처리' 2열로 판별한다.

        화면 개요 표도 2열이므로 열 제목으로 갈라야 한다 — 개요는 '항목|내용' 이다.
        """
        for table in self.all_tables:
            header = [normalize_ws(h) for h in table.header]
            if len(header) < 2:
                continue
            has_cond = any("상황" in h or "조건" in h for h in header)
            has_act = any("처리" in h or "동작" in h for h in header)
            if has_cond and has_act:
                return table
        return None

    def _overview_screen_ids(self, page: ParsedPage) -> list[str]:
        """그 페이지의 '화면 개요' 표들이 선언한 화면 ID.

        화면 개요 표는 '항목 | 내용' 2열이고 '화면 ID' 행을 가진다. 이 표의 등장이
        곧 새 화면의 시작이다 — 기획서가 화면마다 개요를 먼저 적기 때문이다.
        """
        found: list[str] = []
        for table in page.tables:
            if len(table.header) != 2:
                continue
            for row in table.rows[1:]:
                if len(row) < 2:
                    continue
                key, value = normalize_ws(row[0]), row[1].strip()
                if value and "화면" in key and "ID" in key.upper():
                    found.append(value.replace(" ", ""))
        return found

    def split_screens(self) -> tuple[list["ParsedDocument"], list[str]]:
        """화면 개요 표를 기준으로 문서를 화면별로 나눈다. LLM 을 쓰지 않는다.

        ## 왜 페이지 단위인가

        경계를 페이지 시작으로만 잡는다. 개요 표가 페이지 중간에 있어도 그 페이지
        전체를 새 화면의 것으로 본다.

        페이지 안까지 쪼개려면 본문과 표를 순서 있는 블록으로 다시 읽어야 하는데
        (지금 ParsedPage 는 본문을 페이지당 한 덩어리로 담는다), 그러면 이미
        검증된 세 화면의 추출 경로가 전부 영향권에 들어간다. 실물 기획서는 화면마다
        페이지를 새로 시작하는 것이 보통이므로, 이득이 확실할 때까지 미룬다.

        ## 나누지 못하는 경우를 조용히 넘기지 않는다

        한 페이지에 개요 표가 둘 이상이면 그 페이지의 내용이 두 화면 것이 섞여
        있다는 뜻이고, 페이지 단위로는 가를 수 없다. 그때 앞 화면에 몰아 넣으면
        뒤 화면의 요소 표가 앞 화면 것으로 추출되어 **두 화면의 검증이 모두
        조용히 어긋난다.** 그래서 경고로 알린다.

        Returns:
            (화면별 ParsedDocument 목록, 경고 목록).
            개요 표를 하나도 못 찾으면 문서 전체를 한 화면으로 보고 돌려준다 —
            화면당 PDF 하나인 기존 기획서가 그대로 동작해야 한다.
        """
        warnings: list[str] = []
        # 각 페이지가 새 화면을 시작하는가
        starts: list[Optional[str]] = []
        for page in self.pages:
            ids = self._overview_screen_ids(page)
            if len(ids) > 1:
                warnings.append(
                    f"{page.page_no}페이지에 화면 개요 표가 {len(ids)}개 있습니다 "
                    f"({', '.join(ids)}). 페이지 단위로는 가를 수 없어 한 화면으로 "
                    f"묶었습니다 — 화면마다 페이지를 새로 시작하세요."
                )
            starts.append(ids[0] if ids else None)

        if not any(starts):
            return [self], warnings

        # 첫 개요 표 앞의 페이지(표지·문서 정보)는 첫 화면에 붙인다.
        #
        # 별도 문서로 떼면 화면 개요가 없는 '화면' 이 하나 생기고, 그것을 구조화하면
        # 요소가 없는 빈 화면이 되어 리포트에 정체 불명의 항목이 늘어난다. 버리는
        # 것도 답이 아니다 — 앞머리에 화면 공통 규칙이 적혀 있으면 그 규칙이
        # 조용히 사라진다. 화면당 PDF 하나였던 기존 기획서도 표지와 첫 화면이 같은
        # 페이지에 있었으므로, 붙이는 쪽이 기존 동작과도 일치한다.
        docs: list[ParsedDocument] = []
        front: list[ParsedPage] = []
        for page, start in zip(self.pages, starts):
            if start is not None:
                docs.append(ParsedDocument(source=self.source, pages=list(front)))
                front = []
            if docs:
                docs[-1].pages.append(page)
            else:
                front.append(page)
        return docs, warnings

    def declared_precondition_account(self) -> Optional[list[list[str]]]:
        """'전제' 절 아래에서 계정 표(헤더 '이메일|비밀번호')를 찾는다.

        ## 왜 라벨이 아니라 절 제목 위치로 찾는가

        지금까지의 declared_* 는 표의 **열 제목**으로 표를 골랐다. 이 표는 그럴 수
        없다 — 화면 개요 표('항목|내용')처럼 §5 테스트 계정 표도 같은 '이메일|
        비밀번호' 헤더를 쓴다. 열 제목만으로는 어느 표가 '전제' 절의 계정인지
        구분할 수 없다. 그래서 본문에서 '전제' 절 제목이 나온 지점을 먼저 찾고,
        그 뒤에 나오는 표 중 헤더가 맞는 첫 표를 계정 표로 본다.

        절 제목은 본문에 '3. 전제' 처럼 번호와 함께 한 줄로 남는다(표 안 글자는
        _extract_body_lines 가 걷어낸다 — parse_pdf 참고). 그 줄 전체가 번호 +
        '전제' 뿐일 때만 절의 시작으로 본다. 문장 속에 낱말로 등장하는 경우
        ('...상태를 전제한다')와 구별해야 하기 때문이다.

        ## 왜 표의 세로 위치(top)도 같이 보는가

        절 제목과 그 표가 **같은 PDF 페이지**에 있을 수 있다(예: 화면 하나의
        모든 절이 짧아 한 페이지에 다 들어가는 경우). 그러면 그 페이지에 먼저
        나오는 다른 절의 표(화면 개요 등)가 헤더 조건까지 우연히 맞아버리면
        절 제목보다 위에 있는데도 골라질 수 있다. 그래서 절 제목 줄의 top 보다
        아래(나중)에 있는 표만 후보로 본다 — 페이지가 넘어간 뒤에는 그 페이지의
        모든 표가 절 제목보다 아래이므로 제한이 없다.

        ## 왜 헤더도 다시 확인하는가

        절 제목 이후 첫 표가 항상 계정 표라는 보장은 없다(같은 페이지에 다른
        표가 먼저 있을 수 있다). 헤더가 다르면 계정 표가 아니라고 보고 None 을
        돌려준다 — 억측해서 엉뚱한 값으로 계정을 덮어쓰는 것보다, 판별 못 함을
        인정하는 편이 안전하다.
        """
        heading_re = re.compile(r"^\s*[\d.\-]*\s*전제\s*$")
        table = self._table_after_heading(
            heading_re,
            lambda header, t: [normalize_ws(h) for h in header] == ["이메일", "비밀번호"],
        )
        return [list(r) for r in table.rows] if table is not None else None

    def declared_seed_rows(self) -> list[dict[str, str]]:
        """'테스트 주문 데이터' 절 아래 표를 [헤더 -> 값] 딕셔너리 목록으로 읽는다.

        ## 왜 라벨이 아니라 절 제목 위치로 찾는가

        declared_precondition_account 와 같은 이유다. 이 표의 열 제목
        ('주문번호·주문일·상품명·금액·상태')은 요소 표의 라벨과 겹칠 수 있어
        열 제목만으로는 다른 표와 구분할 근거가 없다. 그래서 본문에서
        '테스트 주문 데이터' 절 제목이 나온 지점을 먼저 찾고, 그 뒤에 나오는
        첫 표를 그 표로 본다.

        절 제목은 declared_precondition_account 와 마찬가지로 본문에 번호와
        함께 한 줄로 남을 때만 절의 시작으로 본다('...데이터를 확인한다' 처럼
        문장 속 낱말과 구별하기 위해서다).

        ## 왜 헤더를 그대로 열 이름(딕셔너리 키)으로 쓰는가

        표에 그대로 적힌 사실은 LLM 에 맡기지 않는다는 원칙의 연장이다. 이 표의
        열 이름(주문일·금액 등)은 화면마다 다를 수 있어 미리 알 수 없으므로,
        헤더를 키로 쓰는 dict 로 옮겨 S2 가 화면 요소의 라벨과 값의 모양으로
        직접 대조하게 한다(generator._seed_row_cases 참고).

        표를 찾지 못하면 빈 목록을 돌려준다 — 기획서가 데이터를 제시하지 않으면
        정렬·합계 검증은 만들 수 없고, 그건 기획서의 한계다(스펙 §1-2).
        """
        table = self._seed_rows_table()
        if table is None:
            return []
        header = [normalize_ws(h) for h in table.header]
        return [
            {header[i]: row[i].strip() for i in range(len(header)) if i < len(row)}
            for row in table.rows[1:]
        ]

    _SEED_HEADING_RE = re.compile(r"^\s*[\d.\-]*\s*테스트\s*주문\s*데이터\s*$")

    def _seed_rows_table(self) -> Optional[ParsedTable]:
        """declared_seed_rows 가 찾는 표 자체(행이 아니라 ParsedTable 객체).

        declared_scenarios 가 같은 표를 건너뛰는 데도 쓴다 — '테스트 주문
        데이터' 표의 열 제목(주문일·금액)이 UI 요소 라벨과 겹쳐서, 그 표가
        입력-결과 예시 표로 다시 해석되면 존재하지 않는 시나리오가 만들어진다
        (declared_scenarios 의 '표를 고르는 기준' 참고). 표 객체 자체(정체성)로
        비교해야 '표는 하나인데 두 declared_* 가 다른 이유로 같은 표를 다시
        찾는' 상황에서 반드시 같은 표를 가리킨다.
        """
        return self._table_after_heading(
            self._SEED_HEADING_RE,
            lambda header, t: len(header) >= 2 and len(t.rows) >= 2,
        )

    _DATE_FILTER_HEADING_RE = re.compile(r"^\s*[\d.\-]*\s*날짜\s*필터\s*$")

    def declared_date_filter(self) -> Optional[dict[str, str]]:
        """'날짜 필터' 절 아래 항목|값 표를 {항목: 값} 으로 읽는다.

        declared_precondition_account 와 같은 이유로 절 제목 위치로 찾는다 —
        '항목|값' 헤더는 화면 개요 표와 같아서 열 제목만으로는 구분할 수 없다.
        절이나 표가 없으면 None — 기획서가 필터를 정의하지 않은 화면에서 필터
        케이스를 억측으로 만들지 않기 위한 근거가 된다
        (extractor._apply_declared_date_filter).
        """
        table = self._table_after_heading(
            self._DATE_FILTER_HEADING_RE,
            lambda header, t: [normalize_ws(h) for h in header]
            in (["항목", "값"], ["항목", "내용"]),
        )
        if table is None:
            return None
        return {
            normalize_ws(row[0]): row[1].strip()
            for row in table.rows[1:]
            if len(row) >= 2 and row[0].strip()
        }

    def _table_after_heading(self, heading_re: re.Pattern, header_ok) -> Optional[ParsedTable]:
        """heading_re 절 제목보다 아래(나중)에 나오는 첫 표 중 header_ok 를 만족하는 표.

        declared_precondition_account·declared_seed_rows 가 공유하는 탐색
        로직이다(두 함수의 '왜 라벨이 아니라 절 제목 위치로 찾는가' 참고).
        """
        found = False
        min_top = -1.0  # 제한 없음 — 절 제목이 이전 페이지에 있었던 경우
        for page in self.pages:
            if not found:
                top = page.heading_top(heading_re)
                if top is not None:
                    found = True
                    min_top = top
            if not found:
                continue
            for table in page.tables:
                if table.top < min_top:
                    continue  # 절 제목보다 먼저 나오는, 같은 페이지의 다른 표
                if header_ok(table.header, table):
                    return table
            min_top = -1.0  # 다음 페이지부터는 전부 절 제목보다 아래다
        return None

    def declared_flows(self) -> list[dict]:
        """'화면 흐름' 표를 그대로 흐름으로 옮긴다. LLM 을 쓰지 않는다.

        표를 고르는 기준은 열 제목이다 — '흐름' 이 들어간 열과 화면 순서를 담은
        열이 함께 있는 표. 순서 열은 화면 ID 를 화살표나 쉼표로 이어 적는다.

            | 흐름 ID | 화면 순서 | 확인 문구 |
            | signup_then_login | signup -> login | 환영합니다 |

        캡션이 아니라 열 제목으로 고르는 이유는 다른 표들과 같다 — 기획서마다
        제목 표현이 다르고, 표현을 하나 놓칠 때마다 검증이 조용히 사라진다.
        """
        flows: list[dict] = []
        for table in self.all_tables:
            header = [normalize_ws(h) for h in table.header]
            id_col = next((i for i, h in enumerate(header) if "흐름" in h), None)
            order_col = next(
                (i for i, h in enumerate(header)
                 if "순서" in h or ("화면" in h and "흐름" not in h)), None
            )
            if id_col is None or order_col is None or id_col == order_col:
                continue
            # '이동 방법' 을 '확인 문구' 보다 먼저 고른다. 둘 다 남은 열에서 찾는데
            # '확인' 조건이 넓어서, 순서를 바꾸면 '이동 방법 확인' 같은 제목을
            # 문구 열로 집어 갈 수 있다.
            via_col = next(
                (i for i, h in enumerate(header)
                 if i not in (id_col, order_col) and ("이동" in h or "방법" in h)), None
            )
            text_col = next(
                (i for i, h in enumerate(header)
                 if i not in (id_col, order_col, via_col)
                 and ("문구" in h or "확인" in h)), None
            )
            for row in table.rows[1:]:
                if len(row) <= max(id_col, order_col):
                    continue
                flow_id = row[id_col].strip().replace(" ", "")
                screen_ids = _split_screen_order(row[order_col])
                if not flow_id or len(screen_ids) < 2:
                    continue
                flows.append({
                    "flow_id": flow_id,
                    "screen_ids": screen_ids,
                    "via": (_split_flow_cell(row[via_col])
                            if via_col is not None and via_col < len(row) else []),
                    "expect_text": (row[text_col].strip()
                                    if text_col is not None and text_col < len(row)
                                    else ""),
                })
        return flows

    def declared_element_types(self) -> dict[str, str]:
        """UI 요소 표의 '유형' 열을 ElementType 으로 옮긴다. 라벨 -> 유형 이다.

        ## 왜 이것도 코드가 읽는가

        이 프로젝트가 확장 과정에서 네 번 같은 실패를 겪고 얻은 결론의 적용이다 —
        **표에 그대로 적힌 사실은 LLM 에 맡기지 않는다.** 유형이 그렇다. '입력' 은
        input 이고 '목록' 은 list 다. 여기에 추론할 여지가 없다.

        유형이 틀리면 조용히 검증이 사라진다. 목록 요소를 text 로 읽으면 건수
        검증이 아예 만들어지지 않고(미탐), 반대로 입력란을 목록으로 읽으면 값을
        채우지 않아 정상 케이스까지 실패한다(오탐).

        ## 모르는 표현은 건드리지 않는다

        아래 표에 없는 단어면 그 요소를 빼고 돌려준다. 기획서가 '멀티셀렉트' 처럼
        새로운 유형을 쓰면 LLM 의 판단을 남겨 두는 편이 낫다 — 억지로 매핑하면
        틀린 유형을 확신을 갖고 덮어쓰게 된다.

        라벨을 키로 쓰는 이유: 요소 ID 는 정규화(공백 제거) 대상이라 대조 시점이
        엇갈릴 수 있고, 라벨은 declared_sample_values 와 declared_label_to_id 가
        이미 쓰는 키다.
        """
        return {r["label"]: r["type"]
                for r in self.declared_element_rows() if r["type"]}

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

        '테스트 주문 데이터' 표는 예외로 건너뛴다. 그 표의 열 제목(주문일·금액)이
        마침 UI 요소 라벨과 겹칠 수 있어(위 기준의 '일부만 라벨') 여기 걸리기
        쉬운데, 그 표는 이미 declared_seed_rows 가 정렬·합계 검증의 근거로 쓴다.
        같은 표를 입력-결과 예시로 다시 해석하면 기획서에 없는 시나리오를
        만들어낸다 — '주문일을 2026-08-15 로 입력하면 ORD-005 가 노출된다' 같은,
        아무도 적지 않은 예시다(_seed_rows_table 설명 참고).

        Returns:
            None  판별할 근거가 없다 (라벨을 못 읽었다). 이때만 LLM 결과를 쓴다.
            []    그런 표가 없다. 시나리오가 없는 것이 정답이다.
            [...] 표에서 읽은 시나리오.
        """
        label_to_id = self.declared_label_to_id()
        if not label_to_id:
            return None

        element_table = self._element_table()
        seed_table = self._seed_rows_table()
        for table in self.all_tables:
            if table is element_table or table is seed_table or len(table.rows) < 2:
                continue
            header = [normalize_ws(h) for h in table.header]
            if len(header) < 2:
                continue
            input_cols = [i for i, h in enumerate(header) if h in label_to_id]
            other_cols = [i for i, h in enumerate(header) if h not in label_to_id]
            if not input_cols or not other_cols:
                continue

            # 건수 열은 열 제목이 아니라 **값의 모양**으로 찾는다. 비어 있지 않은
            # 칸이 전부 정수인 열이 건수다.
            #
            # 제목으로 찾지 않는 이유: 기획서마다 '결과 건수' · '개수' · '건수'
            # 로 다르게 쓰고, 그러면 표현을 하나 놓칠 때마다 검증이 조용히
            # 빠진다. 값의 모양은 표현에 흔들리지 않는다. 그리고 '노출돼야 하는
            # 문구' 열의 값("검색 결과 3건")은 정수가 아니므로 섞이지 않는다.
            count_col = next(
                (i for i in other_cols if _is_integer_column(table.rows[1:], i)), None
            )
            # 금지 문구 열은 헤더로 찾는다. 값이 문구라서 기대 문구 열과 모양이
            # 같으므로 값의 모양으로는 가릴 수 없다.
            absent_col = next(
                (i for i in other_cols
                 if i != count_col and _FORBIDDEN_HEADER_RE.search(header[i])), None
            )
            # 기대 문구 열은 건수 열도 금지 열도 아닌 첫 열로 본다. 기획서가 열을
            # 더 두면 (비고 등) 첫 열만 쓰고 나머지는 무시한다 — 억측하지 않는다.
            expect_col = next(
                (i for i in other_cols if i not in (count_col, absent_col)), None
            )
            if expect_col is None:
                continue

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
                absent = (row[absent_col].strip()
                          if absent_col is not None and absent_col < len(row) else "")
                if given and expect_text:
                    scenarios.append({
                        "given": given,
                        "expect_text": expect_text,
                        "expect_count": _cell_int(row, count_col),
                        "expect_absent": absent or None,
                    })
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
    """find_tables() 로 표를 잡는다. bbox 의 top 을 같이 남긴다.

    ## 왜 extract_tables() 가 아니라 find_tables() 인가

    extract_tables() 는 표 내용(행·열)만 준다. declared_seed_rows·
    declared_precondition_account 가 '절 제목보다 아래에 있는 표' 를 가리려면
    표의 세로 위치(top)가 있어야 한다 — find_tables() 가 주는 Table 객체에만
    그 bbox 가 있다. 내용은 find_tables() 의 Table.extract() 로 똑같이 얻는다.
    """
    tables: list[ParsedTable] = []
    for t in page.find_tables():
        rows = [[_clean_cell(c) for c in row] for row in t.extract()]
        # 완전히 빈 행은 버린다 (괘선만 있는 행이 잡히는 경우)
        rows = [r for r in rows if any(r)]
        if rows:
            tables.append(ParsedTable(rows=rows, top=t.bbox[1]))
    return tables


def _extract_body_lines(page) -> list[tuple[str, float]]:
    """표 영역을 제외한 본문을, 줄 텍스트와 세로 위치(top)의 목록으로.

    find_tables() 가 준 bbox 안에 있는 글자를 걸러낸다. 줄 위치가 필요한 이유는
    declared_seed_rows 등이 '절 제목' 줄이 어디 있는지를 표의 top 과 비교해야
    하기 때문이다(ParsedTable.top 설명 참고) — 한 페이지에 여러 절이 있을 때
    제목보다 위에 있는(먼저 나오는 다른 절의) 표를 걸러내는 근거가 된다.
    """
    table_boxes = [t.bbox for t in page.find_tables()]

    def outside_tables(obj) -> bool:
        cx = (obj["x0"] + obj["x1"]) / 2
        cy = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= cx <= x1 and top <= cy <= bottom
                       for x0, top, x1, bottom in table_boxes)

    target = page.filter(outside_tables) if table_boxes else page
    lines = target.extract_text_lines() or []
    out = [(normalize_ws(ln["text"]), ln["top"]) for ln in lines]
    return [(text, top) for text, top in out if text]


def parse_pdf(path: str | Path) -> ParsedDocument:
    """PDF를 페이지별 본문 텍스트 + 표로 분해한다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {path}")

    doc = ParsedDocument(source=str(path))
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            body_lines = _extract_body_lines(page)
            doc.pages.append(ParsedPage(
                page_no=i,
                body_text="\n".join(text for text, _ in body_lines),
                tables=_extract_tables(page),
                body_lines=body_lines,
            ))
    return doc


def _cell_int(row: list[str], col: Optional[int]) -> Optional[int]:
    """행의 col 번째 칸을 정수로. 칸이 없거나 정수가 아니면 None."""
    if col is None or col >= len(row):
        return None
    text = row[col].strip()
    return int(text) if _INT_RE.fullmatch(text) else None


def _is_integer_column(rows: list[list[str]], col: int) -> bool:
    """그 열의 비어 있지 않은 칸이 전부 정수인가.

    값이 하나도 없는 열은 False 다. 빈 열을 건수 열로 골라 두면 모든 행의 건수가
    None 이 되어, 건수 검증이 있는 줄 알았는데 하나도 만들어지지 않는다.
    """
    values = [row[col].strip() for row in rows if col < len(row) and row[col].strip()]
    return bool(values) and all(_INT_RE.fullmatch(v) for v in values)


def _split_screen_order(cell: str) -> list[str]:
    """'signup -> login' 같은 칸을 화면 ID 목록으로.

    기획서가 쓸 수 있는 구분자를 모두 받는다. 화살표 표현이 기획서마다 다르고
    (->, →, >, 쉼표), PDF 변환 과정에서 모양이 바뀌기도 한다. 구분자 하나를
    놓치면 흐름이 화면 하나로 읽혀 조용히 사라진다.
    """
    parts = re.split(_FLOW_SEP, normalize_ws(cell))
    return [p.strip().replace(" ", "") for p in parts if p.strip()]


def _split_flow_cell(cell: str) -> list[str]:
    """'이동 방법' 칸을 전이별 라벨 목록으로.

    화면 ID 와 달리 **공백을 지우지 않는다.** 여기 들어오는 값은 슬러그가 아니라
    화면에 보이는 라벨이고('로그인하러 가기'), 공백이 라벨의 일부다. 지우면 S3 가
    요소를 못 찾는다.
    """
    parts = re.split(_FLOW_SEP, normalize_ws(cell))
    # '-' 는 기획서에서 '해당 없음' 을 뜻하는 관례다. 라벨로 받으면 S3 가 화면에서
    # '-' 라는 요소를 찾다 실패해, 이동 방법을 안 적은 흐름이 전부 끊긴다.
    return [p.strip() for p in parts if p.strip() and p.strip() not in ("-", "—")]
