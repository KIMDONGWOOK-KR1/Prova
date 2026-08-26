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
from conftest import load_script

from prova.s1_spec_extractor.pdf_parser import parse_pdf

SPEC_DIR = Path("fixtures/specs")

#: 조립 스크립트. 함수를 직접 부르는 데(_assemble)와 --check 를 실행하는 데 둘 다 쓴다.
_SCRIPT = Path("scripts/make_multi_spec.py")


def _assemble(name: str = "multi") -> str:
    """make_multi_spec.assemble() 을 그대로 불러 조립 결과를 얻는다."""
    return load_script(str(_SCRIPT)).assemble(name)


#: 조립되는 문서 이름들. 스크립트가 아는 목록을 그대로 읽는다 — 여기에 손으로
#: 적으면 문서를 추가하고 이 목록을 잊었을 때 새 문서만 조용히 안 지켜진다.
ASSEMBLED = tuple(load_script(str(_SCRIPT)).DOCUMENTS)


class TestMultiSpecUpToDate:
    @pytest.mark.parametrize("name", ASSEMBLED)
    def test_통합_문서가_화면_기획서와_맞다(self, name):
        """화면 기획서를 고치고 통합 문서를 다시 조립하지 않으면 여기서 걸린다.

        고치는 방법: `uv run python scripts/make_multi_spec.py` 그다음
        `uv run python scripts/make_spec_pdf.py fixtures/specs/<이름>_spec.md`
        """
        on_disk = (SPEC_DIR / f"{name}_spec.md").read_text(encoding="utf-8")
        assert on_disk == _assemble(name), (
            f"{name}_spec.md 가 화면별 기획서와 어긋났습니다.\n"
            "  uv run python scripts/make_multi_spec.py\n"
            f"  uv run python scripts/make_spec_pdf.py fixtures/specs/{name}_spec.md"
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


@pytest.fixture(scope="module")
def onboarding_doc():
    """가입→로그인→상품등록 문서 PDF."""
    pdf = SPEC_DIR / "onboarding_spec.pdf"
    if not pdf.exists():
        pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
    return parse_pdf(pdf)


class TestOnboardingSpecPdfMatchesMarkdown:
    """가입→로그인→상품등록 문서. 화면 셋을 지나는 흐름이 사는 유일한 픽스처다."""

    def test_화면_수가_맞다(self, onboarding_doc):
        """조각은 둘인데 화면은 셋이다 — product_spec 이 로그인까지 담기 때문이다.
        페이지 구분이 딸려 오지 않으면 여기서 갈린다."""
        screens, warnings = onboarding_doc.split_screens()
        assert len(screens) == 3, f"화면 {len(screens)}개, 경고: {warnings}"

    def test_흐름이_세_화면을_가리킨다(self, onboarding_doc):
        flows = {f["flow_id"]: f["screen_ids"] for f in onboarding_doc.declared_flows()}
        assert flows == {
            "signup_link_to_product": ["signup", "login", "product"],
            "signup_state_to_product": ["signup", "login", "product"],
        }

    def test_전이별_이동_방법이_보존된다(self, onboarding_doc):
        """'로그인하러 가기 → -' 에서 앞의 라벨만 남고 뒤는 주소 이동이 된다.
        자리가 밀리면 기획서가 적은 것과 다른 전이에 클릭이 붙는다."""
        by_id = {f["flow_id"]: f["via"] for f in onboarding_doc.declared_flows()}
        assert by_id["signup_link_to_product"] == ["로그인하러 가기"]
        assert by_id["signup_state_to_product"] == []


class TestScriptIsIdempotent:
    @pytest.mark.parametrize("name", ASSEMBLED)
    def test_두_번_돌려도_바뀌지_않는다(self, name):
        """조립이 결정적이어야 위 대조가 의미를 갖는다. 실행마다 달라지면
        '낡았다' 와 '방금 만들었다' 를 구별할 수 없다."""
        assert _assemble(name) == _assemble(name)

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


class TestProductBadloginTwin:
    """`product_badlogin_spec` 은 `product_spec` 의 손복사 쌍둥이다 — 비밀번호만 틀리다.

    통합 문서(multi_spec)는 조립 스크립트가 있어 낡음이 잡히지만 이 쌍은 없었다.
    product_spec 의 요소 표를 고치면 badlogin 쪽은 낡은 화면을 측정하면서 계속
    통과한다 — 한 번 겪은 사고(이 파일 docstring)의 재발 자리. 두 파일의 차이가
    **의도한 그 줄뿐**임을 못 박는다 (2026-08-22).
    """

    def _lines(self, name: str) -> list[str]:
        return (SPEC_DIR / name).read_text(encoding="utf-8").splitlines()

    def test_md_는_문서번호와_비밀번호_줄만_다르다(self):
        a, b = self._lines("product_spec.md"), self._lines("product_badlogin_spec.md")
        assert len(a) == len(b), "줄 수가 다르다 — 한쪽만 고쳐졌다"
        diff = [(x, y) for x, y in zip(a, b) if x != y]
        assert len(diff) == 2, f"차이가 {len(diff)}줄: {diff}"
        assert all("문서번호" in x for x, _ in diff[:1])
        assert "Seller1!" in diff[1][0] and "Wrong1!" in diff[1][1]

    def test_골든은_account_password_만_다르다(self):
        import json
        a = json.loads((SPEC_DIR / "product_spec.golden.json").read_text(encoding="utf-8"))
        b = json.loads((SPEC_DIR / "product_badlogin_spec.golden.json").read_text(encoding="utf-8"))
        b["precondition"]["account_password"] = a["precondition"]["account_password"]
        assert a == b, "비밀번호 외의 차이가 있다 — 쌍둥이가 낡았다"
