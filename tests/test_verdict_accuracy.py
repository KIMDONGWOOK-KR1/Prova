"""판정 정확도 채점기 — 틀린 판정을 먹이면 정말 점수가 내려가는가.

## 왜 이 테스트가 필요한가

이 채점기가 실제 실행에 대해 낸 첫 값이 **100%** 다(132건, 2026-09-23).
그런데 늘 100% 를 내는 채점기도 똑같이 100% 를 낸다. 눈으로는 구분되지 않는다.

그래서 일부러 틀린 판정을 먹여 오탐·미탐이 올라가는지 본다. 이 파일이
초록불인 동안에만 그 100% 가 뜻을 가진다.

## 오탐과 미탐을 나눠 세는 것도 여기서 지킨다

합치면 성질이 다른 실패가 섞인다. 이 도구에서 오탐이 더 나쁘다 — 미탐은 도구의
한계로 남지만 오탐은 개발자의 시간을 쓰고 도구의 신뢰를 없앤다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import load_script

mod = load_script("scripts/eval_verdict_accuracy.py")

LABELS = Path("fixtures/labels/verdict-labels.json")


def report(*pairs: tuple[str, str]) -> dict:
    return {"cases": [{"case_id": cid, "verdict": v} for cid, v in pairs]}


class TestScore:
    def test_다_맞으면_100(self):
        exp = {"a": "PASS", "b": "FAIL"}
        s = mod.score(exp, {"a": "PASS", "b": "FAIL"})
        assert s["accuracy"] == 100.0
        assert s["false_positive"] == 0 and s["false_negative"] == 0

    def test_오탐을_센다(self):
        """정답은 PASS 인데 FAIL 로 보고했다 — 없는 결함이다."""
        s = mod.score({"a": "PASS", "b": "PASS"}, {"a": "FAIL", "b": "PASS"})
        assert s["false_positive"] == 1
        assert s["false_negative"] == 0
        assert s["accuracy"] == 50.0
        assert s["fp_cases"] == ["a"]

    def test_미탐을_센다(self):
        """정답은 FAIL 인데 PASS 로 보고했다 — 놓친 결함이다."""
        s = mod.score({"a": "FAIL", "b": "PASS"}, {"a": "PASS", "b": "PASS"})
        assert s["false_negative"] == 1
        assert s["false_positive"] == 0
        assert s["fn_cases"] == ["a"]

    def test_둘을_합치지_않는다(self):
        s = mod.score({"a": "PASS", "b": "FAIL"}, {"a": "FAIL", "b": "PASS"})
        assert s["false_positive"] == 1 and s["false_negative"] == 1
        assert s["accuracy"] == 0.0

    def test_판정이_아예_없으면_미탐으로_센다(self):
        """실행이 그 케이스를 내지 않은 것이다. 맞았다고 볼 근거가 없다."""
        s = mod.score({"a": "FAIL"}, {})
        assert s["false_negative"] == 1 and s["accuracy"] == 0.0


class TestExpectedVerdicts:
    def test_all_pass_는_전부_PASS(self):
        exp = mod.expected_verdicts({"expect": "all_pass"}, ["a", "b"])
        assert exp == {"a": "PASS", "b": "PASS"}

    def test_fail_listed_는_적힌_것만_FAIL(self):
        exp = mod.expected_verdicts(
            {"expect": "fail_listed", "fail": {"b": "B1 …"}}, ["a", "b", "c"])
        assert exp == {"a": "PASS", "b": "FAIL", "c": "PASS"}

    def test_라벨이_낡으면_멈춘다(self):
        """없는 케이스를 FAIL 로 적어 두면 미탐으로 잡혀 도구가 억울하게 깎인다.
        원인이 도구가 아니라 라벨이므로 그 둘을 섞지 않고 여기서 멈춘다."""
        with pytest.raises(ValueError, match="라벨에 없는 케이스"):
            mod.expected_verdicts(
                {"expect": "fail_listed", "fail": {"사라진케이스": "x"}}, ["a"])


class TestEvaluate:
    def test_커버리지를_함께_낸다(self):
        """커버리지 없는 정확도는 숫자만 있는 것이다."""
        labels = {
            "runs": {"r1": {"expect": "all_pass", "screen": "s", "target": "good"}},
            "unlabeled": {"r2": "아직"},
        }
        reports = {"r1": report(("a", "PASS")),
                   "r2": report(("x", "PASS"), ("y", "FAIL"))}
        result = mod.evaluate(labels, reports)
        assert result["coverage"] == {"labeled": 1, "unlabeled": 2, "rate": 33.3}

    def test_미라벨은_분모에_넣지_않는다(self):
        """맞았다 쪽에 넣으면 정확도가 부풀고, 틀렸다 쪽에 넣으면 억울하게 깎인다."""
        labels = {"runs": {"r1": {"expect": "all_pass"}}, "unlabeled": {"r2": "아직"}}
        reports = {"r1": report(("a", "PASS")), "r2": report(("x", "FAIL"))}
        result = mod.evaluate(labels, reports)
        assert result["total"]["total"] == 1
        assert result["total"]["accuracy"] == 100.0

    def test_리포트가_없는_실행을_알린다(self):
        labels = {"runs": {"r1": {"expect": "all_pass"}}}
        result = mod.evaluate(labels, {})
        assert result["missing_runs"] == ["r1"]


class TestLabelFile:
    """라벨 파일 자체의 규율 — 결함에 대응되지 않는 FAIL 라벨은 둘 수 없다."""

    def test_모든_FAIL_라벨에_결함_이름이_있다(self):
        labels = json.loads(LABELS.read_text(encoding="utf-8"))
        for run_id, run in labels["runs"].items():
            for cid, why in (run.get("fail") or {}).items():
                assert why and why.strip(), (
                    f"{run_id}/{cid} 의 FAIL 라벨에 근거가 없다 — "
                    "심은 결함 표의 어느 항목인지 적어야 한다"
                )

    def test_good_은_전부_PASS_라벨이다(self):
        """good 은 기획서를 전부 지킨 구현이다. 여기 FAIL 라벨이 생기면
        그건 라벨이 아니라 SUT 의 결함이다."""
        labels = json.loads(LABELS.read_text(encoding="utf-8"))
        for run_id, run in labels["runs"].items():
            if run.get("target") == "good":
                assert run["expect"] == "all_pass", run_id
