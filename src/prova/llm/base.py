"""LLM 백엔드 추상화 — 로컬(vLLM)과 API를 코드 수정 없이 교체한다.

## 인터페이스를 complete_json 하나로 둔 이유

명세서 §10-5는 공통 인터페이스로 extract_spec() / generate_cases() /
classify_failure() 를 제시했다. 그런데 그건 '파이프라인 단계'의 이름이지
'모델 호출'의 이름이 아니다. 단계별 메서드를 백엔드마다 구현하면 각 백엔드가
프롬프트를 복사해 갖게 되고, 프롬프트를 고칠 때마다 백엔드 수만큼 고쳐야 한다.

그래서 백엔드는 '스키마를 강제한 JSON 한 건 생성'이라는 저수준 능력 하나만
제공한다. 프롬프트와 스키마는 각 단계 모듈(s1_spec_extractor 등)이 소유한다.
결과적으로 프롬프트는 한 곳에만 있고, 백엔드는 통신 방식만 다르다.

## 정형 출력을 백엔드 책임으로 둔 이유

7B 급 모델은 자유 생성에 맡기면 JSON 을 자주 깨뜨린다. 재프롬프트 루프로
수습하는 방법도 있지만, 개발 시간이 거기서 다 녹는다. vLLM 의 guided_json
(내부적으로 문법 제약 디코딩)을 쓰면 스키마를 벗어난 토큰이 애초에 생성되지
않는다. Claude API 는 structured outputs 로 같은 일을 한다. 방식이 다르니
백엔드가 각자 처리하고, 호출자는 "스키마에 맞는 dict 가 온다"만 알면 된다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    """LLM 호출 실패. 재시도로 해결되지 않는 상태."""


@runtime_checkable
class LLMClient(Protocol):
    """스키마를 강제해 JSON 한 건을 생성하는 능력."""

    name: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> dict:
        """schema 를 만족하는 JSON 객체를 dict 로 반환한다.

        Args:
            system: 역할·규칙을 담은 시스템 프롬프트
            user: 처리 대상 데이터
            schema: JSON Schema (pydantic model_json_schema() 결과)
            max_tokens: 생성 상한
            temperature: 기본 0.0 — 추출·구조화는 재현 가능해야 한다

        Raises:
            LLMError: 통신 실패, 스키마 위반 응답 등
        """
        ...
