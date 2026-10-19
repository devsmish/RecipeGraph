"""Unit tests for parse_uuid / InvalidIdError (ids.py)."""

import uuid

import pytest

from errors import PublicError
from ids import InvalidIdError, parse_uuid

VALID = uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.parametrize(
    "value",
    [
        "12345678-1234-5678-1234-567812345678",  # canonical form
        "12345678-1234-5678-1234-567812345678".upper(),  # uppercase
        "12345678123456781234567812345678",  # without hyphens
    ],
)
def test_valid_uuid_forms_are_accepted(value):
    assert parse_uuid(value, "id") == VALID


def test_returns_a_uuid_object():
    assert isinstance(parse_uuid(str(uuid.uuid4()), "id"), uuid.UUID)


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "",
        "   ",
        "not-a-uuid",
        "12345678-1234-5678-1234-56781234567",  # one character short
        "12345678-1234-5678-1234-5678123456789",  # one character too long
        "g" * 32,  # right length, not hex
        "x" * 10_000,  # absurdly long
        None,
        12345,
    ],
)
def test_malformed_values_raise_invalid_id_error(value):
    with pytest.raises(InvalidIdError):
        parse_uuid(value, "categoryId")


def test_message_names_the_field_and_does_not_echo_the_value():
    with pytest.raises(InvalidIdError) as caught:
        parse_uuid("secret-looking-garbage", "ingredients[2].ingredientId")

    assert str(caught.value) == 'Invalid ID for "ingredients[2].ingredientId": expected a UUID'
    assert "secret-looking-garbage" not in str(caught.value)


def test_invalid_id_error_is_a_public_error():
    assert issubclass(InvalidIdError, PublicError)


def test_original_value_error_is_not_chained():
    # `from None`: the traceback shouldn't drag in uuid's own ValueError (and the raw value
    # inside its message) when this error is logged.
    with pytest.raises(InvalidIdError) as caught:
        parse_uuid("abc", "id")

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
