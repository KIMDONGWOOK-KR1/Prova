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
        # 검증에 넣지 않는다 — 구현이 이 요소를 안 가진 것이 결함인지
        # 디자인이 앞서간 것인지 판정할 근거가 없다. 넣으면 기획서 준수
        # 구현이 FAIL 이 된다(오탐 — e2e 에서 실제로 났다).
        findings.append(
            f"{screen.screen_name} 화면의 요소 {figma_el.label!r} 는 "
            "기획서에 없습니다 — 어느 쪽이 맞는지 정해지기 전에는 검증하지 "
            "않습니다."
        )
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
    """PDF 흐름은 그대로, Figma 흐름은 채택 규칙을 통과한 것만.

    채택 규칙이 필요한 이유: 디자인의 prototype 연결이 기획서 성공 조건과
    모순일 수 있다 — 실물 픽스처가 바로 그랬다(가입하기→로그인 vs 성공 조건
    /welcome). 그대로 실행하면 구현이 옳아도 FAIL, 즉 오탐이다. 어긋남=발견
    원칙을 흐름에도 적용한다:

        같은 (화면 순서, via) 의 PDF 흐름이 있다  -> 이미 검증된다, 접는다
        via 요소가 병합 화면에 없다               -> 발견 + 미채택
        via 가 link 다                            -> 순수 이동이므로 채택
        via 가 button 등 제출형이다               -> 출발 화면 성공 조건의
            경로와 목적지 경로를 대조: 일치=채택 · 불일치=발견+미채택 ·
            경로 없음=판정 불능이므로 발견+미채택 (억측으로 실행하지 않는다)
    """
    # 순환을 피해 함수 안에서 가져온다 — generator 는 models 만 보지만
    # s1_merge 를 상단에서 물면 향후 generator→merge 참조가 생길 때 얽힌다.
    from prova.s2_case_generator.generator import parse_success_expectation

    merged.flows.extend(f.model_copy(deep=True) for f in pdf_doc.flows)
    name_to_id = {normalize_ws(s.screen_name): s.screen_id
                  for s in merged.screens if s.source_kind == "document"}

    for flow in figma_doc.flows:
        ids = [name_to_id.get(normalize_ws(sid)) for sid in flow.screen_ids]
        if any(i is None for i in ids):
            missing = [sid for sid, i in zip(flow.screen_ids, ids) if i is None]
            findings.append(
                f"디자인 흐름 {flow.flow_id!r} 이 병합되지 않은 화면"
                f"({', '.join(missing)})을 지나 실행하지 않습니다."
            )
            continue
        via = list(flow.via)
        if any(pf.screen_ids == ids and list(pf.via) == via
               for pf in merged.flows):
            continue  # 기획서가 이미 같은 흐름을 적었다

        src = merged.screen_by_id(ids[0])
        dst = merged.screen_by_id(ids[-1])
        via_el = (next((e for e in src.elements if e.label == via[0]), None)
                  if via else None)
        if via and via_el is None:
            findings.append(
                f"디자인 흐름의 이동 요소 {via[0]!r} 가 병합 화면에 없어 "
                "실행하지 않습니다."
            )
            continue
        if via_el is not None and via_el.type != "link":
            expected_path = parse_success_expectation(src).url_contains
            if expected_path is None:
                findings.append(
                    f"디자인은 {via[0]!r} 로 {dst.screen_name!r} 이동을 그렸지만 "
                    f"{src.screen_name!r} 성공 조건에 경로가 없어 맞는지 확인할 "
                    "수 없습니다 — 실행하지 않습니다."
                )
                continue
            if expected_path != dst.url_path:
                findings.append(
                    f"디자인은 {via[0]!r} 가 {dst.screen_name!r}"
                    f"({dst.url_path})로 간다고 그렸지만 기획서 성공 조건은 "
                    f"{expected_path} 로 갑니다 — 실행하지 않고 불일치로 "
                    "보고합니다."
                )
                continue
        merged.flows.append(Flow(
            flow_id=f"{ids[0]}_to_{ids[-1]}_figma",
            title=flow.title, screen_ids=ids, via=via,
        ))
