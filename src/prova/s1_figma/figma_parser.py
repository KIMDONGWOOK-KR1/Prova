"""Figma REST 응답 읽기 — 구조에 적힌 사실만, 결정적으로 (specs/2026-08-25).

## 왜 컴포넌트 이름만 믿는가

폐기된 첫 시도는 노드 이름에 'button/입력' 이 들어가면 요소로 주웠다. Figma
튜토리얼 파일에서 본문 문장 프레임까지 버튼이 됐다 — 이름은 디자이너의 자유
텍스트라서 유형의 근거가 못 된다. INSTANCE 노드의 componentId 가 가리키는
원본 컴포넌트 이름은 디자인 시스템의 구조라 근거가 된다. 컴포넌트가 아닌
노드는 유형을 알 수 없으므로 줍지 않고 경고한다 — 억측하지 않는다.

## LLM 을 부르지 않는 이유

PDF 는 자연어라 구조화에 모델이 필요했다. Figma 응답은 이미 트리다 — 여기서
모델을 부르면 검증 가능한 사실을 검증 불가능한 추측으로 바꾸는 셈이 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from prova.text_utils import normalize_ws

#: 컴포넌트 이름 -> models.ElementType. 정확 일치(공백 정규화만).
#: 여기 없는 이름은 매핑하지 않는다 — pdf_parser.ELEMENT_TYPE_WORDS 와 같은 원칙.
COMPONENT_TYPES: dict[str, str] = {
    "Input": "input",
    "Button": "button",
    "Checkbox": "checkbox",
    "Select": "select",
    "List": "list",
}

#: 요소로 착각하기 쉬운 컨테이너 노드 유형 — 컴포넌트가 아니면서 자식에
#: TEXT 를 가진 이런 노드는 '유형 미상' 경고 대상이다.
_CONTAINER_TYPES = frozenset({"FRAME", "GROUP", "RECTANGLE", "COMPONENT"})


@dataclass
class FigmaElement:
    node_id: str
    type: str
    label: str
    placeholder: Optional[str] = None
    options: list[str] = field(default_factory=list)


@dataclass
class FigmaFrame:
    node_id: str
    name: str
    elements: list[FigmaElement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    transitions: list[tuple[str, str]] = field(default_factory=list)


def parse_figma_file(raw: dict) -> tuple[list[FigmaFrame], list[str]]:
    """응답 전체 -> (최상위 프레임들, 문서 수준 경고)."""
    components = {
        cid: normalize_ws(c.get("name", ""))
        for cid, c in (raw.get("components") or {}).items()
    }
    warnings: list[str] = []
    frames: list[FigmaFrame] = []
    seen: set[str] = set()
    for page in (raw.get("document") or {}).get("children", []):
        for node in page.get("children", []):
            if node.get("type") != "FRAME":
                continue
            name = normalize_ws(node.get("name", ""))
            if name in seen:
                warnings.append(
                    f"최상위 프레임 이름 {name!r} 이 겹쳐 뒤의 것을 무시했습니다 — "
                    "화면 이름은 화면의 정체성이라 겹치면 어느 쪽인지 정할 수 없습니다."
                )
                continue
            seen.add(name)
            frames.append(_parse_frame(node, components))
    return frames, warnings


def _parse_frame(node: dict, components: dict[str, str]) -> FigmaFrame:
    f = FigmaFrame(node_id=node["id"], name=normalize_ws(node.get("name", "")))
    _walk(node, f, components)
    # 같은 연결이 legacy 표기(transitionNodeId)와 interactions 양쪽으로 오면
    # 한 번만 센다 — 순서는 유지한다.
    f.transitions = list(dict.fromkeys(f.transitions))
    return f


def _walk(node: dict, f: FigmaFrame, components: dict[str, str]) -> None:
    for child in node.get("children", []):
        if child.get("type") == "INSTANCE":
            _parse_instance(child, f, components)
        else:
            if _looks_like_element(child):
                f.warnings.append(
                    f"{child.get('name', '?')!r} 은 컴포넌트가 아니라 유형을 알 수 "
                    "없어 요소로 줍지 않았습니다 — 디자인을 컴포넌트 인스턴스로 "
                    "그려야 추출됩니다."
                )
            _walk(child, f, components)
        for dst in _transition_targets(child):
            f.transitions.append((child["id"], dst))


def _transition_targets(node: dict) -> list[str]:
    """이 노드가 가리키는 prototype 이동 대상 프레임 id 들.

    실물 API(2026-08-25 fetch)는 연결을 `interactions` 배열로 준다 — 문서의
    legacy 표기(`transitionNodeId`)만 보던 첫 구현이 실물에서 흐름 0개를 냈다.
    실물이 이기므로 양쪽을 다 읽되, 화면 이동(NODE + NAVIGATE)만 센다 —
    URL 열기·오버레이 등은 화면 흐름이 아니다.
    """
    targets: list[str] = []
    if node.get("transitionNodeId"):
        targets.append(node["transitionNodeId"])
    for interaction in node.get("interactions") or []:
        for action in interaction.get("actions") or []:
            if (action.get("type") == "NODE"
                    and action.get("navigation") == "NAVIGATE"
                    and action.get("destinationId")):
                targets.append(action["destinationId"])
    return targets


def _looks_like_element(node: dict) -> bool:
    """컨테이너 안에 TEXT 를 직접 가진, 요소처럼 보이는 비컴포넌트 노드."""
    if node.get("type") not in _CONTAINER_TYPES:
        return False
    return any(c.get("type") == "TEXT" for c in node.get("children", []))


def _parse_instance(node: dict, f: FigmaFrame, components: dict[str, str]) -> None:
    comp_name = components.get(node.get("componentId", ""), "")
    el_type = COMPONENT_TYPES.get(comp_name)
    if el_type is None:
        f.warnings.append(
            f"컴포넌트 {comp_name or '?'!r} 은 아는 유형이 아니라 요소로 줍지 "
            f"않았습니다 (노드 {node['id']})."
        )
        return
    texts = [(normalize_ws(c.get("name", "")), c.get("characters", "").strip())
             for c in node.get("children", []) if c.get("type") == "TEXT"]
    by_layer: dict[str, str] = {}
    for layer, chars in texts:
        by_layer.setdefault(layer, chars)

    if el_type in ("input", "select"):
        # 입력·셀렉트는 안내 문구(placeholder)·항목(option) 텍스트가 함께 있어
        # '첫 텍스트' 로는 라벨을 특정할 수 없다 — 레이어 이름 'label' 만 믿는다.
        label = by_layer.get("label", "")
    else:
        label = texts[0][1] if texts else ""
    if not label:
        f.warnings.append(
            f"{comp_name} 인스턴스(노드 {node['id']})에 라벨 텍스트가 없어 "
            "요소로 줍지 않았습니다 — 라벨 없는 요소는 화면에서 지목할 수 없습니다."
        )
        return

    f.elements.append(FigmaElement(
        node_id=node["id"],
        type=el_type,
        label=label,
        placeholder=by_layer.get("placeholder") or None,
        options=[chars for layer, chars in texts if layer == "option"],
    ))


_NODE_KEEP = ("id", "name", "type", "characters", "componentId", "transitionNodeId")


def trim_figma_response(raw: dict) -> dict:
    """저장할 응답에서 필요한 키만 남긴다.

    원본은 65k 줄이 넘어 픽스처로 읽을 수 없다. 다듬기는 손이 아니라 이 함수가
    한다 — 손으로 만지면 '실물 API 응답' 이라는 증거가 사라진다. 다듬은 결과의
    파싱이 원본과 같음을 테스트가 지킨다.
    """
    def trim_node(node: dict) -> dict:
        out = {k: node[k] for k in _NODE_KEEP if k in node}
        # 실물 응답은 모든 노드에 interactions:[] 를 달고 온다 — 연결이 있는
        # 것만 남긴다. 빈 배열까지 남기면 픽스처가 소음으로 부푼다.
        if node.get("interactions"):
            out["interactions"] = node["interactions"]
        if "children" in node:
            out["children"] = [trim_node(c) for c in node["children"]]
        return out

    return {
        "name": raw.get("name", ""),
        "document": trim_node(raw.get("document") or {}),
        "components": {
            cid: {"name": c.get("name", "")}
            for cid, c in (raw.get("components") or {}).items()
        },
    }
