"""픽스처가 서로 어긋나지 않는가 — 조용히 낡는 것을 막는다.

## 왜 이 테스트가 있는가

`multi_spec.md`(통합 기획서)는 화면별 기획서를 이어 붙인 문서다. 처음에는 손으로 이어
붙였는데, **화면 기획서를 고쳤을 때 통합 문서가 조용히 낡았다.**

실제로 겪었다. 로그인 기획서에 예시 동작 절을 추가하고 PDF 만 다시 만들었더니 통합
문서에는 그 절이 없었고, 로그인 화면 케이스가 9건이 아니라 7건으로 나왔다. 관통 테스트가
숫자로 잡아 줬지만 그건 운이었다 — 케이스 수를 못 박아 두지 않았다면 **통합 문서 쪽
검증이 두 건 줄어든 채로** 지나갔을 것이다.

조립을 스크립트로 옮기는 것만으로는 부족하다. 스크립트는 실행을 잊는 것을 막지 못한다.
낡았는지를 여기서 확인한다.

## PDF 는 왜 확인하지 않는가

PDF 는 reportlab 이 만드는 바이너리이고, 폰트·버전에 따라 바이트가 달라진다. 내용이
같은지를 바이트로 볼 수 없다. 대신 **PDF 에서 뽑은 화면·요소가 md 와 맞는지**를 본다 —
그게 실제로 파이프라인이 읽는 값이다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from prova.s1_spec_extractor.pdf_parser import parse_pdf

SPEC_DIR = Path("fixtures/specs")

# scripts/ 는 패키지가 아니라 import 할 수 없다. 파일에서 함수만 꺼내 쓴다.
_SCRIPT = Path("scripts/make_multi_spec.py")


def _assemble() -> str:
    """make_multi_spec.assemble() 을 그대로 불러 조립 결과를 얻는다."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_multi_spec", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assemble()


class TestMultiSpecUpToDate:
    def test_통합_문서가_화면_기획서와_맞다(self):
        """화면 기획서를 고치고 통합 문서를 다시 조립하지 않으면 여기서 걸린다.

        고치는 방법: `uv run python scripts/make_multi_spec.py` 그다음
        `uv run python scripts/make_spec_pdf.py fixtures/specs/multi_spec.md`
        """
        on_disk = (SPEC_DIR / "multi_spec.md").read_text(encoding="utf-8")
        assert on_disk == _assemble(), (
            "통합 기획서가 화면별 기획서와 어긋났습니다.\n"
            "  uv run python scripts/make_multi_spec.py\n"
            "  uv run python scripts/make_spec_pdf.py fixtures/specs/multi_spec.md"
        )

    def test_조각_파일은_PDF가_없다(self):
        """'_' 로 시작하는 조각만 담긴 PDF 를 만들면 화면 개요도 요소 표도 없는
        문서가 되어, S1 이 요소 없는 빈 화면을 추출한다."""
        for fragment in SPEC_DIR.glob("_*.md"):
            assert not fragment.with_suffix(".pdf").exists(), fragment


@pytest.fixture(scope="module")
def doc():
    """통합 문서 PDF. 파싱이 느리지 않지만 한 번만 읽는다."""
    pdf = SPEC_DIR / "multi_spec.pdf"
    if not pdf.exists():
        pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
    return parse_pdf(pdf)


class TestMultiSpecPdfMatchesMarkdown:
    """PDF 가 md 보다 낡지 않았는가 — 파이프라인이 읽는 것은 PDF 다."""

    def test_화면_수가_맞다(self, doc):
        screens, warnings = doc.split_screens()
        assert len(screens) == 3, f"화면 {len(screens)}개, 경고: {warnings}"

    def test_화면마다_요소가_단일_문서와_같다(self, doc):
        """PDF 가 낡으면 여기서 갈린다. 요소가 줄면 그 화면의 검증도 함께 줄어든다."""
        screens, _ = doc.split_screens()
        got = {
            sub.declared_screen_meta().get("screen_id"): sub.declared_element_ids()
            for sub in screens
        }
        for stem in ("login", "signup", "search"):
            want = parse_pdf(SPEC_DIR / f"{stem}_spec.pdf").declared_element_ids()
            assert got.get(stem) == want, f"{stem} 요소 불일치"

    def test_예시_시나리오가_단일_문서와_같다(self, doc):
        """로그인의 예시 동작 절이 통합 문서에서 빠졌던 것이 이 대조로 잡힌다."""
        screens, _ = doc.split_screens()
        got = {
            sub.declared_screen_meta().get("screen_id"): sub.declared_scenarios()
            for sub in screens
        }
        for stem in ("login", "signup", "search"):
            want = parse_pdf(SPEC_DIR / f"{stem}_spec.pdf").declared_scenarios()
            assert got.get(stem) == want, f"{stem} 예시 시나리오 불일치"

    def test_흐름이_읽힌다(self, doc):
        assert {f["flow_id"] for f in doc.declared_flows()} == {
            "signup_link_to_login", "signup_then_login"}


class TestScriptIsIdempotent:
    def test_두_번_돌려도_바뀌지_않는다(self):
        """조립이 결정적이어야 위 대조가 의미를 갖는다. 실행마다 달라지면
        '낡았다' 와 '방금 만들었다' 를 구별할 수 없다."""
        assert _assemble() == _assemble()

    def test_스크립트가_실행된다(self):
        """import 로만 시험하면 __main__ 경로가 깨진 것을 못 본다.

        `--check` 로 부른다. 그냥 부르면 **테스트가 추적 중인 픽스처를 고친다** —
        실제로 겪었다. 낡음 검출을 확인하려고 화면 기획서에 임시 절을 넣고 이 파일을
        돌렸더니, 스크립트가 그 임시 절을 통합 문서에 박아 넣어서 임시 절을 지운
        뒤에도 어긋난 상태가 남았다. 테스트는 부작용이 없어야 한다.
        """
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--check"], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr
