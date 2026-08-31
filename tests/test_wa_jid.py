import pytest

from pa.errors import UsageError
from wa import jid


def test_existing_jids_pass_through():
    assert jid.normalise("61412345678@s.whatsapp.net") == "61412345678@s.whatsapp.net"
    assert jid.normalise("123-456@g.us") == "123-456@g.us"
    assert jid.normalise("61412345678@lid") == "61412345678@lid"


def test_unknown_jid_domain_rejected():
    with pytest.raises(UsageError) as info:
        jid.normalise("someone@example.com")
    assert "Unrecognised JID domain" in str(info.value)


def test_malformed_jid_rejected():
    with pytest.raises(UsageError):
        jid.normalise("@g.us")


@pytest.mark.parametrize("raw", [
    "61412345678", "+61 412 345 678", "+61-412-345-678", "(61) 412345678",
])
def test_international_numbers_normalise(raw):
    assert jid.normalise(raw) == "61412345678@s.whatsapp.net"


def test_local_leading_zero_is_refused_not_guessed():
    # Guessing a country code here would deliver a message to a stranger.
    with pytest.raises(UsageError) as info:
        jid.normalise("0412345678")
    assert "international" in str(info.value).lower()


def test_too_short_is_refused():
    with pytest.raises(UsageError) as info:
        jid.normalise("12345")
    assert "country code" in str(info.value)


def test_empty_and_digitless_refused():
    for bad in ("", "   ", "abcdef"):
        with pytest.raises(UsageError):
            jid.normalise(bad)


def test_is_group():
    assert jid.is_group("123@g.us")
    assert not jid.is_group("61412345678@s.whatsapp.net")
    assert not jid.is_group("")


def test_phone_of():
    assert jid.phone_of("61412345678@s.whatsapp.net") == "61412345678"
    assert jid.phone_of("123@g.us") == ""
    assert jid.phone_of("") == ""


def test_describe_prefers_a_name():
    assert jid.describe("61412345678@s.whatsapp.net", "Alex") == "Alex"
    assert jid.describe("123@g.us", "Project Team") == "Project Team (group)"
    assert jid.describe("61412345678@s.whatsapp.net") == "61412345678"
    assert jid.describe("123@g.us") == "group 123"
    assert jid.describe("61412345678@s.whatsapp.net", "   ") == "61412345678"
