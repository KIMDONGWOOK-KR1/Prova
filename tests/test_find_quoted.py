"""기획서 문장에서 따옴표 안 문구를 뽑는다 — 짝이 맞는 따옴표만, 큰따옴표 먼저 (2026-09-23).

## 왜

케이스 생성기는 따옴표 안을 40자까지만 읽었다. parabank 의 성공 문구
"Your account was created successfully. You are now logged in." 은 61자라 기대값에
들어가지 못했고, 정상 가입 케이스가 '에러 없음' 만 보고 통과했다(약한 확인).

한도만 늘리면 다른 구멍이 커진다. 따옴표 목록에 아포스트로피(')가 들어 있어서
"Welcome! You're logged in." 은 "Welcome! You" 로 잘리고, 따옴표가 없는 영어 문장
"user's profile ... John's" 에서도 ' 와 ' 사이를 문구로 잡는다. 40자 한도가 우연히
그걸 줄여 주고 있었을 뿐이다. 그래서 짝을 맞추고, 큰따옴표 계열을 먼저 본다.
"""

from prova.text_utils import find_quoted


def test_긴_성공_문구도_읽는다():
    text = ('모든 필수 값을 올바르게 입력하면 '
            '"Your account was created successfully. You are now logged in." 문구를 노출한다.')
    assert find_quoted(text, 200) == [
        "Your account was created successfully. You are now logged in."]


def test_큰따옴표_안의_아포스트로피는_문구의_일부다():
    assert find_quoted('"Welcome! You\'re logged in." 문구를 노출한다', 200) == [
        "Welcome! You're logged in."]


def test_따옴표_없는_영어_문장의_아포스트로피는_문구가_아니다():
    assert find_quoted("The user's profile shows John's name.", 200) == []


def test_굽은_따옴표도_짝으로():
    assert find_quoted("“환영합니다” 를 노출한다", 200) == ["환영합니다"]


def test_큰따옴표가_없으면_작은따옴표_짝을_쓴다():
    assert find_quoted("'필수 입력 항목입니다.' 를 노출한다", 200) == ["필수 입력 항목입니다."]


def test_여러_문구는_순서대로():
    assert find_quoted('"가" 가 아니라 "나다" 와 "다라" 를', 200) == ["나다", "다라"]


def test_한도를_넘는_문구는_잡지_않는다():
    assert find_quoted('"' + "가" * 30 + '"', 20) == []
