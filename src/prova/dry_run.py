"""dry-run — 쓰기 요청을 막고 실행한다 (A-4, 2026-11-09).

## 왜 있는가

실무 사이트의 폼은 제출하면 실제로 접수된다. 실물 측정에서 문의 폼의 정상 제출을 재지
못한 이유가 그것이다(제출하면 담당자에게 메일이 간다). dry-run 은 브라우저에서 나가는
쓰기 요청(POST·PUT·PATCH·DELETE)을 전부 막는다 — 폼 제출·fetch·XHR·beacon 을 가리지
않고, 대상 사이트가 아닌 주소로 가는 것도 막는다.

## 판정을 어떻게 바꾸는가

요청을 막으면 서버 응답이 없으므로 제출 뒤 화면은 진짜가 아니다. 그래서 **본 스텝에서
쓰기 요청을 하나라도 막은 케이스는 '확인 불가'** 로 둔다. 막은 요청(방법·주소·보낸 칸
이름)을 근거로 남긴다. 지어낸 응답으로 PASS·FAIL 을 내지 않는다.

막은 요청이 없는 케이스(브라우저 쪽 검증이 제출 자체를 막은 경우)는 평소처럼 판정한다 —
필수 칸을 비운 위반 케이스의 대부분이 여기에 든다.

## 전제(로그인) 단계는 통과시킨다

로그인이 필요한 화면은 전제 스텝에서 로그인 요청(POST)을 보내야 세션이 생긴다. 이것까지
막으면 로그인 뒤 화면을 하나도 잴 수 없다. 전제 스텝은 생성기가 로그인으로만 만들므로
(generator.expand_precondition) 통과시키고, 통과시킨 요청도 근거에 남긴다.

## 막는 구멍과 못 막는 구멍

- 컨텍스트 단위로 가로챈다 — 새 창(popup)·가드 케이스의 새 컨텍스트도 같은 차단이 걸린다
  (nodes.page_opener 가 컨텍스트를 열 때마다 건다).
- 서비스 워커는 가로채기를 우회할 수 있어 dry-run 에서는 등록 자체를 막는다.
- 확인창(confirm)은 평소 '취소' 로 닫혀 제출이 일어나지 않는다. dry-run 에서는 '확인' 을
  눌러 요청이 실제로 나가게 하고 그것을 막는다 — 그래야 제출 직전까지가 정상인지 보인다.
- **못 막는 것**: GET 으로 데이터를 바꾸는 사이트(`/delete?id=3`), 웹소켓 메시지.
  리포트가 이 한계를 말한다.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
#: 리포트·엑셀이 같은 말로 쓰는 한계 문장.
LIMITS = ("GET 으로 데이터를 바꾸는 주소와 웹소켓 메시지는 막지 못합니다.")
UNVERIFIABLE_PREFIX = "dry-run: 제출 요청을 막아 서버 응답을 볼 수 없습니다"


def _fields(request) -> list[str]:
    """보낸 칸 이름만 (값은 남기지 않는다 — 비밀번호가 리포트에 남으면 안 된다)."""
    try:
        body = request.post_data or ""
    except Exception:  # 바이너리 본문(파일 업로드 등)
        return ["(바이너리 본문)"]
    ctype = (request.headers.get("content-type") or "").lower()
    if "json" in ctype:
        import json

        try:
            data = json.loads(body)
        except ValueError:
            return []
        return sorted(data) if isinstance(data, dict) else []
    if "multipart" in ctype:
        import re

        return sorted(set(re.findall(r'name="([^"]+)"', body)))
    return sorted(parse_qs(body, keep_blank_values=True))


def describe(record: dict) -> str:
    fields = ", ".join(record.get("fields") or [])
    return f"{record['method']} {record['path']}" + (f" ({fields})" if fields else "")


class WriteGuard:
    """컨텍스트에 걸어 쓰기 요청을 막고 기록한다. 케이스마다 start_case 로 비운다."""

    def __init__(self) -> None:
        self.phase = "test"
        self.blocked: list[dict] = []
        self.allowed_setup: list[dict] = []

    def start_case(self) -> None:
        self.phase = "test"
        self.blocked = []
        self.allowed_setup = []

    def install(self, context) -> None:
        context.route("**/*", self._handle)
        # 확인창을 '확인' 으로 — 제출이 실제로 나가야 막을 수 있다 (모듈 설명).
        context.on("dialog", lambda dialog: dialog.accept())

    def _handle(self, route, request) -> None:
        if request.method.upper() not in WRITE_METHODS:
            route.fallback()
            return
        parts = urlsplit(request.url)
        record = {"method": request.method.upper(), "url": request.url,
                  "path": parts.path or "/", "fields": _fields(request)}
        if self.phase == "setup":
            self.allowed_setup.append(record)
            route.fallback()
            return
        self.blocked.append(record)
        route.abort("blockedbyclient")


def context_options(dry_run: bool) -> dict:
    """dry-run 일 때 new_context 에 더할 옵션 — 서비스 워커 등록을 막는다."""
    return {"service_workers": "block"} if dry_run else {}


def mark_unverifiable(verdict, guard: WriteGuard) -> None:
    """본 스텝에서 쓰기 요청을 막은 케이스를 '확인 불가' 로 바꾼다 (모듈 설명)."""
    if guard.allowed_setup:
        verdict.evidence["dry_run_setup_allowed"] = [describe(r) for r in guard.allowed_setup]
    if not guard.blocked:
        return
    blocked = [describe(r) for r in guard.blocked]
    verdict.evidence["dry_run_blocked"] = blocked
    verdict.evidence["dry_run_original"] = verdict.verdict
    verdict.verdict = "FAIL"
    verdict.failure_category = "unverifiable"
    verdict.failure_detail = f"{UNVERIFIABLE_PREFIX} — 막은 요청: {' / '.join(blocked)}"


def dry_run_summary(verdicts) -> dict:
    """리포트 summary["dry_run"]. 판정의 근거에서 세므로 병렬 실행에서도 맞는다."""
    blocked = [v for v in verdicts if (v.evidence or {}).get("dry_run_blocked")]
    return {
        "cases_blocked": len(blocked),
        "requests_blocked": sum(len(v.evidence["dry_run_blocked"]) for v in blocked),
        "setup_allowed": sum(len((v.evidence or {}).get("dry_run_setup_allowed") or [])
                             for v in verdicts),
        "limits": LIMITS,
    }
