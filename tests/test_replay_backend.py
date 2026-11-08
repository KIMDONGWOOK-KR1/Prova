"""replay 백엔드 — 모델 서버 없이 전에 실모델이 낸 응답(캐시)만으로 돈다.

GPU 를 2026-11-13 에 반납한다. 그 뒤에도 실모델로 뽑은 결과를 시연·재현하려면 저장된
응답을 그대로 다시 써야 한다. mock(골든 정답)과 달리 **그때 모델이 실제로 낸 답**이다.
"""

from __future__ import annotations

import pytest

from prova.llm.base import LLMError
from prova.llm.cache import CachedLLM
from prova.llm.factory import make_llm


class _FakeServer:
    name = "vllm:m"
    model = "m"

    def __init__(self):
        self.calls = 0

    def complete_json(self, **request):
        self.calls += 1
        return {"answer": request["user"]}


def _cfg(tmp_path):
    return {"llm": {"model": "m", "cache_dir": str(tmp_path / "cache")}}


def _ask(llm, user="질문"):
    return llm.complete_json(system="s", user=user, schema={"title": "T"}, max_tokens=10)


def test_vllm_으로_저장한_응답을_서버_없이_그대로_쓴다(tmp_path):
    _ask(CachedLLM(_FakeServer(), tmp_path / "cache"))  # GPU 가 있을 때 한 번
    llm, warnings = make_llm("replay", _cfg(tmp_path), "x.pdf")
    assert _ask(llm) == {"answer": "질문"}
    assert llm.hits == 1 and llm.misses == 0
    assert any("replay" in w for w in warnings)


def test_저장된_응답이_없으면_무엇을_해야_하는지_말하고_실패한다(tmp_path):
    llm, _ = make_llm("replay", _cfg(tmp_path), "x.pdf")
    with pytest.raises(LLMError, match="저장된 모델 응답이 없습니다"):
        _ask(llm, user="처음 보는 질문")


def test_리포트에는_replay_로_남는다(tmp_path):
    llm, _ = make_llm("replay", _cfg(tmp_path), "x.pdf")
    assert llm.name == "replay:vllm:m"


def test_캐시_폴더_설정이_없으면_저장소에_넣어_둔_응답을_본다():
    from prova.llm.factory import REPLAY_DIR

    llm, _ = make_llm("replay", {"llm": {"model": "m"}}, "x.pdf")
    assert llm.directory == REPLAY_DIR


@pytest.mark.parametrize("spec", ["login_spec", "signup_spec", "multi_spec"])
def test_저장소의_시연용_응답으로_픽스처_기획서가_서버_없이_재생된다(tmp_path, spec):
    """동결(2026-11-07)의 계약. 이 테스트가 깨지면 S1·S2 의 프롬프트나 스키마가 동결 뒤에
    바뀐 것이다 — GPU 가 없으니 응답을 다시 받을 수 없고, 시연이 깨진다."""
    from typer.testing import CliRunner

    from prova.cli import app

    cfg = tmp_path / "c.yaml"
    cfg.write_text("llm:\n  model: qwen3.5-4b-awq\n", encoding="utf-8")
    result = CliRunner().invoke(app, [
        "run", "--pdf", f"fixtures/specs/{spec}.pdf", "--backend", "replay",
        "--url", "http://127.0.0.1:9/good", "--config", str(cfg), "--plan-only",
        "--runs-root", str(tmp_path / "runs"),
    ])
    assert "저장된 모델 응답이 없습니다" not in result.output
    assert result.exit_code == 0, result.output


def test_CLI_가_replay_를_받는다(tmp_path):
    from typer.testing import CliRunner

    from prova.cli import app

    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"llm:\n  model: m\n  cache_dir: {(tmp_path / 'cache').as_posix()}\n",
                   encoding="utf-8")
    result = CliRunner().invoke(app, [
        "run", "--pdf", "fixtures/specs/login_spec.pdf", "--backend", "replay",
        "--url", "http://127.0.0.1:9/good", "--config", str(cfg), "--plan-only",
        "--runs-root", str(tmp_path / "runs"),
    ])
    # 서버 확인 단계에서 막히지 않고 S1 까지 가서, 저장된 응답이 없다고 말한다
    assert "없는 백엔드" not in result.output
    assert "저장된 모델 응답이 없습니다" in result.output
