"""S1 추출 정확도 — 실제 LLM 대상 골든 비교.

## 왜 이 테스트가 따로 있는가

S1 이 조용히 실패하면 파이프라인 전체가 무의미해진다. constraints 규칙 하나를
놓치면 S2 가 그 규칙의 위반 케이스를 만들지 않고, 결과적으로 구현이 그 규칙을
빠뜨렸어도 리포트는 초록불이 된다. **미탐이 경고 없이 발생하는 유일한 지점**이다.

그래서 정답(golden)을 손으로 만들어 두고 추출 결과를 대조한다. 이 비교가
명세서 §9 의 '로컬 모델 vs API 단계별 정확도 측정' 의 실행 형태이기도 하다.

## 실행

    uv run pytest tests/test_s1_golden.py -v          # vLLM 없으면 자동 skip
    PROVA_LLM_BACKEND=vllm uv run pytest tests/test_s1_golden.py -v

vLLM 에 연결되지 않으면 skip 한다. 실패로 처리하면 GPU 없는 환경에서 전체
테스트가 빨간불이 되어, 정작 중요한 파이프라인 회귀를 못 보게 된다.

## 비교 강도를 필드마다 다르게 둔다

    constraints    엄격 비교 — 키 이름과 값이 정확히 같아야 한다.
                   키가 흔들리면(min_len 등) rule_expander 가 규칙을 인식하지 못한다.
    error_message  공백 무시 비교 — PDF 추출 문구는 줄바꿈 위치가 다르다.
    screen_name 등 공백 무시 비교.
    success_condition  포함 비교 — 문장 표현은 달라도 핵심 정보(경로·문구)가
                   들어 있으면 된다. S2 가 정규식으로 뽑아 쓰기 때문이다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from prova.llm.base import LLMError
from prova.models import ScreenSpec
from prova.s1_spec_extractor.extractor import extract_from_pdf
from prova.text_utils import contains_loose, loosen

SPEC_PDF = "fixtures/specs/login_spec.pdf"
GOLDEN = Path("fixtures/specs/login_spec.golden.json")


@pytest.fixture(scope="module")
def golden() -> ScreenSpec:
    return ScreenSpec.model_validate(json.loads(GOLDEN.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def extracted() -> ScreenSpec:
    """실제 LLM 으로 추출한 ScreenSpec. 연결 안 되면 skip."""
    import yaml

    cfg = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    llm_cfg = cfg.get("llm", {})
    backend = os.environ.get("PROVA_LLM_BACKEND", llm_cfg.get("backend", "vllm"))

    if backend != "vllm":
        pytest.skip(f"backend={backend} — 이 테스트는 실제 모델 정확도를 측정한다")

    from prova.llm.vllm_backend import VLLMClient

    client = VLLMClient(
        base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
        model=llm_cfg.get("model", "Qwen/Qwen2.5-7B-Instruct-AWQ"),
        timeout=float(llm_cfg.get("timeout", 180)),
    )
    try:
        client.health(timeout=4.0)  # skip 판단은 빨라야 한다
    except LLMError as exc:
        pytest.skip(f"vLLM 에 연결할 수 없습니다 — {exc}")

    try:
        return extract_from_pdf(SPEC_PDF, client)
    except LLMError as exc:
        pytest.fail(f"S1 추출이 실패했습니다: {exc}")


class TestScreenLevel:
    def test_화면_식별정보(self, extracted, golden):
        assert extracted.screen_id == golden.screen_id
        assert loosen(extracted.screen_name) == loosen(golden.screen_name)
        assert extracted.url_path == golden.url_path

    def test_요소를_빠뜨리지_않는다(self, extracted, golden):
        got = {e.element_id for e in extracted.elements}
        want = {e.element_id for e in golden.elements}
        assert not (want - got), f"놓친 요소: {want - got}"

    def test_필수입력_공통문구(self, extracted, golden):
        """required 위반 케이스의 기대 문구가 여기서 온다."""
        if golden.required_message:
            assert extracted.required_message, "required_message 를 추출하지 못했다"
            assert loosen(extracted.required_message) == loosen(golden.required_message)

    def test_성공조건에_경로와_문구가_들어있다(self, extracted, golden):
        """S2 가 여기서 정상 케이스의 기대를 뽑는다. 문장 표현은 달라도 된다."""
        assert contains_loose(extracted.success_condition, "/dashboard")
        assert contains_loose(extracted.success_condition, "환영합니다")


class TestConstraints:
    """가장 중요한 비교. 여기가 틀리면 검증이 조용히 무력해진다."""

    def test_검증규칙이_정확히_일치한다(self, extracted, golden):
        for want in golden.elements:
            got = extracted.element_by_id(want.element_id)
            assert got is not None, f"{want.element_id} 요소 없음"
            assert got.constraints == want.constraints, (
                f"{want.element_id} 의 검증 규칙 불일치\n"
                f"  기대: {want.constraints}\n"
                f"  실제: {got.constraints}\n"
                f"  -> 키 이름이 다르면 rule_expander 가 규칙을 인식하지 못한다"
            )

    def test_필수여부가_일치한다(self, extracted, golden):
        for want in golden.elements:
            got = extracted.element_by_id(want.element_id)
            assert got.required == want.required, f"{want.element_id}.required"

    def test_요소_유형이_일치한다(self, extracted, golden):
        for want in golden.elements:
            got = extracted.element_by_id(want.element_id)
            assert got.type == want.type, f"{want.element_id}.type"


class TestErrorMessages:
    """문구가 판정 근거이므로 정확해야 한다. 공백 차이만 허용한다."""

    def test_에러문구가_일치한다(self, extracted, golden):
        for want in golden.elements:
            if not want.error_message:
                continue
            got = extracted.element_by_id(want.element_id)
            assert got.error_message, f"{want.element_id} 의 에러 문구 누락"
            assert loosen(got.error_message) == loosen(want.error_message), (
                f"{want.element_id} 의 에러 문구 불일치\n"
                f"  기대: {want.error_message}\n"
                f"  실제: {got.error_message}"
            )


class TestSampleValues:
    def test_테스트계정을_추출한다(self, extracted, golden):
        """정상 케이스가 이 값을 쓴다. 없으면 코드가 만든 값이 쓰이고, 그 값은
        규칙은 만족하지만 등록된 계정이 아니어서 정상 케이스가 오탐 FAIL 이 된다."""
        for want in golden.elements:
            if not want.sample_value:
                continue
            got = extracted.element_by_id(want.element_id)
            assert got.sample_value, (
                f"{want.element_id} 의 예시값을 추출하지 못했다 "
                f"(기대: {want.sample_value!r}) — 정상 케이스가 오탐 실패할 수 있다"
            )
            assert loosen(got.sample_value) == loosen(want.sample_value)


class TestNoSilentFailure:
    def test_추출_실패를_경고로_알린다(self, extracted):
        """constraints 가 하나도 없으면 extractor 가 경고를 남겨야 한다.
        경고 없이 빈 결과가 지나가면 리포트가 근거 없이 초록불이 된다."""
        if not any(e.constraints for e in extracted.elements):
            assert extracted.warnings, "추출 실패인데 경고가 없다"
