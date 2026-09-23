"""모델이 기획서를 옮겨 적은 메모는 빼고, 판단을 말한 메모만 남긴다.

## 왜 (2026-09-23 외부 사이트 실측)

프롬프트가 "판단할 수 없는 내용은 warnings 에 적어라" 라고 하자 7B 가 **실패 조건 표의
행을 의역해** 네 줄을 냈다. 기획서에는 아무 문제가 없는데 리포트는 설계 문서 경고 네 줄로
시작한다. 09-22 에 넣은 필터는 글자가 똑같을 때만 걸러서(표현이 바뀌면 못 잡는다) 이 모양을
놓쳤다 — `비어 있음` 이 `비어 있으면` 으로, 큰따옴표가 작은따옴표로 바뀌어 있었다.

겹침 비율로 판별한다. 실측에서 옮겨 적은 메모는 0.82~0.88, 판단을 말한 메모는 0.00~0.10
이었다 — 그 사이는 넓다.
"""

from __future__ import annotations

import pytest

from prova.models import ScreenSpec
from prova.s1_spec_extractor.extractor import _label_model_warnings

DOC = """## 4. 실패 조건

| 상황 | 처리 |
|---|---|
| 사용자 이름이 비어 있음 | "Epic sadface: Username is required" 노출, 이동하지 않음 |
| 비밀번호가 비어 있음 | "Epic sadface: Password is required" 노출, 이동하지 않음 |
| 잠긴 계정 | "Epic sadface: Sorry, this user has been locked out." 노출, 이동하지 않음 |
"""


def _spec(*warnings: str) -> ScreenSpec:
    return ScreenSpec(screen_id="s", screen_name="s", url_path="/", warnings=list(warnings))


# 어제 실제로 뜬 메모 — 표의 행을 살짝 바꿔 쓴 것이다.
@pytest.mark.parametrize("memo", [
    "사용자 이름이 비어 있으면 'Epic sadface: Username is required' 노출",
    "비밀번호가 비어 있으면 'Epic sadface: Password is required' 노출",
    "잠긴 계정이면 'Epic sadface: Sorry, this user has been locked out.' 노출",
    "사용자 이름이 비어 있음 | \"Epic sadface: Username is required\" 노출, 이동하지 않음",
])
def test_옮겨_적은_메모는_뺀다(memo):
    spec = _spec(memo)
    _label_model_warnings(spec, DOC)
    assert spec.warnings == []


# 기획서에 없는 판단을 말한 메모 — 이건 통로가 필요하다.
@pytest.mark.parametrize("memo", [
    "가격의 최대값이 기획서에 없습니다",
    "화면 경로를 판단할 수 없습니다",
    "이 화면의 접근 권한이 기획서에 적혀 있지 않아 추측하지 않았습니다",
])
def test_판단을_말한_메모는_남긴다(memo):
    spec = _spec(memo)
    _label_model_warnings(spec, DOC)
    assert spec.warnings == [f"모델 메모: {memo}"]


def test_짧은_메모도_옮겨_적었으면_뺀다():
    """4글자보다 짧으면 조각을 못 만든다 — 통째로 들어 있는지 본다."""
    spec = _spec("잠긴 계정")
    _label_model_warnings(spec, DOC)
    assert spec.warnings == []


def test_리포트와_터미널이_메모를_경고와_나눠_보인다(capsys):
    from pathlib import Path

    from prova.cli import _print_summary
    from prova.models import TestReport
    from prova.s6_report.report_builder import render_html
    from types import SimpleNamespace

    summary = {"total": 1, "pass": 1, "fail": 0, "pass_rate": 100.0,
               "spec_warnings": ["요소 표에는 4개 요소가 있는데 추출된 것은 0개입니다",
                                 "모델 메모: 가격의 최대값이 기획서에 없습니다"]}
    html = render_html(TestReport(run_id="r", target_url="http://x", summary=summary))
    assert "<b>설계 문서 추출 경고</b>" in html and "<b>모델 메모</b>" in html
    # 메모 상자 안에서는 접두어를 한 번만 말한다
    assert "모델 메모: 가격" not in html

    _print_summary(SimpleNamespace(summary=summary, cases=[]), Path("runs/x"))
    out = capsys.readouterr().out
    assert "! 설계 문서 경고: 요소 표에는" in out
    assert "· 모델 메모(도구가 확인한 사실 아님): 가격의 최대값" in out
