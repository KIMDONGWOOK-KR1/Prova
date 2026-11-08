"""사람이 고친 추출 결과 — 계획 화면에서 S1 이 읽은 것을 고쳐 실행한다 (2026-11-08).

## 왜 있는가

실물 기획서에서 S1 은 45개 중 37개(82.2%)를 맞게 읽었다. 남은 것을 모델로 메우려던
시도(다수결·그림 이미지 읽기)는 성능을 올리지 못했다. 대신 실행 전에 "기획서에서 이렇게
읽었습니다" 를 보여 주고 틀린 칸만 사람이 고치게 한다. 기획서를 아는 사람에게는 몇 분이고,
틀린 추출이 '없는 결함' 으로 보고되는 길을 실행 전에 막는다.

## 계약

- 고친 문서로 S2 부터 다시 돈다. 기획서를 다시 읽지 않는다 — 다시 읽으면 고친 것이 사라진다.
- **무엇을 고쳤는지 리포트가 말한다.** 판정의 근거 일부가 기획서가 아니라 사람이 적은 값이기
  때문이다. 원래 추출과 비교한 목록을 summary["spec_edits"] 로 남긴다.
"""

from __future__ import annotations

from prova.models import SpecDocument, UIElement

#: 계획 화면에서 고칠 수 있는 칸. 화면이 보여 주는 것도 이 목록이다.
ELEMENT_FIELDS = {
    "label": "라벨",
    "required": "필수",
    "placeholder": "안내 문구",
    "error_message": "오류 문구",
    "required_message": "빈 칸 문구",
    "options": "선택 항목",
}
SCREEN_FIELDS = {
    "url_path": "경로",
    "success_condition": "성공 조건",
    "required_message": "필수 공통 문구",
}


def _show(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    return repr(value or "")


def _element_name(e: UIElement) -> str:
    return f"'{e.label}'" if e.label else e.element_id


def diff_docs(original: SpecDocument, edited: SpecDocument) -> list[str]:
    """원래 추출과 고친 문서의 차이를 사람이 읽는 줄로. 같으면 빈 목록."""
    lines: list[str] = []
    before = {s.screen_id: s for s in original.screens}
    for screen in edited.screens:
        old = before.get(screen.screen_id)
        where = f"[{screen.screen_name}]"
        if old is None:
            lines.append(f"{where} 화면을 더함")
            continue
        for field, name in SCREEN_FIELDS.items():
            a, b = getattr(old, field), getattr(screen, field)
            if (a or None) != (b or None):
                lines.append(f"{where} {name}: {_show(a)} → {_show(b)}")
        old_elements = {e.element_id: e for e in old.elements}
        new_ids = {e.element_id for e in screen.elements}
        for e in screen.elements:
            prev = old_elements.get(e.element_id)
            if prev is None:
                lines.append(f"{where} 요소 {_element_name(e)} 을 더함")
                continue
            for field, name in ELEMENT_FIELDS.items():
                a, b = getattr(prev, field), getattr(e, field)
                if (a or None) != (b or None):
                    lines.append(f"{where} {_element_name(prev)} {name}: {_show(a)} → {_show(b)}")
        for element_id, prev in old_elements.items():
            if element_id not in new_ids:
                lines.append(f"{where} 요소 {_element_name(prev)} 을 뺌")
    edited_ids = {s.screen_id for s in edited.screens}
    for screen_id, old in before.items():
        if screen_id not in edited_ids:
            lines.append(f"[{old.screen_name}] 화면을 뺌")
    return lines


def settle(doc: SpecDocument) -> SpecDocument:
    """고친 뒤 낡은 경고를 정리한다 — 사람이 경로를 채웠으면 '경로가 없다' 경고는 거짓이다."""
    from prova.s1_spec_extractor.extractor import NO_PATH_WARNING

    for screen in doc.screens:
        if screen.url_path:
            screen.warnings = [w for w in screen.warnings if not w.startswith(NO_PATH_WARNING)]
    return doc
