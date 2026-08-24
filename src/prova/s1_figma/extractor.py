"""Figma 응답 -> SpecDocument. PDF 경로와 같은 계약, LLM 없음 (specs/2026-08-25).

경로(url_path)는 Figma 가 말하지 않는다 — 사용자가 준 매핑(screen_urls)만
쓰고, 매핑 없는 화면은 문서 경고로 남긴다. 흐름은 prototype 연결에서 추출하되,
누르는 요소가 추출된 요소면 그 라벨을 via 로 채워 '요소를 눌러 옮기는' 검증이
2단계에서 가능하게 남겨 둔다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.s1_figma.figma_parser import parse_figma_file


def _slug(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip()).lower()


def _node_slug(node_id: str) -> str:
    """Figma 노드 id("1:3") -> element_id("n1_3"). 사람이 지은 id 가 없으므로
    노드 정체성을 그대로 쓴다 — 억측한 영문명을 만들지 않는다."""
    return "n" + re.sub(r"[^0-9]+", "_", node_id)


def extract_figma_document(
    json_path: str | Path, screen_urls: dict[str, str]
) -> SpecDocument:
    raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
    frames, doc_warnings = parse_figma_file(raw)

    doc = SpecDocument(source=str(json_path), warnings=doc_warnings)
    frame_id_to_screen: dict[str, str] = {}
    for f in frames:
        screen_id = _slug(f.name)
        frame_id_to_screen[f.node_id] = screen_id
        url = screen_urls.get(screen_id, "")
        if not url:
            doc.warnings.append(
                f"화면 {f.name!r} 의 경로 매핑이 없어 실행하지 않습니다 — "
                "--screen-url 로 화면↔경로를 지정하세요. Figma 에는 경로가 "
                "없으므로 추측하지 않습니다."
            )
        doc.screens.append(ScreenSpec(
            screen_id=screen_id,
            screen_name=f.name,
            url_path=url,
            source_kind="figma",
            elements=[UIElement(
                element_id=_node_slug(e.node_id), type=e.type, label=e.label,
                placeholder=e.placeholder, options=e.options,
            ) for e in f.elements],
            warnings=list(f.warnings),
        ))

    for f in frames:
        labels_by_node = {e.node_id: e.label for e in f.elements}
        for src_node, dst_frame in f.transitions:
            dst = frame_id_to_screen.get(dst_frame)
            if dst is None:
                doc.warnings.append(
                    f"화면 {f.name!r} 의 prototype 연결이 알 수 없는 프레임"
                    f"({dst_frame})을 가리켜 흐름으로 추출하지 않았습니다."
                )
                continue
            src = frame_id_to_screen[f.node_id]
            via_label = labels_by_node.get(src_node)
            doc.flows.append(Flow(
                flow_id=f"{src}_to_{dst}",
                title=f"{f.name} → {dst}",
                screen_ids=[src, dst],
                # 누르는 요소가 추출된 요소면 그 라벨로 옮긴다 — 주소로 직접
                # 이동하면 화면을 잇는 요소 자체가 검증되지 않는다(Flow.via).
                via=[via_label] if via_label else [],
            ))
    return doc
