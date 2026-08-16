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
from prova.models import ScreenSpec
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
  체크박스는 "checkbox", 표시 전용 텍스트는 "text".
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
- required_message: 필수 입력값이 비어 있을 때 노출하는 **화면 공통 문구**.
  요소별 error_message 와 구별하세요. 기획서의 실패 조건에 "필수 입력값이 비어
  있음" 같은 항목이 있으면 그 문구를 여기에 넣습니다. 그런 문구가 기획서에
  없으면 null 로 두세요 — 추측한 문구를 넣으면 실제 화면과 대조할 때 잘못된
  실패로 판정됩니다.
- success_condition: 정상 처리 시 무엇이 일어나는지 (이동 경로, 노출 문구).
- failure_conditions: 실패 상황별 처리를 문장 목록으로.
- 기획서에서 판단할 수 없는 내용은 추측하지 말고 warnings 에 기록하세요.
"""

# 예시로 쓰는 화면은 실제 검증 대상 화면(로그인·회원가입)과 겹치지 않게 고른다.
#
# 이유: S1 정확도를 골든 데이터와 대조해 측정하는데, 예시가 측정 대상과 같으면
# 모델이 기획서를 읽어서 맞힌 것인지 예시를 베낀 것인지 구분할 수 없다. 그러면
# 10/10 이라는 숫자가 실물 기획서에 대한 근거가 되지 못한다.
# 대신 확장된 규칙(same_as·options·체크박스)을 모두 한 화면에 담아 형식은 가르친다.
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
  "success_condition": "/settings 로 이동하고 \\"비밀번호를 변경했습니다\\" 노출",
  "failure_conditions": ["새 비밀번호 규칙 위반 시 에러 메시지 노출",
                         "새 비밀번호 확인이 다르면 \\"새 비밀번호가 일치하지 않습니다.\\" 노출",
                         "변경 사유 미선택 시 \\"변경 사유를 선택하세요.\\" 노출",
                         "필수 항목 누락 시 \\"필수 항목을 입력하세요.\\" 노출"],
  "required_message": "필수 항목을 입력하세요.",
  "warnings": []
}
"""


def build_user_prompt(doc_text: str, declared_ids: list[str] | None = None) -> str:
    """LLM 에 넘길 프롬프트. 결정적으로 알아낸 사실은 직접 알려 준다.

    declared_ids 는 pdfplumber 가 표에서 읽은 요소 ID 목록이다. 이걸 넣는 이유는
    실측에서 7B 가 7행 표의 버튼 행을 빠뜨렸기 때문이다. 제출 버튼이 없으면
    테스트가 폼을 제출하지 못해 구현이 옳아도 전 케이스가 실패로 나온다.

    이건 LLM 이 못하는 일을 대신 해주는 것이 아니라, **코드가 확실히 아는 사실을
    추론에 맡기지 않는 것**이다. 표의 몇 번째 열이 ID 인지는 괘선으로 정해지므로
    추론할 여지가 없다. 그 사실을 프롬프트에 박아 두면 사후에 결과를 손보는
    보정(추출 실패를 가리는 종류)을 하지 않아도 된다.
    """
    hint = ""
    if declared_ids:
        hint = (
            f"\n## 반드시 지킬 것\n\n"
            f"이 기획서의 UI 요소 표에는 요소가 {len(declared_ids)}개 있습니다. "
            f"elements 배열을 정확히 {len(declared_ids)}개로 만드세요.\n"
            f"요소 ID 는 순서대로 다음과 같습니다 — 하나도 빠뜨리지 말고, 이름을 "
            f"바꾸지 말고 그대로 쓰세요:\n"
            f"{', '.join(declared_ids)}\n"
        )
    return (
        f"{FEW_SHOT}\n## 실제 기획서\n\n기획서 텍스트:\n{doc_text}\n"
        f"{hint}\n출력 JSON:"
    )


def extract_screen_spec(doc: ParsedDocument, llm: LLMClient, max_tokens: int = 3072) -> ScreenSpec:
    """추출된 문서 텍스트에서 ScreenSpec 을 만든다."""
    doc_text = doc.to_llm_text()
    if not doc_text.strip():
        raise LLMError(f"PDF 에서 텍스트를 추출하지 못했습니다: {doc.source}")

    raw = llm.complete_json(
        system=SYSTEM_PROMPT,
        user=build_user_prompt(doc_text, doc.declared_element_ids()),
        schema=ScreenSpec.model_json_schema(),
        max_tokens=max_tokens,
    )
    spec = ScreenSpec.model_validate(raw)

    _normalize_element_ids(spec)

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
    return warnings


def extract_from_pdf(pdf_path: str | Path, llm: LLMClient, max_tokens: int = 3072) -> ScreenSpec:
    """PDF 경로 하나로 S1 전체를 수행한다 (파싱 + 구조화)."""
    return extract_screen_spec(parse_pdf(pdf_path), llm, max_tokens=max_tokens)
