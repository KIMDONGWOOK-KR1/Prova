"""Figma 응답 -> SpecDocument 조립 (specs/2026-08-25).

경로(url_path)는 Figma 가 말하지 않는다 — 사용자가 준 매핑(screen_urls)만
쓰고, 매핑 없는 화면은 문서 경고로 남긴다(해석 실패는 더 많이 알리는 쪽으로).

합성 트리 빌더는 test_figma_parser.py 와 같은 6줄을 다시 둔다 — 테스트 파일
사이의 import 결합보다 중복이 싸다.
"""

import json

from prova.s1_figma.extractor import extract_figma_document


def text(node_id, layer_name, chars):
    return {"id": node_id, "type": "TEXT", "name": layer_name, "characters": chars}


def instance(node_id, component_id, children, name="inst", **extra):
    return {"id": node_id, "type": "INSTANCE", "componentId": component_id,
            "name": name, "children": children, **extra}


def frame(node_id, name, children):
    return {"id": node_id, "type": "FRAME", "name": name, "children": children}


def figma_file(frames, components):
    return {
        "name": "prova-fixture",
        "document": {"id": "0:0", "type": "DOCUMENT", "children": [
            {"id": "0:1", "type": "CANVAS", "name": "Page 1", "children": frames},
        ]},
        "components": components,
    }


COMPONENTS = {"9:1": {"name": "Input"}, "9:2": {"name": "Button"}}

LOGIN = frame("1:2", "로그인", [
    instance("1:3", "9:1", [text("1:4", "label", "이메일"),
                            text("1:5", "placeholder", "이메일을 입력하세요")]),
    instance("1:6", "9:1", [text("1:7", "label", "비밀번호"),
                            text("1:8", "placeholder", "비밀번호를 입력하세요")]),
    instance("1:9", "9:2", [text("1:10", "text", "로그인")]),
])


def write_fixture(tmp_path, raw) -> str:
    p = tmp_path / "figma.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return str(p)


class TestExtract:
    def test_프레임이_figma_출처_화면이_된다(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        doc = extract_figma_document(path, {"로그인": "/login"})
        screen = doc.screens[0]
        assert (screen.screen_id, screen.screen_name) == ("로그인", "로그인")
        assert screen.source_kind == "figma"
        assert screen.url_path == "/login"

    def test_요소가_옮겨진다(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        screen = extract_figma_document(path, {"로그인": "/login"}).screens[0]
        assert [(e.element_id, e.type, e.label) for e in screen.elements] == [
            ("n1_3", "input", "이메일"), ("n1_6", "input", "비밀번호"),
            ("n1_9", "button", "로그인"),
        ]
        assert screen.elements[0].placeholder == "이메일을 입력하세요"

    def test_규칙_필드는_전부_빈다(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        screen = extract_figma_document(path, {"로그인": "/login"}).screens[0]
        assert screen.success_condition == ""
        assert all(not e.constraints for e in screen.elements)
        assert screen.precondition is None and screen.seed_rows == []

    def test_매핑_없는_화면은_경로_없이_문서_경고(self, tmp_path):
        path = write_fixture(tmp_path, figma_file([LOGIN], COMPONENTS))
        doc = extract_figma_document(path, {})
        assert doc.screens[0].url_path == ""
        assert any("경로" in w for w in doc.warnings)

    def test_프레임_경고가_화면_경고로_남는다(self, tmp_path):
        fake = {"id": "6:1", "type": "FRAME", "name": "가짜 입력란",
                "children": [text("6:2", "text", "여기에 입력")]}
        path = write_fixture(
            tmp_path, figma_file([frame("6:0", "로그인", [fake])], COMPONENTS))
        doc = extract_figma_document(path, {"로그인": "/login"})
        assert any("컴포넌트가 아니" in w for w in doc.screens[0].warnings)


class TestFlows:
    def _two_screens(self, tmp_path):
        signup_btn = instance("2:9", "9:2", [text("2:10", "text", "가입하기")],
                              transitionNodeId="1:2")
        signup = frame("2:1", "회원가입", [signup_btn])
        return write_fixture(tmp_path, figma_file([LOGIN, signup], COMPONENTS))

    def test_prototype_연결이_흐름이_된다(self, tmp_path):
        doc = extract_figma_document(
            self._two_screens(tmp_path), {"로그인": "/login", "회원가입": "/signup"})
        assert [f.screen_ids for f in doc.flows] == [["회원가입", "로그인"]]

    def test_누르는_요소가_추출됐으면_via_로_남는다(self, tmp_path):
        doc = extract_figma_document(
            self._two_screens(tmp_path), {"로그인": "/login", "회원가입": "/signup"})
        assert doc.flows[0].via == ["가입하기"]

    def test_알_수_없는_프레임으로의_연결은_경고(self, tmp_path):
        btn = instance("3:9", "9:2", [text("3:10", "text", "이동")],
                       transitionNodeId="99:99")
        path = write_fixture(
            tmp_path, figma_file([frame("3:0", "홈", [btn])], COMPONENTS))
        doc = extract_figma_document(path, {"홈": "/"})
        assert doc.flows == []
        assert any("연결" in w for w in doc.warnings)


class TestRealFixture:
    """실물 Figma 응답 대조 — 합성과 실물이 어긋나면 실물이 이긴다.

    실제로 한 번 이겼다: 실물은 prototype 연결을 legacy transitionNodeId 가
    아니라 interactions 배열로 줬고, 첫 구현은 흐름 0개를 냈다
    (figma_parser._transition_targets).
    """

    URLS = {"로그인": "/login", "회원가입": "/signup"}

    def _doc(self):
        import pytest
        from pathlib import Path
        fixture = Path("fixtures/figma/login_signup.json")
        if not fixture.exists():
            pytest.skip("실물 픽스처 없음 — scripts/fetch_figma.py 를 먼저 실행")
        return extract_figma_document(fixture, dict(self.URLS))

    def test_실물_응답이_골든과_같다(self):
        import json
        from pathlib import Path
        doc = self._doc()
        golden = json.loads(Path("fixtures/figma/login_signup.golden.json")
                            .read_text(encoding="utf-8"))
        assert json.loads(doc.model_dump_json()) == golden

    def test_의도적_함정이_경고로_남았다(self):
        doc = self._doc()
        login = doc.screen_by_id("로그인")
        assert any("컴포넌트가 아니" in w for w in login.warnings)

    def test_실물_흐름이_via_와_함께_추출됐다(self):
        doc = self._doc()
        assert [(f.screen_ids, f.via) for f in doc.flows] == \
            [(["회원가입", "로그인"], ["가입하기"])]
