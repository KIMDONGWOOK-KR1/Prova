"""판단 정확도 채점기의 정답 라벨 — SUT 문서가 말하는 기대 건수와 맞는가.

라벨은 도구 출력을 보지 않고 SUT 의 결함 정의에서 만든다(scripts/score_verdicts.py).
여기서는 그 라벨이 SUT 머리 주석·README 의 'FAIL 기대' 건수와 맞는지만 본다 — 판정은 보지 않는다.
"""

from __future__ import annotations

from tests.conftest import load_script

sv = load_script("scripts/score_verdicts.py")

LOGIN = ["login-valid-001", "login-email-required-002", "login-email-format-003",
         "login-password-required-004", "login-password-min_length-005",
         "login-password-require_uppercase-006", "login-password-require_special-007",
         "login-placeholders-001", "login-labels-001", "login-scenario-008"]


def _fails(spec, variant, ids):
    return sorted(c for c in ids if sv.label(spec, variant, c)[0] == "DEFECT")


def test_bad_로그인은_6건():
    # sut/app.py 머리 주석: login 'FAIL 기대 6건'
    assert len(_fails("login_spec", "bad", LOGIN)) == 6


def test_good_계열은_결함이_없다():
    for v in ("good", "slow", "hashed", "table", "grid"):
        assert _fails("login_spec", v, LOGIN) == [], v


def test_변형_결함은_그_변형에만():
    assert _fails("login_spec", "native", LOGIN) == ["login-email-required-002",
                                                     "login-password-required-004"]
    assert _fails("login_spec", "spa", LOGIN) == ["login-valid-001"]
    # badtable·badgrid 의 로그인은 good 로직이다 (LOGIN_VARIANTS)
    assert _fails("orders_spec", "badtable", LOGIN) == []


def test_bad_주문조회는_9건():
    # README: '--only orders' bad 는 O1(무필터·필터 후)·O2·O3·O4·O5·O6 의 9건만 FAIL
    orders = [c for c in sv.DEFECTS["bad"] if c.startswith("orders-")]
    assert len(orders) == 9
    assert {sv.label("orders_spec", v, c)[0] for v in ("badtable", "badgrid") for c in orders} \
        == {"DEFECT"}


def test_화면이_없으면_NA():
    assert sv.label("product_spec", "slow", "product-valid-001")[0] == "NA"
    assert sv.label("multi_spec", "hashed", "flow-signup_then_login-001")[0] == "NA"
    assert sv.label("search_spec", "nolabel", "search-valid-001")[0] == "PASS"


def test_전제_계정이_틀린_기획서는_막힘():
    assert sv.label("product_badlogin_spec", "good", "product-valid-001")[0] == "BLOCKED"
    # 가드 케이스는 로그인이 필요 없다
    assert sv.label("product_badlogin_spec", "bad", "product-precondition-guard-010") \
        == ("DEFECT", "P2")


def test_채점_분류():
    rows = [("login_spec", "bad", "login-email-format-003", "FAIL", "assertion_mismatch"),
            ("login_spec", "good", "login-valid-001", "FAIL", "element_not_found"),
            ("login_spec", "good", "login-labels-001", "FAIL", "assertion_mismatch"),
            ("product_spec", "slow", "product-valid-001", "FAIL", "assertion_mismatch"),
            ("product_spec", "slow", "-", "ERROR", "PageError")]
    s = sv.score(rows)
    assert s["cm"]["결함→지목"] == 1
    assert s["cm"]["PASS→실행 문제"] == 1
    assert s["cm"]["PASS→거짓 결함"] == 1
    assert s["na_false_defect"] == [("product_spec", "slow", "product-valid-001")]
    assert len(s["errors"]) == 1
