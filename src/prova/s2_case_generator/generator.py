"""S2 후반부 — 위반값을 실행 가능한 TestCase 로 조립한다.

## 기대 문구는 규칙마다 출처가 다르다

이 모듈에서 가장 조심해야 하는 부분이다. 케이스의 expected 가 틀리면 구현이
멀쩡한데도 FAIL 이 뜨거나(오탐), 구현이 틀렸는데 PASS 가 뜬다(미탐).

    형식·길이·문자종류 위반  ->  UIElement.error_message
                               (기획서 §2 표의 '에러 메시지' 열)
    required 위반           ->  ScreenSpec.required_message
                               (기획서 §4 실패 조건의 화면 공통 문구)
    문구를 알 수 없을 때      ->  error_shown 으로 격하
                               (문구를 억측하면 오탐이 된다)

마지막 항목이 중요하다. 기대 문구를 모를 때 그럴듯한 문구를 지어 넣으면, 실제
화면에 올바른 에러가 떠 있어도 문구가 달라 FAIL 이 된다. QA 도구에서 오탐은
미탐보다 치명적이다 — 개발자가 도구를 신뢰하지 않게 되면 진짜 결함 보고도
무시되기 시작한다. 그래서 확신이 없으면 '에러가 떴는지'만 확인한다.

## LLM 의 역할은 제목뿐이다

케이스의 입력값·스텝·기대는 전부 코드가 결정한다. LLM 에는 케이스 제목을
자연어로 다듬는 일만 맡긴다(선택). 제목이 틀려도 판정은 바뀌지 않으므로
LLM 실패가 검증 결과를 오염시키지 않는다. llm=None 이면 규칙 기반 제목을 쓴다.
"""

from __future__ import annotations

import re
from typing import Optional

from prova.llm.base import LLMClient, LLMError
from prova.models import Expectation, ScreenSpec, TestCase, TestStep, UIElement
from prova.s2_case_generator.rule_expander import (
    RULE_LABELS,
    resolve_values,
    violations_for_element,
)

# 성공 조건 문장에서 이동 경로와 노출 문구를 뽑는 패턴.
#
# LLM 에 맡기지 않는 이유: success_condition 은 이미 S1 이 정리한 짧은 문장이고,
# 여기서 필요한 건 경로(/로 시작하는 토큰)와 인용부호 안 문구다. 둘 다 표면
# 패턴으로 잡히므로 추론이 필요 없다.
_PATH_RE = re.compile(r"(/[a-zA-Z0-9_\-/]+)")
_QUOTED_RE = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{2,40})[\"'“”‘’]")


def _fillable_inputs(spec: ScreenSpec) -> list[UIElement]:
    """입력 가능한 요소만. 버튼·링크·텍스트는 값을 채우지 않는다."""
    return [e for e in spec.elements if e.type in ("input", "select", "checkbox")]


def _submit_element(spec: ScreenSpec) -> Optional[UIElement]:
    """폼을 제출하는 요소. 첫 번째 버튼을 쓴다.

    화면에 버튼이 여럿이면(예: '로그인' 과 '취소') 순서에 의존하게 되는데,
    기획서의 요소 정의 순서가 곧 화면 순서라는 가정이 깔린다. 버튼이 여러 개인
    화면을 다루게 되면 이 가정을 명시적 지정으로 바꿔야 한다.
    """
    return next((e for e in spec.elements if e.type == "button"), None)


def parse_success_expectation(spec: ScreenSpec) -> Expectation:
    """success_condition 문장에서 정상 케이스의 기대를 만든다.

    경로와 문구를 둘 다 찾으면 둘 다 검증한다(더 강한 확인). 하나만 찾으면
    그것만, 아무것도 못 찾으면 url_path 를 벗어났는지만 본다.
    """
    text = spec.success_condition or ""
    paths = [p for p in _PATH_RE.findall(text) if p != spec.url_path]
    quoted = _QUOTED_RE.findall(text)

    return Expectation(
        type="toast_or_redirect",
        value=quoted[0].strip() if quoted else "",
        url_contains=paths[0] if paths else None,
    )


def _required_message_for(element: UIElement, spec: ScreenSpec) -> Optional[str]:
    """필수 입력 위반 시 기대할 문구.

    기본은 화면 공통 문구다 (§4 실패 조건). 요소의 error_message 는 대개 형식
    검증용 문구이므로 required 에 쓰면 어긋난다.

    예외가 하나 있다. **그 요소에 다른 검증 규칙이 없으면 error_message 는
    필수 여부에 대한 문구일 수밖에 없다.** 회원가입 화면의 '약관 동의' 가
    그렇다 — 체크박스에 형식 검증이 있을 수 없으니 "약관에 동의해야 합니다." 는
    미동의 상태의 문구다. 이때 화면 공통 문구를 쓰면 구현이 옳아도 문구가 달라
    FAIL 이 되어 오탐이 된다.
    """
    if element.error_message and not element.constraints:
        return element.error_message
    return spec.required_message or element.error_message


def _expectation_for_violation(
    element: UIElement, rule: str, spec: ScreenSpec
) -> Expectation:
    """위반 케이스의 기대. 문구 출처가 규칙에 따라 다르다 (모듈 설명 참고)."""
    if rule == "required":
        message = _required_message_for(element, spec)
    else:
        message = element.error_message

    if message:
        return Expectation(type="error_message", value=message)
    # 문구를 모를 때는 격하한다. 억측한 문구로 오탐을 만드는 것보다,
    # '에러가 떴고 이동하지 않았다' 만 확인하는 편이 낫다.
    return Expectation(type="error_shown", value="")


def _input_step(seq: int, element: UIElement, value: str) -> TestStep:
    """요소 유형에 맞는 입력 스텝 하나.

    체크박스에 fill() 을 부르면 Playwright 가 조작 오류로 실패한다. 그러면
    '약관 미동의 시 에러가 뜨는가' 를 검증하려던 케이스가 요소 조작 실패로
    뭉개져, 구현에 결함이 있는지 없는지 알 수 없게 된다. 그래서 유형별로
    액션을 나눈다. 빈 값은 '체크 해제 / 선택 안 함' 을 뜻한다.
    """
    if element.type == "checkbox":
        return TestStep(seq=seq, action="check" if value else "uncheck",
                        target=element.label)
    if element.type == "select":
        return TestStep(seq=seq, action="select", target=element.label, value=value)
    return TestStep(seq=seq, action="fill", target=element.label, value=value)


def _steps_for_case(
    spec: ScreenSpec,
    values: dict[str, str],
) -> list[TestStep]:
    """navigate -> 입력 채우기 -> 제출 순서로 스텝을 만든다.

    target 은 selector 가 아니라 라벨이다. 실제 요소로 바꾸는 일은 S3 가 한다.
    """
    steps = [TestStep(seq=1, action="navigate", target=spec.url_path)]
    seq = 2
    for element in _fillable_inputs(spec):
        steps.append(_input_step(seq, element, values.get(element.element_id, "")))
        seq += 1
    submit = _submit_element(spec)
    if submit:
        steps.append(TestStep(seq=seq, action="click", target=submit.label))
    return steps


def _slug(text: str) -> str:
    """case_id 에 쓸 안전한 토큰. 한글은 그대로 두면 파일 경로에 쓰기 곤란하다."""
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "-", text).strip("-").lower()
    return s or "x"


def _title_for_violation(element: UIElement, rule: str, value: str) -> str:
    label = RULE_LABELS.get(rule, rule)
    if rule == "required":
        if element.type == "checkbox":
            return f"{element.label} 미체크 — 필수 동의 검증 확인"
        if element.type == "select":
            return f"{element.label} 미선택 — 필수 선택 검증 확인"
        return f"{element.label} 미입력 — 필수 입력 검증 확인"
    return f"{element.label} {label} 규칙 위반 (입력값 {value!r}) — 규칙 강제 여부 확인"


def generate_cases(
    spec: ScreenSpec,
    llm: Optional[LLMClient] = None,
) -> list[TestCase]:
    """ScreenSpec 을 TestCase 목록으로 전개한다.

    구성: 정상 1건 + 규칙별 위반 N건. 정상 케이스를 먼저 두는 이유는, 정상
    케이스가 실패하면 그 화면 자체가 동작하지 않는다는 뜻이어서 나머지 위반
    케이스의 결과를 해석할 근거가 사라지기 때문이다. 리포트를 읽는 사람이
    맨 위에서 그 사실을 먼저 보게 된다.
    """
    cases: list[TestCase] = []
    inputs = _fillable_inputs(spec)

    # --- 정상 케이스: 모든 규칙을 만족하는 값 ---
    valid_values, _ = resolve_values(inputs)
    cases.append(TestCase(
        case_id=f"{spec.screen_id}-valid-001",
        screen_id=spec.screen_id,
        title=f"정상 {spec.screen_name} (모든 입력 규칙 충족)",
        type="positive",
        steps=_steps_for_case(spec, valid_values),
        expected=parse_success_expectation(spec),
    ))

    # --- 위반 케이스: 규칙 하나당 한 건 ---
    seq = 2
    for element in inputs:
        ref_id = element.constraints.get("same_as")
        ref_value = valid_values.get(ref_id) if ref_id else None

        for violation in violations_for_element(element, ref_value):
            # 대상 요소만 위반값으로 바꾸고 나머지는 정상값을 넣는다.
            # 이렇게 해야 실패 원인이 이 요소의 이 규칙으로 좁혀진다.
            #
            # 값을 다시 해석하는 이유(dict 복사가 아닌 이유): 이 요소를 참조하는
            # same_as 값이 있으면 그것도 위반값 기준으로 다시 계산돼야 한다.
            # 비밀번호에 위반값을 넣고 비밀번호 확인을 원래 값으로 두면 일치
            # 규칙까지 함께 깨져 FAIL 원인이 둘로 갈린다.
            values, _ = resolve_values(inputs, overrides={element.element_id: violation.value})

            cases.append(TestCase(
                case_id=f"{spec.screen_id}-{_slug(element.element_id)}"
                        f"-{_slug(violation.rule)}-{seq:03d}",
                screen_id=spec.screen_id,
                title=_title_for_violation(element, violation.rule, violation.value),
                type="negative",
                violates=violation.rule,
                target_element=element.element_id,
                steps=_steps_for_case(spec, values),
                expected=_expectation_for_violation(element, violation.rule, spec),
            ))
            seq += 1

    if llm is not None:
        _polish_titles(cases, spec, llm)
    return cases


# ---------------------------------------------------------------------------
# 제목 다듬기 (선택) — 실패해도 판정에 영향이 없다
# ---------------------------------------------------------------------------

_TITLES_SCHEMA = {
    "title": "CaseTitles",
    "type": "object",
    "properties": {
        "titles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["case_id", "title"],
            },
        }
    },
    "required": ["titles"],
}

_TITLE_SYSTEM = """\
당신은 QA 테스트 케이스의 제목을 다듬는 편집자입니다.
주어진 케이스 목록의 제목을 한국어로 자연스럽고 간결하게 고쳐 주세요.

규칙:
- case_id 는 절대 바꾸지 마세요.
- 무엇을 검증하는 케이스인지 한눈에 보이게 쓰세요.
- 30자 이내로, 명사형으로 끝내세요.
- 입력값이나 규칙 이름을 임의로 바꾸지 마세요.
"""


def _polish_titles(cases: list[TestCase], spec: ScreenSpec, llm: LLMClient) -> None:
    """LLM 으로 케이스 제목을 다듬는다. 실패하면 규칙 기반 제목을 유지한다.

    제목은 사람이 리포트를 읽는 편의를 위한 것이고 판정 근거가 아니다. 그래서
    여기서 예외가 나도 파이프라인을 세우지 않는다. 다만 조용히 넘기지는 않고
    spec.warnings 에 남겨, 리포트를 보는 사람이 제목이 다듬어지지 않은 이유를
    알 수 있게 한다.
    """
    listing = "\n".join(f"- {c.case_id}: {c.title}" for c in cases)
    try:
        raw = llm.complete_json(
            system=_TITLE_SYSTEM,
            user=f"화면: {spec.screen_name}\n\n케이스 목록:\n{listing}\n\n출력 JSON:",
            schema=_TITLES_SCHEMA,
            max_tokens=1024,
        )
    except LLMError as exc:
        spec.warnings.append(f"케이스 제목 다듬기를 건너뛰었습니다: {exc}")
        return

    by_id = {c.case_id: c for c in cases}
    for item in raw.get("titles", []):
        case = by_id.get(item.get("case_id", ""))
        new_title = (item.get("title") or "").strip()
        if case and new_title:
            case.title = new_title
