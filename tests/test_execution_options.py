"""실행 설정은 한 곳에서 읽는다.

CLI 두 경로와 웹 UI 가 같은 설정 읽기를 각자 복사해 두었고, 이미 어긋나
있었다 — 웹 UI 만 screenshot_every_step 을 bool 로 바꾸지 않았다. 설정 파일에
문자열 "false" 가 오면 웹 UI 에서만 참으로 읽혔을 것이다.
"""

from prova.pipeline import execution_options


def test_기본값():
    opts = execution_options({})
    assert opts == {
        "headless": True, "viewport": None, "step_timeout_ms": 10000,
        "settle_timeout_ms": 2000, "screenshot_every_step": True,
        "max_heal": 2, "min_confidence": 0.5,
    }


def test_창을_띄우면_headless_가_아니다():
    assert execution_options({}, headed=True)["headless"] is False


def test_값의_형을_맞춘다():
    cfg = {"execution": {"step_timeout_ms": "5000", "screenshot_every_step": 0},
           "agent": {"max_heal": "3"},
           "grounding": {"vlm_confidence_threshold": "0.7"}}
    opts = execution_options(cfg)
    assert opts["step_timeout_ms"] == 5000
    assert opts["screenshot_every_step"] is False
    assert opts["max_heal"] == 3
    assert opts["min_confidence"] == 0.7
