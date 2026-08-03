# QA-Agent

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
