"""Figma 응답 파서 — 구조에 적힌 사실만 결정적으로 읽는다 (specs/2026-08-25).

옛 브랜치는 노드 이름에 'button/입력' 이 들어가면 요소로 주웠고, 튜토리얼
파일의 본문 문장까지 버튼이 됐다. 여기서는 INSTANCE 의 원본 컴포넌트 이름만
믿는다 — 컴포넌트가 아닌 노드는 유형을 알 수 없으므로 줍지 않고 경고한다.
"""

from prova.s1_figma.figma_parser import parse_figma_file, trim_figma_response


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


COMPONENTS = {"9:1": {"name": "Input"}, "9:2": {"name": "Button"},
              "9:3": {"name": "Checkbox"}, "9:4": {"name": "Select"}}

LOGIN = frame("1:2", "로그인", [
    instance("1:3", "9:1", [text("1:4", "label", "이메일"),
                            text("1:5", "placeholder", "이메일을 입력하세요")]),
    instance("1:6", "9:1", [text("1:7", "label", "비밀번호"),
                            text("1:8", "placeholder", "비밀번호를 입력하세요")]),
    instance("1:9", "9:2", [text("1:10", "text", "로그인")],
             transitionNodeId="2:1"),
])


class TestFrames:
    def test_최상위_프레임이_화면이다(self):
        frames, warnings = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        assert [f.name for f in frames] == ["로그인"]
        assert warnings == []

    def test_프레임_이름이_겹치면_경고하고_뒤_프레임을_버린다(self):
        dup = frame("3:1", "로그인", [])
        frames, warnings = parse_figma_file(figma_file([LOGIN, dup], COMPONENTS))
        assert len(frames) == 1
        assert any("겹" in w for w in warnings)


class TestElements:
    def test_컴포넌트_이름으로_유형을_판정한다(self):
        frames, _ = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        got = [(e.type, e.label) for e in frames[0].elements]
        assert got == [("input", "이메일"), ("input", "비밀번호"), ("button", "로그인")]

    def test_element_id_는_노드_id_다(self):
        frames, _ = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        assert frames[0].elements[0].node_id == "1:3"

    def test_placeholder_는_레이어_이름으로_찾는다(self):
        frames, _ = parse_figma_file(figma_file([LOGIN], COMPONENTS))
        assert frames[0].elements[0].placeholder == "이메일을 입력하세요"
        assert frames[0].elements[2].placeholder is None

    def test_select_의_option_레이어들이_순서대로_options_다(self):
        sel = instance("4:1", "9:4", [
            text("4:2", "label", "가입 경로"),
            text("4:3", "option", "검색"), text("4:4", "option", "지인 추천"),
        ])
        frames, _ = parse_figma_file(figma_file([frame("4:0", "s", [sel])], COMPONENTS))
        e = frames[0].elements[0]
        assert (e.type, e.label, e.options) == ("select", "가입 경로", ["검색", "지인 추천"])

    def test_체크박스는_첫_텍스트가_라벨이다(self):
        cb = instance("5:1", "9:3", [text("5:2", "text", "약관에 동의합니다")])
        frames, _ = parse_figma_file(figma_file([frame("5:0", "s", [cb])], COMPONENTS))
        assert (frames[0].elements[0].type, frames[0].elements[0].label) == \
            ("checkbox", "약관에 동의합니다")


class TestWarnings:
    def test_컴포넌트가_아닌_요소형_노드는_줍지_않고_경고한다(self):
        fake = {"id": "6:1", "type": "FRAME", "name": "가짜 입력란",
                "children": [text("6:2", "text", "여기에 입력")]}
        frames, _ = parse_figma_file(
            figma_file([frame("6:0", "s", [fake])], COMPONENTS))
        assert frames[0].elements == []
        assert any("컴포넌트가 아니" in w for w in frames[0].warnings)

    def test_모르는_컴포넌트_이름은_경고한다(self):
        card = instance("7:1", "9:9", [text("7:2", "text", "x")])
        frames, _ = parse_figma_file(
            figma_file([frame("7:0", "s", [card])], {"9:9": {"name": "Card"}}))
        assert frames[0].elements == []
        assert any("Card" in w for w in frames[0].warnings)

    def test_라벨_없는_Input_은_제외하고_경고한다(self):
        no_label = instance("8:1", "9:1", [text("8:2", "placeholder", "값")])
        frames, _ = parse_figma_file(
            figma_file([frame("8:0", "s", [no_label])], COMPONENTS))
        assert frames[0].elements == []
        assert any("라벨" in w for w in frames[0].warnings)


class TestTransitions:
    def test_legacy_transitionNodeId_를_추출한다(self):
        frames, _ = parse_figma_file(
            figma_file([LOGIN, frame("2:1", "회원가입", [])], COMPONENTS))
        assert frames[0].transitions == [("1:9", "2:1")]

    def test_실물_API_의_interactions_배열을_추출한다(self):
        """실물 응답(2026-08-25 fetch)은 transitionNodeId 가 아니라 interactions
        로 연결을 준다 — 실물이 이긴다."""
        btn = instance("3:9", "9:2", [text("3:10", "text", "이동")],
                       interactions=[{
                           "trigger": {"type": "ON_CLICK"},
                           "actions": [{"type": "NODE", "destinationId": "1:2",
                                        "navigation": "NAVIGATE",
                                        "transition": None}],
                       }])
        frames, _ = parse_figma_file(
            figma_file([frame("3:0", "홈", [btn]), LOGIN], COMPONENTS))
        assert frames[0].transitions == [("3:9", "1:2")]

    def test_같은_연결이_두_표기로_와도_한_번만_센다(self):
        btn = instance("4:9", "9:2", [text("4:10", "text", "이동")],
                       transitionNodeId="1:2",
                       interactions=[{
                           "trigger": {"type": "ON_CLICK"},
                           "actions": [{"type": "NODE", "destinationId": "1:2",
                                        "navigation": "NAVIGATE"}],
                       }])
        frames, _ = parse_figma_file(
            figma_file([frame("4:0", "홈", [btn]), LOGIN], COMPONENTS))
        assert frames[0].transitions == [("4:9", "1:2")]

    def test_NAVIGATE_가_아닌_액션은_무시한다(self):
        btn = instance("5:9", "9:2", [text("5:10", "text", "열기")],
                       interactions=[{
                           "trigger": {"type": "ON_CLICK"},
                           "actions": [{"type": "URL", "url": "https://x"}],
                       }])
        frames, _ = parse_figma_file(
            figma_file([frame("5:0", "홈", [btn])], COMPONENTS))
        assert frames[0].transitions == []


class TestTrim:
    def test_필요한_키만_남긴다(self):
        raw = figma_file([LOGIN], COMPONENTS)
        raw["styles"] = {"big": "junk"}
        raw["document"]["children"][0]["children"][0]["children"][0]["fills"] = [{"r": 1}]
        trimmed = trim_figma_response(raw)
        assert "styles" not in trimmed
        node = trimmed["document"]["children"][0]["children"][0]["children"][0]
        assert "fills" not in node

    def test_interactions_는_비어있지_않을_때만_남긴다(self):
        """실물 응답은 모든 노드에 interactions:[] 를 달고 온다 — 빈 배열까지
        남기면 픽스처가 소음으로 부푼다. 연결이 있는 것만 남긴다."""
        btn = instance("3:9", "9:2", [text("3:10", "text", "이동")],
                       interactions=[{
                           "trigger": {"type": "ON_CLICK"},
                           "actions": [{"type": "NODE", "destinationId": "1:2",
                                        "navigation": "NAVIGATE"}],
                       }])
        empty = instance("3:11", "9:1",
                         [text("3:12", "label", "이메일")], interactions=[])
        raw = figma_file([frame("3:0", "홈", [btn, empty])], COMPONENTS)
        trimmed = trim_figma_response(raw)
        home = trimmed["document"]["children"][0]["children"][0]
        assert "interactions" in home["children"][0]
        assert "interactions" not in home["children"][1]
        assert parse_figma_file(trimmed)[0][0].transitions == \
            parse_figma_file(raw)[0][0].transitions
        # 다듬어도 파싱 결과는 같아야 한다 — 다듬기가 사실을 지우면 안 된다
        assert parse_figma_file(trimmed)[0][0].elements == \
            parse_figma_file(raw)[0][0].elements
