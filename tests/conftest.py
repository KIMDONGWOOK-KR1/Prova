"""테스트 공용 픽스처.

## SUT 를 테스트가 직접 띄운다

외부에서 띄워 둔 서버에 의존하면 테스트가 환경에 따라 통과·실패를 오간다.
uvicorn 을 스레드로 올려 테스트가 수명을 소유한다.

세션 범위로 한 번만 띄우는 이유: 검증 대상은 상태를 갖지 않는다(회원가입도
계정을 저장하지 않는다). 그래서 여러 테스트 파일이 같은 서버를 공유해도 서로의
결과에 영향을 주지 않고, 기동 비용을 화면 수만큼 곱하지 않아도 된다.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn


def _free_port() -> int:
    """비어 있는 포트를 OS 에게 받아 온다.

    고정 포트를 쓰면 다른 프로세스(개발 중 띄워 둔 SUT 등)와 충돌해 테스트가
    엉뚱한 서버를 검증한다.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def sut_base() -> str:
    """SUT 를 백그라운드 스레드로 띄우고 base URL(good/bad 변형 제외)을 돌려준다."""
    from sut.app import app

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("SUT 서버가 기동하지 않았습니다")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
