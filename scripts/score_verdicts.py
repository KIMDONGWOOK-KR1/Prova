"""PASS/FAIL 판단 정확도 — SUT 판정 덤프를 심은 결함에서 만든 정답 라벨과 대조한다.

운영 계획서 4-6 의 지표 2('각 테스트 케이스의 성공/실패를 정답 라벨과 비교한 판정 정확도',
목표 90% 이상)를 재는 스크립트다.

## 정답 라벨은 어디서 오는가

**도구의 출력을 보지 않고** SUT 의 정의에서만 만든다:

- 어느 변형이 어느 화면을 내주고, 그 화면이 어느 검증 로직을 쓰는가 — `sut/app.py` 의
  라우트 등록(LOGIN_VARIANTS·SEARCH_VARIANTS·find-account 등록 루프·bad/table/grid 라우트).
- 각 로직에 심은 결함 — `sut/app.py` 머리 주석의 결함 표(B1…O6)와 변형 설명(native·spa·
  nolabel), 결함 자리의 주석.
- 결함이 어느 케이스로 드러나는가 — 케이스가 넣는 값(`scripts/dump_cases.py`·계획의 스텝)과
  기획서의 예시 표·시드 데이터로 계산한다. 예: O3(시작일 당일 제외)는 08-03~08-12 조회에서
  ORD-002 를 빼므로 '3건' 케이스와 'ORD-002 노출' 케이스가 FAIL 이어야 한다.

라벨과 도구가 다르면 **라벨을 고치지 않고** 그대로 센다. 라벨이 틀렸다고 판단한 경우는
이 파일에 근거와 함께 적고 고친다(아래 LABEL_NOTES).

## 라벨 종류

    PASS      구현이 기획서를 지킨다 — 도구는 PASS 여야 한다
    DEFECT    심은 결함이 이 케이스로 드러난다 — 도구는 FAIL(기획서와 다름)이어야 한다
    BLOCKED   기획서의 전제 계정이 틀려 확인할 수 없다 — 도구는 FAIL 이되 '실행 문제' 여야 한다
    NA        그 변형이 이 화면을 내주지 않는다 — 정확도에서 뺀다. 대신 여기서 도구가
              '기획서와 다름' 을 말하면 거짓 결함으로 따로 센다

## 사용법

    uv run uvicorn sut.app:app --port 18199 --reload --reload-dir sut   # 별 터미널
    uv run python scripts/dump_verdicts.py runs/acc/verdicts.tsv runs/acc/runs --base http://localhost:18199
    uv run python scripts/score_verdicts.py runs/acc/verdicts.tsv
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFECT_CATEGORY = "assertion_mismatch"  # 리포트의 '기획서와 다름'

# ── 변형이 내주는 화면과 그 화면의 검증 로직 ────────────────────────────────
# 값은 아래 DEFECTS 의 키(로직 이름)다. 표에 없는 화면은 NA.
GOOD_ALL = {s: "good" for s in ("login", "signup", "search", "find_account",
                                "product", "orders", "flow")}
SERVED: dict[str, dict[str, str]] = {
    "good": GOOD_ALL,
    "bad": {s: "bad" for s in GOOD_ALL},
    # LOGIN_VARIANTS(good 로직) · SEARCH_VARIANTS
    "slow": {"login": "good", "search": "good"},
    "hashed": {"login": "good"},
    "native": {"login": "native"},
    "spa": {"login": "spa"},
    "nolabel": {"search": "nolabel"},
    # find-account 등록 루프 ("good", "bad", "slowleak") — slowleak 은 bad 와 같은 F1
    "slowleak": {"find_account": "bad"},
    # 주문조회 마크업 변형. 로그인은 LOGIN_VARIANTS 의 good 로직이다.
    "table": {"login": "good", "orders": "good"},
    "grid": {"login": "good", "orders": "good"},
    "badtable": {"login": "good", "orders": "bad"},
    "badgrid": {"login": "good", "orders": "bad"},
}

# ── 로직별로 FAIL 이어야 하는 케이스 → 결함 이름 ─────────────────────────────
DEFECTS: dict[str, dict[str, str]] = {
    "good": {},
    "bad": {
        # login — B1(규칙 셋)·B2·B3·B4 = 6건 (머리 주석 'FAIL 기대 6건')
        "login-email-format-003": "B2",
        "login-password-min_length-005": "B1",
        "login-password-require_uppercase-006": "B1",
        "login-password-require_special-007": "B1",
        "login-scenario-008": "B3",
        "login-placeholders-001": "B4",
        # lockout_spec 의 잠금 시나리오 — bad 로그인은 with_lockout 을 부르지 않는다.
        # (2026-11-10 이 측정에서 결함 표에 빠진 것을 찾아 B5 로 더했다. 전에는 코드 주석에만
        # 'B4' 로 있어 표의 B4 와 이름이 겹쳤다.)
        "login-scenario-009": "B5",
        # signup — C1~C4
        "signup-password_confirm-same_as-009": "C1",
        "signup-agree_terms-required-014": "C2",
        "signup-nickname-max_length-012": "C3",
        "signup-options-signup_path-015": "C4",
        # search — D1 은 문구·건수 두 경로, D2 결과 없음 문구, D3 최소 길이
        "search-scenario-005": "D1",
        "search-count-005": "D1",
        "search-scenario-006": "D2",
        "search-query-min_length-003": "D3",
        # find_account — 예시 2행(nobody@test.com, 미등록)에서 노출
        "find_account-scenario-005": "F1",
        "find_account-absent-005": "F1",
        # product
        "product-price-numeric-005": "P1",
        "product-precondition-guard-010": "P2",
        # orders — 시드(005 08-15 배송중, 004 08-12 완료, 003 08-09 완료, 002 08-03 취소,
        # 001 07-28 완료)와 케이스 입력(08-03~08-12, 08-16~08-17, 역전, 상태)으로 계산
        "orders-sorted-002": "O1",
        "orders-filter-006": "O1",        # 필터 뒤에도 오름차순
        "orders-sum-003": "O2",
        "orders-filter-002": "O3",        # 08-03 이 빠져 2건
        "orders-filter-003": "O3",        # ORD-002(08-03) 미노출
        "orders-filter-005": "O4",        # 필터 전 합계 유지
        "orders-filter-010": "O5",        # 역전 문구 없음
        "orders-status-002": "O6",        # 배송완료 3 + 취소 1 = 4건
        "orders-status-003": "O6",        # 배송중 1 + 취소 1 = 2건
        # status-004(취소 1건)는 취소가 한 번만 나와 PASS. status-005~007 이 보는 다른
        # 상태 주문(ORD-005·ORD-004)은 O6 이 섞는 것(ORD-002)이 아니라 PASS.
        # flows — E2: '로그인하러 가기' 가 /search 로, E1: 계정을 등록하지 않음
        "flow-signup_link_to_login-001": "E2",
        "flow-signup_then_login-001": "E1",
        "flow-signup_link_to_product-001": "E2",
        "flow-signup_state_to_product-001": "E1",
    },
    # native — 입력란에 required 를 붙이고 novalidate 를 뗐다(type="text" 라 형식은 막지
    # 않는다). 필수 입력에서 앱의 에러 문구 대신 브라우저 툴팁이 뜬다 — 기획서와 다르다.
    "native": {
        "login-email-required-002": "N-필수",
        "login-password-required-004": "N-필수",
    },
    # spa — 성공해도 URL 이 /dashboard 로 바뀌지 않는다. 기획서가 경로를 명시했다.
    "spa": {"login-valid-001": "SPA"},
    # nolabel — 제출 버튼에 접근성 이름이 없다. 기획서의 버튼 라벨 '검색' 이 없다.
    "nolabel": {"search-labels-001": "NL"},
}

# 기획서의 전제 계정 비밀번호가 틀린 쌍둥이(product_badlogin_spec) — 상품 화면 케이스는
# 로그인 전제를 만들 수 없다. 가드 케이스는 로그인이 필요 없어 제외.
BLOCKED_SPECS = {"product_badlogin_spec": ("product-", ("product-precondition-guard-010",))}

LABEL_NOTES: list[str] = [
    # 라벨을 고친 경우 근거와 함께 여기에 적는다.
]


def screen_of(case_id: str) -> str:
    head = case_id.split("-", 1)[0]
    return "flow" if head == "flow" else head


def label(spec: str, variant: str, case_id: str) -> tuple[str, str]:
    """(라벨, 결함 이름)."""
    logic = SERVED.get(variant, {}).get(screen_of(case_id))
    if logic is None:
        return "NA", ""
    blocked = BLOCKED_SPECS.get(spec)
    if blocked and case_id.startswith(blocked[0]) and case_id not in blocked[1]:
        return "BLOCKED", ""
    defect = DEFECTS[logic].get(case_id)
    return ("DEFECT", defect) if defect else ("PASS", "")


def read_dump(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        spec, variant, case_id, verdict = parts[:4]
        category = parts[4] if len(parts) > 4 else ""
        yield spec, variant, case_id, verdict, category


def score(rows) -> dict:
    out = {"cm": Counter(), "rows": [], "na_false_defect": [], "na": 0,
           "by_variant": defaultdict(Counter)}
    out["errors"] = []
    for spec, variant, case_id, verdict, category in rows:
        if verdict == "ERROR":  # 파이프라인이 멈춘 조합 — 케이스가 없으니 따로 센다
            out["errors"].append((spec, variant, category))
            continue
        lab, defect = label(spec, variant, case_id)
        if lab == "NA":
            out["na"] += 1
            if verdict == "FAIL" and category == DEFECT_CATEGORY:
                out["na_false_defect"].append((spec, variant, case_id))
            continue
        want_fail = lab in ("DEFECT", "BLOCKED")
        got_fail = verdict == "FAIL"
        if lab == "PASS":
            kind = "PASS→PASS" if not got_fail else (
                "PASS→거짓 결함" if category == DEFECT_CATEGORY else "PASS→실행 문제")
        elif lab == "DEFECT":
            kind = "결함→놓침" if not got_fail else (
                "결함→지목" if category == DEFECT_CATEGORY else "결함→실행 문제로 잡음")
        else:  # BLOCKED
            kind = "막힘→PASS(빈 통과)" if not got_fail else (
                "막힘→거짓 결함" if category == DEFECT_CATEGORY else "막힘→실행 문제")
        out["cm"][kind] += 1
        out["by_variant"][variant]["agree" if want_fail == got_fail else "disagree"] += 1
        out["rows"].append((spec, variant, case_id, lab, defect, verdict, category, kind,
                            want_fail == got_fail))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", type=Path, help="dump_verdicts.py 결과 TSV")
    ap.add_argument("--wrong", action="store_true", help="어긋난 케이스를 전부 적는다")
    args = ap.parse_args()

    s = score(read_dump(args.dump))
    n = len(s["rows"])
    agree = sum(1 for r in s["rows"] if r[8])
    print(f"채점 대상 {n}건 (화면이 없는 조합 {s['na']}건 제외)")
    print(f"PASS/FAIL 일치 {agree}/{n} = {agree / n * 100:.1f}%")
    strict = s["cm"]["PASS→PASS"] + s["cm"]["결함→지목"] + s["cm"]["막힘→실행 문제"]
    print(f"분류까지 일치 {strict}/{n} = {strict / n * 100:.1f}%  "
          "(결함은 '기획서와 다름', 막힘은 '실행 문제' 로)")
    print()
    for k in ("PASS→PASS", "PASS→실행 문제", "PASS→거짓 결함",
              "결함→지목", "결함→실행 문제로 잡음", "결함→놓침",
              "막힘→실행 문제", "막힘→거짓 결함", "막힘→PASS(빈 통과)"):
        print(f"  {k:<16} {s['cm'][k]}")
    print(f"  화면 없는 조합에서 '기획서와 다름' 을 말함: {len(s['na_false_defect'])}")
    served = [e for e in s["errors"] if SERVED.get(e[1])]
    print(f"  파이프라인이 멈춘 조합: {len(s['errors'])}"
          + (f" — 그중 화면을 내주는 변형 {len(served)}: {served}" if served else ""))
    print()
    print("변형별 일치")
    for v, c in sorted(s["by_variant"].items()):
        t = c["agree"] + c["disagree"]
        print(f"  {v:<9} {c['agree']}/{t}")
    if args.wrong:
        print()
        for r in s["rows"]:
            if not r[8] or r[7] in ("결함→실행 문제로 잡음", "PASS→거짓 결함"):
                print("  " + "\t".join(r[:8]))
        for r in s["na_false_defect"]:
            print("  NA 거짓 결함\t" + "\t".join(r))


if __name__ == "__main__":
    sys.exit(main())
