"""pipeline 과 graph 의 결과 동일성 검증.

1차 그래프는 선형이라 pipeline.py 와 같은 결과를 내야 한다. 그 동일성을 지금
고정해 두면, 2차에서 self_heal 분기를 추가했을 때 리포트가 달라지는 원인이
'의도한 분기' 인지 '배선 실수' 인지 가릴 수 있다.

비교에서 제외하는 값: run_id, created_at, 소요 시간, 스크린샷 경로.
실행마다 달라지는 것이 정상인 값들이다. 판정 결과와 근거만 대조한다.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from prova.graph import run_graph
from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline

SPEC_PDF = "fixtures/specs/login_spec.pdf"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def sut_base() -> str:
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


def _comparable(report):
    """실행마다 달라지는 값을 걷어낸 비교용 형태."""
    return [
        {
            "case_id": v.case_id,
            "type": v.type,
            "violates": v.violates,
            "verdict": v.verdict,
            "failure_category": v.failure_category,
            "failure_detail": v.failure_detail,
            "expected": v.evidence.get("expected"),
            "actual": v.evidence.get("actual"),
            "steps": [(r.seq, r.action, r.target, r.status, r.error_code)
                      for r in v.step_results],
        }
        for v in report.cases
    ]


@pytest.fixture(scope="module")
def both_runs(sut_base, tmp_path_factory):
    """같은 입력으로 두 경로를 실행한다. bad 변형을 쓰는 이유: 통과와 실패가
    섞여 있어야 판정·분류·근거를 모두 비교할 수 있다."""
    url = f"{sut_base}/bad"
    llm_a = MockLLM.with_login_fixtures()
    llm_b = MockLLM.with_login_fixtures()

    pipe_report, _ = run_pipeline(
        pdf_path=SPEC_PDF, base_url=url, llm=llm_a,
        run_id="parity-pipeline", runs_root=tmp_path_factory.mktemp("pipe"),
    )
    graph_report, _ = run_graph(
        pdf_path=SPEC_PDF, base_url=url, llm=llm_b,
        run_id="parity-graph", runs_root=tmp_path_factory.mktemp("graph"),
    )
    return pipe_report, graph_report


class TestParity:
    def test_요약이_같다(self, both_runs):
        pipe, graph = both_runs
        for key in ("total", "pass", "fail", "pass_rate", "healed"):
            assert pipe.summary[key] == graph.summary[key], key

    def test_케이스별_판정과_근거가_같다(self, both_runs):
        pipe, graph = both_runs
        assert _comparable(pipe) == _comparable(graph)

    def test_실패한_규칙_집합이_같다(self, both_runs):
        pipe, graph = both_runs
        rules = lambda r: {v.violates for v in r.cases if v.verdict == "FAIL"}
        assert rules(pipe) == rules(graph)

    def test_그래프도_실제로_검증을_수행했다(self, both_runs):
        """양쪽이 똑같이 0건이어도 '같다' 는 성립한다. 그 허위 통과를 막는다."""
        _, graph = both_runs
        assert graph.summary["total"] == 7
        assert graph.summary["fail"] == 4


class TestGraphStructure:
    def test_노드가_모두_등록됐다(self):
        from prova.graph import build_graph

        nodes = set(build_graph().get_graph().nodes)
        for name in ("extract_spec", "generate_cases", "run_cases", "build_report"):
            assert name in nodes, name
