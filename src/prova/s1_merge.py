"""기획서 + Figma 병합 — 어긋남은 판정이 아니라 발견이다 (specs/2026-08-25 2단계).

순수 함수, LLM 없음. 화면은 screen_name(정규화), 요소는 라벨 정확 일치로
짝짓는다. 겹치는 정보가 어긋나면 그 항목을 검증에서 빼고 발견으로 보고한다 —
틀린 근거로 판정하는 것보다 입력끼리의 모순을 사람에게 보이는 것이 먼저다.
발견은 경고(spec_warnings)가 아니라 별도 채널이다: 경고는 '추출이 덜 됐다',
발견은 '입력이 서로 모순이다' — 성격이 다른 사실을 한 목록에 섞으면 둘 다
묻힌다(coverage 모듈과 같은 원리).
"""

from __future__ import annotations

from prova.models import Flow, ScreenSpec, SpecDocument, UIElement
from prova.text_utils import loosen, normalize_ws


def merge_documents(
    pdf_doc: SpecDocument, figma_doc: SpecDocument
) -> tuple[SpecDocument, list[str]]:
    findings: list[str] = []
    merged = SpecDocument(
        source=f"{pdf_doc.source} + {figma_doc.source}",
        warnings=list(pdf_doc.warnings) + list(figma_doc.warnings),
    )
    figma_by_name = {normalize_ws(s.screen_name): s for s in figma_doc.screens}
    matched_names: set[str] = set()

    for pdf_screen in pdf_doc.screens:
        name = normalize_ws(pdf_screen.screen_name)
        figma_screen = figma_by_name.get(name)
        if figma_screen is None:
            findings.append(
                f"화면 {pdf_screen.screen_name!r} 이 디자인에 없습니다 — "
                "기획서 단독으로 검증합니다."
            )
            merged.screens.append(pdf_screen.model_copy(deep=True))
            continue
        matched_names.add(name)
        merged.screens.append(
            _merge_screen(pdf_screen, figma_screen, findings))

    for figma_screen in figma_doc.screens:
        if normalize_ws(figma_screen.screen_name) in matched_names:
            continue
        findings.append(
            f"화면 {figma_screen.screen_name!r} 이 기획서에 없습니다 — "
            "디자인 단독(정적 대조)으로 검증합니다."
        )
        merged.screens.append(figma_screen.model_copy(deep=True))

    _merge_flows(merged, pdf_doc, figma_doc, findings)
    return merged, findings


def _merge_screen(
    pdf_screen: ScreenSpec, figma_screen: ScreenSpec, findings: list[str]
) -> ScreenSpec:
    screen = pdf_screen.model_copy(deep=True)  # 규칙·성공조건·계정·시드·경로 유지
    figma_by_label = {e.label: e for e in figma_screen.elements}
    matched_labels: set[str] = set()

    for element in screen.elements:
        figma_el = figma_by_label.get(element.label)
        if figma_el is None:
            findings.append(
                f"{screen.screen_name} 화면의 요소 {element.label!r} 가 "
                "디자인에 없습니다."
            )
            continue
        matched_labels.add(element.label)
        _compare_element(screen.screen_name, element, figma_el, findings)

    for figma_el in figma_screen.elements:
        if figma_el.label in matched_labels:
            continue
        findings.append(
            f"{screen.screen_name} 화면의 요소 {figma_el.label!r} 는 "
            "기획서에 없습니다 — 디자인 기준으로 정적 대조에 넣습니다."
        )
        screen.elements.append(figma_el.model_copy(deep=True))
    return screen


def _compare_element(
    screen_name: str, pdf_el: UIElement, figma_el: UIElement, findings: list[str]
) -> None:
    if pdf_el.type != figma_el.type:
        findings.append(
            f"{screen_name} 화면 {pdf_el.label!r} 의 유형이 다릅니다: "
            f"기획서 {pdf_el.type} / 디자인 {figma_el.type} — 기획서 유형으로 "
            "검증합니다."
        )
    if pdf_el.placeholder and figma_el.placeholder and \
            loosen(pdf_el.placeholder) != loosen(figma_el.placeholder):
        findings.append(
            f"{screen_name} 화면 {pdf_el.label!r} 의 안내 문구가 다릅니다: "
            f"기획서 {pdf_el.placeholder!r} / 디자인 {figma_el.placeholder!r} — "
            "이 요소의 안내 문구는 검증에서 뺐습니다."
        )
        pdf_el.placeholder = None  # 어느 쪽이 진실인지 모른다 — 판정하지 않는다
    if pdf_el.options and figma_el.options and pdf_el.options != figma_el.options:
        findings.append(
            f"{screen_name} 화면 {pdf_el.label!r} 의 선택 항목이 다릅니다: "
            f"기획서 {pdf_el.options} / 디자인 {figma_el.options} — 기획서 "
            "항목으로 검증합니다(항목 검증까지 빼면 둘 다 안 보게 된다)."
        )


def _merge_flows(
    merged: SpecDocument, pdf_doc: SpecDocument, figma_doc: SpecDocument,
    findings: list[str],
) -> None:
    # Task 2 에서 채운다 — 흐름 채택 규칙 (스펙 '흐름 채택 규칙' 절).
    merged.flows.extend(f.model_copy(deep=True) for f in pdf_doc.flows)
