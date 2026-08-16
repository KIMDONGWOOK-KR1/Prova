"""테스트·오프라인 개발용 mock 백엔드.

## 왜 필요한가

GPU 서버 세팅과 파이프라인 개발을 병행하기 위해서다. 이 백엔드가 있으면
LLM 없이도 S1~S6 전체를 끝까지 실행해 볼 수 있고, CI 에서도 파이프라인 로직을
테스트할 수 있다. walking skeleton 전략의 실질적 근거가 이 파일이다.

## 주의: 이건 테스트 도구이지 fallback 이 아니다

실행 중 vLLM 이 죽었을 때 조용히 mock 으로 넘어가면, 리포트는 초록불인데
실제로는 아무 추론도 하지 않은 상태가 된다. QA 도구에서 그건 최악의 실패다.
그래서 mock 은 설정에서 명시적으로 지정해야만 쓰이고, 리포트에도 어떤 백엔드로
실행했는지 남긴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from prova.llm.base import LLMError


class MockLLM:
    """미리 준비한 응답을 돌려주는 백엔드.

    라우팅 기준은 schema 의 title 이다. 어느 단계가 부르는지가 스키마로
    구분되기 때문에, 프롬프트 문자열을 들여다보는 취약한 매칭을 피할 수 있다.
    """

    name = "mock"

    def __init__(self, responses: dict[str, dict] | None = None) -> None:
        self._responses = responses or {}
        self.calls: list[dict] = []  # 테스트에서 호출 내역을 확인할 수 있게 남긴다

    def register(self, schema_title: str, response: dict) -> None:
        self._responses[schema_title] = response

    @classmethod
    def for_spec(cls, pdf_path: str | Path) -> "MockLLM":
        """기획서 PDF 옆의 정답(golden) 파일을 ScreenSpec 응답으로 등록한다.

        S1 이 LLM 을 부르면 golden ScreenSpec 이 그대로 돌아온다. 즉 'LLM 이
        완벽하게 동작했을 때' 파이프라인 나머지가 옳게 도는지 확인할 수 있다.

        PDF 이름에서 golden 을 찾는 이유: 화면이 늘어날 때마다 여기에 분기를
        추가하지 않아도 되게 하려는 것이다. login_spec.pdf 를 넘기면
        login_spec.golden.json 을, signup_spec.pdf 를 넘기면
        signup_spec.golden.json 을 쓴다.

        golden 이 없으면 응답을 등록하지 않는다 — 그러면 S1 에서 '등록되지 않은
        스키마' 오류가 나서, 조용히 빈 결과로 진행되는 일이 없다.
        """
        inst = cls()
        golden = Path(pdf_path).with_suffix(".golden.json")
        if golden.exists():
            inst.register("ScreenSpec", json.loads(golden.read_text(encoding="utf-8")))
        return inst

    @classmethod
    def with_login_fixtures(cls) -> "MockLLM":
        """로그인 기획서 전용 단축 생성자 (기존 호출부 호환)."""
        return cls.for_spec("fixtures/specs/login_spec.pdf")

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> dict:
        title = schema.get("title", "")
        self.calls.append({"schema_title": title, "user_len": len(user)})
        if title not in self._responses:
            raise LLMError(
                f"mock 백엔드에 '{title}' 응답이 등록되지 않았습니다. "
                f"등록된 것: {sorted(self._responses)}"
            )
        return self._responses[title]
