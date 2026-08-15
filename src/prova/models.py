"""Prova 데이터 모델 — 서비스명세서 §3의 타입 계약.

이 파일이 파이프라인 전체의 계약이다. S1~S6의 각 단계는 여기 정의된 타입을
입력으로 받아 다음 타입을 출력한다:

    ScreenSpec -> TestCase[] -> ElementLocation -> StepResult[] -> Verdict -> TestReport

명세서는 TypedDict로 규정했으나 pydantic BaseModel을 쓴다. 이유는 두 가지다.
1) LLM 출력 검증: vLLM의 guided_json에 넘길 JSON Schema를 model_json_schema()로
   그대로 뽑아낼 수 있다. TypedDict는 런타임 검증을 해주지 않는다.
2) 필드 오타·타입 불일치를 실행 시점에 즉시 잡는다.

로그인 화면만 검증하는 1차 목표라도 타입은 명세서 전체를 정의한다.
회원가입·검색으로 확장할 때 이 파일을 다시 손대지 않기 위해서다.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# S1 · 설계 문서에서 추출한 화면 명세
# ---------------------------------------------------------------------------

ElementType = Literal["input", "button", "link", "select", "checkbox", "text"]


class UIElement(BaseModel):
    """화면을 구성하는 UI 요소 하나.

    constraints가 이 프로젝트의 핵심 필드다. 기획서에 적힌 입력 검증 규칙
    (비밀번호 복잡도, 이메일 형식 등)이 여기 담기고, S2가 이 규칙 하나하나를
    '위반 케이스'로 전개해서 구현이 규칙을 실제로 강제하는지 확인한다.

    지원하는 constraints 키:
        format          "email" 등 형식 지정
        min_length      최소 길이
        max_length      최대 길이
        require_uppercase / require_lowercase / require_digit / require_special
                        해당 문자 종류의 최소 개수
        pattern         정규식
    """

    element_id: str
    type: ElementType
    label: str
    required: bool = False
    constraints: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    placeholder: Optional[str] = None


class ScreenSpec(BaseModel):
    """설계 문서에서 추출한 화면 단위 명세. S1의 출력.

    1화면 = 1객체. warnings에는 파싱하지 못한 부분을 기록해 부분 결과를 유지한다
    (명세서 §2-S1 실패 처리).
    """

    screen_id: str
    screen_name: str
    url_path: str
    elements: list[UIElement] = Field(default_factory=list)
    success_condition: str = ""
    failure_conditions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def element_by_id(self, element_id: str) -> Optional[UIElement]:
        return next((e for e in self.elements if e.element_id == element_id), None)


# ---------------------------------------------------------------------------
# S2 · 테스트 케이스
# ---------------------------------------------------------------------------

ActionType = Literal["navigate", "fill", "click", "select", "wait", "assert"]
CaseType = Literal["positive", "negative", "boundary"]

# expected.type 이 가질 수 있는 값
ExpectedType = Literal["toast_or_redirect", "error_message", "redirect", "text_visible"]


class Expectation(BaseModel):
    """케이스의 기대 결과.

    negative 케이스에서는 대체로 type='error_message' 이고, value에 기획서에
    적힌 에러 문구가 들어간다. 그 문구가 화면에 나타나지 않으면 -> 구현이 규칙을
    강제하지 않는다는 뜻이므로 FAIL 이다. 이게 Prova가 증명하려는 바로 그것이다.
    """

    type: ExpectedType
    value: str = ""


class TestStep(BaseModel):
    """실행 단위 하나.

    target은 selector가 아니라 '이메일', '로그인' 같은 자연어 라벨이다.
    실제 요소로 변환하는 일은 S3(Grounder)가 맡는다. 이렇게 분리해두면
    같은 TestCase를 selector 방식과 VLM 방식 양쪽으로 실행해 비교할 수 있다.
    """

    seq: int
    action: ActionType
    target: str = ""
    value: Optional[str] = None
    expected: Optional[Expectation] = None


class TestCase(BaseModel):
    """하나의 검증 시나리오. S2의 출력.

    violates에는 이 케이스가 위반하는 규칙을 '하나만' 적는다. 명세서 예시는
    require_uppercase와 require_special을 동시에 위반시켰는데, 그러면 FAIL이
    떴을 때 어느 규칙이 미구현인지 분리되지 않는다. 규칙당 케이스 하나가
    원칙이다 (계획서 '핵심 설계 판단 1').
    """

    case_id: str
    screen_id: str
    title: str
    type: CaseType
    violates: Optional[str] = None
    target_element: Optional[str] = None  # violates 대상 element_id
    steps: list[TestStep] = Field(default_factory=list)
    expected: Expectation


# ---------------------------------------------------------------------------
# S3 · 요소 탐지 결과
# ---------------------------------------------------------------------------


class ElementLocation(BaseModel):
    """자연어 target을 실제 조작 가능한 위치로 변환한 결과. S3의 출력.

    1차 범위는 method='selector'만 쓴다. bbox/confidence는 2차 VLM fallback을
    위해 미리 자리를 잡아둔 필드다.
    """

    target: str
    method: Literal["selector", "vlm"] = "selector"
    selector: Optional[str] = None
    bbox: Optional[list[int]] = None  # [x, y, w, h]
    confidence: float = 1.0
    healed: bool = False
    strategy: Optional[str] = None  # 어느 탐지 전략이 적중했는지 (평가용)


# ---------------------------------------------------------------------------
# S4 · 실행 결과
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    """스텝 하나의 실행 결과. S4의 출력."""

    seq: int
    action: str
    target: str = ""
    status: Literal["ok", "error"] = "ok"
    elapsed_ms: int = 0
    screenshot: Optional[str] = None
    dom_snapshot: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    location: Optional[ElementLocation] = None


# ---------------------------------------------------------------------------
# S5 · 판정 / S6 · 리포트
# ---------------------------------------------------------------------------

FailureCategory = Literal[
    "element_not_found",
    "input_error",
    "assertion_mismatch",
    "timeout",
    "page_error",
    "unknown",
]


class Verdict(BaseModel):
    """한 케이스의 PASS/FAIL 판정과 근거. S5의 출력.

    evidence에는 '왜 그렇게 판정했는지'를 사람이 확인할 수 있는 재료를 넣는다.
    기대값, 실제 화면에서 찾은 텍스트, 최종 URL, 스크린샷 경로.
    리포트 완결성(명세서 §9, 목표 100%)이 이 필드에 달려 있다.
    """

    case_id: str
    title: str = ""
    type: CaseType = "positive"
    verdict: Literal["PASS", "FAIL"]
    violates: Optional[str] = None
    evidence: dict = Field(default_factory=dict)
    failure_category: Optional[FailureCategory] = None
    failure_detail: Optional[str] = None
    healed: bool = False
    elapsed_ms: int = 0
    step_results: list[StepResult] = Field(default_factory=list)


class TestReport(BaseModel):
    """실행 전체의 최종 리포트. S6의 출력."""

    run_id: str
    target_url: str
    spec_source: str = ""
    summary: dict = Field(default_factory=dict)  # {total, pass, fail, healed, pass_rate}
    cases: list[Verdict] = Field(default_factory=list)
    created_at: str = ""

    @staticmethod
    def summarize(verdicts: list[Verdict]) -> dict:
        total = len(verdicts)
        passed = sum(1 for v in verdicts if v.verdict == "PASS")
        return {
            "total": total,
            "pass": passed,
            "fail": total - passed,
            "healed": sum(1 for v in verdicts if v.healed),
            "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        }
