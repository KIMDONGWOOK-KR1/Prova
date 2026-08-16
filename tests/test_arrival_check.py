"""흐름 중간의 도착 확인 — 브라우저 없이 값으로 시험한다.

## 왜 S5 의 판정 함수와 따로 있는가

이건 판정이 아니라 **선행 조건 확인**이다. 목적은 다음 화면으로 넘어가도 되는지,
넘어가지 못했으면 어느 화면에서 끊겼는지를 남기는 것뿐이다. navigate 스텝이 4xx 를
실패로 확정하는 것과 같은 성질이라 실행 단계(S4)에 있다.

일부러 좁다 — 에러 영역과 화면 텍스트를 구분하지 않고 실패 분류도 하지 않는다.
그 이상을 이 자리에서 판단하면 판정 책임이 두 단계로 흩어진다.
"""

from __future__ import annotations

from prova.models import Expectation
from prova.s4_executor.playwright_driver import arrival_check


class FakePage:
    """url 과 body 텍스트만 갖는 최소 페이지."""

    def __init__(self, url: str = "http://h/good/welcome", text: str = "") -> None:
        self.url = url
        self._text = text

    def inner_text(self, selector: str) -> str:
        return self._text


class TestArrivalCheck:
    def test_경로와_문구를_모두_만족하면_통과(self):
        ok, reason = arrival_check(
            FakePage(text="가입이 완료되었습니다"),
            Expectation(type="toast_or_redirect", url_contains="/welcome",
                        value="가입이 완료되었습니다"),
        )
        assert ok, reason

    def test_이동하지_못하면_실패(self):
        ok, reason = arrival_check(
            FakePage(url="http://h/good/signup", text="가입이 완료되었습니다"),
            Expectation(type="toast_or_redirect", url_contains="/welcome"),
        )
        assert not ok
        assert "미이동" in reason and "/good/signup" in reason

    def test_문구가_없으면_실패(self):
        """URL 은 바뀌었는데 화면이 빈 상태를 도착으로 보면, 그 다음 화면의 결과가
        무엇을 뜻하는지 알 수 없게 된다."""
        ok, reason = arrival_check(
            FakePage(text=""),
            Expectation(type="toast_or_redirect", url_contains="/welcome",
                        value="가입이 완료되었습니다"),
        )
        assert not ok and "미노출" in reason

    def test_공백_배치가_달라도_같은_문구로_본다(self):
        """기획서 PDF 에서 뽑은 문구는 줄바꿈 위치가 화면과 다르다."""
        ok, _ = arrival_check(
            FakePage(text="가입이 완료되었습니다"),
            Expectation(type="toast_or_redirect", value="가입이\n완료되었습니다"),
        )
        assert ok

    def test_확인할_조건이_없으면_통과로_본다(self):
        """여기서 실패로 만들면 기획서가 성공 조건을 안 적은 화면의 흐름이 전부
        끊겨, 흐름 자체를 검증할 수 없게 된다. 그 누락은 S1 이 경고로 알린다."""
        ok, reason = arrival_check(FakePage(), Expectation(type="toast_or_redirect"))
        assert ok and "기획서에 없어" in reason

    def test_본문을_읽지_못해도_예외를_던지지_않는다(self):
        """스텝 실행 중이므로 예외로 파이프라인을 세우면 이후 케이스가 전부
        실행되지 않는다. 실패는 데이터로 다룬다."""

        class Broken(FakePage):
            def inner_text(self, selector: str) -> str:
                raise RuntimeError("detached")

        ok, reason = arrival_check(
            Broken(), Expectation(type="toast_or_redirect", value="문구"))
        assert not ok and "미노출" in reason
