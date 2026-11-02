"""실물 기획서 정답표 채점 — 골든이 없는 기획서의 추출 정확도를 잰다.

## 왜 필요한가

픽스처 기획서는 우리가 쓰고 정답(골든)도 우리가 만들었다. 실물 기획서에는 정답이
없으므로 '90%' 를 채점할 수 없다. 사람이 기획서를 읽고 요소·규칙·문구를 표로 옮기면
그 표가 정답이 된다. 이 모듈은 그 표와 S1 추출 결과를 항목 단위로 맞춰 본다.

## 두 숫자를 합치지 않는다

    놓친 것            기획서에 있는데 추출에 없다 -> 그 규칙의 케이스가 안 생긴다(미탐)
    추출에만 있는 것   추출에 있는데 표에 없다    -> 없는 규칙으로 FAIL 을 낸다(오탐)

재현율 하나로 합치면 어느 쪽 사고인지 사라지고, 이 프로젝트는 오탐을 더 나쁘게 본다.
추출에만 있는 것은 사람이 확인할 목록으로 내놓는다 — 표를 옮기다 빠뜨린 것일 수도
있어서 점수로 만들지 않는다.

## 추출 결과를 보기 전에 적는다

정답표를 추출 결과에서 만들어 주면 편하지만, 사람은 앞에 놓인 답을 고치는 쪽으로
기울어 추출이 놓친 것을 함께 놓친다. 그러면 정확도가 부풀려진다. 그래서 양식은 비어
있고, 추출 결과를 채워 주는 기능을 두지 않았다.

## 유출

실물 기획서는 저장소에 들어오면 안 된다(공개 저장소, 멘토링 합의 2026-10-16). 정답표는
기획서의 사본이나 다름없으므로, 저장소 밖이나 무시되는 경로에 있을 때만 읽고 쓴다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from prova.models import ScreenSpec, SpecDocument
from prova.s2_case_generator.rule_expander import RULE_LABELS
from prova.text_utils import loosen

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 항목 종류. 정답표 칸과 일대일이고 찍는 순서이기도 하다.
KINDS = ("요소", "필수", "규칙", "오류 문구", "선택 항목", "성공 조건", "실패 문구")

_TEMPLATE = """\
# Prova 정답표 — 실물 기획서의 추출 정확도를 재기 위해 사람이 옮겨 적는다.
#
# 1. 이 파일을 저장소에 커밋하지 마세요. 기획서의 사본입니다. 저장소 밖에 두세요.
# 2. S1 추출 결과를 보기 전에 적으세요. 보고 적으면 놓친 것을 함께 놓칩니다.
# 3. 기획서에 적힌 것만 적으세요. 추측한 규칙은 넣지 않습니다.
#
# rules 키: format(email 등) min_length max_length require_uppercase require_lowercase
#           require_digit require_special pattern same_as numeric
#
# 아래 예시의 주석을 풀어 쓰고, 맨 끝의 `screens: []` 를 지우세요.
#
# screens:
#   - name: 로그인                     # 기획서의 화면 이름
#     success: /dashboard              # 성공 조건의 핵심 경로나 문구
#     messages:                        # 실패 시 문구 (칸에 묶이지 않은 것)
#       - 이메일 또는 비밀번호가 올바르지 않습니다.
#     elements:
#       - label: 이메일                # 화면에 보이는 이름
#         required: true               # 필수가 아니면 줄을 지웁니다
#         rules: {format: email}
#         error: 올바른 이메일 형식을 입력하세요.
#       - label: 회원 유형
#         options: [개인, 법인]
screens: []
"""


def blank_template() -> str:
    """빈 정답표. 추출 결과를 채워 주지 않는다 (모듈 설명 참고)."""
    return _TEMPLATE


def is_private_path(path: Path) -> bool:
    """정답표를 둬도 되는 곳인가 — 저장소 밖이거나 git 이 무시하는 경로."""
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        return True
    done = subprocess.run(["git", "check-ignore", "-q", str(resolved)],
                          cwd=REPO_ROOT, capture_output=True)
    return done.returncode == 0


@dataclass
class TruthScore:
    #: 종류 -> [맞은 수, 전체 수]
    by_kind: dict[str, list[int]] = field(
        default_factory=lambda: {k: [0, 0] for k in KINDS})
    #: 화면 이름 -> [맞은 수, 전체 수]
    by_screen: dict[str, list[int]] = field(default_factory=dict)
    missed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return sum(n[0] for n in self.by_kind.values())

    @property
    def total(self) -> int:
        return sum(n[1] for n in self.by_kind.values())

    @property
    def recall(self) -> float:
        return self.matched / self.total if self.total else 0.0

    def add(self, screen: str, kind: str, hit: bool, what: str) -> None:
        self.by_kind[kind][1] += 1
        tally = self.by_screen.setdefault(screen, [0, 0])
        tally[1] += 1
        if hit:
            self.by_kind[kind][0] += 1
            tally[0] += 1
        else:
            self.missed.append(f"[{screen}] {kind}: {what}")


def _strings(value) -> list[str]:
    """중첩된 값 안의 문자열을 모은다. 실패 문구는 어느 칸에 들어갔든 찾으면 된다."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def _score_element(out: TruthScore, name: str, want: dict, have) -> None:
    label = str(want.get("label", ""))
    out.add(name, "요소", have is not None, label)
    rules = want.get("rules") or {}
    if "required" in want:
        out.add(name, "필수", have is not None and have.required == bool(want["required"]),
                f"{label} = {want['required']}")
    for key, value in rules.items():
        got = have.constraints.get(key) if have is not None else None
        out.add(name, "규칙", got is not None and str(got) == str(value),
                f"{label} · {key} = {value} (추출: {got})")
    if want.get("error"):
        hit = have is not None and loosen(have.error_message) == loosen(want["error"])
        out.add(name, "오류 문구", hit, f"{label} · {want['error']}")
    for option in want.get("options") or []:
        hit = have is not None and loosen(str(option)) in {loosen(o) for o in have.options}
        out.add(name, "선택 항목", hit, f"{label} · {option}")
    if have is not None:
        for key, value in have.constraints.items():
            if key not in rules:
                out.extra.append(f"[{name}] 규칙: {label} · {key} = {value} "
                                 f"({RULE_LABELS.get(key, key)})")


def _score_screen(out: TruthScore, want: dict, have: ScreenSpec | None) -> None:
    name = str(want.get("name", "?"))
    elements = {loosen(e.label): e for e in (have.elements if have else [])}
    wanted = set()
    for item in want.get("elements") or []:
        key = loosen(str(item.get("label", "")))
        wanted.add(key)
        _score_element(out, name, item, elements.get(key))
    if want.get("success"):
        hit = have is not None and loosen(str(want["success"])) in loosen(have.success_condition)
        out.add(name, "성공 조건", hit, str(want["success"]))
    texts = loosen(" ".join(_strings(have.model_dump()))) if have else ""
    for message in want.get("messages") or []:
        out.add(name, "실패 문구", loosen(str(message)) in texts, str(message))
    if have is not None:
        out.extra += [f"[{name}] 요소: {e.label}"
                      for key, e in elements.items() if key not in wanted]


def score(truth: dict, doc: SpecDocument) -> TruthScore:
    """정답표와 추출 결과를 항목 단위로 맞춘다.

    Raises:
        ValueError: 정답표에 항목이 없을 때. 0% 로 찍으면 표를 안 적은 것과 추출이
            전부 실패한 것이 같아 보인다.
    """
    screens = {loosen(s.screen_name): s for s in doc.screens}
    out = TruthScore()
    named = set()
    for want in truth.get("screens") or []:
        key = loosen(str(want.get("name", "")))
        named.add(key)
        _score_screen(out, want, screens.get(key))
    if not out.total:
        raise ValueError("정답표가 비어 있습니다 — 기획서를 보고 항목을 먼저 옮겨 적으세요.")
    out.extra += [f"화면: {s.screen_name}" for key, s in screens.items() if key not in named]
    return out


def format_score(s: TruthScore) -> str:
    """터미널용 결과. 기획서 내용이 들어 있으니 파일로 남길 때는 정답표와 같이 다룬다."""
    lines = [f"재현율 {s.recall:.1%} ({s.matched}/{s.total})", "", "종류별"]
    lines += [f"  {k:<8} {n[0]}/{n[1]}" for k, n in s.by_kind.items() if n[1]]
    lines += ["", "화면별"]
    lines += [f"  {k} {n[0]}/{n[1]}" for k, n in s.by_screen.items()]
    lines += ["", f"놓친 것 {len(s.missed)}건 — 미탐으로 이어진다"]
    lines += [f"  {m}" for m in s.missed]
    lines += ["", f"추출에만 있는 것 {len(s.extra)}건 — 표를 빠뜨렸는지, 지어냈는지(오탐) 확인"]
    lines += [f"  {x}" for x in s.extra]
    return "\n".join(lines)
