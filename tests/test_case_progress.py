"""실행 중에 케이스 단위 진행이 보인다.

S3~S5 는 상품등록 한 벌에 2분이 걸리는데, 그동안 터미널과 웹 UI 에는 'S3~S5
브라우저 실행 및 판정' 한 줄뿐이었다. 멈춘 것과 도는 것이 구별되지 않는다.
"""

from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline


def test_케이스마다_n_of_N_한_줄(sut_base, tmp_path):
    lines: list[str] = []
    report, _ = run_pipeline(
        pdf_path="fixtures/specs/login_spec.pdf",
        base_url=f"{sut_base}/good",
        llm=MockLLM.with_login_fixtures(),
        run_id="progress", runs_root=tmp_path,
        on_progress=lines.append,
    )
    n = len(report.cases)
    per_case = [l for l in lines if "케이스 " in l and "/" in l and "·" in l]
    assert len(per_case) == n
    assert per_case[0].strip().startswith(f"케이스 1/{n} ·")
    assert per_case[-1].strip().startswith(f"케이스 {n}/{n} ·")
    # 단계 머리줄 아래 상세로 묶이게 들여 쓴다 (웹 UI 가 들여쓴 줄을 상세로 읽는다)
    assert all(l.startswith("     ") for l in per_case)
