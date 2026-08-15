#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF/HWPX에서 로그인·회원가입·검색 관련 내용을 찾아 JSON으로 저장한다.

기본 모드:
- PDF 텍스트: PyMuPDF
- HWPX 텍스트: ZIP 내부 XML
- 스캔/삽입 이미지: EasyOCR
- JSON 구조화: 규칙 기반
- 선택 사항: 로컬 Ollama 모델로 더 정확하게 구조화

예시:
python extract_auth_search_json.py sample.pdf -o result.json
python extract_auth_search_json.py sample.hwpx -o result.json --ocr always
python extract_auth_search_json.py sample.pdf -o result.json --ollama-model MODEL_NAME
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
import urllib.error
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED = {".pdf", ".hwpx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

FEATURES = [
    ("feature-login", "로그인", "auth"),
    ("feature-signup", "회원가입", "auth"),
    ("feature-search", "검색 기능 확인 결과", "search"),
]

KEYWORDS = (
    "로그인", "회원가입", "검색", "sign in", "sign up", "search",
    "이메일", "아이디", "계정이름", "비밀번호", "password",
    "필수", "오류", "성공", "방 목록", "room list", "그룹", "group",
)


@dataclass
class Block:
    source_ref: str
    kind: str
    text: str
    page: int | None = None


def clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


class OCR:
    def __init__(self, langs: list[str], gpu: bool):
        self.langs = langs
        self.gpu = gpu
        self.reader = None

    def read(self, image) -> str:
        try:
            import easyocr
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "OCR 라이브러리가 없습니다. pip install -r requirements.txt 를 실행하세요."
            ) from exc

        if self.reader is None:
            self.reader = easyocr.Reader(self.langs, gpu=self.gpu, verbose=False)

        image = image.convert("RGB")
        if max(image.size) > 3200:
            image.thumbnail((3200, 3200))

        rows = self.reader.readtext(np.asarray(image), detail=1, paragraph=False)
        return clean("\n".join(
            str(text) for _, text, confidence in rows if float(confidence) >= 0.15
        ))


def extract_pdf(path: Path, ocr_mode: str, ocr: OCR | None, dpi: int,
                min_text_chars: int) -> list[Block]:
    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "PDF 라이브러리가 없습니다. pip install -r requirements.txt 를 실행하세요."
        ) from exc

    result = []
    with fitz.open(path) as doc:
        for page_no, page in enumerate(doc, start=1):
            text = clean(page.get_text("text", sort=True))
            if text:
                result.append(Block(f"pdf-page-{page_no}", "pdf_text", text, page_no))

            need_ocr = (
                ocr_mode == "always"
                or (
                    ocr_mode == "auto"
                    and len(re.sub(r"\s+", "", text)) < min_text_chars
                )
            )
            if need_ocr:
                if ocr is None:
                    raise RuntimeError("OCR 엔진이 준비되지 않았습니다.")
                scale = dpi / 72
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                ocr_text = ocr.read(image)
                if ocr_text:
                    result.append(
                        Block(f"pdf-page-{page_no}-ocr", "pdf_ocr", ocr_text, page_no)
                    )
    return result


def tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_hwpx(path: Path, ocr_mode: str, ocr: OCR | None) -> list[Block]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow가 설치되지 않았습니다.") from exc

    result = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()

        # HWPX 본문 XML
        sections = sorted(
            n for n in names
            if n.lower().startswith("contents/section") and n.lower().endswith(".xml")
        )
        for name in sections:
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            parts = [
                clean(el.text)
                for el in root.iter()
                if tag_name(el.tag) == "t" and el.text and clean(el.text)
            ]
            text = clean("\n".join(parts))
            if text:
                result.append(Block(name, "hwpx_xml", text))

        # HWPX 삽입 이미지
        if ocr_mode != "off":
            if ocr is None:
                raise RuntimeError("OCR 엔진이 준비되지 않았습니다.")
            images = sorted(
                n for n in names
                if n.lower().startswith("bindata/")
                and Path(n).suffix.lower() in IMAGE_EXTS
            )
            for name in images:
                try:
                    image = Image.open(io.BytesIO(zf.read(name)))
                    text = ocr.read(image)
                    if text:
                        result.append(Block(name, "hwpx_image_ocr", text))
                except Exception as exc:
                    print(f"[경고] {name} OCR 실패: {exc}", file=sys.stderr)

    return result


def select_blocks(blocks: list[Block], max_chars: int) -> list[Block]:
    selected_idx = set()
    terms = tuple(k.lower() for k in KEYWORDS)

    for i, block in enumerate(blocks):
        lowered = block.text.lower()
        if any(term in lowered for term in terms):
            selected_idx.add(i)
            if block.page is not None:
                for j, other in enumerate(blocks):
                    if other.page is not None and abs(other.page - block.page) <= 1:
                        selected_idx.add(j)

    if not selected_idx:
        selected_idx = set(range(min(5, len(blocks))))

    selected = []
    used = 0
    for i in sorted(selected_idx):
        if used >= max_chars:
            break
        text = blocks[i].text[: max_chars - used]
        selected.append(Block(blocks[i].source_ref, blocks[i].kind, text, blocks[i].page))
        used += len(text)
    return selected


def prompt_text(blocks: list[Block]) -> str:
    pieces = []
    for block in blocks:
        page = f", page={block.page}" if block.page is not None else ""
        pieces.append(
            f"[source={block.source_ref}, kind={block.kind}{page}]\n{block.text}"
        )
    return "\n\n".join(pieces)


def schema() -> dict[str, Any]:
    nullable_string = {"type": ["string", "null"]}
    feature = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "enum": ["feature-login", "feature-signup", "feature-search"],
            },
            "name": {"type": "string"},
            "category": {"type": "string", "enum": ["auth", "search"]},
            "feature_status": {
                "type": "string",
                "enum": ["FOUND", "PARTIAL", "NOT_FOUND"],
            },
            "description": {"type": "string"},
            "elements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "label": nullable_string,
                        "placeholder": nullable_string,
                        "target": nullable_string,
                        "bbox": {"type": ["array", "null"], "items": {"type": "number"}},
                        "inferred": {"type": "boolean"},
                        "evidence": nullable_string,
                    },
                    "required": [
                        "id", "type", "label", "placeholder", "target",
                        "bbox", "inferred", "evidence"
                    ],
                    "additionalProperties": False,
                },
            },
            "constraints": {"type": "array", "items": {"type": "string"}},
            "error_messages": {"type": "array", "items": {"type": "string"}},
            "success_condition": nullable_string,
            "transitions": {"type": "array", "items": {"type": "string"}},
            "inferred": {"type": "string", "enum": ["false", "true", "mixed"]},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_ref": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["source_ref", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "id", "name", "category", "feature_status", "description",
            "elements", "constraints", "error_messages", "success_condition",
            "transitions", "inferred", "evidence"
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "version": {"type": "integer"},
            "source": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string"},
                    "file_type": {"type": "string"},
                    "extraction_mode": {"type": "string"},
                },
                "required": ["file_name", "file_type", "extraction_mode"],
                "additionalProperties": False,
            },
            "features": {
                "type": "array",
                "items": feature,
                "minItems": 3,
                "maxItems": 3,
            },
        },
        "required": ["version", "source", "features"],
        "additionalProperties": False,
    }


def ollama_prompt(path: Path, text: str) -> str:
    return f"""
아래 자료만 근거로 로그인, 회원가입, 검색 기능을 JSON으로 정리하라.

규칙:
- features는 정확히 세 개이며 순서는 feature-login, feature-signup, feature-search이다.
- 문서에 없는 사실을 만들지 않는다.
- 확인하지 못한 기능은 NOT_FOUND로 기록한다.
- 오류 문구, 성공 조건, 이동 목적지는 원문에 없으면 추정하지 않는다.
- 제한적 해석은 inferred=true로 표시한다.
- bbox가 직접 없으면 null이다.
- evidence에는 source_ref와 짧은 원문 근거를 넣는다.
- 검색 입력창·검색 버튼·검색 동작이 없으면 검색은 NOT_FOUND이다.

파일: {path.name}

추출 자료:
{text}
""".strip()


def call_ollama(model: str, url: str, prompt: str, timeout: int) -> dict[str, Any]:
    endpoint = url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema(),
        "stream": False,
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            envelope = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama 연결 실패: {endpoint}\n{exc}") from exc

    raw = envelope.get("response", "")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)


def unique(lines: list[str]) -> list[str]:
    seen = set()
    out = []
    for line in lines:
        line = clean(line)
        key = line.lower()
        if line and key not in seen:
            out.append(line)
            seen.add(key)
    return out


def rule_based(path: Path, blocks: list[Block]) -> dict[str, Any]:
    lines = unique([
        line
        for block in blocks
        for line in block.text.splitlines()
        if line.strip()
    ])
    full = "\n".join(lines)
    lower = full.lower()

    feature_terms = {
        "feature-login": ("로그인", "sign in", "signin"),
        "feature-signup": ("회원가입", "sign up", "signup"),
        "feature-search": ("검색", "search"),
    }
    related_terms = {
        "feature-login": (
            "로그인", "sign in", "이메일", "아이디", "계정이름",
            "비밀번호", "password", "찾기", "remember"
        ),
        "feature-signup": (
            "회원가입", "sign up", "이메일", "아이디", "계정이름",
            "비밀번호", "필수", "8자", "오류"
        ),
        "feature-search": (
            "검색", "search", "방 목록", "room list", "그룹", "group"
        ),
    }

    output_features = []
    for feature_id, name, category in FEATURES:
        found = any(term.lower() in lower for term in feature_terms[feature_id])
        matched = unique([
            line for line in lines
            if any(term.lower() in line.lower() for term in related_terms[feature_id])
        ])

        elements = []
        for idx, line in enumerate(matched, start=1):
            ll = line.lower()
            element_type = None
            if any(x in ll for x in (
                "이메일", "email", "아이디", "계정이름", "비밀번호", "password"
            )):
                element_type = "input"
            if any(x in ll for x in ("돌아가기", "계정이 있나요", "찾기", "forget")):
                element_type = "link"
            if len(line) <= 35 and any(
                x in ll for x in feature_terms[feature_id]
            ):
                element_type = "button"

            if element_type:
                elements.append({
                    "id": f"{feature_id}-element-{idx}",
                    "type": element_type,
                    "label": line,
                    "placeholder": None,
                    "target": None,
                    "bbox": None,
                    "inferred": True,
                    "evidence": line,
                })

        constraints = [
            line for line in matched
            if re.search(r"필수|이상|올바른|포함|형식|must be|please enter",
                         line, flags=re.I)
        ]
        errors = [
            line for line in matched
            if re.search(r"오류|실패|다시 확인|invalid|error",
                         line, flags=re.I)
        ]
        transitions = [
            line for line in matched
            if re.search(r"돌아가기|계정이 있나요|이동|링크|go to",
                         line, flags=re.I)
        ]

        evidence = []
        for block in blocks:
            quote = next(
                (line for line in block.text.splitlines() if line in matched),
                None
            )
            if quote:
                evidence.append({
                    "source_ref": block.source_ref,
                    "quote": quote[:300],
                })

        output_features.append({
            "id": feature_id,
            "name": name,
            "category": category,
            "feature_status": "FOUND" if found else "NOT_FOUND",
            "description": (
                "문서에서 관련 키워드와 요소를 확인함."
                if found else
                "문서에서 해당 기능을 명시적으로 확인하지 못함."
            ),
            "elements": elements if found else [],
            "constraints": constraints if found else [],
            "error_messages": errors if found else [],
            "success_condition": None,
            "transitions": transitions if found else [],
            "inferred": "mixed" if found else "false",
            "evidence": evidence[:10],
        })

    return {
        "version": 1,
        "source": {
            "file_name": path.name,
            "file_type": path.suffix.lower().lstrip("."),
            "extraction_mode": "rule_based",
        },
        "features": output_features,
    }


def normalize_result(result: dict[str, Any], path: Path, mode: str) -> dict[str, Any]:
    raw = result.get("features", [])
    by_id = {
        item.get("id"): item
        for item in raw
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    normalized = []
    for feature_id, name, category in FEATURES:
        item = by_id.get(feature_id)
        if not item:
            item = {
                "id": feature_id,
                "name": name,
                "category": category,
                "feature_status": "NOT_FOUND",
                "description": "해당 기능을 확인하지 못함.",
                "elements": [],
                "constraints": [],
                "error_messages": [],
                "success_condition": None,
                "transitions": [],
                "inferred": "false",
                "evidence": [],
            }
        item["id"] = feature_id
        item["category"] = category
        normalized.append(item)

    return {
        "version": 1,
        "source": {
            "file_name": path.name,
            "file_type": path.suffix.lower().lstrip("."),
            "extraction_mode": mode,
        },
        "features": normalized,
    }


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDF/HWPX에서 로그인·회원가입·검색 내용을 JSON으로 추출"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--ocr", choices=("auto", "always", "off"), default="auto")
    parser.add_argument("--ocr-langs", default="ko,en")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--min-text-chars", type=int, default=80)
    parser.add_argument("--ollama-model")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-timeout", type=int, default=600)
    parser.add_argument("--require-ollama", action="store_true")
    parser.add_argument("--max-chars", type=int, default=50000)
    parser.add_argument("--dump-text", type=Path)
    return parser.parse_args()


def main() -> int:
    a = args()
    input_path = a.input.expanduser().resolve()
    if not input_path.exists():
        print(f"[오류] 파일이 없습니다: {input_path}", file=sys.stderr)
        return 2
    if input_path.suffix.lower() not in SUPPORTED:
        print("[오류] PDF와 HWPX만 지원합니다.", file=sys.stderr)
        return 2

    output_path = (
        a.output.expanduser().resolve()
        if a.output
        else input_path.with_name(input_path.stem + "_auth_search.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ocr = None
    if a.ocr != "off":
        langs = [x.strip() for x in a.ocr_langs.split(",") if x.strip()]
        ocr = OCR(langs, a.gpu)

    try:
        if input_path.suffix.lower() == ".pdf":
            blocks = extract_pdf(
                input_path, a.ocr, ocr, a.dpi, a.min_text_chars
            )
        else:
            blocks = extract_hwpx(input_path, a.ocr, ocr)
    except Exception as exc:
        print(f"[오류] 추출 실패:\n{exc}", file=sys.stderr)
        return 1

    if not blocks:
        print("[오류] 추출된 텍스트가 없습니다. --ocr always를 사용하세요.",
              file=sys.stderr)
        return 1

    chosen = select_blocks(blocks, a.max_chars)
    text = prompt_text(chosen)

    if a.dump_text:
        dump = a.dump_text.expanduser().resolve()
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(text, encoding="utf-8")
        print(f"[완료] 중간 텍스트: {dump}")

    mode = "rule_based"
    if a.ollama_model:
        try:
            result = call_ollama(
                a.ollama_model,
                a.ollama_url,
                ollama_prompt(input_path, text),
                a.ollama_timeout,
            )
            mode = f"ollama:{a.ollama_model}"
        except Exception as exc:
            if a.require_ollama:
                print(f"[오류] Ollama 실패:\n{exc}", file=sys.stderr)
                return 1
            print(f"[경고] Ollama 실패, 규칙 기반으로 전환:\n{exc}",
                  file=sys.stderr)
            result = rule_based(input_path, chosen)
    else:
        result = rule_based(input_path, chosen)

    final = normalize_result(result, input_path, mode)
    output_path.write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[완료] JSON 저장: {output_path}")
    print(f"[정보] 구조화 방식: {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
