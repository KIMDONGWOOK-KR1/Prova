"""Prova 데이터 모델 — 서비스명세서 §3의 타입 계약.

이 파일이 파이프라인 전체의 계약이다. S1~S6의 각 단계는 여기 정의된 타입을
입력으로 받아 다음 타입을 출력한다:

    ScreenSpec -> TestCase[] -> ElementLocation -> StepResult[] -> Verdict -> TestReport

명세서는 TypedDict로 규정했으나 pydantic BaseModel을 쓴다. 이유는 두 가지다.
1) LLM 출력 검증: vLLM의 guided_json에 넘길 JSON Schema를 model_json_schema()로
   그대로 뽑아낼 수 있다. TypedDict는 런타임 검증을 해주지 않는다.
2) 필드 오타·타입 불일치를 실행 시점에 즉시 잡는다.

로그인 화면만 검증하는 1차 목표라도 타입은 명세서 전체를 정의한다.
회원가입·검색으로 확장할 때 이 파일을 다시 손대지 않기 위해서다.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# S1 · 설계 문서에서 추출한 화면 명세
# ---------------------------------------------------------------------------

# "list" 는 반복 목록(검색 결과 목록 등)이다. 다른 유형과 성질이 다르다 —
# 값을 채우는 대상이 아니고, 화면에 몇 개가 렌더됐는지를 세는 대상이다.
# 그래서 S2 의 _fillable_inputs 에서 빠지고, S3 는 별도 경로로 다룬다.
ElementType = Literal["input", "button", "link", "select", "checkbox", "text", "list"]


class UIElement(BaseModel):
    """화면을 구성하는 UI 요소 하나.

    constraints가 이 프로젝트의 핵심 필드다. 기획서에 적힌 입력 검증 규칙
    (비밀번호 복잡도, 이메일 형식 등)이 여기 담기고, S2가 이 규칙 하나하나를
    '위반 케이스'로 전개해서 구현이 규칙을 실제로 강제하는지 확인한다.

    지원하는 constraints 키:
        format          "email" 등 형식 지정
        min_length      최소 길이
        max_length      최대 길이
        require_uppercase / require_lowercase / require_digit / require_special
                        해당 문자 종류의 최소 개수
        pattern         정규식
        same_as         다른 요소와 값이 같아야 한다 (값은 그 요소의 element_id)
    """

    element_id: str
    type: ElementType
    label: str
    required: bool = False
    constraints: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    placeholder: Optional[str] = None
    # select 의 선택 항목. 기획서의 '선택 목록' 을 그대로 담는다.
    #
    # 왜 constraints 가 아니라 별도 필드인가: constraints 는 '위반값을 만들 수
    # 있는 규칙' 을 담는 곳이다. 선택 항목은 규칙이 아니라 값의 후보 집합이고,
    # 정상 케이스에 넣을 값을 여기서 고른다. constraints 에 섞으면
    # rule_expander 가 이것도 위반 규칙으로 착각해 전개하려 한다.
    options: list[str] = Field(default_factory=list)
    # 기획서가 제시한 유효 입력 예시 (테스트 계정, 샘플 데이터 등).
    #
    # 왜 필요한가: constraints 를 만족하는 값을 코드로 만들 수는 있지만, 그 값이
    # 시스템에 '등록된' 값인지는 알 수 없다. 로그인 화면이 대표적이다 — 규칙을
    # 다 지킨 비밀번호라도 등록된 계정의 것이 아니면 로그인은 실패한다. 그러면
    # 정상 케이스가 구현 결함 없이도 FAIL 이 되어 오탐이 된다.
    # 기획서에 테스트 계정·예시 데이터가 있으면 S1 이 여기에 담고, 정상 케이스는
    # 그 값을 쓴다.
    sample_value: Optional[str] = None


class Scenario(BaseModel):
    """기획서가 직접 제시한 '이 값을 넣으면 이렇게 된다' 한 건.

    ## 왜 규칙(constraints)으로 표현할 수 없는가

    검색 화면에서 드러난 것이다. 로그인·회원가입의 검증은 모두 '값 자체가 규칙을
    어겼는가'였다. 그래서 규칙에서 위반값을 만들어낼 수 있었다. 검색은 다르다 —
    '노트북을 검색하면 3건이 나와야 한다' 는 값의 흠이 아니라 **시스템 상태에
    대한 기대**다. 규칙이 없으므로 위반값을 만들 수도 없다.

    그래서 rule_expander 를 거치지 않는 별도 경로로 둔다. 기획서가 데이터를
    제시하지 않으면 이 검증은 불가능하고, 그건 기획서의 한계이지 도구의 한계가
    아니다.

    ## expect_text 하나로 좁힌 이유

    Expectation 전체를 담으면 표현력은 늘지만 S1 이 type 열거값까지 골라야 한다.
    로컬 7B 에 선택지를 늘리면 추출이 흔들리고, S1 이 흔들리면 검증이 조용히
    무력해진다. 기획서가 '노출돼야 하는 문구' 를 적어 두는 형태면 문구 비교만으로
    충분하므로, 모델이 표에서 문구를 옮기기만 하면 되게 만들었다.

    나중에 건수를 DOM 에서 직접 세거나 URL 을 확인해야 하면 **필드를 추가**한다.
    이 필드의 의미를 넓혀 재해석하면 안 된다 — 필드 이름이 할 수 있는 일을
    말하고 있어야 한다.

    ## expect_count 를 나중에 추가한 이유

    위 문단이 예고한 그 확장이다. expect_text 는 화면이 건수를 **문구로 보여줄
    때만** 쓸 수 있다. "검색 결과 3건" 을 안 찍고 목록만 렌더하는 화면에서는
    문구 비교가 아무것도 확인하지 못한다. 그때 건수를 확인하려면 DOM 의 반복
    요소를 직접 세야 한다.

    expect_text 를 "3" 으로 두고 재해석하지 않은 이유가 여기 있다 — 그러면 화면
    아무 곳의 "3" 에나 걸린다(가격, 페이지 번호). 세는 것과 문구를 찾는 것은
    다른 일이므로 필드도 다르다.
    """

    # element_id -> 입력값. 여기 없는 입력 요소는 정상값으로 채운다.
    given: dict[str, str] = Field(default_factory=dict)
    # 화면에 노출돼야 하는 문구 (공백 무시 비교)
    expect_text: str
    # 반복 목록에 렌더돼야 하는 항목 수. 기획서가 건수를 표로 적어 둔 경우만
    # 채워진다. None 이면 건수 검증을 만들지 않는다 — 0 과 구별해야 한다.
    # (0 은 '아무것도 나오지 않아야 한다' 는 확인할 값이 있는 상태다)
    expect_count: Optional[int] = None
    # 화면에 **나타나면 안 되는** 문구.
    #
    # 지금까지의 검증은 전부 '있어야 할 것이 있는가' 였다. 이건 반대 방향이고,
    # 그 구분이 필요한 요구사항이 실재한다 — 아이디/비밀번호 찾기 화면에서
    # 등록되지 않은 이메일에 '등록되지 않은 이메일입니다' 를 노출하면 공격자가
    # 계정 존재 여부를 알아낼 수 있다(account enumeration). 그래서 기획서는
    # 미등록 계정에도 같은 성공 문구를 노출하라고 적는다.
    #
    # expect_text 로 표현할 수 없다. '보냈습니다' 가 떠 있으면서 '등록되지
    # 않았습니다' 도 함께 떠 있는 화면이 가능하고, 그 화면은 요구를 어긴다.
    # 있어야 할 것과 없어야 할 것은 다른 확인이므로 필드도 다르다.
    expect_absent: Optional[str] = None


class Precondition(BaseModel):
    """화면 진입 전에 세워야 할 전제. 지금은 로그인 하나만 표현한다.

    kind 일반화는 두 번째 전제가 실재할 때(스펙 §7)에 한다.
    """

    requires_login: bool
    account_email: str
    account_password: str
    login_screen_id: str = "login"


class ScreenSpec(BaseModel):
    """설계 문서에서 추출한 화면 단위 명세. S1의 출력.

    1화면 = 1객체. warnings에는 파싱하지 못한 부분을 기록해 부분 결과를 유지한다
    (명세서 §2-S1 실패 처리).
    """

    screen_id: str
    screen_name: str
    url_path: str
    elements: list[UIElement] = Field(default_factory=list)
    # 기획서가 제시한 입력-결과 예시. 규칙으로 표현할 수 없는 검증이 여기 담긴다.
    scenarios: list[Scenario] = Field(default_factory=list)
    success_condition: str = ""
    failure_conditions: list[str] = Field(default_factory=list)
    # 필수 입력 누락 시 노출하는 화면 공통 문구.
    #
    # 왜 요소가 아니라 화면에 두는가: 기획서는 요소별 error_message 를 '그 요소의
    # 형식 검증 실패' 문구로 쓰고, 필수값 누락은 화면 단위 공통 문구로 따로
    # 적는 경우가 많다. 실제 로그인 기획서도 그렇다 (§2 표의 에러 메시지는
    # 형식 검증용, §4 실패 조건 표에 "필수 입력 항목입니다." 가 따로 있다).
    # 이 값이 없으면 required 위반 케이스는 문구를 특정하지 않고
    # error_shown 으로 검증한다 — 문구를 억측하면 오탐이 된다.
    required_message: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    # 이 화면에 진입하기 위한 전제. 없으면 누구나 진입할 수 있다.
    precondition: Optional[Precondition] = None

    def element_by_id(self, element_id: str) -> Optional[UIElement]:
        return next((e for e in self.elements if e.element_id == element_id), None)


class Flow(BaseModel):
    """화면을 이어서 밟는 한 흐름. 기획서가 '화면 흐름' 표로 적어 둔 것.

    ## 왜 화면별 검증만으로는 부족한가

    회원가입 화면의 케이스는 전부 통과하고, 로그인 화면의 케이스도 전부 통과하는데,
    **가입한 계정으로 로그인이 안 되는** 구현이 있을 수 있다. 가입 화면은 입력을
    올바르게 검증하고 완료 화면까지 보여주지만 계정을 실제로 등록하지 않은 경우다.

    화면 하나만 보면 어느 쪽도 결함이 아니다. 결함은 **두 화면 사이**에 있고,
    그래서 화면을 이어서 밟아 봐야만 드러난다.

    ## 무엇을 담고 무엇을 담지 않는가

    담는 것은 화면 순서(screen_ids)와 마지막에 확인할 문구뿐이다. 중간 화면이
    성공했는지는 **그 화면의 성공 조건**으로 확인한다 — 이미 ScreenSpec 에 있는
    것을 흐름 표에 다시 적게 하면 두 곳이 어긋날 수 있다.

    입력값도 담지 않는다. 각 화면의 정상값(sample_value 기반)을 쓰고, **앞 화면에
    넣은 값을 뒤 화면의 같은 라벨에 다시 넣는다.** 사람이 손으로 확인할 때 하는 일이
    정확히 그것이다 — 가입에 쓴 이메일로 로그인한다. 라벨이 다르면 이어지지 않으므로
    기획서가 라벨을 일관되게 쓴다는 전제가 깔린다. 그 전제가 깨지면 값이 이어지지
    않아 흐름이 실패하는데, 그건 기획서의 문제이므로 경고로 알린다.
    """

    flow_id: str
    title: str = ""
    # 밟을 화면의 screen_id 순서. 2개 이상이어야 흐름이다.
    screen_ids: list[str] = Field(default_factory=list)
    # 화면을 옮길 때 누를 요소의 라벨. 전이마다 하나씩이므로
    # len(via) 는 len(screen_ids) - 1 이 된다. 비었거나 짧으면 그 전이는
    # 주소로 직접 이동한다.
    #
    # ## 왜 이 구분이 필요한가
    #
    # 주소로 이동하면 **화면을 잇는 요소 자체가 검증되지 않는다.** 도구가 스스로
    # 주소를 치고 들어가므로, 완료 화면의 '로그인하러 가기' 링크가 엉뚱한 곳을
    # 가리켜도 흐름은 통과한다. 잘못된 링크는 실무에서 흔한 기획-구현 불일치인데
    # 그 경로가 비어 있었다.
    #
    # 라벨이 있으면 그 요소를 눌러서 옮기고, 다음 화면의 경로에 도착했는지
    # 확인한다. 그러면 세 가지가 잡힌다 — 링크가 없다(탐지 실패), 엉뚱한 경로를
    # 가리킨다(도착 확인 실패), 기획서는 링크인데 버튼으로 구현됐다(유형 불일치).
    via: list[str] = Field(default_factory=list)
    # 마지막 화면에서 확인할 문구. 비면 마지막 화면의 성공 조건을 쓴다.
    expect_text: str = ""


class SpecDocument(BaseModel):
    """설계 문서 하나. 화면이 여럿일 수 있다.

    ## 왜 ScreenSpec 을 감싸는 타입을 따로 뒀는가

    1차에서는 화면당 PDF 한 개를 전제했다. 실물 기획서는 그렇게 오지 않는다 —
    한 문서에 여러 화면이 들어 있고, 화면 사이의 흐름도 그 문서에 적혀 있다.

    ScreenSpec 에 화면 목록을 담게 만들지 않은 이유: ScreenSpec 은 '화면 하나' 라는
    이름이고, 거기에 다른 화면을 담으면 이름이 거짓말을 시작한다. 그리고 흐름은
    어느 한 화면의 성질이 아니라 문서의 성질이다.

    warnings 는 **문서 수준** 경고다 (화면 분리 실패, 흐름이 없는 화면 참조 등).
    화면 하나에 대한 경고는 그 ScreenSpec.warnings 에 남는다 — 어디를 고쳐야 하는지
    가 경고의 위치로 드러나야 한다.
    """

    source: str = ""
    screens: list[ScreenSpec] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def screen_by_id(self, screen_id: str) -> Optional[ScreenSpec]:
        return next((s for s in self.screens if s.screen_id == screen_id), None)

    @property
    def all_warnings(self) -> list[str]:
        """문서 경고 + 화면별 경고. 리포트가 한 곳에 모아 보여주는 데 쓴다."""
        out = list(self.warnings)
        for screen in self.screens:
            prefix = f"[{screen.screen_id}] " if len(self.screens) > 1 else ""
            out.extend(f"{prefix}{w}" for w in screen.warnings)
        return out


# ---------------------------------------------------------------------------
# S2 · 테스트 케이스
# ---------------------------------------------------------------------------

# check / uncheck 를 fill 과 나눠 둔 이유
#
# 체크박스에 fill() 을 부르면 Playwright 가 "Element is not an <input> that can be
# filled" 로 실패한다. 그 실패는 요소 조작 오류(input_error)로 기록되는데, 정작
# 검증하려던 것은 '약관 미동의 시 에러가 뜨는가' 였다. 액션을 나누지 않으면
# 회원가입 화면에서 체크박스 케이스가 전부 조작 오류로 뭉개져, 구현 결함이 있는지
# 없는지 알 수 없게 된다.
ActionType = Literal[
    "navigate", "fill", "click", "select", "check", "uncheck", "wait", "assert"
]
CaseType = Literal["positive", "negative", "boundary"]

# expected.type 이 가질 수 있는 값
#   error_message  특정 문구가 노출돼야 한다 (기획서에 문구가 명시된 경우)
#   error_shown    문구는 특정하지 않고, 에러가 노출되고 이동하지 않아야 한다
#                  (기획서에 문구가 없어 문구까지 못 박으면 오탐이 되는 경우)
#   result_count   반복 목록에 정확히 N 개가 렌더돼야 한다 (문구가 아니라 개수)
#   options_present 선택 요소에 기획서가 적은 항목이 모두 있어야 한다
#   placeholders_match 입력 안내 문구가 기획서와 같아야 한다
#   labels_findable 기획서의 라벨로 화면에서 요소를 찾을 수 있어야 한다
#   text_absent    특정 문구가 화면에 **나타나지 않아야** 한다
#                  (지금까지와 방향이 반대다. 계정 존재 여부 노출처럼 '알려주면
#                   안 되는' 요구가 실재한다 — Scenario.expect_absent 참고)
ExpectedType = Literal[
    "toast_or_redirect", "error_message", "error_shown", "redirect", "text_visible",
    "result_count", "options_present", "placeholders_match", "labels_findable",
    "text_absent",
]


class Expectation(BaseModel):
    """케이스의 기대 결과.

    negative 케이스에서는 대체로 type='error_message' 이고, value에 기획서에
    적힌 에러 문구가 들어간다. 그 문구가 화면에 나타나지 않으면 -> 구현이 규칙을
    강제하지 않는다는 뜻이므로 FAIL 이다. 이게 Prova가 증명하려는 바로 그것이다.
    """

    type: ExpectedType
    value: str = ""
    url_contains: Optional[str] = None  # 기대하는 URL 조각 (예: "/dashboard")
    # --- type="result_count" 전용 ---
    #
    # count 를 value 에 문자열로 담지 않은 이유: value 는 '화면에서 찾을 문구' 다.
    # 개수를 거기 넣으면 판정 함수가 value 를 유형에 따라 다르게 해석해야 하고,
    # 그 순간 필드 이름이 거짓말을 시작한다. count_target 도 마찬가지다 —
    # 세는 대상(목록의 라벨)은 기대값이 아니라 '어디를 볼 것인가' 다.
    count: Optional[int] = None
    count_target: Optional[str] = None  # 셀 반복 목록의 라벨
    # --- type="options_present" 전용 ---
    #
    # count/count_target 과 같은 모양이다 — '무엇을 볼 것인가'(라벨)와 '무엇을
    # 기대하는가'(항목 목록)를 나눠 담는다. value 에 쉼표로 이어 담지 않은 이유는
    # 같다: value 는 '화면에서 찾을 문구' 이고, 목록을 거기 넣으면 판정 함수가
    # value 를 유형에 따라 다르게 해석해야 한다.
    options: list[str] = Field(default_factory=list)
    option_target: Optional[str] = None  # 확인할 선택 요소의 라벨
    # --- type="placeholders_match" 전용 ---
    #
    # 라벨 -> 기대 안내 문구. 요소마다 케이스를 만들지 않고 화면 하나에 모으는 이유는
    # generator._placeholder_case 에 적어 뒀다.
    placeholders: dict[str, str] = Field(default_factory=dict)
    # --- type="labels_findable" 전용 ---
    #
    # 화면에서 찾을 수 있어야 하는 라벨들.
    #
    # 이 확인이 왜 따로 필요한가: 2차 경로(화면 이미지로 찾기)를 켜면 라벨로 못 찾은
    # 요소도 케이스가 통과한다. 그러면 **'기획서의 라벨로 요소를 지목할 수 없다' 는
    # 사실이 리포트에서 사라진다.** 보정은 케이스를 살리는 것이고, 지적은 그대로
    # 남아야 한다.
    labels: list[str] = Field(default_factory=list)


class TestStep(BaseModel):
    """실행 단위 하나.

    target은 selector가 아니라 '이메일', '로그인' 같은 자연어 라벨이다.
    실제 요소로 변환하는 일은 S3(Grounder)가 맡는다. 이렇게 분리해두면
    같은 TestCase를 selector 방식과 VLM 방식 양쪽으로 실행해 비교할 수 있다.
    """

    # pytest 가 이름 때문에 테스트 클래스로 오인해 수집하려 하는 것을 막는다.
    # 명세서 §3 의 용어이므로 클래스 이름은 바꾸지 않는다.
    __test__ = False

    seq: int
    action: ActionType
    target: str = ""
    value: Optional[str] = None
    expected: Optional[Expectation] = None


class TestCase(BaseModel):
    """하나의 검증 시나리오. S2의 출력.

    violates에는 이 케이스가 위반하는 규칙을 '하나만' 적는다. 명세서 예시는
    require_uppercase와 require_special을 동시에 위반시켰는데, 그러면 FAIL이
    떴을 때 어느 규칙이 미구현인지 분리되지 않는다. 규칙당 케이스 하나가
    원칙이다 (계획서 '핵심 설계 판단 1').
    """

    # pytest 가 이름 때문에 테스트 클래스로 오인해 수집하려 하는 것을 막는다.
    # 명세서 §3 의 용어이므로 클래스 이름은 바꾸지 않는다.
    __test__ = False

    case_id: str
    # 이 케이스가 검증하는 화면. 흐름 케이스에서는 **마지막 화면**을 적는다 —
    # 흐름의 목적이 '마지막 화면에 제대로 도달했는가' 이기 때문이다. 중간 화면에서
    # 끊기면 그건 스텝 실패로 기록되고 그 스텝이 어느 화면인지도 함께 남는다.
    screen_id: str
    title: str
    type: CaseType
    # 이 케이스가 밟는 흐름의 id. 흐름 케이스가 아니면 None.
    # 리포트에서 화면별 구획과 흐름 구획을 나누는 데 쓴다.
    flow_id: Optional[str] = None
    violates: Optional[str] = None
    target_element: Optional[str] = None  # violates 대상 element_id
    steps: list[TestStep] = Field(default_factory=list)
    # 전제를 세우는 스텝. S2 가 코드로 생성하며, 실패하면 FAIL + precondition_failed 로
    # 분류된다 (명세서 §3-2 참조).
    setup_steps: list[TestStep] = Field(default_factory=list)
    expected: Expectation


class ScreenCoverage(BaseModel):
    """한 화면(또는 흐름)을 이번 실행에서 얼마나 확인했는가.

    ## 왜 '몇 건 제외' 만으로는 부족한가

    실모델 측정에서 "회원가입이 잘 되는지 확인해줘" 에 7B 가 17건 중 6건을 골랐다.
    리포트에는 "11건 제외" 라고만 남는데, 그것만 보면 **회원가입 화면을 확인했다고
    읽힌다.** 실제로는 그 화면의 3분의 1만 봤다.

    화면 단위로 세어 두면 "회원가입 6/17" 이 되고, 통과율이 그 화면의 상태를 뜻하지
    않는다는 사실이 드러난다.
    """

    kind: Literal["screen", "flow"] = "screen"
    key: str
    #: 사람이 읽는 이름 (없으면 key 를 쓴다)
    name: str = ""
    selected: int = 0
    total: int = 0
    #: 요청이 이 화면을 이름으로 지목했는가.
    #:
    #: 지목했는데 일부만 골랐다면 특히 위험하다 — 사람은 그 화면을 통째로
    #: 확인했다고 읽는다.
    named: bool = False

    @property
    def partial(self) -> bool:
        return 0 < self.selected < self.total


class CaseSelection(BaseModel):
    """자연어 요청이 어떤 케이스를 고르게 했는지 (S2 이후, S3 이전).

    ## 왜 별도 자료형인가

    이 층은 **미탐을 만들 수 있는 유일한 경로**다. 지금까지 케이스 선택에 LLM 이
    관여하지 않았기 때문에 "리포트에 없는 결함은 없는 결함" 이 성립했다. 요청
    해석이 케이스를 고르기 시작하면, 모델이 잘못 골라서 못 본 것과 정말 없는 것이
    리포트에서 같아 보인다.

    그래서 고른 결과만이 아니라 **무엇을 왜 제외했는지**를 함께 싣는다. 2차 경로
    보정과 대기 시간을 리포트에 남긴 것과 같은 이유다 — 도구가 판단을 했으면 그
    사실이 리포트에 있어야 한다.
    """

    #: 사용자가 쓴 요청 원문. 비어 있으면 요청 없이 전체를 실행한 것이다.
    request: str = ""
    #: 실제로 실행한 case_id (원본 순서 유지)
    selected: list[str] = Field(default_factory=list)
    #: 생성됐지만 이번에 실행하지 않은 case_id. 리포트에서 coverage_gaps 와
    #: 나란히 보인다 — 둘 다 "판정이 아니라 검증 범위에 대한 사실" 이다.
    excluded: list[str] = Field(default_factory=list)
    #: 모델이 밝힌 선택 근거
    reason: str = ""
    #: 요청을 해석하지 못해 전체를 실행했는가.
    #:
    #: 해석 실패는 반드시 '더 많이 검사하는' 쪽으로 넘어진다. 적게 고르면 결함이
    #: 숨지만 많이 고르면 숨지 않는다 — 방향이 한쪽뿐이라 안전한 쪽이 정해져 있다.
    fallback: bool = False
    #: 사람이 목록을 확인하고 승인했는가 (웹 UI 의 계획 확인 단계).
    #:
    #: 모델이 고른 것과 사람이 고른 것을 리포트에서 구분하기 위해 둔다. 사람의
    #: 선택을 모델이 한 것처럼 적으면, 도구가 한 판단을 남기는 것과 반대 방향의
    #: 같은 부정확이다.
    approved: bool = False
    #: 지어낸 case_id, 해석 실패 등 사람이 알아야 할 사실
    warnings: list[str] = Field(default_factory=list)
    #: 화면·흐름별로 몇 건 중 몇 건을 골랐는지. '11건 제외' 만으로는 어느 화면을
    #: 반쪽만 봤는지 알 수 없다 (ScreenCoverage 참고).
    coverage: list[ScreenCoverage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# S3 · 요소 탐지 결과
# ---------------------------------------------------------------------------


class ElementLocation(BaseModel):
    """자연어 target을 실제 조작 가능한 위치로 변환한 결과. S3의 출력.

    1차 범위는 method='selector'만 쓴다. bbox/confidence는 2차 VLM fallback을
    위해 미리 자리를 잡아둔 필드다.
    """

    target: str
    method: Literal["selector", "vlm"] = "selector"
    selector: Optional[str] = None
    bbox: Optional[list[int]] = None  # [x, y, w, h]
    confidence: float = 1.0
    healed: bool = False
    strategy: Optional[str] = None  # 어느 탐지 전략이 적중했는지 (평가용)


# ---------------------------------------------------------------------------
# S4 · 실행 결과
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    """스텝 하나의 실행 결과. S4의 출력."""

    seq: int
    action: str
    target: str = ""
    status: Literal["ok", "error"] = "ok"
    elapsed_ms: int = 0
    screenshot: Optional[str] = None
    dom_snapshot: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    location: Optional[ElementLocation] = None
    # 전제를 세우는 스텝인지 — 리포트가 구분해 보여준다.
    phase: Literal["setup", "test"] = "test"


# ---------------------------------------------------------------------------
# S5 · 판정 / S6 · 리포트
# ---------------------------------------------------------------------------

FailureCategory = Literal[
    "element_not_found",
    "input_error",
    "assertion_mismatch",
    "timeout",
    "page_error",
    "unknown",
    # 전제(로그인 등)를 세우는 단계에서 끊긴 경우. 이 화면 자체의 결함이 아니므로
    # 다른 분류와 구분해 둬야 화면별 집계에서 결함 수에 합치지 않을 수 있다
    # (명세서 §3-6·§3-7).
    "precondition_failed",
]


class Verdict(BaseModel):
    """한 케이스의 PASS/FAIL 판정과 근거. S5의 출력.

    evidence에는 '왜 그렇게 판정했는지'를 사람이 확인할 수 있는 재료를 넣는다.
    기대값, 실제 화면에서 찾은 텍스트, 최종 URL, 스크린샷 경로.
    리포트 완결성(명세서 §9, 목표 100%)이 이 필드에 달려 있다.
    """

    case_id: str
    title: str = ""
    type: CaseType = "positive"
    # 리포트를 화면별로 묶는 데 쓴다. case_id 접두사에서 잘라낼 수도 있지만,
    # 문자열을 다시 파싱해야 하는 값은 필드로 남기는 편이 낫다 — screen_id 에
    # 하이픈이 들어가면 파싱이 조용히 틀린다.
    screen_id: str = ""
    flow_id: Optional[str] = None
    verdict: Literal["PASS", "FAIL"]
    violates: Optional[str] = None
    # 어느 요소의 규칙이었는지. violates 만으로는 부족하다 — 회원가입 화면처럼
    # required 규칙을 가진 요소가 여럿이면 'required 가 FAIL' 만 보고는 어느 입력의
    # 검증이 빠졌는지 알 수 없다.
    target_element: Optional[str] = None
    evidence: dict = Field(default_factory=dict)
    failure_category: Optional[FailureCategory] = None
    failure_detail: Optional[str] = None
    healed: bool = False
    elapsed_ms: int = 0
    step_results: list[StepResult] = Field(default_factory=list)


class TestReport(BaseModel):
    """실행 전체의 최종 리포트. S6의 출력."""

    # pytest 가 이름 때문에 테스트 클래스로 오인해 수집하려 하는 것을 막는다.
    # 명세서 §3 의 용어이므로 클래스 이름은 바꾸지 않는다.
    __test__ = False

    run_id: str
    target_url: str
    spec_source: str = ""
    summary: dict = Field(default_factory=dict)  # {total, pass, fail, healed, pass_rate}
    cases: list[Verdict] = Field(default_factory=list)
    created_at: str = ""
    #: 자연어 요청으로 케이스를 골랐다면 그 내역. 요청 없이 전체를 실행했으면 None.
    #: 통과율만 보는 사람이 '무엇을 안 봤는지' 를 알 수 있어야 한다.
    selection: Optional[CaseSelection] = None

    @staticmethod
    def summarize(verdicts: list[Verdict]) -> dict:
        total = len(verdicts)
        passed = sum(1 for v in verdicts if v.verdict == "PASS")
        summary = {
            "total": total,
            "pass": passed,
            "fail": total - passed,
            "healed": sum(1 for v in verdicts if v.healed),
            # 기다려서 통과한 케이스 수. '이 화면은 결과를 늦게 보여준다' 는 사실이고,
            # 지우면 통과율만 보는 사람이 그 통과의 성질을 알 수 없다.
            "settled": sum(1 for v in verdicts if v.evidence.get("settled_ms")),
            "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        }
        # 화면별 내역. 화면이 여럿이면 전체 통과율만으로는 어디가 문제인지 알 수
        # 없다 — 29건 중 4건 실패가 한 화면에 몰린 것과 세 화면에 퍼진 것은
        # 읽는 사람이 취할 행동이 다르다.
        #
        # 흐름은 화면 칸에 넣지 않고 따로 센다. 흐름 케이스의 screen_id 는 마지막
        # 화면인데, 그걸 그 화면의 실패로 합치면 **그 화면에 결함이 하나 더 있는
        # 것처럼 읽힌다.** 실제로는 화면 사이의 결함이고 고칠 곳도 다르다.
        by_screen: dict[str, dict] = {}
        by_flow: dict[str, dict] = {}
        for v in verdicts:
            bucket = by_flow if v.flow_id else by_screen
            key = v.flow_id or v.screen_id or "?"
            # "precondition" 칸은 기본값에 넣지 않는다. 전제 실패가 하나도
            # 없는 화면·흐름까지 이 칸을 달면 기존에 {total, pass, fail} 만
            # 보던 소비자(요약 카드, 기존 테스트의 dict 동등 비교)가 깨진다.
            # 실제로 전제 실패가 있을 때만 칸을 만든다.
            slot = bucket.setdefault(key, {"total": 0, "pass": 0, "fail": 0})
            slot["total"] += 1
            if v.verdict == "PASS":
                slot["pass"] += 1
            elif v.failure_category == "precondition_failed":
                # 전제(로그인 등)를 세우지 못해 난 FAIL 은 이 화면의 결함이
                # 아니다. "fail" 에 합치면 같은 결함(예: 로그인 화면의 결함)이
                # 그 결함을 전제로 삼는 화면마다 하나씩 더 있는 것처럼 불어난다
                # (명세서 §3-6·§3-7). 그래서 별도 칸에 센다 — 전체 요약의
                # total/pass/fail 은 그대로 두고(케이스 자체는 여전히 FAIL),
                # 화면별 결함 귀속만 바꾼다.
                slot["precondition"] = slot.get("precondition", 0) + 1
            else:
                slot["fail"] += 1
        summary["by_screen"] = by_screen
        summary["by_flow"] = by_flow
        return summary
