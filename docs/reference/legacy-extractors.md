# 기존 문서 추출 도구

이 파이프라인(S1~S6)이 만들어지기 전에 작성된 독립 추출 도구들이다.
**이 파이프라인에 없는 능력을 갖고 있어 보존한다.**

| 도구 | 위치 | 이 파이프라인에 없는 것 |
|---|---|---|
| auth/search 추출기 | `extract_auth_search_json.py` (main) | **HWPX 파싱**, **EasyOCR** |
| Figma 추출기 | `feature/figma-extractor` 브랜치 | **Figma 연동** |

WITCHES 실물 기획서가 한글 문서·스캔 PDF·Figma로 들어오면 이 코드가 필요하다.
`src/prova/s1_spec_extractor/`는 "결정적 추출 + LLM 구조화" 2단계로 나뉘어 있어
앞단(`pdf_parser.py`)만 교체하면 흡수할 수 있다.

두 도구의 접근 방식이 이 파이프라인과 다른 점도 참고할 만하다.

| | 기존 추출기 | 이 파이프라인의 S1 |
|---|---|---|
| PDF 텍스트 | PyMuPDF | pdfplumber (표 구조 추출) |
| 스캔 이미지 | EasyOCR | 미지원 |
| 구조화 | 규칙 기반 + Ollama(선택) | vLLM 7B + `response_format` 스키마 강제 |
| LLM 실패 시 | 규칙 기반으로 자동 전환 | 명확히 실패시킨다 |

마지막 줄이 설계 차이의 핵심이다. 이 파이프라인은 **조용한 폴백을 두지 않는다** —
스키마가 강제되지 않으면 `constraints` 키가 흔들려 검증이 무력해지는데, 그게 리포트에는
초록불로 보인다. 자세한 이유는 [../teaching/07-cheetah-cuda.md](../teaching/07-cheetah-cuda.md)
의 "함정 3" 절에 있다.

---

아래는 병합 전 `main`의 README 내용이다.

---

# Prova

PDF 또는 HWPX 문서에서 로그인, 회원가입, 검색 기능과 관련된 내용을 추출해
일관된 JSON 형식으로 저장하는 명령줄 도구입니다.

## 설치

```bash
python -m pip install -r requirements.txt
```

## 사용법

```bash
python extract_auth_search_json.py sample.pdf -o result.json
python extract_auth_search_json.py sample.hwpx -o result.json --ocr always
```

기본값인 `--ocr auto`는 텍스트가 거의 없는 PDF 페이지에만 OCR을 수행합니다.
OCR을 사용하지 않으려면 `--ocr off`를 지정하세요.

로컬 Ollama 모델을 사용할 수도 있습니다. Ollama 호출에 실패하면 기본적으로
규칙 기반 추출로 자동 전환하며, `--require-ollama`를 함께 지정하면 실패 시
오류로 종료합니다.

```bash
python extract_auth_search_json.py sample.pdf --ollama-model MODEL_NAME
```
