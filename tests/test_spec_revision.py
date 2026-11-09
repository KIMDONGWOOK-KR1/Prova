"""기획서 개정판 비교 (B-3).

두 판의 추출 결과에서 바뀐 것을 줄로 내고, 바뀐 것을 건드리는 케이스를 고른다.
바뀌지 않은 것을 바뀐 것으로 말하면 안 된다 — ID 만 다르게 읽힌 요소는 라벨로 짝을 맞춘다.
"""

from __future__ import annotations

from prova.models import (Expectation, ScreenSpec, SpecDocument, TestCase, TestStep,
                          UIElement)
from prova.spec_revision import diff_revisions, touched_cases


def _el(eid: str, label: str, **kw) -> UIElement:
    return UIElement(element_id=eid, type=kw.pop("type", "input"), label=label, **kw)


def _doc(*screens: ScreenSpec) -> SpecDocument:
    return SpecDocument(source="s.pdf", screens=list(screens))


def _screen(sid: str = "login", name: str = "로그인", elements=(), **kw) -> ScreenSpec:
    return ScreenSpec(screen_id=sid, screen_name=name, url_path=kw.pop("url_path", "/login"),
                      elements=list(elements), **kw)


BASE = [_el("user_id", "아이디", required=True, placeholder="아이디 입력"),
        _el("password", "비밀번호", required=True, constraints={"min_length": 8}),
        _el("login_btn", "로그인", type="button")]


def test_같은_판이면_차이가_없다():
    assert diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=BASE))) == []


def test_요소_칸이_바뀌면_한_줄씩():
    new = [_el("user_id", "아이디", required=True, placeholder="이메일 입력"),
           _el("password", "비밀번호", required=True, constraints={"min_length": 10}),
           _el("login_btn", "로그인하기", type="button")]
    texts = [c.text for c in diff_revisions(_doc(_screen(elements=BASE)),
                                            _doc(_screen(elements=new)))]
    assert texts == [
        "[로그인] '아이디' 안내 문구: '아이디 입력' → '이메일 입력'",
        "[로그인] '비밀번호' 입력 규칙: {min_length=8} → {min_length=10}",
        "[로그인] '로그인' 라벨: '로그인' → '로그인하기'",
    ]


def test_ID_만_다르게_읽힌_요소는_바뀐_것이_아니다():
    new = [_el("userid", "아이디", required=True, placeholder="아이디 입력"), *BASE[1:]]
    assert diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=new))) == []


def test_요소가_생기고_없어진다():
    new = [*BASE[:2], _el("remember", "로그인 유지", type="checkbox")]
    changes = diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=new)))
    assert [(c.kind, c.text) for c in changes] == [
        ("element_added", "[로그인] 요소 '로그인 유지' 이 새로 생김"),
        ("element_removed", "[로그인] 요소 '로그인' 이 없어짐"),
    ]


def test_화면_칸과_화면_증감():
    old = _doc(_screen(elements=BASE, success_condition="/home"),
               _screen("find", "아이디 찾기"))
    new = _doc(_screen(elements=BASE, success_condition="/main"),
               _screen("join", "회원가입", url_path="/join"))
    assert [c.text for c in diff_revisions(old, new)] == [
        "[로그인] 성공 조건: '/home' → '/main'",
        "[회원가입] 화면이 새로 생김",
        "[아이디 찾기] 화면이 없어짐",
    ]


def test_화면_ID_가_달라도_이름이_같으면_같은_화면():
    old = _doc(_screen("login", "로그인", elements=BASE))
    new = _doc(_screen("signin", "로그인", elements=BASE))
    assert diff_revisions(old, new) == []


def test_성공_조건을_다르게_옮겨_적었을_뿐이면_바뀐_것이_아니다():
    old = _doc(_screen(elements=BASE, success_condition='/inventory.html 로 이동하고 "Products" 문구를 노출한다.',
                       failure_conditions=['비어 있으면 "Required" 노출, 이동하지 않음']))
    new = _doc(_screen(elements=BASE, success_condition='/inventory.html 로 이동하고 "Products" 문구 노출',
                       failure_conditions=['비어 있으면 "Required" 노출']))
    assert diff_revisions(old, new) == []


def test_성공_조건의_문구나_경로가_바뀌면_바뀐_것이다():
    old = _doc(_screen(elements=BASE, success_condition='/home 로 이동하고 "환영합니다" 노출'))
    for changed in ('/main 로 이동하고 "환영합니다" 노출', '/home 로 이동하고 "반갑습니다" 노출'):
        new = _doc(_screen(elements=BASE, success_condition=changed))
        assert [c.kind for c in diff_revisions(old, new)] == ["screen_field"]


def test_선택_항목_변경():
    old = _doc(_screen(elements=[_el("cat", "분류", type="select", options=["A", "B"])]))
    new = _doc(_screen(elements=[_el("cat", "분류", type="select", options=["A", "C"])]))
    assert [c.text for c in diff_revisions(old, new)] == ["[로그인] '분류' 선택 항목: [A, B] → [A, C]"]


def _case(cid: str, screen: str = "login", target=None, steps=()) -> TestCase:
    return TestCase(case_id=cid, screen_id=screen, title=cid, type="negative" if target else "positive",
                    target_element=target, steps=list(steps),
                    expected=Expectation(type="error_shown"))


def test_바뀐_요소를_건드리는_케이스만_고른다():
    new = [_el("user_id", "아이디", required=True, placeholder="이메일 입력"), *BASE[1:]]
    changes = diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=new)))
    cases = [
        _case("login-placeholders-001", steps=[TestStep(seq=1, action="assert", expected=Expectation(
            type="placeholders_match", value="", labels=["아이디"]))]),
        _case("login-user_id-required-002", target="user_id"),
        _case("login-password-required-003", target="password",
              steps=[TestStep(seq=1, action="fill", target="비밀번호", value="")]),
        _case("join-valid-001", screen="join",
              steps=[TestStep(seq=1, action="fill", target="아이디", value="x")]),
    ]
    touched = touched_cases(cases, changes)
    assert set(touched) == {"login-placeholders-001", "login-user_id-required-002"}
    assert touched["login-user_id-required-002"] == ["[로그인] '아이디' 안내 문구: '아이디 입력' → '이메일 입력'"]


def test_라벨이_바뀌면_이전_라벨을_쓰던_케이스도_아닌_이번_라벨_케이스를_고른다():
    new = [*BASE[:2], _el("login_btn", "로그인하기", type="button")]
    changes = diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=new)))
    cases = [_case("login-valid-001",
                   steps=[TestStep(seq=1, action="click", target="로그인하기")])]
    assert set(touched_cases(cases, changes)) == {"login-valid-001"}


def test_안내_문구가_바뀌면_안내_문구_확인_케이스만():
    new = [_el("user_id", "아이디", required=True, placeholder="이메일 입력"), *BASE[1:]]
    changes = diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=new)))
    cases = [
        _case("login-valid-001", steps=[TestStep(seq=1, action="fill", target="아이디", value="a")]),
        _case("login-placeholders-001", steps=[TestStep(seq=1, action="assert", expected=Expectation(
            type="placeholders_match", labels=["아이디"]))]),
    ]
    assert set(touched_cases(cases, changes)) == {"login-placeholders-001"}


def test_규칙이_바뀌면_위반_케이스와_정상_케이스():
    new = [BASE[0], _el("password", "비밀번호", required=True, constraints={"min_length": 10}),
           BASE[2]]
    changes = diff_revisions(_doc(_screen(elements=BASE)), _doc(_screen(elements=new)))
    cases = [
        _case("login-valid-001", steps=[TestStep(seq=1, action="fill", target="비밀번호", value="a")]),
        _case("login-password-min-003", target="password"),
        _case("login-user_id-required-002", target="user_id",
              steps=[TestStep(seq=1, action="fill", target="비밀번호", value="a")]),
    ]
    assert set(touched_cases(cases, changes)) == {"login-valid-001", "login-password-min-003"}


def test_화면_수준_변경은_그_화면_케이스_전부():
    old = _doc(_screen(elements=BASE, success_condition="/home"))
    new = _doc(_screen(elements=BASE, success_condition="/main"))
    cases = [_case("login-valid-001"), _case("login-labels-001"), _case("x", screen="other")]
    assert set(touched_cases(cases, diff_revisions(old, new))) == {"login-valid-001",
                                                                   "login-labels-001"}


# --- 실행 경로 (build_plan · 리포트 · 엑셀 · CLI) ---

import pytest

from prova.llm.mock_backend import MockLLM
from prova.pipeline import build_plan

SPEC = "fixtures/specs/login_spec.pdf"


def _since_with_old_email_label(tmp_path):
    """login_spec 을 읽은 결과에서 '이메일' 라벨만 다른 '이전 판'."""
    first, _ = build_plan(SPEC, "http://x", MockLLM.with_login_fixtures(), run_dir=tmp_path)
    old = first.doc.model_copy(deep=True)
    email = next(e for e in old.screens[0].elements if e.label == "이메일")
    email.label = "아이디"
    old.source = "login_v1.pdf"
    return old


def test_이전_판을_주면_바뀐_것과_건드리는_케이스를_상태에_남긴다(tmp_path):
    since = _since_with_old_email_label(tmp_path)
    state, n_all = build_plan(SPEC, "http://x", MockLLM.with_login_fixtures(), run_dir=tmp_path,
                              since_doc=since)
    rev = state.revision
    assert rev["since"] == "login_v1.pdf"
    assert rev["changes"] == ["[로그인] '아이디' 라벨: '아이디' → '이메일'"]
    # 라벨은 그 칸을 찾는 모든 케이스가 기댄다 — 로그인 화면에서는 전부다.
    assert rev["touched"]
    assert len(state.cases) == n_all  # 표시만 하고 좁히지 않는다


def _since_with_old_placeholder(tmp_path):
    first, _ = build_plan(SPEC, "http://x", MockLLM.with_login_fixtures(), run_dir=tmp_path)
    old = first.doc.model_copy(deep=True)
    email = next(e for e in old.screens[0].elements if e.label == "이메일")
    email.placeholder = "옛 안내 문구"
    return old


def test_바뀐_것만_실행하면_건드리는_케이스로_좁힌다(tmp_path):
    since = _since_with_old_placeholder(tmp_path)
    state, n_all = build_plan(SPEC, "http://x", MockLLM.with_login_fixtures(), run_dir=tmp_path,
                              since_doc=since, changed_only=True)
    assert {c.case_id for c in state.cases} == set(state.revision["touched"])
    assert 0 < len(state.cases) < n_all
    assert state.revision["changed_only"] is True
    assert state.revision["cases_available"] == n_all


def test_바뀐_것이_없는데_바뀐_것만_실행하라면_멈춘다(tmp_path):
    same, _ = build_plan(SPEC, "http://x", MockLLM.with_login_fixtures(), run_dir=tmp_path)
    with pytest.raises(ValueError, match="건드리는 케이스가 없습니다"):
        build_plan(SPEC, "http://x", MockLLM.with_login_fixtures(), run_dir=tmp_path,
                   since_doc=same.doc, changed_only=True)


def _report_with_revision():
    from prova.models import TestReport, Verdict

    v = [Verdict(case_id="login-valid-001", title="정상", verdict="PASS", screen_id="login"),
         Verdict(case_id="login-pw-002", title="비번", verdict="PASS", screen_id="login")]
    s = TestReport.summarize(v)
    s["revision"] = {"since": "login_v1.pdf", "changes": ["[로그인] '아이디' 라벨: '아이디' → '이메일'"],
                     "touched": {"login-valid-001": ["[로그인] '아이디' 라벨: '아이디' → '이메일'"]},
                     "changed_only": False, "cases_available": 2}
    return TestReport(run_id="r", target_url="http://x", spec_source="login_v2.pdf", summary=s,
                      cases=v, created_at="2026-11-09T00:00:00+09:00")


def test_리포트가_바뀐_것을_보이고_건드리는_케이스에_표시한다():
    from prova.s6_report.report_builder import render_html

    html = render_html(_report_with_revision())
    assert "이전 판" in html and "login_v1.pdf" in html
    assert "[로그인] &#x27;아이디&#x27; 라벨" in html or "[로그인] '아이디' 라벨" in html
    assert html.count("class='tag revised'") == 1


def test_엑셀_케이스_시트에_개정_칸이_있다(tmp_path):
    from openpyxl import load_workbook

    from prova.s6_report.xlsx_export import save_xlsx

    wb = load_workbook(save_xlsx(_report_with_revision(), tmp_path))
    rows = list(wb["케이스"].iter_rows(values_only=True))
    col = rows[0].index("개정")
    assert "아이디" in rows[1][col] and rows[2][col] in (None, "")
    summary = " ".join(str(c) for r in wb["요약"].iter_rows(values_only=True) for c in r if c)
    assert "login_v1.pdf" in summary and "바뀐 것" in summary


def test_CLI_changed_only_는_since_없이_쓸_수_없다():
    from typer.testing import CliRunner

    from prova.cli import app

    result = CliRunner().invoke(app, ["run", "--pdf", SPEC, "--url", "http://x",
                                      "--backend", "mock", "--changed-only"])
    assert result.exit_code != 0
    assert "--since" in result.output


def test_CLI_diff_spec_은_바뀐_것을_찍는다():
    from typer.testing import CliRunner

    from prova.cli import app

    same = CliRunner().invoke(app, ["diff-spec", "--old", SPEC, "--new", SPEC, "--backend", "mock"])
    assert same.exit_code == 0, same.output
    assert "바뀐 것이 없습니다" in same.output


def test_끝까지_바뀐_것만_실행하고_리포트와_엑셀에_남긴다(sut_base, tmp_path):
    """SUT 를 상대로 실제 브라우저 실행 — 바뀐 것만 돌고, 산출물 셋이 같은 사실을 말한다."""
    import json

    from openpyxl import load_workbook

    from prova.pipeline import run_pipeline

    since = _since_with_old_placeholder(tmp_path / "plan")
    report, run_dir = run_pipeline(
        pdf_path=SPEC, base_url=f"{sut_base}/good", llm=MockLLM.with_login_fixtures(),
        run_id="rev", runs_root=tmp_path, since_doc=since, changed_only=True)
    rev = report.summary["revision"]
    assert rev["changed_only"] and rev["changes"]
    assert {v.case_id for v in report.cases} == set(rev["touched"])
    assert json.loads((run_dir / "report.json").read_text(encoding="utf-8"))["summary"]["revision"]
    assert "이전 판 기획서와 비교" in (run_dir / "report.html").read_text(encoding="utf-8")
    rows = list(load_workbook(run_dir / "report.xlsx")["케이스"].iter_rows(values_only=True))
    col = rows[0].index("개정")
    assert all(r[col] for r in rows[1:])
