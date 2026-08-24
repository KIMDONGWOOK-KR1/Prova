# 날짜 필터·기간 조회 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주문 조회 화면에 날짜 필터(시작일·종료일 → 조회 → 재조회)를 추가하고, 파이프라인이 입력↔재조회 뒤의 화면을 검증하게 한다.

**Architecture:** 기획서에 "날짜 필터" 절을 표로 명시 → S1 이 `ScreenSpec.date_filter` 로 추출(LLM + `declared_date_filter()` 결정적 교정) → S2 가 시드 표 기반 + 자기일관성의 8개 filter 케이스를 코드로 생성 → 기존 S4(fill+click)·S5(컬렉션 판정) 기계를 그대로 재사용. SUT 에는 결함 O3(경계일 제외)·O4(합계 미재계산)를 심는다.

**Tech Stack:** Python 3.11, pydantic, Playwright, FastAPI(SUT), pdfplumber, reportlab, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-date-filter-design.md`

## Global Constraints

- 공개 저장소 — `.env`·`private.pem`·CHEETAH 접속 정보는 절대 커밋 금지. 푸시 전 `git diff origin/main | grep -nE '168\.131|ssh -p [0-9]|jovyan@|kdw51@|PRIVATE KEY'` 로 스캔.
- 오탐 0 · 판정 불능=FAIL · "탐지 실패와 구현 결함을 섞지 않는다" · 만들 수 없는 검증은 **경고를 남기고** 만들지 않는다(조용히 넘어가지 않는다).
- 커밋 메시지는 서술형 한국어(기존 로그 스타일). 테스트 먼저(TDD).
- 전체 테스트: `uv run pytest -x -q` (실모델 골든 69+N개는 터널이 열려 있어야 skip 0).
- 작업 디렉터리: `C:\dev\prova`, 브랜치 `feature/prova-pipeline`.

---

### Task 1: 요소 유형 `date` 신설

**Files:**
- Modify: `src/prova/models.py:31` (ElementType)
- Modify: `src/prova/s1_spec_extractor/pdf_parser.py:85` (ELEMENT_TYPE_WORDS)
- Test: `tests/test_pdf_parser.py`

**Interfaces:**
- Produces: `ElementType` 에 `"date"` 추가. 기획서 유형 열의 `날짜` → `"date"`. `_fillable_inputs`(generator.py:74)는 `("input","select","checkbox")` 만 보므로 **수정 없이** date 가 자동 채움에서 빠진다.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_pdf_parser.py` 의 ELEMENT_TYPE_WORDS 관련 테스트 클래스 근처에 추가:

```python
class TestDateElementType:
    def test_유형_날짜가_date_로_매핑된다(self):
        from prova.s1_spec_extractor.pdf_parser import ELEMENT_TYPE_WORDS
        assert ELEMENT_TYPE_WORDS["날짜"] == "date"

    def test_date_는_자동_채움_대상이_아니다(self):
        from prova.models import ScreenSpec, UIElement
        from prova.s2_case_generator.generator import _fillable_inputs
        spec = ScreenSpec(
            screen_id="s", screen_name="s", url_path="/s",
            elements=[UIElement(element_id="start_date", type="date", label="시작일")],
        )
        assert _fillable_inputs(spec) == []
```

(UIElement 필수 필드가 다르면 기존 테스트의 UIElement 생성부를 따라 맞춘다.)

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_pdf_parser.py -k 날짜 -x -q` → KeyError/ValidationError 로 FAIL.
- [ ] **Step 3: 구현** — `models.py:31` 을 `ElementType = Literal["input", "button", "link", "select", "checkbox", "text", "list", "date"]` 로. `pdf_parser.py` ELEMENT_TYPE_WORDS 에 `"날짜": "date",` 추가.
- [ ] **Step 4: 통과 확인** — 같은 명령 PASS. 이어서 `uv run pytest tests/test_spec_type_conformance.py tests/test_generator.py -q` 로 파급 없음 확인.
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "요소 유형 '날짜'를 신설한다 — 자동 채움에서 제외되는 date 입력"`

---

### Task 2: 기획서 확장 + PDF 재생성 + `declared_date_filter()`

**Files:**
- Modify: `fixtures/specs/orders_spec.md` (요소 3줄 + §6 절)
- Regenerate: `fixtures/specs/orders_spec.pdf`
- Modify: `src/prova/s1_spec_extractor/pdf_parser.py` (declared_date_filter)
- Test: `tests/test_pdf_parser.py`

**Interfaces:**
- Produces: `ParsedDocument.declared_date_filter() -> Optional[dict[str, str]]` — "날짜 필터" 절의 항목|값 표를 `{정규화된 항목: 값}` 으로. 절이나 표가 없으면 None.

- [ ] **Step 1: 기획서 수정** — `orders_spec.md` §2 표(85행 부근)의 `order_total` 줄 다음에:

```markdown
| start_date | 날짜 | 시작일 | - | - | - | - |
| end_date | 날짜 | 종료일 | - | - | - | - |
| filter_btn | 버튼 | 조회 | - | - | - | - |
```

파일 끝(§5 시드 표 다음)에:

```markdown
## 6. 날짜 필터

시작일과 종료일을 입력하고 조회 버튼을 누르면 주문일이 그 기간 안에 있는 주문만
표시한다. 경계일을 포함한다 — 시작일 당일과 종료일 당일의 주문도 결과에 들어간다.
시작일·종료일이 비어 있으면 전체 기간으로 조회한다. 필터를 적용한 뒤에도 §5 의
정렬(주문일 내림차순)과 합계(표시된 주문 금액의 합) 규칙은 그대로 유지된다.
조회 결과가 없으면 "기간 내 주문이 없습니다." 를 노출한다.

| 항목 | 값 |
|---|---|
| 시작일 요소 | 시작일 |
| 종료일 요소 | 종료일 |
| 조회 버튼 | 조회 |
| 대상 목록 | 주문 목록 |
| 날짜 컬럼 | 주문일 |
| 빈 결과 문구 | 기간 내 주문이 없습니다. |
```

- [ ] **Step 2: PDF 재생성** — `uv run python scripts/make_spec_pdf.py fixtures/specs/orders_spec.md`
- [ ] **Step 3: 실패하는 테스트** — `tests/test_pdf_parser.py` 에 (기존 declared_seed_rows 테스트의 픽스처 사용 방식을 따라, orders PDF 를 파싱하는 헬퍼가 있으면 재사용):

```python
class TestDeclaredDateFilter:
    def test_orders_기획서의_날짜_필터_표를_읽는다(self, orders_doc):  # 기존 픽스처명 확인
        got = orders_doc.declared_date_filter()
        assert got == {
            "시작일 요소": "시작일", "종료일 요소": "종료일", "조회 버튼": "조회",
            "대상 목록": "주문 목록", "날짜 컬럼": "주문일",
            "빈 결과 문구": "기간 내 주문이 없습니다.",
        }

    def test_절이_없는_기획서는_None(self, login_doc):
        assert login_doc.declared_date_filter() is None
```

- [ ] **Step 4: 실패 확인** — `uv run pytest tests/test_pdf_parser.py -k DateFilter -x -q` → AttributeError.
- [ ] **Step 5: 구현** — `pdf_parser.py` 의 `declared_seed_rows` 다음에 (`_table_after_heading` 재사용):

```python
_DATE_FILTER_HEADING_RE = re.compile(r"^\s*[\d.\-]*\s*날짜\s*필터\s*$")

def declared_date_filter(self) -> Optional[dict[str, str]]:
    """'날짜 필터' 절 아래 항목|값 표를 {항목: 값} 으로 읽는다.

    declared_precondition_account 와 같은 이유로 절 제목 위치로 찾는다 —
    '항목|값' 헤더는 화면 개요 표와 같아서 열 제목만으로는 구분할 수 없다.
    절이나 표가 없으면 None — 기획서가 필터를 정의하지 않은 화면에서 필터
    케이스를 억측으로 만들지 않기 위한 근거가 된다.
    """
    table = self._table_after_heading(
        self._DATE_FILTER_HEADING_RE,
        lambda header, t: [normalize_ws(h) for h in header] in (["항목", "값"], ["항목", "내용"]),
    )
    if table is None:
        return None
    return {
        normalize_ws(row[0]): row[1].strip()
        for row in table.rows[1:] if len(row) >= 2 and row[0].strip()
    }
```

(상수는 `_SEED_HEADING_RE` 와 같은 자리 — 클래스 상수 `_DATE_FILTER_HEADING_RE` 로 둔다.)

- [ ] **Step 6: 통과 확인** — 같은 명령 PASS. `uv run pytest tests/test_pdf_parser.py -q` 전체 회귀 확인 (시드 표·전제 표 테스트가 §6 추가로 깨지지 않는지 — `_table_after_heading` 은 절 제목 뒤 첫 표만 보므로 안전해야 한다).
- [ ] **Step 7: 커밋** — `git commit -am "orders 기획서에 날짜 필터 절을 더하고 결정적으로 읽는다"`

---

### Task 3: `DateFilter` 모델 + S1 교정 + 골든 갱신

**Files:**
- Modify: `src/prova/models.py` (DateFilter, ScreenSpec.date_filter)
- Modify: `src/prova/s1_spec_extractor/extractor.py` (교정 호출부 :325 부근 + 함수)
- Modify: `fixtures/specs/orders_spec.golden.json`
- Test: `tests/test_extractor_guards.py`

**Interfaces:**
- Produces:

```python
class DateFilter(BaseModel):
    start_label: str      # 시작일 입력의 라벨
    end_label: str        # 종료일 입력의 라벨
    submit_label: str     # 조회 버튼의 라벨
    target_label: str     # 필터가 적용되는 반복 목록의 라벨
    date_column: str      # 시드 표에서 기간 판정에 쓰는 날짜 열 이름
    empty_message: Optional[str] = None  # 0건일 때 노출 문구 (기획서가 정한 경우만)
```

`ScreenSpec.date_filter: Optional[DateFilter] = None`. **declared 표가 진실**: 표가 없으면 LLM 이 무엇을 냈든 None 으로 되돌린다(억측한 필터로 케이스를 만들지 않는다). 표가 있는데 필수 5키(시작일 요소·종료일 요소·조회 버튼·대상 목록·날짜 컬럼) 중 빠진 게 있으면 경고 + None. `빈 결과 문구` 만 선택.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_extractor_guards.py` 에 (기존 `_apply_declared_*` 테스트의 spec 생성 방식을 따라):

```python
class TestApplyDeclaredDateFilter:
    def _spec(self):
        return ScreenSpec(screen_id="orders", screen_name="주문 조회", url_path="/orders")

    def test_표가_있으면_date_filter_를_채운다(self):
        spec = self._spec()
        _apply_declared_date_filter(spec, {
            "시작일 요소": "시작일", "종료일 요소": "종료일", "조회 버튼": "조회",
            "대상 목록": "주문 목록", "날짜 컬럼": "주문일",
            "빈 결과 문구": "기간 내 주문이 없습니다.",
        })
        f = spec.date_filter
        assert (f.start_label, f.end_label, f.submit_label) == ("시작일", "종료일", "조회")
        assert (f.target_label, f.date_column) == ("주문 목록", "주문일")
        assert f.empty_message == "기간 내 주문이 없습니다."

    def test_표가_없으면_LLM_이_지어낸_필터를_지운다(self):
        spec = self._spec()
        spec.date_filter = DateFilter(start_label="a", end_label="b", submit_label="c",
                                      target_label="d", date_column="e")
        _apply_declared_date_filter(spec, None)
        assert spec.date_filter is None

    def test_필수_키가_빠지면_경고하고_채우지_않는다(self):
        spec = self._spec()
        _apply_declared_date_filter(spec, {"시작일 요소": "시작일"})
        assert spec.date_filter is None
        assert any("날짜 필터" in w for w in spec.warnings)

    def test_빈_결과_문구는_선택이다(self):
        spec = self._spec()
        _apply_declared_date_filter(spec, {
            "시작일 요소": "시작일", "종료일 요소": "종료일", "조회 버튼": "조회",
            "대상 목록": "주문 목록", "날짜 컬럼": "주문일",
        })
        assert spec.date_filter is not None and spec.date_filter.empty_message is None
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_extractor_guards.py -k DateFilter -x -q` → ImportError.
- [ ] **Step 3: 구현** — `models.py` 에 DateFilter(위 정의 그대로, 각 필드에 `Field(description=...)` 한국어 설명 — `ScreenSpec.model_json_schema()` 를 통해 LLM 스키마에 그대로 실린다) + `ScreenSpec.date_filter`. `extractor.py` 에:

```python
_DATE_FILTER_KEYS = {
    "시작일 요소": "start_label", "종료일 요소": "end_label", "조회 버튼": "submit_label",
    "대상 목록": "target_label", "날짜 컬럼": "date_column", "빈 결과 문구": "empty_message",
}

def _apply_declared_date_filter(spec: ScreenSpec, declared: Optional[dict[str, str]]) -> None:
    """'날짜 필터' 표가 진실이다 — 표가 없으면 LLM 이 지어낸 필터도 지운다.

    표가 있는데 필수 항목이 빠졌으면 경고하고 만들지 않는다 — 반쪽 필터로
    케이스를 만들면 무엇을 확인한 것인지 말할 수 없다(판정 불능이면 만들지
    않는다 원칙).
    """
    if declared is None:
        spec.date_filter = None
        return
    kwargs = {v: declared[k] for k, v in _DATE_FILTER_KEYS.items() if declared.get(k)}
    required = {"start_label", "end_label", "submit_label", "target_label", "date_column"}
    missing = required - kwargs.keys()
    if missing:
        spec.date_filter = None
        spec.warnings.append(
            "날짜 필터 표에 필수 항목이 빠져 있어 기간 조회 케이스를 만들지 "
            f"않았습니다 (빠진 항목: {len(missing)}개)."
        )
        return
    spec.date_filter = DateFilter(**kwargs)
```

extractor.py:325 `_apply_declared_seed_rows(...)` 다음 줄에 `_apply_declared_date_filter(spec, doc.declared_date_filter())` 추가. `_drop_invented_strings` 가 date_filter 문자열을 건드리지 않는지 확인(건드리면 교정 순서를 그 뒤로).

- [ ] **Step 4: 통과 확인** — 같은 명령 PASS.
- [ ] **Step 5: 골든 갱신** — `orders_spec.golden.json` 최상위에 추가(다른 키 순서는 유지):

```json
"date_filter": {
  "start_label": "시작일", "end_label": "종료일", "submit_label": "조회",
  "target_label": "주문 목록", "date_column": "주문일",
  "empty_message": "기간 내 주문이 없습니다."
}
```

elements 배열에도 세 요소 추가 (기존 요소의 JSON 모양을 그대로 따라):

```json
{"element_id": "start_date", "type": "date", "label": "시작일"},
{"element_id": "end_date", "type": "date", "label": "종료일"},
{"element_id": "filter_btn", "type": "button", "label": "조회"}
```

(기존 elements 항목에 required/constraints 등 추가 키가 있으면 그 모양을 맞춘다.)

- [ ] **Step 6: 골든 정합 확인** — `uv run pytest tests/test_mock_multiscreen.py tests/test_fixture_consistency.py -q`. 실모델 골든은 Task 8 에서.
- [ ] **Step 7: 커밋** — `git commit -am "ScreenSpec 에 날짜 필터를 싣는다 — declared 표가 진실, 반쪽이면 경고 후 미생성"`

---

### Task 4: S2 — `_filter_cases` 생성

**Files:**
- Modify: `src/prova/s2_case_generator/generator.py` (267행 호출부 + 새 함수)
- Test: `tests/test_orders_cases.py`

**Interfaces:**
- Consumes: `spec.date_filter`(Task 3), `spec.seed_rows`, `_seed_column_label`·`_SEED_AMOUNT_RE`(기존), `TestStep`/`Expectation`(기존 필드: `count`·`count_target`·`order_target`·`sum_row_target`·`sum_total_target`·`value`).
- Produces: case_id `{screen_id}-filter-{seq:03d}` 케이스 최대 8개. 스텝 공통형: navigate → fill(시작일) → fill(종료일) → click(조회).

- [ ] **Step 1: 실패하는 테스트** — `tests/test_orders_cases.py` 에 (파일의 기존 spec 빌더/픽스처를 따라 orders 형태 ScreenSpec 을 만든다 — elements 에 주문 목록(list)·주문일(text)·금액(text)·합계(text)·시작일(date)·종료일(date)·조회(button), seed_rows 는 orders 기획서 §5 의 5행, date_filter 는 Task 3 값):

```python
class TestFilterCases:
    def test_기간은_고유_날짜의_양끝을_하나씩_남기고_잡는다(self, orders_spec):
        cases = _filter_cases(orders_spec, start_seq=10)
        fills = [s for s in cases[0].steps if s.action == "fill"]
        assert [s.value for s in fills] == ["2026-08-03", "2026-08-12"]

    def test_케이스_여덟_개가_생성된다(self, orders_spec):
        cases = _filter_cases(orders_spec, start_seq=10)
        assert len(cases) == 8
        assert all("-filter-" in c.case_id for c in cases)

    def test_건수는_기간_내_시드_행_수다(self, orders_spec):
        count = _filter_cases(orders_spec, start_seq=10)[0]
        assert count.expected.type == "result_count"
        assert count.expected.count == 3
        assert count.expected.count_target == "주문 목록"

    def test_경계_포함과_기간_밖_배제를_시드의_고유값으로_확인한다(self, orders_spec):
        cases = _filter_cases(orders_spec, start_seq=10)
        visible, absent = cases[1], cases[2]
        assert visible.expected.type == "text_visible" and visible.expected.value == "ORD-002"
        assert absent.expected.type == "text_absent" and absent.expected.value == "ORD-005"

    def test_합계와_정렬은_필터_스텝_뒤에_같은_판정을_다시_건다(self, orders_spec):
        cases = _filter_cases(orders_spec, start_seq=10)
        assert cases[3].expected.type == "sum_matches"
        assert cases[4].expected.type == "sorted_desc"
        assert [s.action for s in cases[4].steps] == ["navigate", "fill", "fill", "click"]

    def test_빈_기간은_최대_날짜_다음날부터다(self, orders_spec):
        empty = _filter_cases(orders_spec, start_seq=10)[5]
        fills = [s.value for s in empty.steps if s.action == "fill"]
        assert fills == ["2026-08-16", "2026-08-17"]
        assert empty.expected.type == "result_count" and empty.expected.count == 0

    def test_빈_문구_케이스는_기획서가_문구를_정했을_때만(self, orders_spec):
        assert _filter_cases(orders_spec, start_seq=10)[6].expected.value == "기간 내 주문이 없습니다."
        orders_spec.date_filter.empty_message = None
        assert len(_filter_cases(orders_spec, start_seq=10)) == 7

    def test_빈_값_조회는_전체_건수다(self, orders_spec):
        full = _filter_cases(orders_spec, start_seq=10)[-1]
        assert [s.action for s in full.steps] == ["navigate", "click"]
        assert full.expected.count == 5

    def test_필터가_없으면_케이스도_경고도_없다(self, orders_spec):
        orders_spec.date_filter = None
        assert _filter_cases(orders_spec, start_seq=10) == []
        assert orders_spec.warnings == []

    def test_시드가_없으면_경고하고_만들지_않는다(self, orders_spec):
        orders_spec.seed_rows = []
        assert _filter_cases(orders_spec, start_seq=10) == []
        assert any("기간 조회" in w for w in orders_spec.warnings)

    def test_날짜를_읽지_못하면_경고하고_만들지_않는다(self, orders_spec):
        for row in orders_spec.seed_rows:
            row["주문일"] = "언젠가"
        assert _filter_cases(orders_spec, start_seq=10) == []
        assert any("날짜로 읽지 못해" in w for w in orders_spec.warnings)

    def test_고유_날짜가_3개_미만이면_경고하고_만들지_않는다(self, orders_spec):
        orders_spec.seed_rows = orders_spec.seed_rows[:2]
        assert _filter_cases(orders_spec, start_seq=10) == []
        assert any("고유 날짜" in w for w in orders_spec.warnings)
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_orders_cases.py -k Filter -x -q` → ImportError.
- [ ] **Step 3: 구현** — `generator.py` 의 `_seed_row_cases` 다음에 (파일 상단에 `from datetime import date, timedelta` 추가):

```python
def _filter_cases(spec: ScreenSpec, start_seq: int) -> list[TestCase]:
    """날짜 필터 케이스 — 입력↔재조회 뒤의 화면을 검증한다 (설계: specs/2026-08-24).

    근거는 두 층이다. 시드 표 기반(기간 내 행 수·경계 포함/기간 밖 배제·빈 기간·
    빈 값 전체)은 기획서 §5 에서 결정적으로 계산하고, 자기일관성(필터 후에도
    정렬·합계 판정이 성립)은 기존 판정을 필터 스텝 뒤에 다시 건다.

    ## 왜 기간을 고유 날짜의 양끝 하나씩을 남기고 잡는가

    양끝 밖에 각각 1건 이상이 남아 '걸러졌는가' 를 셀 수 있고, 경계가 실제
    주문일이라 '경계일 포함' 이 검증된다. 임의 기간을 잡으면 둘 다 우연에
    맡겨진다.

    ## 왜 date_filter 가 없을 때는 경고하지 않는가

    필터 없는 화면이 정상이다(_seed_row_cases 가 seed_rows 없음에 침묵하는
    것과 같은 원칙). 반대로 필터 절은 있는데 계산 근거가 무너진 경우는 전부
    경고한다 — 기획서가 검증을 약속했는데 도구가 못 지키는 상황이므로.
    """
    f = spec.date_filter
    if f is None:
        return []
    if not spec.seed_rows:
        spec.warnings.append(
            "날짜 필터 절은 있지만 테스트 주문 데이터 표가 없어 기간 조회 "
            "케이스를 만들지 않았습니다."
        )
        return []
    by_date: dict[date, list[dict[str, str]]] = {}
    try:
        for row in spec.seed_rows:
            by_date.setdefault(date.fromisoformat(row[f.date_column].strip()), []).append(row)
    except (KeyError, ValueError):
        spec.warnings.append(
            f"시드 표의 '{f.date_column}' 열을 날짜로 읽지 못해 기간 조회 "
            "케이스를 만들지 않았습니다."
        )
        return []
    dates = sorted(by_date)
    if len(dates) < 3:
        spec.warnings.append(
            "시드 표의 고유 날짜가 3개 미만이라 기간 밖 주문을 남기는 기간을 "
            "잡을 수 없어 기간 조회 케이스를 만들지 않았습니다."
        )
        return []

    start, end = dates[1], dates[-2]
    in_rows = [r for d in dates if start <= d <= end for r in by_date[d]]

    def _steps(fills: list[tuple[str, str]]) -> list[TestStep]:
        steps = [TestStep(seq=1, action="navigate", target=spec.url_path)]
        for i, (label, value) in enumerate(fills, start=2):
            steps.append(TestStep(seq=i, action="fill", target=label, value=value))
        steps.append(TestStep(seq=len(steps) + 1, action="click", target=f.submit_label))
        return steps

    range_fills = [(f.start_label, start.isoformat()), (f.end_label, end.isoformat())]
    empty_fills = [
        (f.start_label, (dates[-1] + timedelta(days=1)).isoformat()),
        (f.end_label, (dates[-1] + timedelta(days=2)).isoformat()),
    ]

    seq = start_seq
    cases: list[TestCase] = []

    def add(title: str, steps: list[TestStep], expected: Expectation) -> None:
        nonlocal seq
        cases.append(TestCase(
            case_id=f"{spec.screen_id}-filter-{seq:03d}", screen_id=spec.screen_id,
            title=title, type="positive", steps=steps, expected=expected,
        ))
        seq += 1

    add(f"기간 조회 시 기간 내 주문 {len(in_rows)}건이 표시되는지 확인",
        _steps(range_fills),
        Expectation(type="result_count", count=len(in_rows), count_target=f.target_label))

    boundary_text = _unique_cell(by_date[start][0], spec.seed_rows, f.date_column)
    if boundary_text is not None:
        add("기간 시작일 당일 주문이 결과에 포함되는지 확인 (경계 포함)",
            _steps(range_fills), Expectation(type="text_visible", value=boundary_text))
    else:
        spec.warnings.append(
            "시드 표에서 시작 경계일 행을 유일하게 가리키는 값을 찾지 못해 "
            "경계 포함 케이스를 만들지 않았습니다."
        )
    absent_text = _unique_cell(by_date[dates[-1]][0], spec.seed_rows, f.date_column)
    if absent_text is not None:
        add("기간 밖 주문이 결과에 나오지 않는지 확인",
            _steps(range_fills), Expectation(type="text_absent", value=absent_text))
    else:
        spec.warnings.append(
            "시드 표에서 기간 밖 행을 유일하게 가리키는 값을 찾지 못해 "
            "기간 밖 배제 케이스를 만들지 않았습니다."
        )

    labels = {e.label for e in spec.elements}
    amount_label, _ = _seed_column_label(spec.seed_rows, _SEED_AMOUNT_RE)
    total_element = next(
        (e for e in spec.elements if e.label == "합계" and e.type == "text"), None
    )
    # 합계·정렬 재판정은 _seed_row_cases 가 무필터 케이스를 만들 수 있었던
    # 조건과 같을 때만 만든다. 조건이 무너진 경우의 경고는 _seed_row_cases 가
    # 이미 남기므로 여기서 또 남기지 않는다(같은 사실을 두 번 경고하지 않는다).
    if amount_label is not None and amount_label in labels and total_element is not None:
        add("기간 조회 후에도 합계가 표시된 금액의 합과 일치하는지 확인",
            _steps(range_fills),
            Expectation(type="sum_matches", sum_row_target=amount_label,
                        sum_total_target=total_element.label))
    if f.date_column in labels:
        add(f"기간 조회 후에도 {f.date_column} 이 최신순으로 정렬되는지 확인",
            _steps(range_fills),
            Expectation(type="sorted_desc", order_target=f.date_column))

    add("주문 없는 기간을 조회하면 0건인지 확인", _steps(empty_fills),
        Expectation(type="result_count", count=0, count_target=f.target_label))
    if f.empty_message:
        add(f"주문 없는 기간을 조회하면 '{f.empty_message}' 가 노출되는지 확인",
            _steps(empty_fills), Expectation(type="text_visible", value=f.empty_message))

    add(f"날짜를 비워 두고 조회하면 전체 {len(spec.seed_rows)}건이 표시되는지 확인",
        _steps([]),
        Expectation(type="result_count", count=len(spec.seed_rows),
                    count_target=f.target_label))
    return cases


def _unique_cell(row: dict[str, str], seed_rows: list[dict[str, str]], skip_col: str) -> Optional[str]:
    """시드 행 하나를 화면에서 유일하게 가리키는 셀 값 (열 순서대로 첫 번째).

    날짜 열은 제외한다 — 필터 입력값과 같은 문자열이라 '화면에 보인다/안 보인다'
    의 근거로 쓸 수 없다. 유일하지 않은 값(상태 열의 '배송완료' 등)도 제외한다 —
    다른 행 때문에 보이는 것을 이 행이 보인다고 착각하게 된다.
    """
    for col, val in row.items():
        v = val.strip()
        if col == skip_col or not v:
            continue
        if sum(1 for r in seed_rows if r.get(col, "").strip() == v) == 1:
            return v
    return None
```

`generate_cases` 267행 `cases.extend(_seed_row_cases(spec, start_seq=seq))` 다음 줄에 `cases.extend(_filter_cases(spec, start_seq=seq))` 추가 (다른 kind 와 seq 가 겹쳐도 kind 세그먼트가 달라 case_id 는 유일 — `_scenario_cases`/`_seed_row_cases` 와 같은 방식).

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_orders_cases.py -x -q` (기존 테스트가 케이스 총수를 단언하면 8개 증가를 반영해 갱신).
- [ ] **Step 5: 파급 확인** — `uv run pytest tests/test_generator.py tests/test_coverage.py tests/test_screen_coverage.py tests/test_case_selector.py -q`. 케이스 수 하드코딩이 깨지면 갱신(늘어난 이유를 주석 한 줄로).
- [ ] **Step 6: 커밋** — `git commit -am "기간 조회 케이스 8종을 시드와 자기일관성으로 만든다 — 입력↔재조회의 첫 검증"`

---

### Task 5: selector — filter 묶음 인지

**Files:**
- Modify: `src/prova/s2_case_generator/selector.py:382` (_GROUP_KINDS)·:386 (_KIND_WORDS)
- Test: `tests/test_widen_selection.py`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_widen_selection.py` 에 기존 R1/R3 테스트의 케이스 빌더를 따라:

```python
class TestFilterKind:
    def test_filter_묶음도_R1_로_채워진다(self):
        cases = [_case("orders-filter-004"), _case("orders-filter-005"), _case("orders-valid-001")]
        picked, widened = widen_selection(cases, ["orders-filter-004"], "기간 조회 확인해줘")
        assert {c.case_id for c in picked} >= {"orders-filter-004", "orders-filter-005"}

    def test_기간_날짜_필터가_kind_word_다(self):
        from prova.s2_case_generator.selector import _KIND_WORDS
        assert set(_KIND_WORDS["filter"]) == {"필터", "기간", "날짜"}
```

(`_case` 헬퍼는 파일의 기존 헬퍼를 그대로 쓴다 — 없으면 기존 테스트가 TestCase 를 만드는 코드를 복사.)

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_widen_selection.py -k Filter -x -q`
- [ ] **Step 3: 구현** — `_GROUP_KINDS` 에 `"filter"` 추가, `_KIND_WORDS` 에 `"filter": ("필터", "기간", "날짜"),` 추가 (기존 항목들 스타일 그대로 — 도구가 만드는 케이스 종류의 이름이라 기획서마다 낡지 않는다는 주석 원칙 유지).
- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_widen_selection.py tests/test_request_grounding.py -q`
- [ ] **Step 5: 커밋** — `git commit -am "선택 넓히기가 기간 조회 묶음을 안다 — filter kind"`

---

### Task 6: SUT — 필터 폼 + 결함 O3·O4

**Files:**
- Modify: `sut/templates/orders.html`
- Modify: `sut/app.py` (`render_orders`·`_good_orders_data`·`_bad_orders_data`·orders 라우트 4개·헤더 결함 표·`MSG_ORDERS_EMPTY`)
- Test: `tests/test_sut_orders.py`

**Interfaces:**
- Produces: `/{variant}/orders?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`. 폼은 GET, 라벨은 `<label>` 감싸기(aria-label 금지 — table 변형의 "aria-label 0개" 성질을 지킨다).

- [ ] **Step 1: 실패하는 테스트** — `tests/test_sut_orders.py` 에 (파일의 client/로그인 픽스처 방식 그대로):

```python
class TestDateFilter:
    RANGE = "?start_date=2026-08-03&end_date=2026-08-12"
    EMPTY = "?start_date=2026-08-16&end_date=2026-08-17"

    def test_good_은_경계_포함_3건이다(self, client):
        html = self._get(client, "good", self.RANGE)
        assert html.count("ORD-00") == 3
        assert "ORD-002" in html and "ORD-005" not in html

    def test_good_합계는_표시_행의_합이다(self, client):
        html = self._get(client, "good", self.RANGE)
        assert "557,000" in html  # 39,000+89,000+429,000

    def test_good_빈_기간은_문구를_노출한다(self, client):
        html = self._get(client, "good", self.EMPTY)
        assert "기간 내 주문이 없습니다." in html and "ORD-00" not in html

    def test_good_빈_값은_전체_5건이다(self, client):
        assert self._get(client, "good", "").count("ORD-00") == 5

    def test_bad_는_시작_경계일을_뺀다(self, client):
        html = self._get(client, "bad", self.RANGE)
        assert "ORD-002" not in html and html.count("ORD-00") == 2

    def test_bad_합계는_필터_전_값_그대로다(self, client):
        html = self._get(client, "bad", self.RANGE)
        assert "569,000" in html  # 무필터 O2 값 그대로 — O4

    def test_bad_도_빈_문구는_올바르다(self, client):
        assert "기간 내 주문이 없습니다." in self._get(client, "bad", self.EMPTY)

    def test_table_쌍둥이도_같은_필터_결과다(self, client):
        html = self._get(client, "table", self.RANGE)
        assert "aria-label" not in html
        assert html.count("ORD-00") == 3 and "ORD-002" in html
```

(`_get` 은 해당 variant 로 로그인 후 `/{variant}/orders{query}` 를 GET 해 text 를 돌려주는 헬퍼 — 기존 테스트의 로그인 코드를 재사용해 클래스에 하나 만든다.)

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_sut_orders.py -k DateFilter -x -q`
- [ ] **Step 3: 템플릿 구현** — `orders.html` `<h1>` 다음에:

```html
<!-- 필터 폼은 목록 마크업 밖이라 list/table 변형이 공유한다. 라벨은 label
     요소로 감싼다 — table 변형의 'aria-label 0개' 성질을 폼이 깨면 안 된다. -->
<form method="get" class="filter">
  <label>시작일 <input type="date" name="start_date" value="{{ start_date }}"></label>
  <label>종료일 <input type="date" name="end_date" value="{{ end_date }}"></label>
  <button type="submit">조회</button>
</form>
```

`{% endif %}`(마크업 분기 끝) 다음에:

```html
{% if not orders and empty_message %}
<p class="empty">{{ empty_message }}</p>
{% endif %}
```

CSS 에 `.filter { display:flex; gap:8px; margin-bottom:16px; font-size:13px; align-items:center; } .filter input { margin-left:4px; } .empty { color:#888; font-size:14px; }` 추가.

- [ ] **Step 4: 서버 구현** — `app.py` 메시지 상수들 옆에 `MSG_ORDERS_EMPTY = "기간 내 주문이 없습니다."`. 데이터 함수 교체:

```python
def _filter_rows(rows: list[dict], start: str, end: str, *, include_start: bool = True) -> list[dict]:
    """주문일(ISO 문자열 — 사전순=시간순)로 기간을 거른다. 빈 값은 그 방향 무제한."""
    def keep(o: dict) -> bool:
        d = o["주문일"]
        ok_start = not start or (start <= d if include_start else start < d)
        return ok_start and (not end or d <= end)
    return [o for o in rows if keep(o)]


def _good_orders_data(start: str = "", end: str = "") -> tuple[list[dict], int]:
    rows = sorted(_filter_rows(SEED_ORDERS, start, end),
                  key=lambda o: o["주문일"], reverse=True)
    return rows, sum(o["금액"] for o in rows)
```

`_bad_orders_data`:

```python
def _bad_orders_data(start: str = "", end: str = "") -> tuple[list[dict], int]:
    # O1: 오름차순(과거 → 최근)으로 정렬한다. 기획서는 내림차순을 요구한다.
    all_rows = sorted(SEED_ORDERS, key=lambda o: o["주문일"])
    # O2: 합계에서 마지막 표시 행(오름차순이라 ORD-005)의 금액을 뺀다.
    total = sum(o["금액"] for o in all_rows) - all_rows[-1]["금액"]
    # O3: 시작일 비교에서 등호가 빠졌다 — 시작일 당일 주문이 사라진다.
    # O4: 필터를 걸어도 합계를 다시 계산하지 않는다 — 필터 전 값(total) 그대로.
    rows = _filter_rows(all_rows, start, end, include_start=False)
    return rows, total
```

라우트 4개(good/table/bad/badtable)를 같은 모양으로 — good 예:

```python
@app.get("/good/orders", response_class=HTMLResponse)
def good_orders(request: Request, start_date: str = "", end_date: str = ""):
    if "session_good" not in request.cookies:
        return RedirectResponse("/good/login", status_code=303)
    rows, total = _good_orders_data(start_date, end_date)
    return render_orders(request, "good", rows, total,
                         start_date=start_date, end_date=end_date)
```

`render_orders` 시그니처에 `start_date: str = "", end_date: str = ""` 추가, context 에 `"start_date"`·`"end_date"`·`"empty_message": MSG_ORDERS_EMPTY if not rows else None` 전달. 헤더 docstring 결함 표에 O3·O4 두 줄 추가.

- [ ] **Step 5: 통과 확인** — `uv run pytest tests/test_sut_orders.py -x -q` (기존 TestTableMarkup 의 "aria-label 0개" 포함 전체 회귀).
- [ ] **Step 6: 커밋** — `git commit -am "SUT 주문조회에 날짜 필터를 단다 — 결함 O3(경계일 제외)·O4(합계 미재계산)"`

---

### Task 7: e2e — 관통 + 결함 매트릭스 + 쌍둥이 유지

**Files:**
- Modify: `tests/test_orders_e2e.py` (docstring·TestGood·TestBad·TestTableMarkup)

**Interfaces:**
- Consumes: MockLLM 이 골든(date_filter 포함)을 돌려주므로 파이프라인이 filter 케이스를 자동 생성·실행한다. 이 태스크가 S4 fill(`input[type=date]` ISO)·S5 (스텝 후 판정) 두 가정의 증명이다.

- [ ] **Step 1: 실패하는 테스트** — 헬퍼와 케이스 추가:

```python
def _filter_cases_of(report):
    return [v for v in report.cases if "-filter-" in v.case_id]

class TestGood:  # 기존 클래스에 추가
    def test_필터_케이스_여덟_개가_만들어져_전부_통과했다(self, good_run):
        report, _ = good_run
        cases = _filter_cases_of(report)
        assert len(cases) == 8
        fails = [c for c in cases if c.verdict != "PASS"]
        assert not fails, "\n".join(f"{c.case_id}: {c.failure_detail}" for c in fails)

class TestBad:  # 기존 클래스의 실패 집합 단언을 교체
    def test_실패는_O1_O2_O3_O4_의_케이스뿐이다(self, bad_run):
        report, _ = bad_run
        fails = {v.case_id: v for v in report.cases if v.verdict == "FAIL"}
        # 무필터 정렬(O1)·합계(O2) + 필터 건수/경계(O3)·합계(O4)·정렬(O1 지속)
        expected_types = [
            ("sorted_desc", False), ("sum_matches", False),          # O1·O2
            ("result_count", True), ("text_visible", True),          # O3 (건수·경계)
            ("sum_matches", True), ("sorted_desc", True),            # O4·O1 지속
        ]
        got = sorted((v.expected.type, "-filter-" in cid) for cid, v in fails.items())
        assert got == sorted(expected_types), fails.keys()
```

(verdict 객체가 expected 를 들고 있지 않으면 — 실제 필드를 확인해 case_id 의 kind 세그먼트와 title 로 같은 사실을 단언한다. 핵심 계약: **FAIL 이 정확히 6건이고, 그 6건이 위 여섯 검증**이라는 것. 빈 기간·빈 문구·빈 값 케이스는 bad 에서도 PASS — 결함 분리.)

TestTableMarkup 의 쌍 판정 동일성 단언은 케이스 집합이 커져도 자동으로 넓어지는 모양인지 확인하고, 케이스 수를 하드코딩했다면 filter 8건을 반영한다.

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_orders_e2e.py -x -q` (Task 6 까지 반영됐으면 이 시점에 이미 통과할 수도 있다 — 그 경우 단언이 실제로 8건·6건을 세는지 임시로 숫자를 틀어 확인하고 되돌린다).
- [ ] **Step 3: 통과 확인** — `uv run pytest tests/test_orders_e2e.py tests/test_real_markup_variants.py tests/test_pipeline_e2e.py -q`
- [ ] **Step 4: 리포트 눈 확인** — 실행 산출물의 리포트 HTML 에서 filter 케이스 6건 FAIL 사유에 판정 근거(두 합계값·깨진 정렬 쌍·기대 3 실측 2)가 실리는지 확인.
- [ ] **Step 5: 커밋** — `git commit -am "기간 조회를 파이프라인으로 관통한다 — good 8/8, bad 는 O1·O3·O4 만"`

---

### Task 8: 풀스위트 + 실모델 골든 + 푸시

- [ ] **Step 1: 실모델 골든** — 터널 확인(`uv run prova check`) 후 `uv run pytest tests/test_s1_golden.py -q`. orders 골든에 date_filter 가 실려도 declared 교정이 결정적이라 통과해야 한다. LLM 이 date_filter 를 요동치게 내도 교정이 덮는지 이 실행이 증명한다.
- [ ] **Step 2: 프로브 기대 목록 기계 갱신** — `scripts/probe_request_selection.py` 의 "화면 전 케이스" 류 기대 집합에 orders filter 케이스 id 를 추가. 파일 상단 주석과 `docs/measurements/request-selection-2026-08-22.md` 에 한 줄: "2026-08-24 filter 8종 추가로 집합 정의가 갱신됨 — 이후 수치는 B 9/10 과 1:1 비교 불가". 재측정은 하지 않는다(다음 실측정 때 함께).
- [ ] **Step 3: 풀스위트** — `uv run pytest -q` → 기대 858 + 신규 (약 30~35개), **skip 0**. 케이스 수·문서 수 하드코딩 실패가 나오면 하나씩 갱신.
- [ ] **Step 4: 비밀 스캔 + 푸시** — `git diff origin/main --stat` 확인 후 `git diff origin/main | grep -nE '168\.131|ssh -p [0-9]|jovyan@|kdw51@|PRIVATE KEY'` 가 0건이면 `git push origin feature/prova-pipeline` → `git checkout main && git merge --ff-only feature/prova-pipeline && git push origin main && git checkout feature/prova-pipeline`.

---

### Task 9: 문서

**Files:**
- Create: `docs/teaching/20-date-filter.md` (기존 노트 스타일 — 결정·측정·남은 것)
- Modify: `README.md` (결과 표에 filter 행·결함 O3/O4, 남은 것 갱신, 테스트 수, 설계 판단에 '경계일·병행 근거' 문단)
- Modify: `docs/README.md`·`docs/pr/00-reading-guide.md`·`docs/teaching/00-overview.md` (노트 수·테스트 수)
- Modify: `docs/teaching/overview.src.html` → `uv run python scripts/embed_media.py` 로 `overview.html` 재생성 (남은 것 표에서 날짜 필터 닫힘, 요약 절 추가)
- Modify: `docs/teaching/18-natural-language-request.md` 또는 19 — 남은 것에서 날짜 필터 항목 닫음

- [ ] **Step 1: 노트 20 작성** — 다룰 것: 왜 입력↔재조회가 새 검증 층인가, 병행 근거(시드/자기일관성) 결정, 기간 산정 규칙(양끝 하나씩), O3·O4 가 각각 어느 케이스에 잡히는가, 유형 '날짜' 보정(자동 채움 충돌), 홀드아웃 집합 정의 갱신 사실.
- [ ] **Step 2: 나머지 문서 갱신 + overview 재생성** — 수치는 Task 8 풀스위트 실측값으로.
- [ ] **Step 3: 커밋 + 푸시** — Task 8 Step 4 와 같은 절차(스캔 포함).
- [ ] **Step 4: 메모리 갱신** — `prova-implementation.md` 에 완료 기록(커밋 해시·수치), 다음 작업(Figma 재설계)을 남긴다.
