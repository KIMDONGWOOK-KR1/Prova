"""[멈추기] — 다음 진행 보고에서 작업이 멈추고, 실행기는 다음 작업을 받을 수 있어야 한다."""

import threading
import time

from prova.server.runner import JobRunner


def test_멈추면_다음_보고에서_끝나고_실행기가_비워진다():
    runner = JobRunner()
    gate = threading.Event()

    def work(report):
        report("케이스 1/3")
        gate.wait(2)
        report("케이스 2/3")  # 여기서 멈춘다
        return "끝까지 돌았다"

    job = runner.submit("run", work)
    assert runner.cancel(job.job_id)
    gate.set()
    for _ in range(50):
        if job.status != "running":
            break
        time.sleep(0.05)
    assert job.status == "error" and job.error.startswith("실행을 멈췄습니다")
    assert job.result is None
    assert not runner.busy
    assert not runner.cancel(job.job_id)  # 끝난 작업은 다시 멈출 수 없다
