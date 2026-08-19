"""정렬·합계는 화면 스스로 모순인지를 본다 (스펙 §3-4). 요소 0개는 FAIL —
0건 목록이 '정렬돼 있다' 로 통과하면 아무것도 확인하지 않은 초록불이다."""
from prova.models import Expectation
from prova.s3_grounder.dom_locator import CollectionTexts
from prova.s5_verifier.assertion_engine import PageState, _judge_sorted_desc, _judge_sum_matches


def _state(**cols):
    return PageState(url="x", text="", column_texts={
        k: CollectionTexts(status="ok", texts=v, detail="") for k, v in cols.items()})

EXP_SORT = Expectation(type="sorted_desc", order_target="주문일")
EXP_SUM = Expectation(type="sum_matches", sum_row_target="금액",
                      sum_total_target="합계")


class TestSorted:
    def test_내림차순이면_통과(self):
        ok, _ = _judge_sorted_desc(EXP_SORT, _state(주문일=["2026-08-15", "2026-08-12", "2026-07-28"]))
        assert ok

    def test_역순이_섞이면_실패하고_어디서_깨졌는지_말한다(self):
        ok, why = _judge_sorted_desc(EXP_SORT, _state(주문일=["2026-08-12", "2026-08-15"]))
        assert not ok and "2026-08-15" in why

    def test_같은_날짜는_허용(self):
        ok, _ = _judge_sorted_desc(EXP_SORT, _state(주문일=["2026-08-15", "2026-08-15"]))
        assert ok

    def test_요소_0개는_실패(self):
        ok, why = _judge_sorted_desc(EXP_SORT, _state(주문일=[]))
        assert not ok and "0" in why

    def test_날짜가_아니면_파싱_실패로_실패(self):
        ok, why = _judge_sorted_desc(EXP_SORT, _state(주문일=["8월 15일"]))
        assert not ok and "파싱" in why


class TestSum:
    def test_합이_맞으면_통과(self):
        ok, _ = _judge_sum_matches(EXP_SUM, _state(
            금액=["1,290,000", "39,000"], 합계=["1,329,000원"]))
        assert ok

    def test_합이_다르면_두_값을_모두_말한다(self):
        ok, why = _judge_sum_matches(EXP_SUM, _state(
            금액=["1,290,000", "39,000"], 합계=["1,290,000원"]))
        assert not ok
        digits = why.replace(",", "")
        assert "1329000" in digits and "1290000" in digits

    def test_행_0개는_실패(self):
        ok, _ = _judge_sum_matches(EXP_SUM, _state(금액=[], 합계=["0원"]))
        assert not ok

    def test_금액에_이상한_문자가_있으면_파싱_실패(self):
        ok, why = _judge_sum_matches(EXP_SUM, _state(
            금액=["삼만원"], 합계=["30000"]))
        assert not ok and "파싱" in why

    def test_합계_요소가_여러_개면_판정_불능으로_실패한다(self):
        ok, why = _judge_sum_matches(EXP_SUM, _state(
            금액=["1,000", "2,000"], 합계=["3,000원", "9,999원"]))
        assert not ok and "2개" in why
