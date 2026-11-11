# 구조

```
src/prova/
├── models.py                 데이터 계약 (명세서 §3) — 파이프라인 전체의 타입
├── theme.py                  디자인 토큰 — 웹 UI 와 리포트가 공유하는 단일 출처
├── text_utils.py             PDF 문구 ↔ 화면 문구 비교 규칙
├── wording.py                사람이 읽는 문장 — 기대 결과·재현 절차·규칙 이름 (리포트·엑셀·계획 화면 공용)
├── llm/                      백엔드 추상화 (base / mock / vllm / replay) + claude_backend(비교 측정 전용)
├── s1_spec_extractor/        PDF -> ScreenSpec
│   ├── pdf_parser.py           결정적 추출 (pdfplumber, LLM 없음)
│   └── extractor.py            LLM 구조화 + 표에서 읽은 사실로 교정
├── s1_figma/                 Figma API 응답 -> ScreenSpec (전부 결정적, LLM 없음)
│   ├── figma_parser.py         컴포넌트 기반 요소 인지 + 저장용 다듬기
│   └── extractor.py            SpecDocument 조립 — 경로는 --screen-url 매핑
├── s1_merge.py               기획서+Figma 병합 — 어긋남은 판정 대신 발견으로
├── spec_edits.py             사람이 고친 '기획서에서 읽은 내용' 을 SpecDocument 에 적용 (웹 UI 계획 화면)
├── spec_source.py            기획서 근거 — 케이스의 기대가 몇 쪽 어느 줄에 적혀 있는지 (LLM 없음)
├── spec_revision.py          기획서 두 판 비교 — 바뀐 것과 그것을 건드리는 케이스 (diff-spec · --since)
├── s2_case_generator/        ScreenSpec -> TestCase[]
│   ├── rule_expander.py        규칙 -> 위반값 + 요소 간 의존 해석 (순수 함수, LLM 없음)
│   ├── precondition.py         전제(로그인) 스텝 생성 (순수 함수, LLM 없음)
│   ├── generator.py            케이스 조립 + 기대 결정 + 요소 유형별 액션
│   ├── selector.py             자연어 요청 -> 실행할 케이스 고르기 (부분집합만)
│   └── coverage.py             기획서에 적혀 있는데 확인하지 않는 것을 찾는다
├── s3_grounder/dom_locator.py  라벨 -> 실제 요소 (selector-first) + 2차 경로 진입점 (heal_with_vlm)
├── vlm/                      2차 경로의 시각 모델 (base / mock_backend / qwen_vl / metrics)
├── s4_executor/                Playwright 실행 + 스텝별 증거 수집
├── s5_verifier/                PASS/FAIL 판정
├── s6_report/                  JSON + HTML 리포트 + 엑셀(xlsx_export.py)
├── dry_run.py                쓰기 요청(POST·PUT·PATCH·DELETE)을 막는 장치 (--dry-run)
├── nodes.py                  (state) -> state 노드
├── pipeline.py               build_plan (브라우저 없이 S1~S2+선택) + run_pipeline
├── graph.py                  같은 노드를 LangGraph 로 배선
├── server/                   로컬 웹 UI — 계획 확인 -> 실행
│   ├── app.py                  /api/plan (브라우저 없음) · /api/run (승인 목록) · /api/runs
│   ├── runner.py               워커 스레드 하나, 동시 실행 하나
│   └── static/                 작업 콘솔 (index.html · app.css · app.js, CDN 없음)
└── cli.py                    prova run · serve · login · diff-spec · export-xlsx · check

sut/                          테스트 대상 미니 웹앱 — 6화면(로그인·회원가입·검색·비밀번호 찾기·상품등록·주문조회) good / bad + 도구를 시험하는 변형 8종
fixtures/specs/               화면기획서 md / pdf / 정답(golden) — 화면마다 한 벌
├── multi_spec.md               통합 문서 — 화면별 md 에서 조립한다 (직접 고치지 않는다)
├── onboarding_spec.md          가입→로그인→상품등록 — 화면 셋을 지나는 흐름이 사는 문서 (조립)
└── _multi_*.md · _onboarding_*.md  조립용 조각 ('_' 로 시작하면 PDF 로 만들지 않는다)
fixtures/figma/               Figma API 응답 픽스처 (합성 + 실물, 다듬기는 fetch 스크립트가)
scripts/                      기획서 PDF 생성 · 통합 문서 조립 · Figma fetch · 데모 자료 생성
└── legacy/                   파이프라인 이전에 만든 독립 추출 도구 (HWPX·OCR)
docs/
├── specs/                    Prova_서비스명세서.md (개발 기준 문서)
├── reference/                옛 추출기 안내
├── teaching/                 티칭 노트 24개 + overview.html (그림 자료)
├── measurements/             실측 결과 — 보고에 쓰는 숫자의 출처
├── pr/                       PR 읽기 안내
├── superpowers/              지난 설계·구현 계획서 (도구가 남긴 것)
├── cheetah-setup.md          GPU 서버 vLLM 세팅 절차
├── design-decisions.md       명세서와 다르게 한 38군데
├── lessons.md                코드를 돌려서 알게 된 것들
├── roadmap.md                아직 안 한 것
└── README.md                 문서 안내
```
