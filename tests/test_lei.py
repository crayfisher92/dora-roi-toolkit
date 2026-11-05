import pytest

from dora_roi.lei import explain_lei_error, is_valid_lei, lei_check_digits, make_lei

# Public, well-known example LEIs (checksums verified by MOD 97-10)
VALID = ["529900T8BM49AURSDO55", "5493001KJTIIGC8Y1R12", "HWUPKR0MPOU8FGXBT394"]


@pytest.mark.parametrize("lei", VALID)
def test_valid_leis(lei: str) -> None:
    assert is_valid_lei(lei)
    assert explain_lei_error(lei) == ""


def test_checksum_failure_suggests_digits() -> None:
    msg = explain_lei_error("529900T8BM49AURSDO56")
    assert "checksum" in msg and "55" in msg


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("529900T8BM49AURSDO5", "20 characters"),
        ("529900t8bm49aursdo55", "uppercase"),
        ("529900T8BM49AURSDOAB", "check digits"),
    ],
)
def test_format_errors(value: str, fragment: str) -> None:
    assert fragment in explain_lei_error(value)
    assert not is_valid_lei(value)


def test_make_lei_roundtrip() -> None:
    lei = make_lei("ABCDEF0123456789XY")
    assert len(lei) == 20 and is_valid_lei(lei)
    assert lei_check_digits("529900T8BM49AURSDO") == "55"


def test_make_lei_rejects_bad_base() -> None:
    with pytest.raises(ValueError):
        lei_check_digits("short")
