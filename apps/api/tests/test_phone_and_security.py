import pytest

from app.core.phone import InvalidPhoneError, mask_phone, normalize_phone
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_token,
    password_problems,
    verify_password,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01012345678", "01012345678"),
        ("+201012345678", "01012345678"),
        ("00201112345678", "01112345678"),
        ("201212345678", "01212345678"),
        ("010 1234 5678", "01012345678"),
        ("٠١٥١٢٣٤٥٦٧٨", "01512345678"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["0101234567", "01312345678", "abc", "", "+1 555 1234"])
def test_invalid_phone(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_mask_phone() -> None:
    assert mask_phone("01012345678") == "********678"


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse")
    assert not verify_password(h, "wrong")
    assert not verify_password(None, "anything")
    assert not verify_password("not-a-hash", "anything")


def test_session_tokens_are_random_and_hashed() -> None:
    a, b = generate_session_token(), generate_session_token()
    assert a != b and a.startswith("gd_") and len(a) > 40
    assert hash_token(a) != a and len(hash_token(a)) == 64


def test_password_policy() -> None:
    assert password_problems("short") != []
    assert password_problems("aaaaaaaaaa") != []
    assert password_problems("x01012345678y", phone="01012345678") != []
    assert password_problems("Str0ng-pass-123") == []
