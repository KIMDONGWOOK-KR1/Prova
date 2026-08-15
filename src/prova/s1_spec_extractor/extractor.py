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

키 이름을 바꾸거나 새로 만들지 마세요. 표에 없는 규칙은 constraints 에 넣지 말고
failure_conditions 에 문장으로 남기세요.

## 그 밖의 규칙

- element_id: 기획서에 요소 ID 가 있으면 그대로 쓰고, 없으면 라벨에서 영문
  snake_case 로 만드세요 (이메일 -> email, 로그인 버튼 -> login_btn).
- type: 입력란은 "input", 버튼은 "button", 링크는 "link", 선택은 "select",
  체크박스는 "checkbox", 표시 전용 텍스트는 "text".
- required: 기획서에 '필수' 로 표시된 요소만 true.
- error_message: 그 요소의 검증 실패 시 노출할 문구를 **기획서에 적힌 그대로**
  옮기세요. 문구를 다듬거나 요약하지 마세요. 이 문구가 실제 화면과 일치하는지
  대조하는 것이 검증의 근거입니다.
- sample_value: 기획서가 제시한 **유효 입력 예시**. 테스트 계정 표, 샘플 데이터,
  '예:' 로 시작하는 값이 있으면 해당 요소에 넣으세요. 없으면 null 로 두세요.
  이 값은 정상 케이스의 입력으로 쓰이므로, 임의로 만들어 넣으면 정상 케이스가
  구현 결함 없이 실패합니다.
- required_message: 필수 입력값이 비어 있을 때 노출하는 **화면 공통 문구**.
  요소별 error_message 와 구별하세요. 기획서의 실패 조건에 "필수 입력값이 비어
  있음" 같은 항목이 있으면 그 문구를 여기에 넣습니다. 그런 문구가 기획서에
  없으면 null 로 두세요 — 추측한 문구를 넣으면 실제 화면과 대조할 때 잘못된
  실패로 판정됩니다.
- success_condition: 정상 처리 시 무엇이 일어나는지 (이동 경로, 노출 문구).
- failure_conditions: 실패 상황별 처리를 문장 목록으로.
- 기획서에서 판단할 수 없는 내용은 추측하지 말고 warnings 에 기록하세요.
"""

FEW_SHOT = """\
## 예시

기획서 텍스트:
=== 페이지 1 ===
회원가입

[표 1-1]
| 요소 ID | 유형 | 라벨 | 필수 | 입력 검증 규칙 | 에러 메시지 |
|---|---|---|---|---|---|
| nickname | 입력 | 닉네임 | 필수 | 2자 이상 10자 이하 | 닉네임은 2자 이상 10자 이하로 입력하세요. |
| agree | 체크박스 | 약관 동의 | 필수 | - | 약관에 동의해야 합니다. |
| submit | 버튼 | 가입하기 | - | - | - |

가입 성공 시 /welcome 으로 이동하고 "가입이 완료되었습니다" 를 노출한다.
필수 항목이 비어 있으면 "필수 항목을 입력하세요." 를 노출한다.

[표 1-2] 테스트 데이터
| 닉네임 |
|---|
| 테스터 |

출력 JSON:
{
  "screen_id": "signup",
  "screen_name": "회원가입",
  "url_path": "/signup",
  "elements": [
    {"element_id": "nickname", "type": "input", "label": "닉네임", "required": true,
     "constraints": {"min_length": 2, "max_length": 10},
     "error_message": "닉네임은 2자 이상 10자 이하로 입력하세요.",
     "sample_value": "테스터"},
    {"element_id": "agree", "type": "checkbox", "label": "약관 동의", "required": true,
     "constraints": {}, "error_message": "약관에 동의해야 합니다."},
    {"element_id": "submit", "type": "button", "label": "가입하기", "required": false,
     "constraints": {}, "error_message": null}
  ],
  "success_condition": "/welcome 으로 이동하고 \\"가입이 완료되었습니다\\" 노출",
  "failure_conditions": ["닉네임 길이 규칙 위반 시 에러 메시지 노출",
                         "약관 미동의 시 에러 메시지 노출",
                         "필수 항목 누락 시 \\"필수 항목을 입력하세요.\\" 노출"],
  "required_message": "필수 항목을 입력하세요.",
  "warnings": []
}
"""


def build_user_prompt(doc_text: str) -> str:
    return f"{FEW_SHOT}\n## 실제 기획서\n\n기획서 텍스트:\n{doc_text}\n\n출력 JSON:"


def extract_screen_spec(doc: ParsedDocument, llm: LLMClient, max_tokens: int = 3072) -> ScreenSpec:
    """추출된 문서 텍스트에서 ScreenSpec 을 만든다."""
    doc_text = doc.to_llm_text()
    if not doc_text.strip():
        raise LLMError(f"PDF 에서 텍스트를 추출하지 못했습니다: {doc.source}")

    raw = llm.complete_json(
        system=SYSTEM_PROMPT,
        user=build_user_prompt(doc_text),
        schema=ScreenSpec.model_json_schema(),
        max_tokens=max_tokens,
    )
    spec = ScreenSpec.model_validate(raw)

    # constraints 가 하나도 없으면 거의 확실히 추출 실패다. 조용히 넘어가면
    # negative 케이스가 아예 생성되지 않아 리포트가 근거 없이 초록불이 된다.
    if not any(e.constraints for e in spec.elements):
        spec.warnings.append(
            "입력 검증 규칙(constraints)이 하나도 추출되지 않았습니다. "
            "기획서에 규칙이 없는 화면이 아니라면 S1 추출 실패를 의심하세요."
        )
    return spec


def extract_from_pdf(pdf_path: str | Path, llm: LLMClient, max_tokens: int = 3072) -> ScreenSpec:
    """PDF 경로 하나로 S1 전체를 수행한다 (파싱 + 구조화)."""
    return extract_screen_spec(parse_pdf(pdf_path), llm, max_tokens=max_tokens)
