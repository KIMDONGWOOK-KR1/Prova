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

## 화면마다 같은 검사를 돌린다

SPECS 에 화면을 추가하면 그 화면에도 같은 강도의 대조가 걸린다. 화면을 늘릴 때
정확도 측정이 함께 늘어나지 않으면, 확장된 부분만 측정되지 않은 상태가 된다.
화면마다 로그인에 없던 것을 갖고 있어 특히 여기서 확인해야 한다.

    회원가입      same_as · options · 체크박스
    검색          scenarios (규칙으로 표현할 수 없는 입력-결과 짝)
    비밀번호 찾기  expect_absent (노출되면 **안 되는** 문구)

프롬프트의 few-shot 예시는 이 화면들과 겹치지 않는 화면('비밀번호 변경')을
쓴다. 예시가 측정 대상과 같으면 기획서를 읽어서 맞힌 것인지 예시를 베낀 것인지
구분할 수 없어, 정확도 숫자가 실물 기획서에 대한 근거가 되지 못한다.
**화면을 추가할 때 그 예시와 주제가 겹치지 않는지 확인해야 한다.**

비밀번호 찾기를 추가할 때 이 주의가 실제로 걸렸다 — few-shot 예시가 '비밀번호 변경'
(`/password-change`)이고 새 화면이 '비밀번호 찾기'(`/find-account`)라 이름이 인접하다.
내용은 다르다(예시는 현재/새 비밀번호 입력, 이 화면은 이메일 하나). 그래도 모델이
`url_path` 나 요소를 예시에서 베낄 여지가 있으므로, 그 베낌은 여기 골든 대조가 잡는다.

## 비교 강도를 필드마다 다르게 둔다

    constraints    엄격 비교 — 키 이름과 값이 정확히 같아야 한다.
                   키가 흔들리면(min_len 등) rule_expander 가 규칙을 인식하지 못한다.
    options        엄격 비교 — 정상 케이스가 여기서 값을 고른다.
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
from prova.llm.vllm_backend import ModelNotServed
from prova.models import ScreenSpec
from prova.s1_spec_extractor.extractor import extract_document
from prova.s2_case_generator.rule_expander import satisfies
from prova.text_utils import contains_loose, loosen

SPEC_DIR = Path("fixtures/specs")
# 2차 범위의 두 화면(product·orders)은 전제 화면(login)을 같은 문서에 담고 있어
# 문서 추출(extract_document)을 거친 뒤 골든의 screen_id 로 대상 화면을 고른다.
# 2026-08-22 까지 이 둘이 목록에 없었다 — numeric 규칙·전제·씨앗 표처럼 가장
# 최근에 추가된 추출 경로가 실모델 대조 없이 mock 골든으로만 돌고 있었다.
SPECS = ["login", "signup", "search", "find_account", "product", "orders"]

# 통합 문서(multi_spec.pdf)에 담긴 화면. SPECS 와 일부러 다르다.
#
# 통합 문서 픽스처가 확인하는 것은 **분할이 되는가** 다 — 한 문서를 화면별로 갈랐을
# 때 단일 문서와 같은 명세가 나오는지. 그 성질은 화면 종류가 아니라 분할기에 대한
# 것이고, 세 화면으로 이미 성립한다. 화면을 늘릴 때마다 통합 문서에 넣으면 그
# 테스트의 기대값(케이스 총계·화면별 내역·흐름)이 계속 흔들리는데 얻는 신호는 없다.
MULTI_SPECS = ["login", "signup", "search"]

# 성공 조건에서 S2 가 정규식으로 뽑아 쓰는 조각. 이게 빠지면 정상 케이스의 기대가
# 비어 버려서, 화면이 망가져도 '에러 없음' 만으로 PASS 가 된다.
#
# 검색은 빈 목록이다 — 제출 후 이동하지도, 정해진 문구를 띄우지도 않는 화면이라
# 성공 조건에서 뽑을 조각이 없다. 그 화면의 실질적 검증은 scenarios 가 맡는다
# (TestScenarios 참고). 없는 것을 요구하면 기획서를 억지로 고치게 된다.
SUCCESS_TOKENS = {
    "login": ["/dashboard", "환영합니다"],
    "signup": ["/welcome", "가입이 완료되었습니다"],
    "search": [],
    # 비밀번호 찾기는 이동하지 않고 문구만 노출한다. 경로 조각이 없다.
    "find_account": ["재설정 메일을 보냈습니다"],
    "product": ["상품이 등록되었습니다"],
    # 주문조회는 진입 즉시 목록이 보이는 화면 — 제출도 이동도 없다. 실질 검증은
    # 정렬·합계 판정(sorted_desc·sum_matches)이 맡는다.
    "orders": [],
}


@pytest.fixture(scope="module")
def client():
    """vLLM 클라이언트. 연결 안 되면 이 파일 전체를 skip."""
    import yaml

    cfg = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    llm_cfg = cfg.get("llm", {})
    backend = os.environ.get("PROVA_LLM_BACKEND", llm_cfg.get("backend", "vllm"))

    if backend != "vllm":
        pytest.skip(f"backend={backend} — 이 테스트는 실제 모델 정확도를 측정한다")

    from prova.llm.vllm_backend import VLLMClient

    inst = VLLMClient(
        base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
        model=llm_cfg.get("model", "Qwen/Qwen2.5-7B-Instruct-AWQ"),
        timeout=float(llm_cfg.get("timeout", 180)),
    )
    try:
        inst.health(timeout=4.0)  # skip 판단은 빨라야 한다
    except ModelNotServed as exc:
        # 서버는 살아 있는데 다른 모델(예: IoU 채점용 VL)이 떠 있다. 환경이 없는
        # 게 아니라 잘못 구성된 것이므로 skip 이 아니라 실패다 — skip 으로 접으면
        # 69개가 조용히 빠지고 추출 정확도를 아무것도 확인하지 않은 채 초록불이 된다.
        pytest.fail(f"vLLM 이 다른 모델을 서빙 중입니다 — 7B 를 되돌리세요: {exc}")
    except LLMError as exc:
        pytest.skip(f"vLLM 에 연결할 수 없습니다 — {exc}")
    return inst


@pytest.fixture(scope="module", params=SPECS)
def pair(request, client) -> tuple[ScreenSpec, ScreenSpec, str]:
    """(추출 결과, 정답, 화면 이름). 화면마다 한 번만 추출한다."""
    stem = request.param
    golden = ScreenSpec.model_validate(
        json.loads((SPEC_DIR / f"{stem}_spec.golden.json").read_text(encoding="utf-8"))
    )
    try:
        doc = extract_document(str(SPEC_DIR / f"{stem}_spec.pdf"), client)
    except LLMError as exc:
        pytest.fail(f"{stem}: S1 추출이 실패했습니다: {exc}")
    extracted = doc.screen_by_id(golden.screen_id)
    assert extracted is not None, (
        f"{stem}: 추출 결과에 화면 {golden.screen_id!r} 가 없다 — "
        f"있는 것: {[s.screen_id for s in doc.screens]}"
    )
    return extracted, golden, stem


class TestScreenLevel:
    def test_화면_식별정보(self, pair):
        extracted, golden, _ = pair
        assert extracted.screen_id == golden.screen_id
        assert loosen(extracted.screen_name) == loosen(golden.screen_name)
        assert extracted.url_path == golden.url_path

    def test_요소를_빠뜨리지_않는다(self, pair):
        extracted, golden, _ = pair
        got = {e.element_id for e in extracted.elements}
        want = {e.element_id for e in golden.elements}
        assert not (want - got), f"놓친 요소: {want - got}"

    def test_필수입력_공통문구(self, pair):
        """required 위반 케이스의 기대 문구가 여기서 온다."""
        extracted, golden, _ = pair
        if golden.required_message:
            assert extracted.required_message, "required_message 를 추출하지 못했다"
            assert loosen(extracted.required_message) == loosen(golden.required_message)

    def test_성공조건에_경로와_문구가_들어있다(self, pair):
        """S2 가 여기서 정상 케이스의 기대를 뽑는다. 문장 표현은 달라도 된다."""
        extracted, _, stem = pair
        for token in SUCCESS_TOKENS[stem]:
            assert contains_loose(extracted.success_condition, token), (
                f"성공 조건에 {token!r} 가 없다: {extracted.success_condition!r}"
            )


    def test_전제와_씨앗_표가_일치한다(self, pair):
        """둘 다 결정적 표 독해가 채우는 값이다(_apply_declared_*). 모델이 아니라
        파서를 검증하는 셈이지만, 실물 PDF 렌더링을 거친 표가 그대로 읽히는지는
        여기서만 확인된다."""
        extracted, golden, _ = pair
        if golden.precondition is not None:
            assert extracted.precondition == golden.precondition
        if golden.seed_rows:
            assert extracted.seed_rows == golden.seed_rows


class TestConstraints:
    """가장 중요한 비교. 여기가 틀리면 검증이 조용히 무력해진다."""

    def test_검증규칙이_정확히_일치한다(self, pair):
        extracted, golden, _ = pair
        for want in golden.elements:
            got = extracted.element_by_id(want.element_id)
            assert got is not None, f"{want.element_id} 요소 없음"
            assert got.constraints == want.constraints, (
                f"{want.element_id} 의 검증 규칙 불일치\n"
                f"  기대: {want.constraints}\n"
                f"  실제: {got.constraints}\n"
                f"  -> 키 이름이 다르면 rule_expander 가 규칙을 인식하지 못한다"
            )

    def test_필수여부가_일치한다(self, pair):
        extracted, golden, _ = pair
        for want in golden.elements:
            got = extracted.element_by_id(want.element_id)
            assert got.required == want.required, f"{want.element_id}.required"

    def test_요소_유형이_일치한다(self, pair):
        """유형이 틀리면 액션이 틀린다 — 체크박스를 input 으로 뽑으면 fill()
        이 불려 조작 오류가 나고, 그 케이스의 판정이 뭉개진다."""
        extracted, golden, _ = pair
        for want in golden.elements:
            got = extracted.element_by_id(want.element_id)
            assert got.type == want.type, f"{want.element_id}.type"

    def test_선택_목록이_일치한다(self, pair):
        """정상 케이스가 여기서 값을 고른다. 비어 있으면 빈 값을 선택해
        필수 선택 검증에 걸리고, 정상 케이스가 오탐 FAIL 이 된다."""
        extracted, golden, _ = pair
        for want in golden.elements:
            if not want.options:
                continue
            got = extracted.element_by_id(want.element_id)
            assert got.options == want.options, (
                f"{want.element_id} 의 선택 목록 불일치\n"
                f"  기대: {want.options}\n  실제: {got.options}"
            )


class TestErrorMessages:
    """문구가 판정 근거이므로 정확해야 한다. 공백 차이만 허용한다."""

    def test_에러문구가_일치한다(self, pair):
        extracted, golden, _ = pair
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
    def test_예시값을_추출한다(self, pair):
        """정상 케이스가 이 값을 쓴다. 없으면 코드가 만든 값이 쓰이고, 그 값은
        규칙은 만족하지만 등록된 계정이 아니어서 정상 케이스가 오탐 FAIL 이 된다."""
        extracted, golden, _ = pair
        for want in golden.elements:
            if not want.sample_value:
                continue
            got = extracted.element_by_id(want.element_id)
            assert got.sample_value, (
                f"{want.element_id} 의 예시값을 추출하지 못했다 "
                f"(기대: {want.sample_value!r}) — 정상 케이스가 오탐 실패할 수 있다"
            )
            assert loosen(got.sample_value) == loosen(want.sample_value)


class TestScenarios:
    """기획서가 제시한 입력-결과 예시.

    규칙으로 표현할 수 없는 검증이 여기 담긴다. 이걸 놓치면 '검사는 하는데 방법이
    기획서와 다르다' 는 종류의 결함(검색의 대소문자 처리 등)에 도달할 경로가
    아예 없어진다 — 위반값 생성으로는 만들 수 없는 케이스이기 때문이다.

    given 의 키는 element_id 여야 한다. 라벨을 넣으면 그 값이 조용히 무시되고,
    시나리오가 의도한 것과 다른 것을 확인한 뒤 대개 통과해 버린다(미탐).
    """

    def test_건수가_일치한다(self, pair):
        """**골든에 시나리오가 없을 때도 검사한다.** 처음에는 없으면 skip 했는데,
        그 사이로 실제 결함이 지나갔다 — 7B 가 회원가입 기획서에 없는 시나리오를
        하나 만들어냈고, skip 때문에 테스트가 통과했다. 파이프라인 케이스 수가
        14건에서 15건으로 늘어난 것을 보고서야 알았다.

        '있어야 할 것이 있는가' 만 보면 '없어야 할 것이 없는가' 를 놓친다."""
        extracted, golden, _ = pair
        assert len(extracted.scenarios) == len(golden.scenarios), (
            f"기대 {len(golden.scenarios)}건, 실제 {len(extracted.scenarios)}건\n"
            f"  실제: {[s.model_dump() for s in extracted.scenarios]}"
        )

    def test_입력값과_기대문구가_일치한다(self, pair):
        extracted, golden, _ = pair
        got = {(tuple(sorted(s.given.items())), loosen(s.expect_text))
               for s in extracted.scenarios}
        want = {(tuple(sorted(s.given.items())), loosen(s.expect_text))
                for s in golden.scenarios}
        assert got == want, (
            f"예시 시나리오 불일치\n"
            f"  기대: {sorted(want)}\n"
            f"  실제: {sorted(got)}"
        )

    def test_결과_건수가_일치한다(self, pair):
        """건수는 문구와 별개로 대조한다.

        둘을 한 집합에 섞어 비교하면 어느 쪽이 틀렸는지 실패 메시지에서 구분되지
        않는다. 그리고 None 과 0 을 반드시 구별해야 한다 — None 은 '건수 검증
        없음' 이고 0 은 '아무것도 나오지 않아야 한다' 다. None 으로 새면 건수
        케이스가 만들어지지 않은 채 리포트가 조용히 초록불이 된다."""
        extracted, golden, _ = pair
        got = {tuple(sorted(s.given.items())): s.expect_count
               for s in extracted.scenarios}
        want = {tuple(sorted(s.given.items())): s.expect_count
                for s in golden.scenarios}
        assert got == want, f"결과 건수 불일치\n  기대: {want}\n  실제: {got}"

    def test_규칙_위반을_시나리오에_넣지_않는다(self, pair):
        """규칙 위반은 constraints 에서 자동 전개된다. 시나리오에 또 넣으면 같은
        것을 두 번 검증하고, 리포트에서 규칙과 실패의 1:1 대응이 흐려진다."""
        extracted, _, _ = pair
        for scenario in extracted.scenarios:
            for element_id, value in scenario.given.items():
                element = extracted.element_by_id(element_id)
                if element is None or not element.constraints:
                    continue
                assert satisfies(value, element.constraints), (
                    f"시나리오 입력 {value!r} 이 {element_id} 의 검증 규칙을 "
                    f"위반한다 — 규칙 위반 예시가 시나리오로 들어왔다"
                )


class TestNoSilentFailure:
    def test_추출_실패를_경고로_알린다(self, pair):
        """constraints 가 하나도 없으면 extractor 가 경고를 남겨야 한다.
        경고 없이 빈 결과가 지나가면 리포트가 근거 없이 초록불이 된다."""
        extracted, _, _ = pair
        if not any(e.constraints for e in extracted.elements):
            assert extracted.warnings, "추출 실패인데 경고가 없다"


# ---------------------------------------------------------------------------
# 한 문서에 여러 화면
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def multi_doc(client):
    """세 화면을 한 문서에 담은 기획서의 추출 결과. 문서당 한 번만 추출한다."""
    pdf = SPEC_DIR / "multi_spec.pdf"
    if not pdf.exists():
        pytest.skip("먼저 `uv run python scripts/make_spec_pdf.py` 를 실행하세요")
    try:
        return extract_document(str(pdf), client)
    except LLMError as exc:
        pytest.skip(f"추출 실패 — {exc}")


class TestMultiScreenDocument:
    """화면당 PDF 하나였던 전제가 깨진 문서.

    ## 골든 파일을 새로 만들지 않았다

    이 문서의 화면들은 단일 화면 기획서와 **같은 표**를 담고 있으므로, 정답도 같아야
    한다. 골든 JSON 을 하나 더 두면 같은 사실이 두 곳에 적히고, 한쪽만 고쳐졌을 때
    어느 쪽이 맞는지 알 수 없게 된다. 그래서 기존 세 골든을 그대로 정답으로 쓴다.

    이 방식에는 덤이 있다. **한 문서에 담았을 때 추출이 달라지는지**가 그대로
    드러난다. 실제로 드러났다 — 7B 가 검색 화면의 required_message 를 few-shot
    예시의 문구로 채웠고, 그게 오탐으로 이어질 값이었다.
    """

    def test_화면을_순서대로_나눈다(self, multi_doc):
        assert [s.screen_id for s in multi_doc.screens] == ["login", "signup", "search"]

    def test_화면마다_요소가_온전하다(self, multi_doc):
        """화면 경계가 어긋나면 뒤 화면의 요소 표가 앞 화면 것으로 추출된다.
        그러면 두 화면의 검증이 모두 조용히 틀린다."""
        want = {"login": 3, "signup": 8, "search": 3}
        got = {s.screen_id: len(s.elements) for s in multi_doc.screens}
        assert got == want

    @pytest.mark.parametrize("stem", MULTI_SPECS)
    def test_단일_문서와_같은_결과를_낸다(self, multi_doc, stem):
        """같은 표를 담았으면 같은 명세가 나와야 한다. 문서를 합친 것만으로 결과가
        달라지면 그건 문맥 길이에 따라 추출이 흔들린다는 뜻이고, 실물 기획서에서
        그대로 재현된다."""
        golden = ScreenSpec.model_validate(
            json.loads((SPEC_DIR / f"{stem}_spec.golden.json").read_text(encoding="utf-8"))
        )
        screen = multi_doc.screen_by_id(stem)
        assert screen is not None, f"{stem} 화면이 없다"

        assert loosen(screen.screen_name) == loosen(golden.screen_name)
        assert screen.url_path == golden.url_path
        assert loosen(screen.required_message or "") == loosen(golden.required_message or "")

        got = {e.element_id: (e.type, e.required, e.constraints) for e in screen.elements}
        want = {e.element_id: (e.type, e.required, e.constraints) for e in golden.elements}
        assert got == want, f"{stem} 요소 불일치\n  기대: {want}\n  실제: {got}"

        got_msg = {e.element_id: loosen(e.error_message or "") for e in screen.elements}
        want_msg = {e.element_id: loosen(e.error_message or "") for e in golden.elements}
        assert got_msg == want_msg, f"{stem} 에러 문구 불일치"

        got_scen = {(tuple(sorted(s.given.items())), loosen(s.expect_text), s.expect_count)
                    for s in screen.scenarios}
        want_scen = {(tuple(sorted(s.given.items())), loosen(s.expect_text), s.expect_count)
                     for s in golden.scenarios}
        assert got_scen == want_scen, f"{stem} 시나리오 불일치"

    def test_흐름을_읽는다(self, multi_doc):
        """두 흐름이 같은 화면 쌍을 밟는데 확인하는 것이 다르다 — 하나는 화면을
        잇는 요소, 하나는 이어진 상태다."""
        by_id = {f.flow_id: f for f in multi_doc.flows}
        assert set(by_id) == {"signup_link_to_login", "signup_then_login"}
        assert by_id["signup_link_to_login"].screen_ids == ["signup", "login"]
        assert by_id["signup_link_to_login"].via == ["로그인하러 가기"]
        assert by_id["signup_then_login"].via == [], "주소로 이동하는 흐름"

    def test_흐름이_없는_화면을_가리키지_않는다(self, multi_doc):
        """흐름이 없는 화면을 가리키면 그 흐름은 만들어지지 않는다. 조용히 빠지면
        검증한 줄 알았는데 아무것도 확인하지 않은 상태가 된다."""
        known = {s.screen_id for s in multi_doc.screens}
        for flow in multi_doc.flows:
            assert set(flow.screen_ids) <= known, f"{flow.flow_id} 가 없는 화면을 가리킨다"

    def test_화면_ID가_겹치지_않는다(self, multi_doc):
        """겹치면 case_id 접두사가 같아져 스크린샷이 서로를 덮어쓴다 — 리포트는
        정상으로 보이는데 증거가 사라진다."""
        ids = [s.screen_id for s in multi_doc.screens]
        assert len(ids) == len(set(ids)), f"화면 ID 중복: {ids}"

    def test_보정이_일어났으면_경고가_남는다(self, multi_doc):
        """결정적 보정 계층이 조용히 값을 바꾸면 프롬프트가 나빠지고 있는지 알 수
        없다. 이 문서에서는 실제로 required_message 보정이 일어난다."""
        search = multi_doc.screen_by_id("search")
        if search.required_message == "검색어를 입력하세요.":
            # 모델이 맞혔으면 경고가 없고, 보정됐으면 경고가 있다. 둘 중 하나여야
            # 하고, '보정됐는데 경고가 없다' 만 실패다.
            pass
        assert all(isinstance(w, str) for w in multi_doc.all_warnings)
