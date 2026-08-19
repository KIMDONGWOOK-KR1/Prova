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
import re
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
        # 화면이 여럿인 문서용. screen_id -> ScreenSpec 응답.
        self._by_screen: dict[str, dict] = {}
        self.calls: list[dict] = []  # 테스트에서 호출 내역을 확인할 수 있게 남긴다

    def register(self, schema_title: str, response: dict) -> None:
        self._responses[schema_title] = response

    def register_screen(self, screen_id: str, response: dict) -> None:
        """화면 하나의 ScreenSpec 응답. 프롬프트 내용을 보고 골라 쓴다."""
        self._by_screen[screen_id] = response

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

        ## 화면이 여럿인 문서 — UI 는 어느 기획서를 고를지 모른 채 mock 을 만든다

        상품등록·주문조회처럼 전제(로그인) 화면을 같은 PDF 에 담는 기획서는
        페이지(화면)마다 S1 을 따로 부른다. 이 PDF 자신의 골든 하나만 등록하면
        두 번째 이후 화면 호출도 같은 응답을 받아 화면 ID 가 뒤섞인다 — 로그인
        페이지가 '주문 조회' 로 추출되는 식이다(웹 UI 스모크에서 실측했다).

        그래서 `fixtures/specs/*_spec.golden.json` 을 전부 화면별로도 등록해
        둔다. 화면 ID 정확 매칭(`_pick_screen`, 표의 행 모양)이 이미 있으므로
        관계없는 골든이 섞여도 오염되지 않는다 — 프롬프트에 그 화면 ID 가 없으면
        애초에 후보에 들지 않는다. 요청한 PDF 자신의 골든은 마지막에 다시 한 번
        등록해, 같은 screen_id 를 공유하는 다른 픽스처(`product_spec` vs
        `product_badlogin_spec`)보다 우선하게 한다 — **부른 이가 지정한 문서가
        이긴다.**
        """
        inst = cls()
        for other in sorted(Path(pdf_path).parent.glob("*_spec.golden.json")):
            try:
                data = json.loads(other.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            sid = data.get("screen_id")
            if sid:
                inst.register_screen(sid, data)

        golden = Path(pdf_path).with_suffix(".golden.json")
        if golden.exists():
            data = json.loads(golden.read_text(encoding="utf-8"))
            inst.register("ScreenSpec", data)
            if data.get("screen_id"):
                inst.register_screen(data["screen_id"], data)
        return inst

    @classmethod
    def for_document(cls, *pdf_paths: str | Path) -> "MockLLM":
        """화면이 여럿인 문서용. 화면마다 골든을 등록한다.

        ## 순서가 아니라 내용으로 고른다

        호출 순서대로 돌려주면 **화면 분리가 뒤바뀌어도 테스트가 통과한다** —
        mock 은 첫 번째 호출에 로그인을 주고, 파이프라인은 그것을 로그인 화면의
        명세로 받아들인다. 정작 넘긴 텍스트가 회원가입 것이었어도 알 수 없다.

        그래서 프롬프트에 그 화면의 screen_id 가 들어 있는지 보고 고른다. 화면 개요
        표의 '화면 ID' 값이 프롬프트에 그대로 실려 있으므로(pdf_parser 가 표를
        마크다운으로 재조립한다) 판별이 가능하다. 못 고르면 오류를 낸다 — 조용히
        아무 응답이나 돌려주면 이 테스트가 무엇을 확인했는지 알 수 없게 된다.
        """
        inst = cls()
        for path in pdf_paths:
            golden = Path(path).with_suffix(".golden.json")
            if not golden.exists():
                raise FileNotFoundError(f"골든 파일이 없습니다: {golden}")
            data = json.loads(golden.read_text(encoding="utf-8"))
            inst.register_screen(data["screen_id"], data)
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

        if title == "ScreenSpec" and self._by_screen:
            return self._pick_screen(user)

        if title not in self._responses:
            raise LLMError(
                f"mock 백엔드에 '{title}' 응답이 등록되지 않았습니다. "
                f"등록된 것: {sorted(self._responses)}"
            )
        return self._responses[title]

    def _pick_screen(self, user: str) -> dict:
        """프롬프트에 실린 화면 ID 로 응답을 고른다 (for_document 설명 참고).

        '화면 ID | login' 형태를 찾는다. 화면 ID 문자열이 프롬프트 다른 곳에도
        나타날 수 있으므로(url_path 등) 표의 행 모양을 요구한다 — 그러지 않으면
        '/login' 만 스쳐도 로그인 화면으로 골라 버린다.
        """
        matched = [
            sid for sid in self._by_screen
            if re.search(r"화면\s*ID\s*\|\s*" + re.escape(sid) + r"\s*\|", user)
        ]
        if len(matched) != 1:
            raise LLMError(
                f"프롬프트에서 화면을 하나로 특정하지 못했습니다: {matched or '없음'}. "
                f"등록된 화면: {sorted(self._by_screen)}"
            )
        return self._by_screen[matched[0]]
