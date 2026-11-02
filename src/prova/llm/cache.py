"""모델 응답 캐시 — 같은 기획서를 다시 돌릴 때 S1 을 기다리지 않는다.

## 왜 모델 호출 층에 두는가

'이 PDF 는 추출해 봤다' 로 저장하면 추출 프롬프트나 스키마를 고쳤을 때 낡은 결과가
조용히 살아남는다. 프롬프트·스키마·모델 이름까지 통째로 해시하면 무엇이 바뀌든 키가
바뀌므로 무효화를 따로 신경 쓸 필요가 없다. 응답 뒤의 교정(`_apply_declared_*`)은 매번
도니, 코드만 고친 경우에도 옛 결과가 남지 않는다. 기획서를 한 글자라도 고치면 그 화면의
호출만 다시 나간다.

## 재사용이 사실을 덮지 않게

같은 입력이어도 모델을 다시 부르면 답이 조금 달라질 수 있다. 재사용은 '이번에 모델을
돌렸다' 는 사실을 바꾸므로 리포트가 건수를 말하고, `--no-cache` 로 새로 물을 수 있다.
측정 스크립트는 켜지 않는다(make_llm 의 기본값) — 옛 답을 재면 측정이 아니다.

실패와 mock 은 저장하지 않는다. 서버 없는 mock 은 아낄 시간이 없다.

## 유출

응답에는 기획서 내용이 그대로 들어 있다. 그래서 저장소가 무시하는 runs/ 아래에 둔다.
받은 기획서를 지워야 할 때는 이 폴더도 함께 지운다.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path


class CachedLLM:
    """LLMClient 를 감싸 complete_json 의 성공 응답을 파일로 남긴다."""

    def __init__(self, inner, directory: Path | str, read: bool = True) -> None:
        """
        Args:
            read: False 면 저장된 답을 쓰지 않고 새로 물어 덮어쓴다 (--no-cache).
        """
        self.inner = inner
        self.directory = Path(directory)
        self.read = read
        self.hits = 0
        self.misses = 0
        # 제목 다듬기가 다른 스레드에서 돈다 (nodes.finish_titles)
        self._lock = threading.Lock()

    def __getattr__(self, name: str):
        # name·health·model·base_url 등은 원래 백엔드의 것을 그대로 보인다.
        return getattr(self.inner, name)

    def _path(self, **request) -> Path:
        text = json.dumps({"model": self.inner.name, **request},
                          ensure_ascii=False, sort_keys=True, default=str)
        return self.directory / f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}.json"

    def _load(self, path: Path):
        if not self.read:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # 없거나 깨졌으면 새로 묻는다

    def complete_json(self, *, system: str, user: str, schema: dict,
                      max_tokens: int = 2048, temperature: float = 0.0) -> dict:
        request = dict(system=system, user=user, schema=schema, max_tokens=max_tokens,
                       temperature=temperature)
        path = self._path(**request)
        saved = self._load(path)
        if saved is not None:
            with self._lock:
                self.hits += 1
            return saved
        answer = self.inner.complete_json(**request)
        with self._lock:
            self.misses += 1
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f".{threading.get_ident()}.tmp")
        temp.write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
        return answer
