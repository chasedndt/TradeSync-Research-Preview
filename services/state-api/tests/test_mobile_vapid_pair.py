"""The key pair signs only when its two halves belong together, and the contact is checked; no value is ever repeated."""

from unittest.mock import patch

import pytest
from Crypto.PublicKey import ECC

from app import mobile_vapid as vapid
from web_push_receiver import b64


def pair():
    key = ECC.generate(curve="P-256")
    return b64(key.public_key().export_key(format="raw")), b64(int(key.d).to_bytes(32, "big"))


PUBLIC, PRIVATE = pair()
OTHER_PUBLIC, OTHER_PRIVATE = pair()


def env(public=PUBLIC, private=PRIVATE, subject=""):
    return patch.dict("os.environ", {vapid.PUBLIC_ENV: public, vapid.PRIVATE_ENV: private, vapid.SUBJECT_ENV: subject})


def test_a_matching_pair_gives_a_key_that_produces_the_configured_public_key():
    with env():
        key = vapid.signing_key()
        assert b64(key.public_key().export_key(format="raw")) == PUBLIC
        assert vapid.configured() is True and vapid.problem() is None


def test_two_halves_of_different_pairs_are_refused_by_name_without_either_value():
    with env(PUBLIC, OTHER_PRIVATE):
        with pytest.raises(vapid.VapidKeyError) as refused:
            vapid.signing_key()
        problem = vapid.problem()
        assert vapid.configured() is False
    for text in (str(refused.value), problem):
        assert "not the two halves of one key pair" in text
        assert PUBLIC not in text and OTHER_PRIVATE not in text and PRIVATE not in text


def test_a_scalar_that_is_not_a_private_key_is_refused_without_repeating_it():
    zero = b64(bytes(32))
    with env(PUBLIC, zero):
        with pytest.raises(vapid.VapidKeyError) as refused:
            vapid.signing_key()
    assert "not a usable P-256 private key" in str(refused.value) and zero not in str(refused.value)


def test_a_missing_half_cannot_sign():
    for public, private in (("", PRIVATE), (PUBLIC, ""), ("", "")):
        with env(public, private), pytest.raises(vapid.VapidKeyError):
            vapid.signing_key()


@pytest.mark.parametrize("subject,state", [
    ("", "missing"),
    ("mailto:operator@example.invalid", "ok"),
    ("https://tradesync.example.invalid/contact", "ok"),
    ("mailto:", "malformed"),
    ("mailto:nobody", "malformed"),
    ("http://tradesync.example.invalid", "malformed"),
    ("https://localhost", "malformed"),
    ("https://user@tradesync.example.invalid", "malformed"),
    ("https://[broken", "malformed"),
    ("operator@example.invalid", "malformed"),
])
def test_the_contact_is_a_mailto_address_or_an_https_url_with_a_real_host(subject, state):
    with env(subject=subject):
        assert vapid.subject_state() == state
        assert vapid.subject() == (subject if state == "ok" else None)
