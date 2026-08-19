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

    def test_요소_1개는_통과(self):
        """문서화 목적의 경계값 — 비교할 상대가 없으므로 '정렬이 깨졌다' 는
        말을 할 수 없다. _judge_sorted_desc 는 인접 쌍(range(len-1))만 보므로
        1개일 때 그 루프가 아예 돌지 않아 자연히 통과다. 요소 0개(FAIL)와
        나란히 두면 이 함수의 경계가 어디인지 코드를 안 읽어도 알 수 있다."""
        ok, _ = _judge_sorted_desc(EXP_SORT, _state(주문일=["2026-08-15"]))
        assert ok

    def test_수집되지_않았으면_두_판정_모두_실패(self):
        """column_texts 자체가 None 이면(이 케이스 유형이 아니라서 nodes 가
        모으지 않은 경우) '수집하지 않았다' 는 사유로 FAIL — 판정 불능을
        조용히 통과로 접지 않는다."""
        empty = PageState(url="x", text="", column_texts=None)
        ok, why = _judge_sorted_desc(EXP_SORT, empty)
        assert not ok and "수집" in why

    def test_라벨_요소가_화면에_없으면_실패(self):
        """column_texts 는 있지만 그 라벨의 컨테이너를 화면에서 못 찾은
        경우(status="absent") — 목록의 부재는 CollectionCount 와 같은 원칙으로
        판정 재료이지 도구 실패가 아니다. 여기서는 '정렬을 확인할 수 없다' 는
        뜻이므로 FAIL 이다."""
        state = _state()
        state.column_texts["주문일"] = CollectionTexts(
            status="absent", texts=[], detail="라벨 없음")
        ok, why = _judge_sorted_desc(EXP_SORT, state)
        assert not ok and "셀 수 없습니다" in why


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

    def test_수집되지_않았으면_실패(self):
        """TestSorted 의 같은 경계값과 대칭이다 — column_texts=None 은 '수집
        안 함' 이고, 두 판정 모두 이 상태를 통과로 접지 않아야 한다."""
        empty = PageState(url="x", text="", column_texts=None)
        ok, why = _judge_sum_matches(EXP_SUM, empty)
        assert not ok and "수집" in why

    def test_라벨_요소가_화면에_없으면_실패(self):
        """TestSorted 의 같은 경계값과 대칭이다 — status="absent" 는 그
        라벨의 요소를 화면에서 못 찾았다는 뜻이고, 합계를 확인할 수 없으므로
        FAIL 이다."""
        state = _state(금액=["1,000"])
        state.column_texts["합계"] = CollectionTexts(
            status="absent", texts=[], detail="라벨 없음")
        ok, why = _judge_sum_matches(EXP_SUM, state)
        assert not ok and "찾지 못했습니다" in why
