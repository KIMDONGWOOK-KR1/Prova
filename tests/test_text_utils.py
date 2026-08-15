"""텍스트 정규화 규칙 — PDF 추출 문구와 화면 실제 문구를 비교하기 위한 기준.

이 테스트가 못 박는 명제: PDF에서 뽑은 에러 문구와 브라우저 화면에서 읽은
에러 문구는 공백 배치가 다를 수 있다. 그래도 '같은 문구'로 판정해야 한다.
"""

from prova.text_utils import contains_loose, loosen, normalize_ws, strip_cid


class TestNormalizeWs:
    def test_줄바꿈을_공백으로_바꾸고_연속공백을_하나로(self):
        assert normalize_ws("비밀번호는 8자\n이상이며") == "비밀번호는 8자 이상이며"
        assert normalize_ws("a  \t b\n\nc") == "a b c"

    def test_앞뒤_공백_제거(self):
        assert normalize_ws("  로그인  ") == "로그인"

    def test_None_안전(self):
        assert normalize_ws(None) == ""


class TestLoosen:
    def test_모든_공백을_제거한다(self):
        assert loosen("비밀번호는 8자 이상") == "비밀번호는8자이상"

    def test_PDF_줄바꿈_위치가_달라도_같은_정규형(self):
        # 같은 원문이 PDF에서 두 가지로 깨져 나온 경우
        from_pdf_cell = "비밀번호는 8자\n이상이며 대문자·\n특수문자를 각\n1자 이상\n포함해야 합니다."
        from_pdf_body = "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자\n이상 포함해야 합니다."
        from_browser = "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다."
        assert loosen(from_pdf_cell) == loosen(from_browser)
        assert loosen(from_pdf_body) == loosen(from_browser)

    def test_문구가_실제로_다르면_다른_정규형(self):
        # 구현이 다른 문구를 쓴 경우 — 이건 반드시 FAIL로 잡아야 한다
        spec = "이메일 또는 비밀번호가 올바르지 않습니다."
        impl = "로그인 정보를 확인해주세요."
        assert loosen(spec) != loosen(impl)


class TestContainsLoose:
    def test_화면_전체_텍스트에서_기대문구를_찾는다(self):
        page = "로그인\n이메일\n비밀번호\n비밀번호는 8자 이상이며 대문자·특수문자를\n각 1자 이상 포함해야 합니다.\n로그인"
        expected = "비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다."
        assert contains_loose(page, expected)

    def test_없는_문구는_찾지_못한다(self):
        assert not contains_loose("로그인\n이메일", "필수 입력 항목입니다.")

    def test_빈_기대문구는_찾은_것으로_보지_않는다(self):
        # 빈 문자열은 어디에나 포함되므로, 실수로 PASS가 나가는 걸 막는다
        assert not contains_loose("아무 텍스트", "")


class TestStripCid:
    def test_cid_자리표시자를_제거한다(self):
        assert strip_cid("(cid:127) 필수 입력이다.").strip() == "필수 입력이다."

    def test_여러개도_제거한다(self):
        assert "cid" not in strip_cid("(cid:3)가(cid:127)나(cid:9)")

    def test_normalize_ws가_cid를_함께_걷어낸다(self):
        assert normalize_ws("(cid:127) 최소 길이는 8자다.") == "최소 길이는 8자다."

    def test_loosen도_cid에_영향받지_않는다(self):
        assert loosen("(cid:127) 8자 이상") == loosen("8자 이상")
