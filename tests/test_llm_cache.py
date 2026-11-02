"""모델 응답 캐시 — 같은 입력이면 다시 묻지 않되, 재사용했다는 사실은 남긴다."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from prova.llm.base import LLMError
from prova.llm.cache import CachedLLM
from prova.llm.factory import make_llm
from prova.llm.mock_backend import MockLLM
from prova.pipeline import run_pipeline
from prova.s6_report.report_builder import render_html
from prova.truth import is_private_path

ASK = dict(system="s", user="u", schema={"title": "T"}, max_tokens=10, temperature=0.0)


class Fake:
    name = "fake:m"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def complete_json(self, **_):
        self.calls += 1
        if self.fail:
            raise LLMError("꺼짐")
        return {"n": self.calls}

    def health(self):
        return "ok"


def test_같은_입력은_다시_묻지_않는다(tmp_path):
    inner = Fake()
    llm = CachedLLM(inner, tmp_path)
    assert llm.complete_json(**ASK) == llm.complete_json(**ASK) == {"n": 1}
    assert inner.calls == 1
    assert (llm.hits, llm.misses) == (1, 1)


def test_재시작해도_남는다(tmp_path):
    CachedLLM(Fake(), tmp_path).complete_json(**ASK)
    inner = Fake()
    assert CachedLLM(inner, tmp_path).complete_json(**ASK) == {"n": 1}
    assert inner.calls == 0


@pytest.mark.parametrize("change", [{"user": "x"}, {"system": "x"}, {"schema": {"title": "U"}},
                                    {"max_tokens": 11}])
def test_입력이_다르면_다시_묻는다(tmp_path, change):
    inner = Fake()
    llm = CachedLLM(inner, tmp_path)
    llm.complete_json(**ASK)
    llm.complete_json(**{**ASK, **change})
    assert inner.calls == 2


def test_모델이_다르면_다시_묻는다(tmp_path):
    CachedLLM(Fake(), tmp_path).complete_json(**ASK)
    other = Fake()
    other.name = "fake:다른모델"
    CachedLLM(other, tmp_path).complete_json(**ASK)
    assert other.calls == 1


def test_실패는_저장하지_않는다(tmp_path):
    with pytest.raises(LLMError):
        CachedLLM(Fake(fail=True), tmp_path).complete_json(**ASK)
    assert not list(tmp_path.iterdir())


def test_깨진_파일은_없는_것으로_친다(tmp_path):
    llm = CachedLLM(Fake(), tmp_path)
    llm.complete_json(**ASK)
    next(tmp_path.iterdir()).write_text("{", encoding="utf-8")
    assert CachedLLM(Fake(), tmp_path).complete_json(**ASK) == {"n": 1}


def test_읽기를_끄면_새로_묻고_저장은_한다(tmp_path):
    CachedLLM(Fake(), tmp_path).complete_json(**ASK)
    inner = Fake()
    inner.calls = 4
    assert CachedLLM(inner, tmp_path, read=False).complete_json(**ASK) == {"n": 5}
    assert CachedLLM(Fake(), tmp_path).complete_json(**ASK) == {"n": 5}


def test_이름과_나머지_속성을_그대로_보인다(tmp_path):
    llm = CachedLLM(Fake(), tmp_path)
    assert llm.name == "fake:m" and llm.health() == "ok"


def test_mock_은_감싸지_않는다():
    llm, _ = make_llm("mock", {"llm": {"cache_dir": "x"}}, "fixtures/specs/login_spec.pdf",
                      cache=True)
    assert isinstance(llm, MockLLM)


def test_기본값으로_캐시가_붙지_않는다(monkeypatch):
    # 측정 스크립트가 모르는 새 옛 답을 재면 안 된다
    from prova.llm import vllm_backend

    monkeypatch.setattr(vllm_backend.VLLMClient, "health", lambda self, timeout=10.0: "ok")
    llm, _ = make_llm("vllm", {"llm": {"cache_dir": "x"}}, "x.pdf")
    assert not isinstance(llm, CachedLLM)
    llm, _ = make_llm("vllm", {"llm": {"cache_dir": "x"}}, "x.pdf", cache=True)
    assert isinstance(llm, CachedLLM)
    llm, _ = make_llm("vllm", {"llm": {}}, "x.pdf", cache=True)
    assert not isinstance(llm, CachedLLM)


def test_저장_위치가_저장소에_올라가지_않는다():
    # 응답에 기획서 내용이 들어 있다
    cfg = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    assert is_private_path(Path(cfg["llm"]["cache_dir"]) / "x.json")


def test_재사용했다는_사실을_리포트가_말한다(sut_base, tmp_path):
    pdf = "fixtures/specs/login_spec.pdf"
    for rid in ("a", "b"):
        llm = CachedLLM(MockLLM.for_document(pdf), tmp_path / "cache")
        report, _ = run_pipeline(pdf, f"{sut_base}/good", llm, run_id=rid,
                                 runs_root=tmp_path / "runs", only="login-valid")
    assert report.summary["llm_cache"]["hits"] >= 1
    assert report.summary["llm_cache"]["misses"] == 0
    assert "저장된 모델 응답" in render_html(report)
