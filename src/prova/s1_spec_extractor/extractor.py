"""S1 후반부 — 추출한 텍스트를 ScreenSpec 으로 구조화한다.

## 이 단계가 실패하면 파이프라인 전체가 무의미해진다

Prova 가 증명하려는 명제는 "기획서에 적힌 검증 규칙이 구현에 빠져 있으면
짚어낸다" 이다. 그 규칙이 담기는 곳이 UIElement.constraints 다. 여기서 규칙
하나를 놓치면 S2 가 그 규칙의 위반 케이스를 만들지 않고, 결과적으로 구현이
그 규칙을 빠뜨렸어도 리포트는 초록불이 된다. **조용한 오탐**이라 가장 위험하다.

그래서 프롬프트는 constraints 추출에 집중하고, 회귀 테스트(golden 비교)도
constraints 를 가장 엄격하게 본다.

## 자연어 규칙 -> constraints 키 매핑

기획서는 "8자 이상, 대문자 1자 이상, 특수문자 1자 이상" 처럼 사람 말로 쓰인다.
이걸 {"min_length": 8, "require_uppercase": 1, "require_special": 1} 로 옮기는
것이 LLM 의 일이다. 매핑 규칙을 프롬프트에 표로 명시하고 few-shot 예시를 준다.
자유롭게 판단하게 두면 min_len / minLength / length_min 처럼 키 이름이 흔들리고,
그러면 S2 의 rule_expander 가 규칙을 인식하지 못한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from prova.llm.base import LLMClient, LLMError
from prova.models import Flow, Scenario, ScreenSpec, SpecDocument
from prova.s1_spec_extractor.pdf_parser import ParsedDocument, parse_pdf

SYSTEM_PROMPT = """\
당신은 웹 서비스 화면기획서를 읽고 QA 테스트에 쓸 구조화 명세를 만드는 전문가입니다.
주어진 기획서 텍스트에서 화면 정보와 UI 요소, 특히 **입력 검증 규칙**을 정확히 추출하세요.

## 가장 중요한 규칙: constraints 를 빠뜨리지 마세요

입력 검증 규칙은 이 작업의 핵심입니다. 규칙 하나를 놓치면 그 규칙이 구현에서
빠졌는지 확인할 수 없게 됩니다. 기획서에 적힌 모든 검증 규칙을 아래 표의 키로
정확히 옮기세요.

| 기획서 표현 | constraints 키 | 값 |
|---|---|---|
| 이메일 형식 | format | "email" |
| N자 이상 / 최소 길이 N자 | min_length | N (정수) |
| N자 이하 / 최대 길이 N자 | max_length | N (정수) |
| 대문자 N자 이상 포함 | require_uppercase | N (정수) |
| 소문자 N자 이상 포함 | require_lowercase | N (정수) |
| 숫자 N자 이상 포함 | require_digit | N (정수) |
| 특수문자 N자 이상 포함 | require_special | N (정수) |
| 정규식 패턴 | pattern | 정규식 문자열 |
| 다른 항목과 같은 값 (비밀번호 확인 등) | same_as | 그 항목의 element_id (문자열) |

키 이름을 바꾸거나 새로 만들지 마세요. 표에 없는 규칙은 constraints 에 넣지 말고
failure_conditions 에 문장으로 남기세요.

same_as 는 값 하나만 봐서는 판정할 수 없는 규칙이므로 특히 주의하세요. "비밀번호와
동일", "위에 입력한 값과 같아야 함" 같은 표현이 나오면 그 대상 요소의 element_id 를
값으로 넣습니다. 라벨이 아니라 element_id 입니다.

## 두 번째로 중요한 규칙: UI 요소 표의 행을 하나도 빠뜨리지 마세요

요소 표에 행이 7개면 elements 도 7개여야 합니다. 특히 **검증 규칙과 에러
메시지가 모두 '-' 인 행(버튼·링크)을 생략하지 마세요.** 그 행이 폼을 제출하는
요소입니다. 버튼이 빠지면 테스트가 아무것도 제출하지 못해, 구현이 멀쩡해도 모든
케이스가 실패로 보고됩니다.

## 그 밖의 규칙

- element_id: 기획서에 요소 ID 가 있으면 **한 글자도 바꾸지 말고 그대로** 쓰세요.
  공백을 넣지 말고, 표에 적힌 문자를 그대로 옮깁니다 (password_confirm 은
  password_confirm 입니다). 기획서에 ID 가 없으면 라벨에서 영문 snake_case 로
  만드세요 (이메일 -> email, 로그인 버튼 -> login_btn).
- type: 입력란은 "input", 버튼은 "button", 링크는 "link", 선택은 "select",
  체크박스는 "checkbox", 표시 전용 텍스트는 "text", **반복 목록은 "list"**.
  요소 표의 '유형' 열에 적힌 그대로 옮기세요 (목록 -> list). 검색 결과 목록처럼
  항목이 여러 개 반복되는 영역이 "list" 입니다.
- required: 기획서에 '필수' 로 표시된 요소만 true.
- options: type 이 "select" 인 요소의 선택 항목을 순서대로 담으세요. 기획서의
  '선택 목록: A, B, C' 같은 표현에서 A, B, C 를 뽑습니다. '선택하세요' 처럼
  값이 아닌 안내 문구는 넣지 마세요. select 가 아닌 요소는 빈 배열로 두세요.
  이 목록이 비면 정상 케이스가 무엇을 골라야 할지 알 수 없게 됩니다.
- error_message: 그 요소의 검증 실패 시 노출할 문구를 **기획서에 적힌 그대로**
  옮기세요. 문구를 다듬거나 요약하지 마세요. 이 문구가 실제 화면과 일치하는지
  대조하는 것이 검증의 근거입니다.
- sample_value: 기획서가 제시한 **유효 입력 예시**. '테스트 계정', '입력 예시
  데이터', '샘플 데이터' 같은 제목의 표가 있으면 **그 표의 열 제목이 요소의
  라벨**이고 아래 칸의 값이 그 요소의 sample_value 입니다. 열 제목이 '이메일'
  이고 값이 'user@test.com' 이면 라벨이 '이메일' 인 요소에 그 값을 넣으세요.
  '예:' 로 시작하는 문장에 적힌 값도 마찬가지입니다.
  그런 표나 문장이 없는 요소만 null 로 두세요. 이 값은 정상 케이스의 입력으로
  쓰이므로, 있는데 빠뜨리면 코드가 만든 값이 대신 쓰이고 그 값은 규칙은
  만족하지만 등록된 계정이 아니어서 정상 케이스가 잘못 실패합니다. 반대로 임의로
  만들어 넣어도 같은 문제가 생깁니다.
- scenarios: 기획서가 **입력과 그 결과를 짝으로** 제시한 예시. '예시 검색',
  '예시 동작' 처럼 **입력값 열과 '노출돼야 하는 문구' 열이 함께 있는 표**가
  그것입니다. 각 행을 하나씩 넣으세요.
      given        그 행의 입력값. 열 제목이 요소의 라벨이므로, 해당 요소의
                   element_id 를 키로 씁니다 ({"query": "notebook"}).
      expect_text  그 행의 '노출돼야 하는 문구' 를 기획서에 적힌 그대로.
      expect_count 그 행에 **숫자만 적힌 열**(결과 건수 등)이 있으면 그 숫자.
                   없으면 null. "검색 결과 3건" 같은 문구에서 숫자를 뽑아내지
                   마세요 — 숫자만 있는 열이 따로 있을 때만 채웁니다.
  **입력값 열만 있고 결과 문구 열이 없는 표는 scenarios 가 아니라 sample_value
  입니다.** 두 표를 혼동하지 마세요 — 결과 문구 열의 유무로 구분합니다.
  또한 **검증 규칙 위반 예시는 여기 넣지 마세요.** 규칙 위반은 constraints 에서
  자동으로 전개됩니다. scenarios 는 규칙으로 표현할 수 없는 것(검색 결과 건수,
  선택에 따른 안내 문구 등)만 담습니다.
  그런 표가 없으면 빈 배열로 두세요.
- required_message: 입력이 **비어 있을 때** 노출하는 문구. 기획서의 실패 조건
  표에서 '~가 비어 있음', '~를 입력하지 않음', '필수 항목 누락' 처럼 **값이
  없는 상황**을 다루는 행을 찾아 그 문구를 그대로 옮기세요. 상황 표현은
  기획서마다 다릅니다 ("필수 입력값이 비어 있음", "검색어가 비어 있음" 등) —
  표현이 아니라 **의미**로 찾으세요.
  요소별 error_message 와 구별하세요. 그런 행이 없으면 null 로 두세요 —
  추측한 문구를 넣으면 실제 화면과 대조할 때 잘못된 실패로 판정됩니다.
- success_condition: 정상 처리 시 무엇이 일어나는지 (이동 경로, 노출 문구).
- failure_conditions: 실패 상황별 처리를 문장 목록으로.
- 기획서에서 판단할 수 없는 내용은 추측하지 말고 warnings 에 기록하세요.

## 예시의 값을 베끼지 마세요

아래 예시는 **형식**을 보여주는 것입니다. 문구·경로·값은 반드시 지금 주어진
기획서에서 옮기세요. 예시에 있던 문구를 그대로 쓰면, 실제 화면과 대조할 때
있지도 않은 불일치를 보고하게 됩니다. 기획서에 해당 내용이 없으면 예시를
가져오지 말고 null 이나 빈 값으로 두세요.
"""

# 예시로 쓰는 화면은 실제 검증 대상 화면(로그인·회원가입·검색)과 겹치지 않게 고른다.
#
# 이유: S1 정확도를 골든 데이터와 대조해 측정하는데, 예시가 측정 대상과 같으면
# 모델이 기획서를 읽어서 맞힌 것인지 예시를 베낀 것인지 구분할 수 없다. 그러면
# 정확도 숫자가 실물 기획서에 대한 근거가 되지 못한다.
# 대신 확장된 형식(same_as·options·체크박스·scenarios)을 모두 한 화면에 담아
# 형식만 가르친다. 화면을 추가할 때 이 예시와 주제가 겹치지 않는지 확인해야 한다.
FEW_SHOT = """\
## 예시

기획서 텍스트:
=== 페이지 1 ===
비밀번호 변경

[표 1-1]
| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 에러 메시지 |
|---|---|---|---|---|---|
| current_pw | 입력 | 현재 비밀번호 | 필수 | - | 현재 비밀번호를 입력하세요. |
| new_pw | 입력 | 새 비밀번호 | 필수 | 10자 이상, 숫자 1자 이상 | 새 비밀번호는 10자 이상이며 숫자를 1자 이상 포함해야 합니다. |
| new_pw_confirm | 입력 | 새 비밀번호 확인 | 필수 | 새 비밀번호와 동일한 값 | 새 비밀번호가 일치하지 않습니다. |
| reason | 선택 | 변경 사유 | 필수 | 선택 목록: 정기 변경, 분실 우려 | 변경 사유를 선택하세요. |
| logout_all | 체크박스 | 모든 기기에서 로그아웃 | - | - | - |
| submit | 버튼 | 변경하기 | - | - | - |

변경이 완료되면 /settings 로 이동하고 "비밀번호를 변경했습니다" 를 노출한다.
필수 항목이 비어 있으면 "필수 항목을 입력하세요." 를 노출한다.

[표 1-2] 입력 예시 데이터
| 현재 비밀번호 | 새 비밀번호 |
|---|---|
| Old12345678 | New98765432 |

[표 1-3] 예시 동작
| 변경 사유 | 노출돼야 하는 문구 |
|---|---|
| 정기 변경 | 90일 후 다시 안내합니다 |

출력 JSON:
{
  "screen_id": "password_change",
  "screen_name": "비밀번호 변경",
  "url_path": "/password-change",
  "elements": [
    {"element_id": "current_pw", "type": "input", "label": "현재 비밀번호", "required": true,
     "constraints": {}, "error_message": "현재 비밀번호를 입력하세요.",
     "options": [], "sample_value": "Old12345678"},
    {"element_id": "new_pw", "type": "input", "label": "새 비밀번호", "required": true,
     "constraints": {"min_length": 10, "require_digit": 1},
     "error_message": "새 비밀번호는 10자 이상이며 숫자를 1자 이상 포함해야 합니다.",
     "options": [], "sample_value": "New98765432"},
    {"element_id": "new_pw_confirm", "type": "input", "label": "새 비밀번호 확인",
     "required": true, "constraints": {"same_as": "new_pw"},
     "error_message": "새 비밀번호가 일치하지 않습니다.",
     "options": [], "sample_value": null},
    {"element_id": "reason", "type": "select", "label": "변경 사유", "required": true,
     "constraints": {}, "error_message": "변경 사유를 선택하세요.",
     "options": ["정기 변경", "분실 우려"], "sample_value": null},
    {"element_id": "logout_all", "type": "checkbox", "label": "모든 기기에서 로그아웃",
     "required": false, "constraints": {}, "error_message": null,
     "options": [], "sample_value": null},
    {"element_id": "submit", "type": "button", "label": "변경하기", "required": false,
     "constraints": {}, "error_message": null, "options": [], "sample_value": null}
  ],
  "scenarios": [
    {"given": {"reason": "정기 변경"}, "expect_text": "90일 후 다시 안내합니다"}
  ],
  "success_condition": "/settings 로 이동하고 \\"비밀번호를 변경했습니다\\" 노출",
  "failure_conditions": ["새 비밀번호 규칙 위반 시 에러 메시지 노출",
                         "새 비밀번호 확인이 다르면 \\"새 비밀번호가 일치하지 않습니다.\\" 노출",
                         "변경 사유 미선택 시 \\"변경 사유를 선택하세요.\\" 노출",
                         "필수 항목 누락 시 \\"필수 항목을 입력하세요.\\" 노출"],
  "required_message": "필수 항목을 입력하세요.",
  "warnings": []
}
"""


def build_user_prompt(
    doc_text: str,
    declared_ids: list[str] | None = None,
    screen_meta: dict[str, str] | None = None,
    sample_values: dict[str, str] | None = None,
    scenarios: list[dict] | None = None,
) -> str:
    """LLM 에 넘길 프롬프트. 결정적으로 알아낸 사실은 직접 알려 준다.

    넘기는 것은 모두 pdfplumber 가 표에서 그대로 읽은 값이다. 이걸 넣는 이유는
    실측에서 7B 가 표에 적힌 사실을 다시 만들어내려 했기 때문이다.

        declared_ids   7행 표의 버튼 행을 빠뜨렸다. 제출 버튼이 없으면 폼이
                       제출되지 않아 구현이 옳아도 전 케이스가 실패로 나온다.
        screen_meta    '화면 ID | search' 를 두고도 화면명에서 'product_search'
                       를 지어냈다. screen_id 는 case_id 접두사이자 스크린샷 경로다.
        sample_values  few-shot 예시의 표 제목을 바꾼 것만으로 추출이 두 번
                       깨졌다. 예시값이 빠지면 정상 케이스가 오탐 실패한다.
        scenarios      기획서에 없는 시나리오를 만들어냈다. 성공 조건과 예시
                       입력값을 조합해 그럴듯한 것을 지었고, 체크박스 값으로
                       'checked' 라는 규약까지 창작했다. 지어낸 기대 문구는
                       화면에 없는 문구를 요구해 오탐이 된다.

    이건 LLM 이 못하는 일을 대신 해주는 것이 아니라, **코드가 확실히 아는 사실을
    추론에 맡기지 않는 것**이다. 표의 몇 번째 열이 ID 인지는 괘선으로 정해지므로
    추론할 여지가 없다. 그 사실을 프롬프트에 박아 두면 사후에 결과를 손보는
    보정(추출 실패를 가리는 종류)을 하지 않아도 된다.
    """
    lines: list[str] = []
    if declared_ids:
        lines.append(
            f"이 기획서의 UI 요소 표에는 요소가 {len(declared_ids)}개 있습니다. "
            f"elements 배열을 정확히 {len(declared_ids)}개로 만드세요.\n"
            f"요소 ID 는 순서대로 다음과 같습니다 — 하나도 빠뜨리지 말고, 이름을 "
            f"바꾸지 말고 그대로 쓰세요:\n{', '.join(declared_ids)}"
        )
    if screen_meta:
        pairs = ", ".join(f"{k} = {v}" for k, v in screen_meta.items())
        lines.append(
            f"화면 개요 표에 적힌 값을 그대로 쓰세요 (새로 만들지 마세요): {pairs}"
        )
    if sample_values:
        pairs = "\n".join(f"  라벨 '{k}' -> {v!r}" for k, v in sample_values.items())
        lines.append(
            "기획서가 제시한 예시 입력값입니다. 해당 라벨을 가진 요소의 "
            f"sample_value 에 그대로 넣으세요:\n{pairs}"
        )
    if scenarios is not None:
        if scenarios:
            lines.append(
                f"이 기획서의 입력-결과 예시는 다음 {len(scenarios)}건입니다. "
                f"scenarios 에 이대로 넣으세요:\n"
                + "\n".join(f"  {s}" for s in scenarios)
            )
        else:
            lines.append(
                "이 기획서에는 입력-결과 짝을 제시한 예시 표가 없습니다. "
                "scenarios 는 빈 배열([])이어야 합니다. 성공 조건이나 예시 입력값을 "
                "조합해 시나리오를 만들어 내지 마세요."
            )

    hint = ""
    if lines:
        hint = "\n## 반드시 지킬 것\n\n" + "\n\n".join(lines) + "\n"
    return (
        f"{FEW_SHOT}\n## 실제 기획서\n\n기획서 텍스트:\n{doc_text}\n"
        f"{hint}\n출력 JSON:"
    )


def extract_screen_spec(doc: ParsedDocument, llm: LLMClient, max_tokens: int = 3072) -> ScreenSpec:
    """추출된 문서 텍스트에서 ScreenSpec 을 만든다."""
    doc_text = doc.to_llm_text()
    if not doc_text.strip():
        raise LLMError(f"PDF 에서 텍스트를 추출하지 못했습니다: {doc.source}")

    declared_scenarios = doc.declared_scenarios()

    raw = llm.complete_json(
        system=SYSTEM_PROMPT,
        user=build_user_prompt(
            doc_text,
            doc.declared_element_ids(),
            doc.declared_screen_meta(),
            doc.declared_sample_values(),
            declared_scenarios,
        ),
        schema=ScreenSpec.model_json_schema(),
        max_tokens=max_tokens,
    )
    spec = ScreenSpec.model_validate(raw)

    _normalize_element_ids(spec)
    _apply_declared_types(spec, doc.declared_element_types())
    _apply_declared_required_message(spec, doc.declared_required_message())
    _apply_declared_scenarios(spec, declared_scenarios)

    # constraints 가 하나도 없으면 거의 확실히 추출 실패다. 조용히 넘어가면
    # negative 케이스가 아예 생성되지 않아 리포트가 근거 없이 초록불이 된다.
    if not any(e.constraints for e in spec.elements):
        spec.warnings.append(
            "입력 검증 규칙(constraints)이 하나도 추출되지 않았습니다. "
            "기획서에 규칙이 없는 화면이 아니라면 S1 추출 실패를 의심하세요."
        )

    spec.warnings.extend(structural_warnings(spec, doc))
    return spec


def _normalize_element_ids(spec: ScreenSpec) -> None:
    """element_id 안의 공백을 없앤다. same_as 참조도 함께 고친다.

    왜 고쳐도 되는가: element_id 는 슬러그라서 공백이 들어갈 여지가 없고, 공백이
    섞였을 때 고칠 방법도 하나뿐이다(지운다). 실측에서 7B 가 password_confirm 을
    'password_confir m' 으로 낸 적이 있는데, 그러면 same_as 참조가 어긋나고
    case_id 에도 공백이 들어가 스크린샷 경로가 깨진다.

    판정 강도를 낮추는 종류의 보정이 아니라 표기 복원이므로 조용히 처리한다.
    같은 이유로 경고를 남기지도 않는다 — 매 실행마다 뜨는 경고는 정작 중요한
    경고를 묻는다.
    """
    renames = {}
    for element in spec.elements:
        clean = re.sub(r"\s+", "", element.element_id)
        if clean != element.element_id:
            renames[element.element_id] = clean
            element.element_id = clean

    if not renames:
        return
    for element in spec.elements:
        ref = element.constraints.get("same_as")
        if ref in renames:
            element.constraints["same_as"] = renames[ref]


def _apply_declared_types(spec: ScreenSpec, declared: dict[str, str]) -> None:
    """요소 유형을 기획서 표의 '유형' 열로 맞춘다 (라벨 -> 유형).

    표에 적힌 사실이므로 LLM 결과를 덮어쓴다 (declared_element_types 설명 참고).
    다만 여기서는 경고를 남긴다 — _normalize_element_ids 와 다른 점이다. 공백
    제거는 표기 복원이지만, 유형이 달랐다는 것은 모델이 표를 잘못 읽었다는
    뜻이고 그건 프롬프트가 나빠지고 있다는 신호다.

    표에 없는 라벨의 요소는 건드리지 않는다. LLM 이 표에 없는 요소를 추가한
    경우인데, 그 누락·추가는 structural_warnings 가 따로 알린다.
    """
    if not declared:
        return
    for element in spec.elements:
        want = declared.get(element.label)
        if want is None or want == element.type:
            continue
        spec.warnings.append(
            f"'{element.label}' 의 유형을 기획서 표대로 {want!r} 로 맞췄습니다 "
            f"(모델: {element.type!r}). 프롬프트를 확인하세요."
        )
        element.type = want


def _apply_declared_required_message(spec: ScreenSpec, declared: str | None) -> None:
    """필수 입력 누락 문구를 실패 조건 표의 값으로 맞춘다.

    화면을 한 문서에 모으자 7B 가 검색 화면의 이 값을 **few-shot 예시의 문구로**
    채웠다("필수 항목을 입력하세요."). 기획서에는 "검색어를 입력하세요." 라고 적혀
    있었고, 그 차이가 곧 오탐이다 — 구현이 올바른 문구를 노출하는데 FAIL 이 된다.

    표에서 후보를 하나로 특정하지 못하면 declared 가 None 이고, 그때는 손대지
    않는다 (declared_required_message 참고).
    """
    if declared is None or declared == spec.required_message:
        return
    spec.warnings.append(
        f"필수 입력 문구를 기획서 실패 조건 표대로 {declared!r} 로 맞췄습니다 "
        f"(모델: {spec.required_message!r}). 프롬프트를 확인하세요."
    )
    spec.required_message = declared


def _apply_declared_scenarios(
    spec: ScreenSpec, declared: list[dict] | None
) -> None:
    """표에서 읽은 시나리오를 정답으로 삼는다.

    ## 왜 LLM 결과를 덮어쓰는가

    보정을 하는 것이 아니라, **애초에 LLM 이 판단할 일이 아니었다.** 열 제목에서
    요소 ID 를 찾고 셀 값을 옮기는 데는 추론이 없다. 그걸 맡긴 대가로 실측에서
    두 가지가 나왔다 — 기획서에 없는 시나리오를 만들어내는 것, 그리고 실패 조건
    표의 행을 시나리오로 들여오는 것. 둘 다 오탐으로 이어진다.

    검증을 약하게 만드는 방향의 보정이 아니라 **같은 문서에서 더 확실한 값으로
    바꾸는 것**이므로 조용히 처리한다. 다만 LLM 이 다른 답을 냈다는 사실은
    남긴다 — 프롬프트가 나빠지고 있는지 알 수 있어야 한다.

    표를 판별할 근거가 없으면(declared is None) LLM 결과를 그대로 쓴다. 실물
    기획서가 시나리오를 표가 아니라 문장으로 적어 두면 그 경로가 필요하다.
    """
    if declared is None:
        return

    # 비교는 필드를 갖춘 형태로 맞춰서 한다. 표에서 읽은 dict 에 expect_count 가
    # 없고 모델 쪽에는 None 이 있으면, 값이 같은데도 다르다고 판정되어 매 실행마다
    # 경고가 뜬다. 매번 뜨는 경고는 정작 중요한 경고를 묻는다.
    declared = [
        {"given": dict(d.get("given", {})), "expect_text": d.get("expect_text", ""),
         "expect_count": d.get("expect_count")}
        for d in declared
    ]
    llm_scenarios = [
        {"given": dict(s.given), "expect_text": s.expect_text,
         "expect_count": s.expect_count}
        for s in spec.scenarios
    ]
    spec.scenarios = [Scenario.model_validate(item) for item in declared]

    if llm_scenarios != declared:
        spec.warnings.append(
            f"예시 시나리오를 기획서 표에서 직접 읽어 썼습니다 "
            f"({len(declared)}건). 모델이 낸 것과 달랐습니다 — "
            f"모델: {llm_scenarios}. 프롬프트를 확인하세요."
        )


def structural_warnings(spec: ScreenSpec, doc: ParsedDocument) -> list[str]:
    """기획서 표와 추출 결과를 대조해 누락을 찾는다. LLM 을 쓰지 않는다.

    LLM 이 표의 행을 빠뜨리는 것은 실제로 일어나는 실패다. 그 결과가 리포트에서
    '전 케이스 실패' 로 보이는데, 원인은 구현이 아니라 추출이다. 그 구분을
    사람이 할 수 있게 하려면 여기서 알려야 한다.
    """
    warnings: list[str] = []

    declared = doc.declared_element_ids()
    if declared:
        got = {e.element_id for e in spec.elements}
        missing = [eid for eid in declared if eid not in got]
        if missing:
            warnings.append(
                f"기획서 UI 요소 표에는 {len(declared)}개 요소가 있는데 추출된 것은 "
                f"{len(got)}개입니다. 빠진 요소: {', '.join(missing)}. "
                f"S1 추출 실패이며, 구현 결함이 아닙니다."
            )

    if not any(e.type == "button" for e in spec.elements):
        warnings.append(
            "버튼 요소를 하나도 추출하지 못했습니다. 제출 버튼이 없으면 테스트가 "
            "폼을 제출하지 못해, 구현이 옳아도 모든 케이스가 실패로 나옵니다."
        )

    # 기획서가 예시값을 표로 줬는데 추출에서 빠진 경우. 그러면 정상 케이스가
    # 코드가 만든 값을 쓰게 되고, 그 값은 규칙은 만족하지만 시스템에 등록된 값이
    # 아니어서 **구현 결함 없이 실패한다**(오탐).
    declared_samples = doc.declared_sample_values()
    if declared_samples:
        by_label = {e.label: e for e in spec.elements}
        missing = [
            f"'{label}' (기획서 예시 {value!r})"
            for label, value in declared_samples.items()
            if label in by_label and not by_label[label].sample_value
        ]
        if missing:
            warnings.append(
                f"기획서가 제시한 예시 입력값이 추출되지 않았습니다: "
                f"{', '.join(missing)}. 정상 케이스가 코드로 만든 값을 쓰게 되어 "
                f"구현 결함 없이 실패할 수 있습니다."
            )

    declared_meta = doc.declared_screen_meta()
    if declared_meta.get("screen_id") and spec.screen_id != declared_meta["screen_id"]:
        warnings.append(
            f"화면 ID 가 기획서와 다릅니다 — 기획서 "
            f"{declared_meta['screen_id']!r}, 추출 {spec.screen_id!r}. "
            f"case_id 와 스크린샷 경로가 기획서와 어긋납니다."
        )
    return warnings


def extract_from_pdf(pdf_path: str | Path, llm: LLMClient, max_tokens: int = 3072) -> ScreenSpec:
    """PDF 경로 하나로 S1 전체를 수행한다 (파싱 + 구조화). 화면이 하나인 문서용.

    화면이 여럿이면 예외를 던진다. 첫 화면만 돌려주면 나머지 화면의 검증이
    **아무 흔적도 남기지 않고 사라진다** — 리포트에는 첫 화면이 전부 통과한 것으로
    보이고, 읽는 사람은 다른 화면이 검증되지 않았다는 사실을 알 방법이 없다.
    """
    doc = parse_pdf(pdf_path)
    screens, _ = doc.split_screens()
    if len(screens) > 1:
        raise LLMError(
            f"이 PDF 에는 화면이 {len(screens)}개 있습니다: {pdf_path}. "
            f"extract_document() 를 쓰세요."
        )
    return extract_screen_spec(doc, llm, max_tokens=max_tokens)


def extract_document(
    pdf_path: str | Path, llm: LLMClient, max_tokens: int = 3072
) -> SpecDocument:
    """PDF 경로 하나로 문서 전체를 추출한다. 화면이 여럿이어도 된다.

    화면 분리는 코드가 하고(split_screens), 화면 하나를 구조화하는 일만 LLM 에
    맡긴다. 화면마다 따로 부르는 이유가 두 가지 있다.

    1) 컨텍스트. 세 화면을 한 번에 넣으면 8192 토큰 창을 금세 넘긴다. 넘치지
       않더라도 입력이 길어질수록 7B 가 행을 빠뜨리는 빈도가 올라간다 —
       이미 7행 표에서 버튼 행을 놓친 적이 있다.
    2) 실패 격리. 한 화면의 추출이 흔들려도 다른 화면의 결과가 오염되지 않는다.
       한 번에 넣으면 어느 화면의 요소인지 모델이 섞을 위험이 생긴다.

    흐름은 문서 수준이므로 화면을 다 읽은 뒤 한 번만 읽는다.
    """
    doc = parse_pdf(pdf_path)
    screen_docs, warnings = doc.split_screens()

    screens = [
        extract_screen_spec(sub, llm, max_tokens=max_tokens) for sub in screen_docs
    ]
    flows = [Flow.model_validate(f) for f in doc.declared_flows()]

    result = SpecDocument(source=str(pdf_path), screens=screens, flows=flows,
                          warnings=warnings)
    result.warnings.extend(_document_warnings(result))
    return result


def _document_warnings(doc: SpecDocument) -> list[str]:
    """문서 수준 대조. 화면 하나만 봐서는 알 수 없는 어긋남을 찾는다."""
    warnings: list[str] = []

    ids = [s.screen_id for s in doc.screens]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        # case_id 접두사가 겹치면 스크린샷 경로가 서로를 덮어쓴다. 증거가 사라지는데
        # 리포트에는 정상으로 보인다.
        warnings.append(
            f"화면 ID 가 중복됩니다: {', '.join(duplicated)}. "
            f"case_id 와 스크린샷 경로가 겹쳐 증거가 서로를 덮어씁니다."
        )

    for flow in doc.flows:
        missing = [sid for sid in flow.screen_ids if doc.screen_by_id(sid) is None]
        if missing:
            warnings.append(
                f"흐름 '{flow.flow_id}' 가 이 문서에 없는 화면을 가리킵니다: "
                f"{', '.join(missing)}. 이 흐름은 검증하지 못했습니다."
            )
    return warnings
