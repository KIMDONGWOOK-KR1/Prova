"""A-3 변이 시험 — 기획서 글자 하나를 바꿔 '기획서와 사이트가 다른' 상태를 만들고 도구가 잡는지 본다.

정답이 정해진 차이를 기획서 쪽에 심는다(사이트는 그대로). 변이 하나마다 PDF 를 다시 만들어
S1(실모델)부터 끝까지 돌린다. 결과 폴더는 저장소가 무시하는 runs/ 아래에 둔다.

    uv run python scripts/mutation_test.py plan   runs/mutation   # 변이 기획서(md·pdf) 만들기
    uv run python scripts/mutation_test.py run    runs/mutation   # 기준 + 변이 실행(실모델, 이어서 돌림)
    uv run python scripts/mutation_test.py report runs/mutation   # 집계

실모델(configs/default.yaml 의 llm)이 필요하다. 외부 연습 사이트 다섯 곳에 요청을 보낸다
(가입 기획서는 계정이 생겨서 뺐다). 결과 기록: docs/measurements/mutation-2026-11-07.md

변이 종류
  MSG     기획서의 따옴표 문구(성공·실패 문구) — 문서 안 같은 문구 전부
  LABEL   UI 요소 표의 라벨 칸(입력·버튼·선택)
  OPTION  '선택 목록:' 의 선택지 하나
  SEED    예시 데이터 표의 첫 칸 값 하나(상품명 등)
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("runs/mutation")
SRC = Path("docs/measurements/external-specs")
SPECS = {
    "pta_login2_spec": "https://practicetestautomation.com",
    "herokuapp_login2_spec": "https://the-internet.herokuapp.com",
    "saucedemo_login2_spec": "https://www.saucedemo.com",
    "ae_search_spec": "https://automationexercise.com",
    "inventory_spec": "https://www.saucedemo.com",
}
CONTROL_TYPES = ("입력", "버튼", "선택", "체크")


def alter(text: str) -> str:
    """눈에 띄게 다른 문구로. 띄어쓰기만 다른 것은 결함으로 세지 않으므로(D4) 글자를 바꾼다."""
    if re.search(r"[가-힣]", text):
        return text + " 변경"
    words = re.findall(r"[A-Za-z]+", text)
    if not words:
        return text + " Sample"
    last = words[-1]
    i = text.rfind(last)
    return text[:i] + "Sample" + text[i + len(last):]


def mutants(md: str) -> list[dict]:
    out = []
    seen = set()
    for m in re.finditer(r'"([^"\n]{4,})"', md):
        s = m.group(1)
        if s.startswith("/") or s in seen:
            continue
        seen.add(s)
        out.append({"kind": "MSG", "target": s, "new": alter(s), "scope": "all"})
    # UI 요소 표
    in_ui = False
    for line in md.splitlines():
        if line.startswith("| 요소 ID"):
            in_ui = True
            continue
        if in_ui and not line.startswith("|"):
            in_ui = False
        if in_ui and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 3 and cells[1] in CONTROL_TYPES and cells[2] not in ("-", ""):
                out.append({"kind": "LABEL", "target": line, "label": cells[2],
                            "new": line.replace(f"| {cells[2]} |", f"| {alter(cells[2])} |", 1),
                            "scope": "line"})
            m = re.search(r"선택 목록:\s*([^|]+)", line)
            if m:
                opts = [o.strip() for o in re.split(r",\s*(?![^()]*\))", m.group(1)) if o.strip()]
                o = opts[0]
                out.append({"kind": "OPTION", "target": line, "label": o,
                            "new": line.replace(o, alter(o), 1), "scope": "line"})
    # 예시 데이터 표(상품명 | 가격)
    m = re.search(r"\| 상품명 \| 가격 \|\n\|---\|---\|\n\| ([^|]+) \|", md)
    if m:
        v = m.group(1).strip()
        out.append({"kind": "SEED", "target": f"| {v} |", "label": v,
                    "new": f"| {alter(v)} |", "scope": "first"})
    return out


def apply(md: str, mu: dict) -> str:
    if mu["scope"] == "all":
        return md.replace(f'"{mu["target"]}"', f'"{mu["new"]}"').replace(
            f"| {mu['target']} |", f"| {mu['new']} |")
    return md.replace(mu["target"], mu["new"], 1)


def plan() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from make_spec_pdf import convert, register_fonts
    register_fonts()
    table = {}
    for stem in SPECS:
        d = ROOT / stem
        d.mkdir(parents=True, exist_ok=True)
        md = (SRC / f"{stem}.md").read_text(encoding="utf-8")
        shutil.copy(SRC / f"{stem}.md", d / "base.md")
        convert(d / "base.md")
        ms = mutants(md)
        for i, mu in enumerate(ms, 1):
            name = f"{mu['kind'].lower()}{i:02d}"
            new = apply(md, mu)
            assert new != md, (stem, name)
            (d / f"{name}.md").write_text(new, encoding="utf-8")
            convert(d / f"{name}.md")
            mu["name"] = name
        table[stem] = ms
    (ROOT / "mutants.json").write_text(json.dumps(table, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    for stem, ms in table.items():
        print(stem, len(ms), [m["name"] for m in ms])
    return table


def run(only: list[str]) -> None:
    from prova.llm.factory import make_llm
    from prova.pipeline import run_pipeline

    cfg = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    table = json.loads((ROOT / "mutants.json").read_text(encoding="utf-8"))
    out = ROOT / "results.tsv"
    done = set()
    if out.exists():
        done = {tuple(l.split("\t")[:2]) for l in out.read_text(encoding="utf-8").splitlines()}
    for stem, ms in table.items():
        if only and stem not in only:
            continue
        for name in ["base"] + [m["name"] for m in ms]:
            if (stem, name) in done:
                continue
            pdf = ROOT / stem / f"{name}.pdf"
            llm, _ = make_llm("vllm", cfg, pdf, cache=True)
            try:
                report, _ = run_pipeline(str(pdf), SPECS[stem], llm, run_id=f"{stem}-{name}",
                                         runs_root=ROOT / "runs", screenshot_every_step=False)
                rows = [f"{stem}\t{name}\t{c.case_id}\t{c.verdict}\t{c.failure_category}"
                        for c in report.cases]
            except Exception as exc:
                rows = [f"{stem}\t{name}\t-\tERROR\t{type(exc).__name__}"]
            with out.open("a", encoding="utf-8") as f:
                f.write("\n".join(rows) + "\n")
            print(stem, name, len(rows), flush=True)


DEFECT = {"assertion_mismatch", "input_error"}


def report() -> None:
    """기준 실행과 비교해 새로 FAIL 이 된 케이스가 있으면 '잡음'.

    잡음(결함으로)    새 FAIL 중 하나라도 assertion_mismatch·input_error
    잡음(실행 문제로) 새 FAIL 이 element_not_found·page_error 등뿐
    놓침             새 FAIL 없음 — 기준 실행에서 이미 FAIL 인 케이스가 맡는 변이면
                     실제로는 잴 수 없는 것이다. 사람이 한 번 본다(측정 기록 참고)
    잴 수 없음        기준 실행에 PASS 가 하나도 없음
    """
    from collections import defaultdict

    rows = defaultdict(dict)
    for line in (ROOT / "results.tsv").read_text(encoding="utf-8").splitlines():
        stem, name, cid, verdict, cat = line.split("\t")
        rows[(stem, name)][cid] = (verdict, cat)
    table = json.loads((ROOT / "mutants.json").read_text(encoding="utf-8"))

    tally = defaultdict(lambda: defaultdict(int))
    detail = []
    for stem, ms in table.items():
        base = rows.get((stem, "base"), {})
        base_pass = {c for c, (v, _) in base.items() if v == "PASS"}
        for mu in ms:
            got = rows.get((stem, mu["name"]))
            if got is None:
                continue
            if "-" in got:
                outcome, new_fail, extra = "오류", {}, set()
            else:
                new_fail = {c: cat for c, (v, cat) in got.items()
                            if v == "FAIL" and (c in base_pass or c not in base)}
                if any(cat in DEFECT for cat in new_fail.values()):
                    outcome = "잡음(결함으로)"
                elif new_fail:
                    outcome = "잡음(실행 문제로)"
                elif not base_pass:
                    outcome = "잴 수 없음"
                else:
                    outcome = "놓침"
                extra = {c for c in got if c not in base} | {c for c in base if c not in got}
            tally[mu["kind"]][outcome] += 1
            tally["합계"][outcome] += 1
            detail.append(f"{stem}\t{mu['name']}\t{outcome}\t" +
                          ",".join(f"{c}:{cat}" for c, cat in sorted(new_fail.items())) +
                          f"\t케이스 증감 {len(extra)}")

    order = ["잡음(결함으로)", "잡음(실행 문제로)", "놓침", "잴 수 없음", "오류"]
    print("종류\t" + "\t".join(order))
    for kind, t in tally.items():
        print(kind + "\t" + "\t".join(str(t.get(o, 0)) for o in order))
    print()
    print("\n".join(detail))


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        plan()
    elif sys.argv[1] == "report":
        report()
    else:
        run(sys.argv[3:])
