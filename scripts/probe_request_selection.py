"""요청 해석 정확도 측정 — 자연어 요청이 어떤 케이스를 고르는가.

## 왜 재현율을 먼저 보는가

이 층에서 나올 수 있는 두 가지 오류의 값이 다르다.

    빠뜨린 케이스 (재현율 손실)   결함이 조용히 숨는다        치명적
    더 넣은 케이스 (정밀도 손실)  시간만 더 쓴다              괜찮다

그래서 "정답 집합을 정확히 맞혔는가" 가 아니라 **"정답 집합을 빠짐없이 담았는가"**
를 먼저 본다. 여유분(정답 밖 케이스)은 따로 세되 실패로 치지 않는다.

브라우저를 열지 않는다 — build_plan 은 S1~S2 와 선택까지만 하므로 몇 초면 끝난다.

    uv run python scripts/probe_request_selection.py            # 튜닝 세트
    uv run python scripts/probe_request_selection.py login      # 한 기획서만
    uv run python scripts/probe_request_selection.py heldout    # 홀드아웃 A (튜닝 세트로 강등)
    uv run python scripts/probe_request_selection.py heldout-b  # 홀드아웃 B — 보고에 쓰는 숫자
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from prova.llm.factory import make_llm
from prova.pipeline import build_plan

CONFIG = Path("configs/default.yaml")

# 요청 -> 반드시 들어가야 하는 케이스 (정답 집합).
#
# case_id 를 그대로 쓰지 않고 정규식으로 적는다. 케이스 번호는 기획서가 바뀌면
# 움직이지만 "무엇을 검사하는 케이스인가" 는 그대로이기 때문이다.
CASES: list[tuple[str, str, str, list[str]]] = [
    # (기획서, 요청, 설명, 반드시 포함해야 하는 case_id 패턴)
    ("login", "비밀번호 규칙이 제대로 걸리는지 확인해줘", "규칙 묶음 지목",
     [r"password-min_length", r"password-require_uppercase", r"password-require_special"]),
    ("login", "이메일 입력 검증만 봐줘", "요소 지목",
     [r"email-required", r"email-format"]),
    ("login", "전부 다 확인해줘", "전체 지목",
     [r"login-valid", r"email-required", r"email-format", r"password-required",
      r"password-min_length", r"password-require_uppercase", r"password-require_special"]),
    ("login", "정상적으로 로그인되는지만 보면 돼", "정상 경로만",
     [r"login-valid"]),
    # 화면 단위 요청. '대표 케이스 하나' 로 답하면 결함이 숨는다 —
    # 실측에서 7B 가 17건 중 1건만 골랐다.
    ("signup", "회원가입이 잘 되는지 확인해줘", "화면 지목",
     [r"signup-valid", r"email-required", r"email-format",
      r"password-required", r"password-min_length",
      r"password_confirm-same_as", r"nickname-required", r"agree_terms-required"]),
    ("signup", "비밀번호 확인란이 제대로 동작하는지", "요소 간 규칙",
     [r"password_confirm-required", r"password_confirm-same_as"]),
    ("signup", "닉네임 규칙이 맞는지 봐줘", "요소 지목",
     [r"nickname-required", r"nickname-min_length", r"nickname-max_length"]),
    ("search", "검색 결과가 제대로 나오는지 봐줘", "화면 지목",
     [r"search-valid", r"search-scenario-005", r"search-count-005",
      r"search-scenario-006", r"search-count-006"]),
    ("search", "검색어 입력 규칙 확인", "요소 지목",
     [r"query-required", r"query-min_length", r"query-max_length"]),
    ("find_account", "계정 찾기에서 개인정보가 새지 않는지 확인해줘", "금지 문구",
     [r"find_account-"]),
]

# 아무 케이스도 고르면 안 되는 요청 — 0건 거부가 살아 있는지 본다.
EMPTY = [
    ("login", "결제 화면 확인해줘"),
    ("login", "장바구니 담기가 되는지 봐줘"),
]

# ---------------------------------------------------------------------------
# 홀드아웃 — 프롬프트를 고칠 때 보지 않은 문서(multi)와 새 말투로 잰다.
#
# 위의 CASES 를 보면서 프롬프트를 두 번 고쳤으므로 그 9/10 은 과적합됐을 수
# 있다. 이 목록은 측정 전에 굳혔고, **이 결과를 보고 프롬프트를 고치지 않는다**
# — 고치는 순간 이것도 튜닝 세트가 된다. 실패하면 실패로 보고한다.
#
# 새 유형: 흐름 지목(튜닝 세트에 없었다), 문구·라벨 케이스 지목, 의문문 말투.
# ---------------------------------------------------------------------------
HELDOUT: list[tuple[str, str, str, list[str]]] = [
    ("multi", "가입 화면의 입력값 검사가 빠짐없이 붙어 있는지 봐야 해", "화면 지목(전 규칙)",
     [r"signup-email-required", r"signup-email-format", r"signup-password-min_length",
      r"signup-password_confirm-same_as", r"signup-nickname-max_length",
      r"signup-agree_terms-required"]),
    ("multi", "회원가입 마치고 그 계정으로 바로 로그인까지 되는지", "흐름 지목",
     [r"flow-signup_then_login"]),
    ("multi", "검색어를 너무 길게 넣으면 막아주나?", "단일 규칙(의문문)",
     [r"search-query-max_length"]),
    ("multi", "닉네임 글자수 제한 확인 부탁", "요소+규칙 축약",
     [r"nickname-min_length", r"nickname-max_length"]),
    ("multi", "로그인 쪽 안내 문구랑 라벨이 기획서랑 같은지", "문구·라벨 지목",
     [r"login-placeholders", r"login-labels"]),
    ("multi", "상품 검색 결과 개수가 맞게 나오는지", "건수 검증 지목",
     [r"search-count-005", r"search-count-006"]),
    ("multi", "약관 동의 안 하면 가입이 막히는지", "단일 요소",
     [r"agree_terms-required"]),
    ("multi", "가입 화면에서 로그인 화면으로 가는 링크가 동작하는지", "다른 흐름",
     [r"flow-signup_link_to_login"]),
    ("orders", "주문 내역이 최신순으로 나오는지 확인해줘", "정렬 지목",
     [r"orders-sorted"]),
]

EMPTY_HELDOUT = [
    ("multi", "포인트 적립이 되는지 봐줘"),
    ("multi", "고객센터 문의가 접수되는지 확인"),
]

# ---------------------------------------------------------------------------
# 홀드아웃 B — 2026-08-22 에 굳혔다. 선택 넓히기(widen_selection)를 구현하기
# **전에** 적고 커밋했다.
#
# 위 HELDOUT(A)은 6/9 의 빠뜨림 3건(흐름·건수·정렬)을 보고 넓히기 규칙을 설계했으므로
# 이 시점부터 **튜닝 세트**다. A 의 숫자는 더 이상 일반화 증거가 아니다 — 보고에는
# B 를 쓴다. B 의 결과를 보고는 고치지 않는다. 실패하면 실패로 보고한다.
#
# 유형은 A 와 같게 두고(흐름·건수·정렬·문구·축약·의문문) 문서와 말투를 바꿨다.
# product·orders 문서는 A 에 거의 없었다.
# ---------------------------------------------------------------------------
HELDOUT_B: list[tuple[str, str, str, list[str]]] = [
    ("orders", "주문 합계 금액이 화면에 맞게 찍히는지 봐줘", "합계 지목",
     [r"orders-sum"]),
    ("orders", "로그인 안 한 상태로 주문조회 들어가면 막히나?", "가드 지목(의문문)",
     [r"orders-precondition-guard"]),
    # 2026-08-24 날짜 필터 작업으로 orders 의 케이스 집합이 커졌다(labels 1 +
    # filter 8). '전 종류' 의 정의가 따라 커진 것이라 기대 목록을 기계적으로
    # 갱신했다 — 판정 기준 변경이 아니지만, 이후 수치는 갱신 전 B 9/10 과
    # 1:1 비교할 수 없다 (docs/measurements/request-selection-2026-08-22.md).
    ("orders", "주문조회 화면 전반적으로 점검 부탁", "화면 지목(전 종류)",
     [r"orders-valid", r"orders-labels", r"orders-sorted", r"orders-sum",
      r"orders-seedcount", r"orders-filter", r"orders-precondition-guard"]),
    ("product", "가격이랑 재고에 숫자 아닌 값 넣으면 튕기는지", "두 항목 규칙",
     [r"product-price-numeric", r"product-stock-numeric"]),
    ("product", "상품명 길이 제한 걸리는지 확인", "요소+규칙 축약",
     [r"product-name-max_length"]),
    ("product", "상품등록 화면 문구가 기획서 그대로인지", "문구·라벨 지목",
     [r"product-placeholders", r"product-labels"]),
    ("multi", "검색했을 때 결과 건수가 기획서랑 같게 나오나", "건수 검증(의문문)",
     [r"search-count-005", r"search-count-006"]),
    ("multi", "가입 끝나고 이어서 로그인하는 것까지 한 번에", "흐름 지목(축약)",
     [r"flow-signup_then_login"]),
    ("multi", "로그인 화면의 비밀번호 규칙 세 가지 다 걸리는지", "규칙 묶음",
     [r"login-password-min_length", r"login-password-require_uppercase",
      r"login-password-require_special"]),
    ("multi", "가입 경로 선택지가 기획서 항목대로 다 있는지", "선택 항목 대조",
     [r"signup-options-signup_path"]),
]

EMPTY_HELDOUT_B = [
    ("orders", "배송 조회가 되는지 봐줘"),
    ("product", "쿠폰 적용이 되는지 확인"),
]


def spec_path(name: str) -> Path:
    return Path(f"fixtures/specs/{name}_spec.pdf")


def plan_for(name: str, request: str | None):
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    llm, _ = make_llm("vllm", cfg, spec_path(name))
    return build_plan(
        pdf_path=str(spec_path(name)),
        base_url="http://localhost:8100/bad",
        llm=llm,
        request=request,
    )


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cases, empties, label = CASES, EMPTY, "튜닝 세트"
    if only == "heldout":
        cases, empties, label = HELDOUT, EMPTY_HELDOUT, "홀드아웃 A (2026-08-22 부터 튜닝 세트)"
        only = None
    elif only == "heldout-b":
        cases, empties, label = HELDOUT_B, EMPTY_HELDOUT_B, "홀드아웃 B (보고용)"
        only = None
    rows, misses = [], 0

    print("=" * 78)
    print(f"요청 해석 정확도 — 실모델(vLLM) · {label}")
    print("=" * 78)

    for name, request, kind, wanted in cases:
        if only and only != name:
            continue
        try:
            state, _ = plan_for(name, request)
        except ValueError as exc:
            # 어휘 검사에 걸린 경우. 한 건이 막혔다고 측정 전체를 멈추면
            # 나머지를 못 본다 — 오탐인지 정탐인지 판단할 정보가 줄어든다.
            misses += 1
            print(f"\n[REJECT] {name} · {kind}")
            print(f"       요청: {request}")
            for line in str(exc).splitlines():
                print(f"       {line}")
            continue
        picked = [c.case_id for c in state.cases]
        sel = state.selection

        hit = [p for p in wanted if any(re.search(p, cid) for cid in picked)]
        lost = [p for p in wanted if p not in hit]
        # 정답 밖으로 더 담은 것. 실패가 아니라 '여유분' 이다.
        spare = [cid for cid in picked
                 if not any(re.search(p, cid) for p in wanted)]

        ok = not lost and not sel.fallback
        if not ok:
            misses += 1
        rows.append((name, kind, request, len(picked), len(lost), len(spare),
                     sel.fallback, lost, sel.warnings))

        mark = "OK " if ok else "MISS"
        print(f"\n[{mark}] {name} · {kind}")
        print(f"       요청: {request}")
        print(f"       고름: {len(picked)}건 / 전체 {len(state.all_cases)}건"
              + (f"  (여유분 {len(spare)})" if spare else ""))
        if sel.reason:
            print(f"       근거: {sel.reason}")
        if sel.fallback:
            print("       ** 해석 실패 → 전체 실행으로 넘어짐")
        if lost:
            print(f"       ** 빠뜨림: {lost}")
        for w in sel.warnings:
            print(f"       ! {w}")

    print("\n" + "-" * 78)
    print("0건 거부 확인 (기획서에 없는 화면을 요청)")
    for name, request in empties:
        if only and only != name:
            continue
        try:
            state, _ = plan_for(name, request)
            sel = state.selection
            if sel.fallback:
                print(f"  [OK ] '{request}' → 해석 실패, 전체 실행 (안전한 쪽)")
            else:
                print(f"  [WARN] '{request}' → {len(state.cases)}건을 골랐다: "
                      f"{[c.case_id for c in state.cases]}")
        except ValueError:
            print(f"  [OK ] '{request}' → 0건이라 거부됨")

    print("\n" + "=" * 78)
    total = len(rows)
    print(f"재현율: {total - misses}/{total} 요청에서 정답 집합을 빠짐없이 담았다")
    print("=" * 78)
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
