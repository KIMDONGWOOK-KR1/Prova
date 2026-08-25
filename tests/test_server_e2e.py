"""웹 UI 의 HTTP 층 관통 테스트 — 계획 확인 단계가 실제로 안전장치인지 고정한다.

## 이 테스트가 지키는 것

UI 를 붙이는 이유는 편의가 아니라 **자연어 층이 만드는 미탐을 사람이 볼 수 있게
하는 것**이다. 그래서 확인할 것은 화면이 예쁘게 뜨는가가 아니라 다음이다.

    1. 계획 단계는 브라우저를 열지 않는다 — 승인 전에 아무것도 실행되지 않는다
    2. 계획에는 제외된 케이스도 실려 온다 — 사람이 도로 넣을 수 있어야 한다
    3. 실행은 승인한 목록으로만 돈다 — 승인하지 않은 것이 몰래 돌지 않는다
    4. 0건 실행은 거부된다 — "통과율 100%" 리포트를 만들 수 없다
    5. 동시 실행은 거부된다 — 브라우저·GPU 경합이 판정 타이밍을 흔든다
    6. 허용되지 않은 경로는 열지 않는다

SUT 는 conftest.py 의 sut_base 픽스처가 띄운다.
"""

from __future__ import annotations

import re
import time

import pytest
from fastapi.testclient import TestClient

from prova.server import app as server_app

SPEC = "fixtures/specs/login_spec.pdf"

# 요청 해석이 성공했을 때 고를 케이스.
PICKED = [
    "login-password-min_length-005",
    "login-password-require_uppercase-006",
    "login-password-require_special-007",
]


@pytest.fixture
def selecting_llm(monkeypatch):
    """요청 해석에 성공하는 백엔드를 물린다.

    기본 mock 에는 CaseSelection 응답이 없어 항상 해석 실패로 빠진다. 그러면
    '선택이 실제로 일어나는가' 를 확인할 수 없다 — 통과하지만 아무것도 확인하지
    않는 테스트가 된다.
    """
    from prova.llm.mock_backend import MockLLM

    def fake(backend, cfg, pdf):
        llm = MockLLM.for_spec(pdf)
        llm.register(
            "CaseSelection",
            {"case_ids": list(PICKED), "reason": "비밀번호 규칙 케이스만 골랐습니다"},
        )
        return llm, []

    monkeypatch.setattr(server_app, "make_llm", fake)


@pytest.fixture
def client(monkeypatch, tmp_path):
    # 리포트가 저장소의 runs/ 를 어지럽히지 않게 한다. chdir 은 못 쓴다 —
    # 서버가 fixtures/specs·configs 를 상대 경로로 읽는다. 실행 뿌리(RUNS)만
    # 옮긴다. (2026-08-22 까지 `chdir(Path.cwd())` 라는 no-op 이었고, 실행
    # 기록 테스트가 저장소에 쌓인 잔여물에 기대고 있었다.)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(server_app, "RUNS", runs)
    # /runs 정적 마운트는 import 시점에 디렉터리를 굳히므로 함께 옮긴다.
    from starlette.routing import Mount
    static = next(r.app for r in server_app.app.routes
                  if isinstance(r, Mount) and r.name == "runs")
    monkeypatch.setattr(static, "directory", runs)
    monkeypatch.setattr(static, "all_directories", [runs])
    server_app.runner.__init__()  # 작업 상태를 테스트마다 초기화
    return TestClient(server_app.app)


def wait(client, job_id, timeout=180):
    """작업이 끝날 때까지 진행 메시지를 이어 받는다 (화면이 하는 일과 같다)."""
    since = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/job/{job_id}?since={since}").json()
        since = job["next"]
        if job["status"] != "running":
            return job
        time.sleep(0.2)
    raise AssertionError(f"작업이 {timeout}초 안에 끝나지 않았습니다: {job_id}")


def make_plan(client, sut_base, request=None):
    res = client.post("/api/plan", json={
        "pdf": SPEC, "url": f"{sut_base}/bad", "request": request, "backend": "mock",
    })
    assert res.status_code == 200, res.text
    job = wait(client, res.json()["job_id"])
    assert job["status"] == "done", job["error"]
    return job["result"]


class TestPlanStage:
    def test_계획은_브라우저_없이_만들어진다(self, client, sut_base):
        """대상 URL 이 없는 곳을 가리켜도 계획은 나와야 한다 — 계획 단계가
        브라우저를 열지 않는다는 증거다. 승인 전에는 아무것도 실행되지 않는다."""
        res = client.post("/api/plan", json={
            "pdf": SPEC, "url": "http://localhost:1/없는곳", "backend": "mock",
        })
        job = wait(client, res.json()["job_id"])
        assert job["status"] == "done"
        assert job["result"]["cases"]

    def test_요청이_없으면_전부_선택된다(self, client, sut_base):
        plan = make_plan(client, sut_base)
        assert all(c["selected"] for c in plan["cases"])
        assert plan["request"] == ""

    def test_제외된_케이스도_실려_온다(self, client, sut_base, selecting_llm):
        """이 화면의 핵심은 무엇을 안 보는지다. 제외된 것이 안 보이면
        사람이 도로 넣을 수 없고, 그러면 확인 단계가 형식만 남는다."""
        plan = make_plan(client, sut_base, "비밀번호 규칙만 봐줘")
        on = [c["case_id"] for c in plan["cases"] if c["selected"]]
        off = [c["case_id"] for c in plan["cases"] if not c["selected"]]

        assert on == PICKED
        assert off, "제외된 케이스가 목록에서 사라지면 사람이 도로 넣을 수 없다"
        assert len(plan["cases"]) == plan["total_generated"]
        assert "login-email-format-003" in off

    def test_제외된_케이스도_제목과_규칙을_그대로_갖는다(self, client, sut_base, selecting_llm):
        """확인 단계의 존재 이유는 '이 제외가 안전한가' 를 사람이 판단하는 것이다.
        제외된 행에 case_id 만 남으면 판단이 가장 필요한 자리에 정보가 가장 없다."""
        plan = make_plan(client, sut_base, "비밀번호 규칙만 봐줘")
        off = [c for c in plan["cases"] if not c["selected"]]
        assert off

        by_id = {c["case_id"]: c for c in off}
        email = by_id["login-email-format-003"]
        assert email["title"] != email["case_id"], "제목이 case_id 로 대체되면 안 된다"
        assert email["screen_id"] == "login"
        assert email["violates"] == "format"

        # 제외된 것 전부가 화면 정보를 갖는다
        assert all(c["screen_id"] for c in off)

    def test_목록이_생성_순서를_지킨다(self, client, sut_base, selecting_llm):
        """선택된 것을 앞으로 몰면 기획서를 읽은 순서가 사라져, 사람이 무엇이
        빠졌는지 문맥 없이 봐야 한다."""
        plan = make_plan(client, sut_base, "비밀번호 규칙만 봐줘")
        ids = [c["case_id"] for c in plan["cases"]]
        full = [c["case_id"] for c in make_plan(client, sut_base)["cases"]]
        assert ids == full

    def test_모델의_선택_근거를_보여준다(self, client, sut_base, selecting_llm):
        plan = make_plan(client, sut_base, "비밀번호 규칙만 봐줘")
        assert plan["reason"] == "비밀번호 규칙 케이스만 골랐습니다"
        assert plan["fallback"] is False

    def test_해석_실패는_전체를_고르는_쪽으로_넘어진다(self, client, sut_base):
        """mock 백엔드에는 CaseSelection 응답이 없다 — 해석 실패 상황이다.
        적게 고르면 결함이 숨지만 많이 고르면 숨지 않는다."""
        plan = make_plan(client, sut_base, "비밀번호 규칙만 봐줘")
        assert plan["fallback"] is True
        assert all(c["selected"] for c in plan["cases"])
        assert plan["warnings"]


class TestRunStage:
    def test_승인한_목록으로만_돈다(self, client, sut_base):
        plan = make_plan(client, sut_base)
        approved = [
            "login-password-min_length-005",
            "login-password-require_uppercase-006",
        ]
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": approved, "reason": "테스트",
        })
        assert res.status_code == 200, res.text
        job = wait(client, res.json()["job_id"])
        assert job["status"] == "done", job["error"]
        assert job["result"]["summary"]["total"] == len(approved)

    def test_리포트를_받아_볼_수_있다(self, client, sut_base):
        make_plan(client, sut_base)
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        job = wait(client, res.json()["job_id"])
        page = client.get(job["result"]["report_url"])
        assert page.status_code == 200
        assert "Prova" in page.text


class TestSafety:
    def test_0건_실행은_거부한다(self, client, sut_base):
        """0건 실행은 '전체 0건, 통과율 100%' 리포트가 된다."""
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock", "case_ids": [],
        })
        assert res.status_code == 400
        assert "100%" in res.json()["detail"]

    def test_허용되지_않은_경로는_열지_않는다(self, client, sut_base):
        res = client.post("/api/plan", json={
            "pdf": "../../etc/passwd", "url": f"{sut_base}/bad", "backend": "mock",
        })
        assert res.status_code in (400, 404)

    def test_없는_기획서는_404(self, client, sut_base):
        res = client.post("/api/plan", json={
            "pdf": "fixtures/specs/없는것.pdf", "url": f"{sut_base}/bad", "backend": "mock",
        })
        assert res.status_code == 404

    def test_동시_실행을_거부한다(self, client, sut_base):
        """브라우저와 GPU 를 두 작업이 함께 쓰면 대기 상한에 기대는 판정이 흔들린다.
        느린 것은 참을 수 있지만 판정이 흔들리는 것은 참을 수 없다."""
        first = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        assert first.status_code == 200
        second = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        assert second.status_code == 409
        wait(client, first.json()["job_id"])  # 뒷정리

    def test_없는_작업은_404(self, client):
        assert client.get("/api/job/없는것").status_code == 404


class TestRunHistory:
    def test_리포트가_있는_실행만_준다(self, client, sut_base):
        """runs/ 에는 report.json 이 없는 디버그·데모 잔여물이 많다. 목록에
        넣으면 눌렀을 때 404 가 난다."""
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        wait(client, res.json()["job_id"])

        runs = client.get("/api/runs").json()["runs"]
        assert runs
        for r in runs:
            assert r["run_id"] and r["summary"]
            assert client.get(f"/api/report/{r['run_id']}").status_code == 200

    def test_최신순이다(self, client, sut_base):
        """실행 2건을 여기서 직접 만든다 — 앞 테스트의 잔여물에 기대면 빈 환경에서
        `[] == sorted([])` 로 공허하게 통과한다."""
        for _ in range(2):
            res = client.post("/api/run", json={
                "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
                "case_ids": ["login-valid-001"],
            })
            wait(client, res.json()["job_id"])
            time.sleep(1.1)  # run_id 가 초 단위라 같은 초에 겹치면 덮어쓴다
        runs = client.get("/api/runs").json()["runs"]
        assert len(runs) >= 2
        stamps = [r["created_at"] for r in runs]
        assert stamps == sorted(stamps, reverse=True)

    def test_저장소의_runs_를_쓰지_않는다(self, client, sut_base, tmp_path):
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        wait(client, res.json()["job_id"])
        made = list((tmp_path / "runs").iterdir())
        assert made, "실행 결과가 격리된 runs/ 에 쓰여야 한다"


class TestShell:
    def test_첫_화면이_뜬다(self, client):
        page = client.get("/")
        assert page.status_code == 200
        assert "설계 문서 기반 QA 에이전트" in page.text

    def test_외부_자원을_불러오지_않는다(self, client):
        """리포트와 같은 원칙이다 — 폐쇄망에서도 열려야 한다."""
        page = client.get("/").text
        for tag in ("//cdn", "https://", "http://fonts", "@import"):
            assert tag not in page, f"외부 자원을 불러옵니다: {tag}"

    def test_스타일과_스크립트가_같은_출처에서_온다(self, client):
        for path in ("/static/tokens.css", "/static/app.css", "/static/app.js"):
            assert client.get(path).status_code == 200, path

    def test_토큰이_theme_에서_온다(self, client):
        """색을 만드는 곳이 하나여야 UI 와 리포트가 갈라지지 않는다."""
        css = client.get("/static/tokens.css").text
        assert "--bg-canvas" in css and "prefers-color-scheme: dark" in css

    def test_기획서_목록을_준다(self, client):
        st = client.get("/api/state").json()
        assert any("login_spec.pdf" in p for p in st["specs"])


class TestReportAssets:
    """리포트 안의 증거 자료(스크린샷·DOM 스냅샷)가 화면에서 살아 있는지.

    리포트는 스크린샷을 상대 경로로 참조한다. 리포트 파일만 돌려주면 그 경로가
    엉뚱한 곳으로 풀려 이미지가 전부 깨진다 — 판정의 근거를 보여주는 것이 이
    도구의 값인데, 그 근거가 화면에서 사라진다.
    """

    def test_스크린샷이_화면에서도_열린다(self, client, sut_base):
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-password-min_length-005"],
        })
        job = wait(client, res.json()["job_id"])
        url = job["result"]["report_url"]

        page = client.get(url)
        assert page.status_code == 200

        shots = re.findall(r"<img src='([^']+)'", page.text)
        assert shots, "리포트에 스크린샷이 없다"

        base = url.rsplit("/", 1)[0]
        for rel in shots[:3]:
            got = client.get(f"{base}/{rel}")
            assert got.status_code == 200, f"증거 자료가 깨졌다: {base}/{rel}"

    def test_옛_경로는_리포트로_넘긴다(self, client, sut_base):
        make_plan(client, sut_base)
        res = client.post("/api/run", json={
            "pdf": SPEC, "url": f"{sut_base}/bad", "backend": "mock",
            "case_ids": ["login-valid-001"],
        })
        job = wait(client, res.json()["job_id"])
        run_id = job["result"]["run_id"]
        assert client.get(f"/api/report/{run_id}").status_code == 200


class TestFigmaMerge:
    """병합 모드 — 계획 화면이 실행 전에 기획↔디자인 모순을 보여준다."""

    FIGMA = "fixtures/figma/synthetic_mismatch.json"

    def _plan(self, client, sut_base, **extra):
        job = wait(client, client.post("/api/plan", json={
            "pdf": SPEC, "url": f"{sut_base}/good", "backend": "mock", **extra,
        }).json()["job_id"])
        assert job["status"] == "done", job.get("error")
        return job["result"]

    def test_figma_를_주면_계획에_불일치가_실린다(self, client, sut_base):
        found = self._plan(client, sut_base, figma=self.FIGMA)["design_mismatches"]
        assert any("아이디를 입력하세요" in f for f in found)
        assert any("OTP" in f for f in found)

    def test_figma_없으면_불일치_목록이_빈다(self, client, sut_base):
        assert self._plan(client, sut_base)["design_mismatches"] == []

    def test_허용되지_않은_figma_경로는_거부한다(self, client, sut_base):
        r = client.post("/api/plan", json={
            "pdf": SPEC, "url": f"{sut_base}/good", "backend": "mock",
            "figma": "../../.env",
        })
        assert r.status_code == 400

    def test_state_가_figma_목록을_준다(self, client):
        figmas = client.get("/api/state").json()["figmas"]
        assert any(p.endswith("login_signup.json") for p in figmas)

    def test_json_업로드를_받는다(self, client, tmp_path, monkeypatch):
        uploads = tmp_path / "up"
        monkeypatch.setattr(server_app, "UPLOADS", uploads)
        r = client.post("/api/upload", files={
            "file": ("resp.json", b"{}", "application/json")})
        assert r.status_code == 200 and r.json()["path"].endswith("resp.json")
