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
