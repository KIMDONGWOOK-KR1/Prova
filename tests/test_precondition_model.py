"""전제 계약이 직렬화 왕복에서 깨지지 않는지 고정한다.

golden(json) <-> 모델 왕복이 S1 정확도 측정의 기반이므로, 필드가 기본값으로
사라지면 골든 대조가 조용히 무력해진다.
"""
from prova.models import Precondition, ScreenSpec, StepResult, TestCase


def test_전제가_골든_왕복에서_보존된다():
    spec = ScreenSpec(
        screen_id="product", screen_name="상품 등록", url_path="/product",
        precondition=Precondition(
            requires_login=True,
            account_email="seller@test.com", account_password="Seller1!"),
    )
    again = ScreenSpec.model_validate(spec.model_dump())
    assert again.precondition is not None
    assert again.precondition.account_email == "seller@test.com"
    assert again.precondition.login_screen_id == "login"


def test_전제가_없는_화면은_None_이다():
    spec = ScreenSpec(screen_id="login", screen_name="로그인", url_path="/login")
    assert spec.precondition is None


def test_스텝결과의_phase_기본은_test_다():
    r = StepResult(seq=1, action="navigate")
    assert r.phase == "test"
