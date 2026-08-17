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
from prova.models import (
    Expectation,
    Flow,
    ScreenSpec,
    SpecDocument,
    TestCase,
    TestStep,
    UIElement,
)
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


def _collection_element(spec: ScreenSpec) -> Optional[UIElement]:
    """건수를 셀 반복 목록. 기획서가 목록 요소를 정의하지 않으면 None.

    None 일 때 건수 케이스를 만들지 않는 이유: 셀 대상이 없으면 무엇을 세야 할지
    추측해야 하고, 추측한 대상을 세면 그 숫자를 신뢰할 수 없다. 기획서가 건수를
    적어 두고 목록 요소는 정의하지 않은 상태는 기획서의 결함이므로
    rule_expander.spec_defects 가 경고로 알린다 — 조용히 검증을 빠뜨리지 않는다.
    """
    return next((e for e in spec.elements if e.type == "list"), None)


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

    cases.extend(_option_cases(spec, start_seq=seq))
    cases.extend(_placeholder_case(spec))
    cases.extend(_label_case(spec))
    cases.extend(_scenario_cases(spec, inputs, start_seq=seq))

    if llm is not None:
        _polish_titles(cases, spec, llm)
    return cases


def _scenario_cases(
    spec: ScreenSpec, inputs: list[UIElement], start_seq: int
) -> list[TestCase]:
    """기획서가 제시한 입력-결과 예시를 케이스로 만든다.

    위반값 생성을 거치지 않는다. 시나리오의 입력값은 기획서가 준 것이고, 코드가
    만들 수 있는 종류의 값이 아니다 — '노트북을 검색하면 3건' 은 규칙에서 유도되지
    않는다(Scenario 설명 참고).

    type 은 negative 가 아니라 positive 다. 규칙을 어긴 값이 아니라 **정상 입력에
    대한 정해진 결과**를 확인하는 것이기 때문이다. S5 의 판정이 케이스 유형으로
    뒤집히지 않게 하려면 이 구분이 맞아야 한다.

    시나리오에 없는 입력 요소는 정상값으로 채운다. 검색처럼 입력이 하나면 차이가
    없지만, 여러 입력 중 하나만 지정한 시나리오에서는 나머지가 비어 있으면 필수
    검증에 먼저 걸려 시나리오가 확인되지 않는다.
    """
    collection = _collection_element(spec)

    cases: list[TestCase] = []
    for i, scenario in enumerate(spec.scenarios):
        values, _ = resolve_values(inputs, overrides=dict(scenario.given))
        steps = _steps_for_case(spec, values)
        shown = ", ".join(f"{k}={v!r}" for k, v in scenario.given.items()) or "기본값"

        cases.append(TestCase(
            case_id=f"{spec.screen_id}-scenario-{start_seq + i:03d}",
            screen_id=spec.screen_id,
            title=f"기획서 예시: {shown} → {scenario.expect_text!r} 노출 확인",
            type="positive",
            steps=steps,
            expected=Expectation(type="text_visible", value=scenario.expect_text),
        ))

        # 건수 확인은 같은 케이스에 합치지 않고 한 건 더 만든다.
        #
        # 합치면 FAIL 하나가 두 가지를 뜻하게 된다 — 문구가 틀렸는지, 개수가
        # 틀렸는지. 그 둘은 원인도 고칠 곳도 다르다. 검색 결과가 3건인데 문구만
        # "검색 결과 2건" 으로 잘못 찍는 결함과, 문구는 맞는데 목록에 2개만
        # 렌더되는 결함은 다른 버그다. '한 케이스는 한 가지만 말한다' 는 이
        # 프로젝트의 원칙을 여기서도 지킨다.
        if scenario.expect_count is None or collection is None:
            continue
        cases.append(TestCase(
            case_id=f"{spec.screen_id}-count-{start_seq + i:03d}",
            screen_id=spec.screen_id,
            title=f"기획서 예시: {shown} → {collection.label} {scenario.expect_count}개 확인",
            type="positive",
            steps=steps,
            expected=Expectation(
                type="result_count",
                count=scenario.expect_count,
                count_target=collection.label,
            ),
        ))
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


# ---------------------------------------------------------------------------
# 흐름 케이스 — 화면을 이어서 밟는다
# ---------------------------------------------------------------------------


def generate_flow_cases(doc: SpecDocument) -> list[TestCase]:
    """문서가 선언한 흐름마다 케이스 하나를 만든다.

    ## 왜 화면별 케이스로는 부족한가

    회원가입 케이스가 전부 통과하고 로그인 케이스도 전부 통과하는데 **가입한 계정으로
    로그인이 안 되는** 구현이 있을 수 있다. 가입 화면이 입력을 올바르게 검증하고
    완료 화면까지 보여주면서 계정을 실제로 등록하지 않은 경우다. 결함이 화면 안이
    아니라 화면 사이에 있으므로, 이어서 밟아 봐야만 드러난다.

    ## 중간 화면마다 도착을 확인한다

    이 케이스의 위험은 하나뿐이다 — **마지막 화면에서 FAIL 이 났을 때 앞 화면 탓인지
    구분되지 않는 것.** 그래서 화면을 넘길 때마다 assert 스텝을 넣어 그 화면의 성공
    조건이 충족됐는지 확인한다. 앞 화면에서 끊기면 그 스텝의 실패로 기록되고,
    S5 는 '스텝이 끊기면 그 원인이 케이스 실패 원인' 규칙에 따라 그 화면을 지목한다.
    마지막 화면이 애먼 소리를 듣지 않는다.

    확인할 문구를 흐름 표에 다시 적게 하지 않는다 — 각 화면의 success_condition 을
    쓴다. 같은 사실을 두 곳에 적으면 언젠가 어긋난다.
    """
    cases: list[TestCase] = []
    for flow in doc.flows:
        screens = [doc.screen_by_id(sid) for sid in flow.screen_ids]
        if any(s is None for s in screens) or len(screens) < 2:
            # 없는 화면을 가리키는 흐름은 만들지 않는다. 그 사실은 S1 의
            # _document_warnings 가 이미 경고로 남겼다 — 조용히 빠지지는 않는다.
            continue
        cases.append(_flow_case(flow, screens))
    return cases


def _flow_case(flow: Flow, screens: list[ScreenSpec]) -> TestCase:
    steps: list[TestStep] = []
    seq = 1
    # 라벨 -> 값. 앞 화면에 넣은 값을 뒤 화면의 같은 라벨에 다시 넣는다.
    # 사람이 손으로 확인할 때 하는 일이 정확히 이것이다 — 가입에 쓴 이메일로
    # 로그인한다. element_id 가 아니라 라벨을 키로 쓰는 이유: 화면이 다르면
    # element_id 도 다를 수 있지만(signup.email vs login.user_email) 사용자가
    # 보는 라벨은 같다.
    carried: dict[str, str] = {}

    for i, screen in enumerate(screens):
        if i > 0:
            # 이 화면으로 '어떻게' 왔는지가 검증 대상이 될 수 있다.
            #
            # 기획서가 이동 방법을 적어 두지 않으면 주소로 직접 들어간다. 그때는
            # 화면을 잇는 요소가 검증되지 않는다 — 도구가 스스로 주소를 치므로
            # 완료 화면의 링크가 엉뚱한 곳을 가리켜도 흐름은 통과한다.
            via = flow.via[i - 1] if i - 1 < len(flow.via) else ""
            if via:
                steps.append(TestStep(seq=seq, action="click", target=via))
                seq += 1
                # 눌렀더니 정말 그 화면에 왔는지 본다. 링크가 엉뚱한 경로를
                # 가리키면 여기서 걸린다. 문구가 아니라 경로만 보는 이유: 도착
                # 직후의 화면은 아직 아무 동작도 하지 않은 상태이므로 기획서의
                # 성공 조건(제출 후 결과)을 요구하면 항상 실패한다.
                steps.append(TestStep(
                    seq=seq, action="assert",
                    target=f"{screen.screen_id} 도착",
                    expected=Expectation(type="redirect",
                                         url_contains=screen.url_path),
                ))
                seq += 1
            else:
                steps.append(TestStep(seq=seq, action="navigate",
                                      target=screen.url_path))
                seq += 1

        inputs = _fillable_inputs(screen)
        # 이어받은 값을 element_id 기준 override 로 바꾼다. resolve_values 를
        # 거치는 이유: 이어받은 값이 same_as 참조 대상이면 그 의존값(비밀번호 확인)도
        # 함께 다시 계산돼야 한다. dict 를 그대로 덮으면 일치 규칙이 깨진다.
        overrides = {
            e.element_id: carried[e.label] for e in inputs if e.label in carried
        }
        values, _ = resolve_values(inputs, overrides=overrides)

        if i == 0:
            steps.append(TestStep(seq=seq, action="navigate", target=screen.url_path))
            seq += 1
        for element in inputs:
            steps.append(_input_step(seq, element, values.get(element.element_id, "")))
            seq += 1
        submit = _submit_element(screen)
        if submit:
            steps.append(TestStep(seq=seq, action="click", target=submit.label))
            seq += 1

        for element in inputs:
            carried[element.label] = values.get(element.element_id, "")

        if i < len(screens) - 1:
            # 도착 확인. 실패하면 이 스텝이 끊긴 것으로 기록되어 이 화면이 지목된다.
            steps.append(TestStep(
                seq=seq, action="assert",
                target=f"{screen.screen_id} 성공",
                expected=parse_success_expectation(screen),
            ))
            seq += 1

    last = screens[-1]
    expected = (Expectation(type="text_visible", value=flow.expect_text)
                if flow.expect_text else parse_success_expectation(last))
    path = " → ".join(s.screen_id for s in screens)

    # 이동 방법을 제목에 넣는다. 같은 화면 쌍을 두 흐름이 밟을 수 있고(하나는
    # 링크를 눌러, 하나는 주소로), 그때 제목이 같으면 리포트에서 어느 쪽이
    # 실패했는지 구분할 수 없다. 둘이 확인하는 것은 서로 다르다 —
    # 하나는 화면을 잇는 요소, 하나는 이어진 상태다.
    how = (f"'{', '.join(flow.via)}' 를 눌러 이동" if flow.via else "주소로 이동")

    return TestCase(
        case_id=f"flow-{_slug(flow.flow_id)}-001",
        screen_id=last.screen_id,
        flow_id=flow.flow_id,
        title=flow.title or f"흐름 {path} ({how})",
        type="positive",
        steps=steps,
        expected=expected,
    )


def _option_cases(spec: ScreenSpec, start_seq: int) -> list[TestCase]:
    """선택 요소마다 '기획서가 적은 항목이 화면에 다 있는가' 를 확인하는 케이스.

    ## 왜 필요한가

    기획서의 '선택 목록: 검색, 지인 추천, 광고' 는 지금까지 **정상 케이스가 넣을 값을
    고르는 데만** 쓰였다. 첫 항목을 골라 넣고 그것이 있으면 통과한다. 그래서 화면에
    '지인 추천' 이 빠져 있어도 아무 일도 일어나지 않았다.

    기획서에 적혀 있는데 아무도 확인하지 않는 항목이 있으면 그건 도구의 구멍이다.

    ## 왜 요소마다 한 건인가

    선택 요소를 조작하는 케이스마다 대조하면, 항목 하나가 빠진 결함이 그 요소를 쓰는
    모든 케이스에서 터진다(회원가입은 14건이다). 결함 하나가 FAIL 14건이 되면 리포트를
    읽는 사람이 규모를 잘못 읽는다.

    스텝은 navigate 하나뿐이다. 선택 항목은 화면에 들어간 시점에 이미 정해져 있으므로
    입력하고 제출할 이유가 없다 — 필요 없는 스텝은 실패 지점만 늘린다.
    """
    cases: list[TestCase] = []
    selects = [e for e in spec.elements if e.type == "select" and e.options]
    for i, element in enumerate(selects):
        cases.append(TestCase(
            case_id=f"{spec.screen_id}-options-{_slug(element.element_id)}"
                    f"-{start_seq + i:03d}",
            screen_id=spec.screen_id,
            title=f"{element.label} 선택 목록이 기획서와 같은지 확인",
            type="positive",
            target_element=element.element_id,
            steps=[TestStep(seq=1, action="navigate", target=spec.url_path)],
            expected=Expectation(
                type="options_present",
                options=list(element.options),
                option_target=element.label,
            ),
        ))
    return cases


def _placeholder_case(spec: ScreenSpec) -> list[TestCase]:
    """입력 안내 문구가 기획서와 같은지 확인하는 케이스. 화면당 한 건.

    ## 왜 요소마다가 아니라 화면당 한 건인가

    선택 목록(_option_cases)은 요소마다 한 건인데 여기는 화면당 한 건이다. 기준은
    '무엇이 한 가지 확인인가' 다.

    선택 목록은 요소 하나가 목록 하나를 갖는다. 목록이 길고, 어느 항목이 빠졌는지가
    그 요소만의 사실이므로 요소가 곧 확인 단위다.

    안내 문구는 요소마다 짧은 문구 하나다. 요소마다 케이스를 만들면 회원가입에서만
    4건이 늘어나는데, 각 케이스가 확인하는 것은 문구 한 줄이다. **리포트에 늘어나는
    줄 수가 그 정보량보다 많다.** 대신 실패 사유에 어느 요소가 다른지 모두 적어,
    한 건으로도 고칠 곳이 좁혀지게 한다.

    스텝은 navigate 하나뿐이다 — 안내 문구는 입력 전에 보이는 글자이므로 채우고
    제출할 이유가 없다. 오히려 값을 채우면 placeholder 가 가려진다.
    """
    declared = {e.label: e.placeholder for e in spec.elements if e.placeholder}
    if not declared:
        return []
    return [TestCase(
        case_id=f"{spec.screen_id}-placeholders-001",
        screen_id=spec.screen_id,
        title="입력 안내 문구가 기획서와 같은지 확인",
        type="positive",
        steps=[TestStep(seq=1, action="navigate", target=spec.url_path)],
        expected=Expectation(type="placeholders_match", placeholders=declared),
    )]


def _label_case(spec: ScreenSpec) -> list[TestCase]:
    """기획서의 라벨로 요소를 찾을 수 있는지 확인하는 케이스. 화면당 한 건.

    ## 왜 이 케이스가 필요한가

    2차 경로(화면 이미지로 찾기)를 켜면 라벨로 못 찾은 요소도 보정으로 조작되어 케이스가
    통과한다. 그러면 **'기획서의 라벨로 요소를 지목할 수 없다' 는 사실이 리포트에서
    사라진다.** 그건 기획-구현 불일치이면서 접근성 결함이다 — 스크린리더 사용자도 그
    요소가 무엇인지 알 수 없다.

    보정은 케이스를 살리는 장치이고, 지적은 그대로 남아야 한다. 그래서 보정 여부와
    **무관하게** 라벨로 찾을 수 있는지를 따로 확인한다.

    ## 무엇을 확인 대상으로 삼는가

    그 화면의 케이스가 실제로 조작하는 요소만 본다 — 입력 요소들과 제출 버튼이다.

    빼는 것이 둘 있다.

    - **목록(list)**: 결과 목록은 동작의 산물이라 초기 화면에 없는 것이 정상이다.
      넣으면 검색 화면이 늘 실패한다(오탐).
    - **링크(link)**: 회원가입의 '로그인하러 가기' 는 완료 화면에 있고 /signup 에는
      없다. 초기 화면에서 찾으면 없는 것이 맞다. 그 요소는 흐름 케이스가 눌러 보며
      확인한다.

    확인할 수 없는 것을 확인한다고 하지 않는 것이 이 도구에서 지키는 선이다.
    """
    labels = [e.label for e in _fillable_inputs(spec) if e.label]
    submit = _submit_element(spec)
    if submit and submit.label:
        labels.append(submit.label)
    if not labels:
        return []
    return [TestCase(
        case_id=f"{spec.screen_id}-labels-001",
        screen_id=spec.screen_id,
        title="기획서의 라벨로 요소를 찾을 수 있는지 확인",
        type="positive",
        steps=[TestStep(seq=1, action="navigate", target=spec.url_path)],
        expected=Expectation(type="labels_findable", labels=labels),
    )]
