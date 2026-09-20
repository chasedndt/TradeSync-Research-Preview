"""The VAPID token a push service is shown: signed with ES256, for the right audience, never longer than a day."""

import json

import pytest
from Crypto.PublicKey import ECC

from app import web_push_jwt as jwt
from web_push_receiver import b64, unb64, verify_vapid

NOW = 1_789_000_000
ENDPOINT = "https://fcm.googleapis.com/fcm/send/this-part-is-a-capability-token"
SUBJECT = "mailto:operator@example.invalid"
KEY = ECC.generate(curve="P-256")
PUBLIC = b64(KEY.public_key().export_key(format="raw"))


def test_the_audience_is_the_push_services_origin_and_nothing_of_the_path():
    assert jwt.audience(ENDPOINT) == "https://fcm.googleapis.com"
    assert jwt.audience("https://Updates.Push.Services.Mozilla.com:443/wpush/v2/abc") == "https://updates.push.services.mozilla.com"
    assert jwt.audience("https://push.example.net:8443/push/abc") == "https://push.example.net:8443"
    for bad in ("http://fcm.googleapis.com/fcm/send/abc", "https:///no-host", "fcm.googleapis.com/abc"):
        with pytest.raises(ValueError):
            jwt.audience(bad)


def test_a_push_service_accepts_the_authorization_and_reads_the_claims_it_needs():
    header = jwt.authorization(ENDPOINT, SUBJECT, PUBLIC, KEY, now=NOW)
    claims = verify_vapid(header, "https://fcm.googleapis.com", NOW)
    assert claims == {"aud": "https://fcm.googleapis.com", "exp": NOW + 12 * 3600, "sub": SUBJECT, "k": PUBLIC}
    assert header.startswith("vapid t=") and header.endswith(f", k={PUBLIC}")


def test_the_signature_is_the_64_octet_jose_form_and_the_same_input_signs_the_same_way():
    token = jwt.token("https://web.push.apple.com", SUBJECT, KEY, now=NOW)
    assert len(unb64(token.split(".")[2])) == 64
    assert json.loads(unb64(token.split(".")[0])) == {"typ": "JWT", "alg": "ES256"}
    # RFC 6979: no random nonce to go wrong.
    assert token == jwt.token("https://web.push.apple.com", SUBJECT, KEY, now=NOW)


def test_a_token_signed_by_another_key_is_refused_by_the_push_service():
    stranger = ECC.generate(curve="P-256")
    forged = jwt.authorization(ENDPOINT, SUBJECT, PUBLIC, stranger, now=NOW)
    with pytest.raises(ValueError):
        verify_vapid(forged, "https://fcm.googleapis.com", NOW)


def test_a_token_is_for_one_audience_and_expires_within_a_day():
    header = jwt.authorization(ENDPOINT, SUBJECT, PUBLIC, KEY, now=NOW)
    with pytest.raises(AssertionError):
        verify_vapid(header, "https://updates.push.services.mozilla.com", NOW)
    with pytest.raises(AssertionError):
        verify_vapid(header, "https://fcm.googleapis.com", NOW + 12 * 3600)
    for lifetime in (0, 24 * 3600 + 1):
        with pytest.raises(ValueError):
            jwt.token("https://fcm.googleapis.com", SUBJECT, KEY, now=NOW, lifetime=lifetime)
