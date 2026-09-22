"""웹 UI 와 리포트가 사람이 읽는 말로 원인을 구분한다 (2026-09-22 사용성 점검).

- 작업 실패는 `str(exc)` 를 그대로 화면에 보냈다. KeyError 면 `'screen_id'`
  한 단어가 뜬다. 우리가 쓴 한국어 메시지는 그대로 두고, 그 밖의 예외만
  '내부 오류' 로 감싸 무엇을 하면 되는지 말한다.
- 리포트는 실패 분류가 펼친 카드 안쪽 표에만 있었다. 요약 줄만 보면 구현
  결함과 도구·환경 실패가 똑같이 'FAIL' 이다.
"""

from __future__ import annotations

import time

from prova.models import TestReport, Verdict
from prova.s6_report.report_builder import render_html
from prova.server.runner import JobRunner as Runner


def _wait(runner, job):
    for _ in range(100):
        if runner.get(job.job_id).status != "running":
            return runner.get(job.job_id)
        time.sleep(0.02)
    raise AssertionError("작업이 끝나지 않았다")


class TestJobError:
    def test_우리가_쓴_안내문은_그대로_보인다(self):
        r = Runner()

        def work(report):
            raise ValueError("요청에 맞는 케이스가 없습니다")

        job = _wait(r, r.submit("run", work))
        assert job.error == "요청에 맞는 케이스가 없습니다"

    def test_내부_예외는_내부_오류로_감싼다(self):
        r = Runner()

        def work(report):
            raise KeyError("screen_id")

        job = _wait(r, r.submit("run", work))
        assert job.error.startswith("내부 오류 (KeyError)")
        assert "screen_id" in job.error
        assert "개발자" in job.error


def _fail(case_id, category, title):
    return Verdict(case_id=case_id, title=title, type="negative", screen_id="login",
                   verdict="FAIL", failure_category=category, failure_detail="사유")


class TestReportBadges:
    def _html(self):
        verdicts = [
            _fail("login-a-001", "assertion_mismatch", "형식 검증"),
            _fail("login-b-002", "precondition_failed", "가격 검증"),
            Verdict(case_id="login-c-003", title="정상", type="positive",
                    screen_id="login", verdict="PASS"),
        ]
        report = TestReport(run_id="r", target_url="http://x/good",
                            spec_source="login_spec.pdf", cases=verdicts,
                            summary={"total": 3, "pass": 1, "fail": 2,
                                     "pass_rate": 33.3})
        return render_html(report)

    def test_요약_줄에_분류_배지가_붙는다(self):
        html = self._html()
        assert "class='tag cat defect'>기획서와 다름<" in html
        assert "class='tag cat infra'>전제 미충족<" in html

    def test_카드_아래에_실패_구성이_한_줄로_나온다(self):
        html = self._html()
        assert "기획서와 다름 1 · 실행 문제 1" in html

    def test_폴더째_공유하라는_안내가_있다(self):
        assert "폴더째" in self._html()
