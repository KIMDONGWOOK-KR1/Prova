"""실물 기획서 정답표 채점 — 골든이 없는 기획서의 추출 정확도를 사람이 옮겨 적은 표로 잰다.

놓친 것(재현율)과 지어낸 것(추출에만 있는 것)을 따로 센다. 놓친 규칙은 미탐이 되고
지어낸 규칙은 오탐이 되어서, 한 숫자로 합치면 어느 쪽 사고인지 사라진다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from prova.models import ScreenSpec, SpecDocument, UIElement
from prova.truth import blank_template, format_score, is_private_path, score

DOC = SpecDocument(source="s.pdf", screens=[ScreenSpec(
    screen_id="login", screen_name="로그인", url_path="/login",
    success_condition="성공 시 /dashboard 로 이동한다",
    failure_conditions=["로그인 5회 실패 시 잠금 안내"],
    elements=[
        UIElement(element_id="email", type="input", label="이메일", required=True,
                  constraints={"format": "email"}, error_message="이메일 형식이\n아닙니다."),
        UIElement(element_id="kind", type="select", label="회원 유형", options=["개인", "법인"]),
        UIElement(element_id="memo", type="input", label="지어낸 칸"),
    ],
)])

TRUTH = {"screens": [{
    "name": "로그인",
    "success": "/dashboard",
    "messages": ["로그인 5회 실패 시 잠금 안내", "기획서에는 있는데 추출에 없는 문구"],
    "elements": [
        {"label": "이메 일", "required": True, "rules": {"format": "email", "max_length": 50},
         "error": "이메일 형식이 아닙니다."},
        {"label": "회원 유형", "options": ["개인", "법인", "단체"]},
        {"label": "없는 칸", "rules": {"min_length": 2}},
    ],
}]}


def test_항목마다_맞은_수와_전체_수를_센다():
    s = score(TRUTH, DOC)
    # 요소3 필수1 규칙3 오류1 선택3 성공1 문구2 = 14, 놓친 것: max_length·단체·없는 칸(+규칙)·문구
    assert (s.matched, s.total) == (9, 14)
    assert s.recall == pytest.approx(9 / 14)


def test_놓친_항목을_이름으로_말한다():
    missed = "\n".join(score(TRUTH, DOC).missed)
    for word in ("max_length", "단체", "없는 칸", "기획서에는 있는데"):
        assert word in missed


def test_요소를_놓치면_그_규칙도_놓친_것으로_센다():
    s = score({"screens": [{"name": "로그인", "elements": [
        {"label": "없는 칸", "rules": {"min_length": 2, "max_length": 9}}]}]}, DOC)
    assert (s.matched, s.total) == (0, 3)


def test_추출에만_있는_것을_따로_센다():
    extra = score(TRUTH, DOC).extra
    assert any("지어낸 칸" in x for x in extra)


def test_정답에_없는_규칙을_추출하면_추출에만_있는_것이다():
    truth = {"screens": [{"name": "로그인", "elements": [{"label": "이메일"}]}]}
    assert any("format" in x for x in score(truth, DOC).extra)


def test_화면을_통째로_놓치면_그_항목이_전부_놓친_것이다():
    s = score({"screens": [{"name": "없는 화면", "success": "/x",
                            "elements": [{"label": "칸"}]}]}, DOC)
    assert (s.matched, s.total) == (0, 2)
    assert any("없는 화면" in m for m in s.missed)


def test_정답표가_비었으면_0점이_아니라_오류다():
    with pytest.raises(ValueError, match="비어"):
        score({"screens": []}, DOC)


def test_빈_양식은_읽을_수_있고_항목이_없어_그대로_채점되지_않는다():
    with pytest.raises(ValueError, match="비어"):
        score(yaml.safe_load(blank_template()), DOC)


def test_빈_양식이_금지와_순서를_적어_둔다():
    text = blank_template()
    assert "커밋" in text and "보기 전에" in text


def test_종류별_결과를_글로_찍는다():
    text = format_score(score(TRUTH, DOC))
    assert "9/14" in text and "규칙" in text and "놓친 것" in text and "추출에만" in text


def test_저장소_안_일반_경로는_비공개가_아니다():
    assert not is_private_path(Path("docs/truth.yaml"))


def test_저장소_안_무시_경로는_비공개다():
    assert is_private_path(Path("uploads/truth.yaml"))


def test_저장소_밖은_비공개다(tmp_path):
    assert is_private_path(tmp_path / "truth.yaml")


def test_스크립트가_저장소_안_정답표를_거부한다():
    done = subprocess.run(
        ["uv", "run", "python", "scripts/score_truth.py", "--pdf", "fixtures/specs/login_spec.pdf",
         "--truth", "docs/truth.yaml", "--backend", "mock"],
        capture_output=True, text=True, encoding="utf-8")
    assert done.returncode != 0 and "저장소" in done.stderr


def test_스크립트가_양식을_저장소_밖에_쓴다(tmp_path):
    out = tmp_path / "t.yaml"
    subprocess.run(["uv", "run", "python", "scripts/score_truth.py", "--template", str(out)],
                   check=True, capture_output=True)
    assert "screens" in out.read_text(encoding="utf-8")


def test_스크립트가_채점한다(tmp_path):
    out = tmp_path / "t.yaml"
    out.write_text(yaml.safe_dump({"screens": [{"name": "로그인", "elements": [
        {"label": "이메일"}]}]}, allow_unicode=True), encoding="utf-8")
    done = subprocess.run(
        ["uv", "run", "python", "scripts/score_truth.py", "--pdf", "fixtures/specs/login_spec.pdf",
         "--truth", str(out), "--backend", "mock"],
        capture_output=True, text=True, encoding="utf-8",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stderr
    assert "1/1" in done.stdout
