"""2026-11-27 서비스 점검에서 나온 웹 UI 고침 (app.js·app.css, 실제 브라우저).

- 오류 상자: 서버가 줄을 나눠 보낸 안내(`\n`)가 한 줄로 붙어 읽혔다.
- 결과 상세의 '끝난 주소': 요청이 막힌 페이지(chrome-error://…)의 경로 '/' 를 주소처럼 보였다.
- 백엔드 기본값: 지난번에 고른 '실제 모델' 이 모델 서버 없이 띄운 서버의 기본값을 덮었다.
"""

from __future__ import annotations

import pytest

from test_ui_run_progress import base, page  # noqa: F401 — 같은 정적 서버·브라우저를 쓴다


def test_오류_상자는_서버가_나눈_줄을_지킨다(page):  # noqa: F811
    why = page.evaluate("""() => {
      showError('요청을 처리하지 못했어요', '기획서에 없는 항목: <결제>\\n  기획서의 말로 다시 써 주세요.');
      return document.querySelector('#formNote .why').innerHTML;
    }""")
    assert why == "기획서에 없는 항목: &lt;결제&gt;<br>기획서의 말로 다시 써 주세요."


@pytest.mark.parametrize("url, shown", [
    ("http://localhost:8100/good/welcome", "/good/welcome"),
    ("chrome-error://chromewebdata/", ""),
    ("about:blank", ""),
    ("", ""),
    ("주소가 아님", ""),
])
def test_끝난_주소는_웹_주소일_때만_보인다(page, url, shown):  # noqa: F811
    assert page.evaluate("(u) => endPath(u)", url) == shown


@pytest.mark.parametrize("saved, server, picked", [
    (None, "replay", "replay"),      # 처음 여는 브라우저 — 서버 기본값
    ("vllm", "replay", "replay"),    # 모델 서버 없이 띄웠다 — 지난번 '실제 모델' 이 덮으면 바로 실패한다
    ("mock", "replay", "mock"),      # 서버 없이 도는 선택은 지난번 것을 지킨다
    ("vllm", "mock", "mock"),        # 연습용 설정(configs/demo.yaml)은 서버의 뜻이 우선 (전부터)
    ("replay", "mock", "mock"),
    ("replay", "vllm", "replay"),    # 실제 모델 서버라도 지난번 선택을 지킨다 (전부터)
    ("mock", "vllm", "mock"),
    ("vllm", "vllm", "vllm"),
])
def test_지난번_실제_모델_선택은_모델_없는_서버를_덮지_않는다(page, saved, server, picked):  # noqa: F811
    assert page.evaluate("([s, d]) => pickBackend(s, d)", [saved, server]) == picked
