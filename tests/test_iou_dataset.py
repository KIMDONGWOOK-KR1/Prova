"""굳혀 둔 탐지 데이터셋과 채점 경로를 고정한다 (GPU 불필요).

## 왜 데이터셋에 테스트를 붙이는가

`fixtures/iou/` 는 저장소에 굳혀 둔 시험지다. 화면이 바뀌면 정답 좌표가 실제 화면과
어긋나는데, 그 사실이 **채점 결과에서는 '모델이 틀렸다' 로만 보인다.** 시험지가 낡은 것과
모델이 못 맞힌 것을 구분할 수 없게 되므로, 시험지 자체의 무결성을 여기서 지킨다.

## 오탐 집계를 테스트하는 이유 ← 이게 가장 중요하다

보고서에서 좋은 소식만 낼 수 있는 지표는 없는 것보다 나쁘다. '없는 것을 찾았다고 했는가'
집계가 고장 나면 오탐이 항상 0 으로 나오고, 그 0 은 측정한 0 처럼 보인다. 그래서
**일부러 오탐하는 가짜 모델**을 넣어 집계가 실제로 올라가는지 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prova.vlm.base import Located

from conftest import load_script  # pytest 가 tests/ 를 sys.path 에 넣는다

DATASET = Path("fixtures/iou/dataset.json")


@pytest.fixture(scope="module")
def data() -> dict:
    if not DATASET.exists():
        pytest.skip("먼저 `uv run python scripts/build_iou_dataset.py` 를 실행하세요")
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def evaluator():
    return load_script("scripts/eval_vlm_iou.py")


def _items(data: dict) -> list[dict]:
    """채점에 넘길 항목. 이미지 경로를 데이터셋 폴더로 맞춘다."""
    items = [dict(item) for item in data["items"]]
    for item in items:
        item["_dir"] = str(DATASET.parent)
    return items


class TestDatasetIntegrity:
    def test_해시가_내용과_맞다(self, data):
        """데이터셋을 손으로 고치면 여기서 걸린다.

        점수와 시험지를 묶는 것이 dataset_id 인데, 그 값이 내용과 어긋나면
        '어느 시험지의 점수인가' 를 말할 수 없다.
        """
        builder = load_script("scripts/build_iou_dataset.py")
        assert builder.dataset_id(data["items"]) == data["dataset_id"], (
            "dataset.json 의 내용과 dataset_id 가 어긋났습니다. "
            "다시 만드세요: uv run python scripts/build_iou_dataset.py")

    def test_있음_항목은_0과_1_사이_상자를_갖는다(self, data):
        for item in data["items"]:
            if not item["present"]:
                continue
            x1, y1, x2, y2 = item["truth"]
            assert 0.0 <= x1 < x2 <= 1.0, item
            assert 0.0 <= y1 < y2 <= 1.0, item

    def test_없음_항목은_정답_상자가_없다(self, data):
        # 없는 요소에 좌표가 있으면 채점이 그것을 정답으로 쓴다.
        for item in data["items"]:
            if not item["present"]:
                assert item["truth"] is None, item

    def test_이미지가_모두_있다(self, data):
        for item in data["items"]:
            assert (DATASET.parent / item["image"]).exists(), item["image"]

    def test_없는_요소를_묻는_항목이_있다(self, data):
        # 있는 것만 묻는 시험지는 '없다고 말하는가' 를 재지 않는다.
        assert data["absent"] >= 5, data["absent"]

    def test_아이콘_버튼_화면이_들어있다(self, data):
        # 2차 경로가 필요한 이유가 이 화면이다. 빠지면 쉬운 문제만 재게 된다.
        assert any(i["state_id"].startswith("nolabel") for i in data["items"])

    def test_힌트가_파이프라인과_같은_표에서_온다(self, data):
        from prova.s3_grounder.dom_locator import VLM_HINTS

        for item in data["items"]:
            assert item["hint"] == VLM_HINTS.get(item["kind"], ""), item


class TestScoring:
    def test_정답을_그대로_답하면_전부_성공이다(self, data, evaluator):
        oracle = evaluator.OracleVLM()
        rows = evaluator.evaluate(_items(data), oracle, min_conf=0.5,
                                  threshold=0.5, oracle=oracle)
        s = evaluator.summarize(rows, 0.5)
        assert s["success_iou"] == s["present"] == data["present"]
        assert s["false_positive"] == 0
        assert s["call_failed"] == 0

    def test_좌표를_밀면_IoU는_실패하고_적중은_남는다(self, data, evaluator):
        """두 지표가 갈리는 것을 채점 경로 전체에서 확인한다.

        요소 크기의 30% 를 밀면 중심은 아직 요소 안에 있고(클릭 성공) IoU 는 0.5
        아래로 떨어진다. 한 지표만 보고 있으면 이 구간이 통째로 보이지 않는다.
        """
        oracle = evaluator.OracleVLM(jitter=0.3)
        rows = evaluator.evaluate(_items(data), oracle, min_conf=0.5,
                                  threshold=0.5, oracle=oracle)
        s = evaluator.summarize(rows, 0.5)
        assert s["success_iou"] == 0
        assert s["success_hit"] == s["present"]

    def test_오탐이_실제로_집계된다(self, data, evaluator):
        """없는 것을 '찾았다' 고 답하는 모델을 넣으면 오탐 수가 올라가야 한다.

        이 테스트가 없으면 집계가 고장 나도 보고서는 늘 '오탐 0' 을 낸다. 좋은
        소식만 낼 수 있는 지표는 신뢰의 근거가 되지 못한다.
        """

        class 항상찾았다고답한다:
            name = "always"

            def locate(self, *, image_png, target, hint=""):
                return Located(bbox=(0.1, 0.1, 0.2, 0.2), confidence=0.99)

        rows = evaluator.evaluate(_items(data), 항상찾았다고답한다(),
                                  min_conf=0.5, threshold=0.5, oracle=None)
        s = evaluator.summarize(rows, 0.5)
        assert s["false_positive"] == s["absent"] == data["absent"]

    def test_신뢰도가_낮으면_좌표가_맞아도_실패다(self, data, evaluator):
        """파이프라인은 관문 아래를 버린다. 채점도 같아야 보고서가 실행을 대표한다.

        동시에 '관문이 버린 정답' 이 세어지는지 확인한다 — 그 수가 크면 고칠 곳은
        모델이 아니라 문턱값이고, 두 원인을 섞으면 어느 쪽도 고칠 수 없다.
        """
        oracle = evaluator.OracleVLM()
        items = _items(data)
        rows = evaluator.evaluate(items, oracle, min_conf=1.1,  # 아무도 통과 못 한다
                                  threshold=0.5, oracle=oracle)
        s = evaluator.summarize(rows, 0.5)
        assert s["success_iou"] == 0
        assert s["gate_dropped"] == data["present"]


@pytest.fixture(scope="module")
def selector_eval():
    return load_script("scripts/eval_selector_speed.py")


class TestSelectorScoring:
    """같은 시험지를 1차 경로(selector)로 채점한다 — 명세서 §9 의 비교 측정.

    §9 는 'selector 방식 vs VLM 방식의 탐지 성공률·처리 속도를 별도 비교' 를
    요구한다. VLM 쪽은 이미 쟀고(2026-08-22) 저장돼 있으므로, 같은 50개 항목을
    같은 화면에서 1차 경로로 재면 사과 대 사과 비교가 된다.

    브라우저를 여는 일과 채점을 나눈다 — 채점은 `locate` 를 받아서 부르기만
    하므로, 여기서는 가짜 `locate` 로 집계만 확인할 수 있다. VLM 채점이
    `evaluate(items, vlm)` 로 갈라 둔 것과 같은 모양이다.
    """

    def test_전부_찾으면_있음_항목이_전부_성공이다(self, data, selector_eval):
        def 항상찾는다(item):
            return True, "label"

        rows = selector_eval.evaluate_selector(_items(data), 항상찾는다)
        s = selector_eval.summarize_selector(rows)
        assert s["found"] == s["present"] == data["present"]

    def test_없는_요소를_찾았다고_하면_오탐이_올라간다(self, data, selector_eval):
        """이 테스트가 가장 중요하다. 집계가 고장 나면 보고서는 늘 '오탐 0' 을
        내고, 그 0 은 측정한 0 처럼 보인다 — 1차 경로가 유리해 보이는 방향으로
        조용히 틀린다."""
        def 항상찾는다(item):
            return True, "label"

        rows = selector_eval.evaluate_selector(_items(data), 항상찾는다)
        s = selector_eval.summarize_selector(rows)
        assert s["false_positive"] == s["absent"] == data["absent"]

    def test_아무것도_못_찾으면_성공도_오탐도_0이다(self, data, selector_eval):
        """없는 요소를 못 찾는 것은 오탐이 아니라 정답이다."""
        def 못찾는다(item):
            return False, None

        rows = selector_eval.evaluate_selector(_items(data), 못찾는다)
        s = selector_eval.summarize_selector(rows)
        assert s["found"] == 0
        assert s["false_positive"] == 0

    def test_탐지_실패와_오류를_섞지_않는다(self, data, selector_eval):
        """'못 찾았다' 와 '재는 중에 터졌다' 는 다르다. 섞으면 도구가 고장 난
        것을 탐지 실패로 보고하게 된다 — 이 프로젝트가 반복해서 경계해 온 모양."""
        def 터진다(item):
            raise RuntimeError("브라우저가 죽었다")

        rows = selector_eval.evaluate_selector(_items(data), 터진다)
        s = selector_eval.summarize_selector(rows)
        assert s["call_failed"] == len(data["items"])
        assert s["found"] == 0
        assert s["false_positive"] == 0

    def test_시간이_기록된다(self, data, selector_eval):
        def 항상찾는다(item):
            return True, "label"

        rows = selector_eval.evaluate_selector(_items(data), 항상찾는다)
        assert all("elapsed_ms" in r for r in rows)
        s = selector_eval.summarize_selector(rows)
        assert s["mean_ms"] >= 0 and s["max_ms"] >= 0


class TestPopulationGuard:
    """두 경로의 숫자를 나란히 놓기 전에 **같은 항목인지** 확인한다.

    실제로 어긋난 적이 있다(2026-08-27). 1차 경로를 재면서 select·list 를
    뺐는데, 그 제외는 정체 대조 재생(08-25)의 범위였고 IoU 채점(08-22)은 50개
    전부였다. 그대로 표를 만들었으면 43개로 잰 숫자와 50개로 잰 숫자를 나란히
    놓고 '비교' 라고 불렀을 것이다.

    모집단이 다른 두 수치는 비교가 아니라 착시다. 그리고 그 어긋남은 표에서
    보이지 않는다 — 그래서 코드가 막는다.
    """

    def test_같은_항목이_아니면_비교하지_않는다(self, selector_eval):
        with pytest.raises(ValueError, match="모집단"):
            selector_eval.check_same_population(
                [{"id": 1}, {"id": 2}], [{"id": 1}, {"id": 3}])

    def test_같은_항목이면_통과한다(self, selector_eval):
        selector_eval.check_same_population(
            [{"id": 2}, {"id": 1}], [{"id": 1}, {"id": 2}])

    def test_VLM_행을_같은_항목으로_좁혀_요약한다(self, selector_eval):
        """비교 대상이 부분집합이면 VLM 쪽도 그 부분집합으로 다시 세야 한다.
        저장된 문서의 숫자를 그대로 옮겨 적으면 모집단이 조용히 갈라진다."""
        rows = [
            {"id": 0, "present": True, "hit": True, "gate": True, "elapsed_ms": 100.0},
            {"id": 1, "present": True, "hit": False, "gate": True, "elapsed_ms": 300.0},
            {"id": 2, "present": False, "hit": False, "gate": True, "elapsed_ms": 200.0},
        ]
        s = selector_eval.summarize_vlm(rows, keep_ids={0, 2})
        assert s["present"] == 1 and s["absent"] == 1
        assert s["found"] == 1          # id 0 만 남는다
        assert s["false_positive"] == 1  # id 2 는 없는 것을 찾았다고 했다
        assert s["mean_ms"] == 150.0     # 100 과 200 의 평균 — 300 은 빠진다


class TestDatasetIdGuard:
    """점수는 어느 시험지의 것인지까지 맞아야 비교가 된다.

    항목 id 는 열거 순서로 매겨진다. 시험지가 바뀌어도 **같은 id 가 존재할 수
    있고**, 그때 id 집합 비교는 통과하면서 실제로는 다른 항목을 나란히 놓게
    된다. 저장된 채점 결과가 `meta.dataset_id` 를 들고 다니는 이유가 이것이다.

    2026-08-27 에 실제로 이 구멍을 만들 뻔했다 — 모집단 가드를 만들면서 id
    집합만 봤고, 바로 다음 작업이 시험지를 넓히는 것이었다.
    """

    def test_시험지가_다르면_비교하지_않는다(self, selector_eval):
        with pytest.raises(ValueError, match="시험지"):
            selector_eval.check_same_dataset("536392d2154b", {"dataset_id": "다른값"})

    def test_같은_시험지면_통과한다(self, selector_eval):
        selector_eval.check_same_dataset("536392d2154b", {"dataset_id": "536392d2154b"})

    def test_옛_결과에_시험지_표시가_없으면_멈춘다(self, selector_eval):
        """표시가 없다고 통과시키면 '모르는 것' 이 '같은 것' 으로 둔갑한다."""
        with pytest.raises(ValueError, match="시험지"):
            selector_eval.check_same_dataset("536392d2154b", {})


class TestGatedScreens:
    """로그인 뒤 화면을 시험지가 어떻게 데리고 다니는가.

    2026-08-27 에 시험지를 상품등록·주문조회까지 넓히면서 겪었다. 채점 스크립트가
    경로만 열었더니 세션이 없어 **전부 로그인 화면으로 리다이렉트**됐고, 그 화면에
    있는 '비밀번호' 를 '없는 요소를 찾았다'(오탐)로 집계했다. 1차 경로의 오탐이
    0 에서 3 으로 올라간 것처럼 보였는데 원인은 도구였다.

    **도구 결함이 탐지 실패로 둔갑하는 모양**이라 시험지가 스스로 막아야 한다 —
    화면에 닿는 방법을 시험지가 들고 다니고, 채점하는 쪽이 그것을 쓴다.
    """

    def test_로그인_뒤_화면은_항목에_표시가_있다(self, data):
        gated = [i for i in data["items"]
                 if i["path"].endswith(("/product", "/orders"))
                 or "/orders?" in i["path"]]
        assert gated, "상품등록·주문조회 항목이 시험지에 없습니다"
        assert all(i.get("login") for i in gated), [
            i["state_id"] for i in gated if not i.get("login")]

    def test_로그인_없이_닿는_화면은_표시가_없다(self, data):
        """표시를 남발하면 채점이 매번 로그인해 느려지고, 로그인 자체가 화면을
        바꾸는 경우(가입 완료 등)를 가릴 수 있다."""
        open_items = [i for i in data["items"] if i["path"].startswith("/good/login")]
        assert open_items
        assert not any(i.get("login") for i in open_items)


class TestGatedLocator:
    """채점 쪽이 그 표시를 실제로 쓰는가 — 브라우저 없이 확인한다."""

    class FakePage:
        def __init__(self):
            self.actions: list[tuple] = []

        def goto(self, url, **kw):
            self.actions.append(("goto", url))

        def fill(self, selector, value):
            self.actions.append(("fill", selector))

        def click(self, selector):
            self.actions.append(("click", selector))

        def wait_for_load_state(self, *a, **kw):
            pass

    def test_로그인_항목은_먼저_로그인한다(self, selector_eval):
        page = self.FakePage()
        locate = selector_eval.make_page_locator(page, "http://sut")
        item = {"id": 1, "path": "/good/orders", "target": "시작일",
                "kind": "date", "login": True}
        try:
            locate(item)
        except Exception:
            pass  # ground() 는 가짜 페이지에서 터진다 — 여기서 보는 것은 이동 경로다
        urls = [a[1] for a in page.actions if a[0] == "goto"]
        assert "http://sut/good/login" in urls, page.actions
        assert urls.index("http://sut/good/login") < urls.index("http://sut/good/orders")

    def test_표시가_없으면_로그인하지_않는다(self, selector_eval):
        page = self.FakePage()
        locate = selector_eval.make_page_locator(page, "http://sut")
        item = {"id": 2, "path": "/good/login", "target": "이메일",
                "kind": "input", "login": False}
        try:
            locate(item)
        except Exception:
            pass
        assert [a for a in page.actions if a[0] == "click"] == []


class RecordingPage:
    """이동·입력을 기록만 하는 가짜 페이지. 값까지 남긴다 —
    '누가 로그인 계정을 아는가' 를 확인하려면 채운 값을 봐야 한다."""

    def __init__(self):
        self.actions: list[tuple] = []

    def goto(self, url, **kw):
        self.actions.append(("goto", url))

    def fill(self, selector, value):
        self.actions.append(("fill", selector, value))

    def click(self, selector):
        self.actions.append(("click", selector))

    def wait_for_load_state(self, *a, **kw):
        pass

    def screenshot(self, *a, **kw):
        return b""

    def gotos(self) -> list[str]:
        return [a[1] for a in self.actions if a[0] == "goto"]

    def filled(self) -> list[str]:
        return [a[2] for a in self.actions if a[0] == "fill"]


@pytest.fixture
def builder():
    """`build_iou_dataset` — **채점 스크립트가 실제로 쓰는 그 모듈 객체**로 잡는다.

    `load_script` 는 `_script_<이름>` 으로 따로 등록하므로 그것을 패치해도 스크립트
    쪽에는 닿지 않는다. 계정 상수를 바꿔 '한 곳에서 온다' 를 확인하려면 같은
    인스턴스여야 한다.
    """
    import sys
    scripts = str(Path("scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import build_iou_dataset
    return build_iou_dataset


@pytest.fixture
def guard_eval():
    return load_script("scripts/eval_identity_guard.py")


class TestOneLoginProcedure:
    """SUT 로그인 절차는 한 곳에만 있어야 한다.

    2026-08-27 에 `eval_selector_speed` 가 세션 없이 화면을 열어 오탐 3건을
    만들었고, 고치면서 노트에 이렇게 적었다 — "채점 스크립트마다 로그인 절차를
    따로 적으면 한쪽만 고쳐지는 날이 온다". 08-28 에 그 날이 왔다:
    `eval_identity_guard` 에는 로그인이 아예 없어 새 화면에서 돌지 못했다.

    그래서 계정도 절차도 `build_iou_dataset` 하나가 갖는다. 이 테스트는 그것을
    **행동으로** 고정한다 — 계정 상수를 바꾸면 모든 채점 경로가 따라와야 한다.
    """

    ACCOUNT = ("probe@example.com", "Probe1!")

    def test_셀렉터_채점이_같은_계정을_쓴다(self, builder, selector_eval, monkeypatch):
        monkeypatch.setattr(builder, "LOGIN_ACCOUNT", self.ACCOUNT)
        page = RecordingPage()
        locate = selector_eval.make_page_locator(page, "http://sut")
        try:
            locate({"id": 1, "path": "/good/orders", "target": "시작일",
                    "kind": "date", "login": True})
        except Exception:
            pass  # ground() 는 가짜 페이지에서 터진다 — 여기서 보는 것은 로그인이다
        assert self.ACCOUNT[0] in page.filled(), page.actions

    def test_관문_재생이_같은_계정을_쓴다(self, builder, guard_eval, monkeypatch, tmp_path):
        monkeypatch.setattr(builder, "LOGIN_ACCOUNT", self.ACCOUNT)
        page = RecordingPage()
        row = {"state_id": "orders-list", "target": "비밀번호", "kind": "input",
               "bbox": [0.1, 0.1, 0.2, 0.2], "confidence": 0.9, "present": False}
        try:
            guard_eval.replay(page, "http://sut", tmp_path, [row])
        except Exception:
            pass  # _require_actionable 은 가짜 페이지에서 터진다
        assert self.ACCOUNT[0] in page.filled(), page.actions


class TestGuardReachesNewScreens:
    """관문 재생이 넓힌 시험지의 화면에 실제로 닿는가."""

    def test_모든_시험지_화면에_골든이_있다(self, data, guard_eval):
        """골든이 없으면 KeyError 로 터진다 — 그 화면의 오탐은 재생되지 않는다."""
        missing = sorted({
            i["state_id"] for i in data["items"]
            if i["state_id"].split("-")[0] not in guard_eval.GOLDEN_BY_PREFIX
        })
        assert not missing, missing

    def test_로그인_뒤_화면은_로그인부터_한다(self, guard_eval, tmp_path):
        page = RecordingPage()
        row = {"state_id": "orders-list", "target": "비밀번호", "kind": "input",
               "bbox": [0.1, 0.1, 0.2, 0.2], "confidence": 0.9, "present": False}
        try:
            guard_eval.replay(page, "http://sut", tmp_path, [row])
        except Exception:
            pass
        urls = page.gotos()
        assert "http://sut/good/login" in urls, page.actions
        assert urls.index("http://sut/good/login") < urls.index("http://sut/good/orders")

    def test_열린_화면은_로그인하지_않는다(self, guard_eval, tmp_path):
        page = RecordingPage()
        row = {"state_id": "login-empty", "target": "검색어", "kind": "input",
               "bbox": [0.1, 0.1, 0.2, 0.2], "confidence": 0.9, "present": False}
        try:
            guard_eval.replay(page, "http://sut", tmp_path, [row])
        except Exception:
            pass
        assert [a for a in page.actions if a[0] == "click"] == [], page.actions


class TestGuardAnswerSheet:
    """재생하는 답안이 **지금 시험지**의 것인가.

    옛 답안을 지금 화면에 재생하면 좌표가 어긋난 이유가 '관문이 막았다' 로
    보인다 — 재는 대상과 답안이 다른데 표에서는 보이지 않는다.
    """

    def test_기본_답안_파일이_있다(self, guard_eval):
        assert guard_eval.MEASUREMENT.exists(), guard_eval.MEASUREMENT

    def test_답안이_지금_시험지로_채점된_것이다(self, guard_eval, data):
        answer = json.loads(guard_eval.MEASUREMENT.read_text(encoding="utf-8"))
        assert answer["meta"]["dataset_id"] == data["dataset_id"]
