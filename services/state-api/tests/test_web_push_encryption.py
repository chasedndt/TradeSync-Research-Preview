"""RFC 8291's own example reproduced byte for byte, and messages a browser can actually open."""

import os

import pytest
from Crypto.PublicKey import ECC

from app import web_push_encryption as wpe
from web_push_receiver import decrypt, unb64

# RFC 8291 section 5 and Appendix A, as published, with the whitespace from line wrapping removed.
PLAINTEXT = "V2hlbiBJIGdyb3cgdXAsIEkgd2FudCB0byBiZSBhIHdhdGVybWVsb24"
AS_PUBLIC = "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"
AUTH_SECRET = "BTBZMqHH6r4Tts7J_aSIgg"
ECDH_SECRET = "kyrL1jIIOHEzg3sM2ZWRHDRB62YACZhhSlknJ672kSs"
PRK_KEY = "Snr3JMxaHVDXHWJn5wdC52WjpCtd2EIEGBykDcZW32k"
KEY_INFO = ("V2ViUHVzaDogaW5mbwAEJXGyvs3942BVGq8e0PTNNmwRzr5VX4m8t7GGpTM5FzFo7OLr4BhZe9MEebhuPI-OztV3"
            "ylkYfpJGmQ22ggCLDgT-M_SrDepxkU21WCP3O1SUj0EwbZIHMtu5pZpTKGSCIA5Zent7wmC6HCJ5mFgJkuk5cwAvMBKiiujwa7t45ewP")
IKM = "S4lYMb_L0FxCeq0WhDx813KgSYqU26kOyzWUdsXYyrg"
PRK = "09_eUZGrsvxChDCGRCdkLiDXrReGOEVeSCdCcPBSJSc"
CEK_INFO = "Q29udGVudC1FbmNvZGluZzogYWVzMTI4Z2NtAA"
CEK = "oIhVW04MRdy2XN9CiKLxTg"
NONCE_INFO = "Q29udGVudC1FbmNvZGluZzogbm9uY2UA"
NONCE = "4h_95klXJ5E_qnoN"
HEADER = "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
DELIMITED = "V2hlbiBJIGdyb3cgdXAsIEkgd2FudCB0byBiZSBhIHdhdGVybWVsb24C"
CIPHERTEXT = "8pfeW0KbunFT06SuDKoJH9Ql87S1QUrdirN6GcG7sFz1y1sqLgVi1VhjVkHsUoEsbI_0LpXMuGvnzQ"
MESSAGE = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
           "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
           "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def private(value: str):
    return ECC.construct(curve="P-256", d=int.from_bytes(unb64(value), "big"))


def test_the_example_keys_are_the_pairs_the_rfc_says_they_are():
    assert wpe.raw_public(private(AS_PRIVATE)) == unb64(AS_PUBLIC)
    assert wpe.raw_public(private(UA_PRIVATE)) == unb64(UA_PUBLIC)
    assert unb64(PLAINTEXT) == b"When I grow up, I want to be a watermelon"
    assert unb64(DELIMITED) == unb64(PLAINTEXT) + b"\x02"


def test_every_intermediate_value_in_appendix_a_is_derived_exactly():
    schedule = wpe.key_schedule(private(AS_PRIVATE), unb64(UA_PUBLIC), unb64(AUTH_SECRET), unb64(SALT))
    assert schedule.ecdh_secret == unb64(ECDH_SECRET)
    assert schedule.prk_key == unb64(PRK_KEY)
    assert schedule.key_info == unb64(KEY_INFO)
    assert schedule.ikm == unb64(IKM)
    assert schedule.prk == unb64(PRK)
    assert (wpe.CEK_INFO, wpe.NONCE_INFO) == (unb64(CEK_INFO), unb64(NONCE_INFO))
    assert schedule.cek == unb64(CEK)
    assert schedule.nonce == unb64(NONCE)


def test_the_example_message_in_section_5_is_reproduced_byte_for_byte():
    body = wpe.encrypt(unb64(PLAINTEXT), unb64(UA_PUBLIC), unb64(AUTH_SECRET),
                       salt=unb64(SALT), sender_key=private(AS_PRIVATE))
    assert body[:wpe.HEADER_BYTES] == unb64(HEADER)
    assert body[wpe.HEADER_BYTES:] == unb64(CIPHERTEXT)
    assert body == unb64(MESSAGE) and len(body) == 144


def test_the_browser_in_the_example_opens_it_and_the_shared_secret_agrees_from_both_sides():
    assert decrypt(unb64(MESSAGE), private(UA_PRIVATE), unb64(AUTH_SECRET)) == unb64(PLAINTEXT)
    reverse = wpe.key_schedule(private(UA_PRIVATE), unb64(AS_PUBLIC), unb64(AUTH_SECRET), unb64(SALT))
    assert reverse.ecdh_secret == unb64(ECDH_SECRET)


def test_a_real_message_gets_a_new_key_and_salt_every_time_and_opens_with_its_padding_removed():
    browser = ECC.generate(curve="P-256")
    public, auth = wpe.raw_public(browser), os.urandom(16)
    first = wpe.encrypt(b'{"title":"TradeSync"}', public, auth, pad_to=512)
    second = wpe.encrypt(b'{"title":"TradeSync"}', public, auth, pad_to=512)
    assert first[:16] != second[:16] and first[21:86] != second[21:86]
    assert len(first) == len(second) == wpe.HEADER_BYTES + 512 + wpe.TAG_BYTES
    assert decrypt(first, browser, auth) == decrypt(second, browser, auth) == b'{"title":"TradeSync"}'


def test_padding_makes_a_short_and_a_long_message_the_same_size():
    browser = ECC.generate(curve="P-256")
    public, auth = wpe.raw_public(browser), os.urandom(16)
    short, long = wpe.encrypt(b"test", public, auth, pad_to=256), wpe.encrypt(b"attention" * 20, public, auth, pad_to=256)
    assert len(short) == len(long)
    assert decrypt(long, browser, auth) == b"attention" * 20


def test_a_changed_byte_means_the_browser_refuses_the_message():
    browser = ECC.generate(curve="P-256")
    public, auth = wpe.raw_public(browser), os.urandom(16)
    body = bytearray(wpe.encrypt(b"hello", public, auth, pad_to=64))
    body[100] ^= 1
    with pytest.raises(ValueError):
        decrypt(bytes(body), browser, auth)


def test_bad_inputs_are_refused_without_repeating_them():
    public, auth = wpe.raw_public(ECC.generate(curve="P-256")), os.urandom(16)
    off_curve = bytes([4]) + bytes(range(64))
    with pytest.raises(ValueError) as refused:
        wpe.encrypt(b"x", off_curve, auth)
    assert "not a point on the P-256 curve" in str(refused.value) and off_curve.hex() not in str(refused.value)
    for bad_public, bad_auth in ((public[:64], auth), (bytes([2]) + public[1:], auth), (public, auth[:15])):
        with pytest.raises(ValueError):
            wpe.encrypt(b"x", bad_public, bad_auth)
    with pytest.raises(ValueError):
        wpe.encrypt(b"x" * 64, public, auth, pad_to=64)
    with pytest.raises(ValueError):
        wpe.encrypt(b"x" * wpe.RECORD_SIZE, public, auth)
    with pytest.raises(ValueError):
        wpe.encrypt(b"x", public, auth, salt=b"short")
