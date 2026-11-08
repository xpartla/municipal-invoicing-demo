"""`Email`, the password policy, argon2id hashing and the common-password list."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from riso.identity.domain import Email, PasswordPolicy
from riso.identity.domain.passwords import MAX_LENGTH, MIN_LENGTH
from riso.identity.infrastructure.hashing import Argon2Hasher, common_passwords, default_policy
from riso.shared import ValidationFailed


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("jana@obec-boldog.sk", "jana@obec-boldog.sk"),
        ("  Jana.Vzorova@Obec-Boldog.SK ", "jana.vzorova@obec-boldog.sk"),
        ("first+tag@sub.example.com", "first+tag@sub.example.com"),
        ("o'neil@example.ie", "o'neil@example.ie"),
        ("starosta@žilina.sk", "starosta@žilina.sk"),
        ("a@b.co", "a@b.co"),
    ],
)
def test_valid_addresses_are_normalised(typed, stored):
    assert Email.parse(typed).value == stored


@pytest.mark.parametrize(
    "typed",
    [
        "",
        "   ",
        "jana",
        "jana@",
        "@obec.sk",
        "jana@obec",
        "jana@@obec.sk",
        "ja na@obec.sk",
        "jana@obec..sk",
        "jana@-obec.sk",
        "jana@obec-.sk",
        ".jana@obec.sk",
        "jana.@obec.sk",
        "ja..na@obec.sk",
        "jana\n@obec.sk",
        'ja"na@obec.sk',
        "<jana@obec.sk>",
        "x" * 65 + "@obec.sk",
        "a@" + "b" * 64 + ".sk",
        "a@" + ".".join(["abcdefghi"] * 26) + ".sk",
    ],
)
def test_invalid_addresses_are_refused(typed):
    with pytest.raises(ValidationFailed) as caught:
        Email.parse(typed, field="login_email")
    assert caught.value.errors[0].field == "login_email"
    assert caught.value.errors[0].code == "email"


def test_the_constructor_accepts_only_normalised_addresses():
    assert Email("jana@obec.sk").local_part == "jana"
    with pytest.raises(ValidationFailed):
        Email("Jana@obec.sk")


@given(st.from_regex(r"[a-z0-9._%+-]{1,20}@[a-z0-9]{1,10}\.(sk|cz|com)", fullmatch=True))
def test_parsing_is_idempotent(address):
    try:
        once = Email.parse(address)
    except ValidationFailed:
        return  # e.g. dots at the edges of the local part
    assert Email.parse(once.value) == once
    assert Email.parse(address.upper()) == once


POLICY = PasswordPolicy(common=frozenset({"password1234", "qwertyuiop12"}))


def codes(password, **kwargs):
    return POLICY.problems(password, **kwargs)


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("a" * 11 + "B", ["password_common"]),  # two distinct characters
        ("Kôň-skáče-13", []),
        ("correct horse battery staple", []),
        ("x" * (MIN_LENGTH - 1), ["password_too_short"]),
        ("", ["password_too_short"]),
        ("x1" * (MAX_LENGTH // 2) + "y", ["password_too_long"]),
        ("PASSWORD1234", ["password_common"]),
        ("  password1234", ["password_common"]),
        ("aaaaaaaaaaaa", ["password_common"]),
        ("abababababab", ["password_common"]),
    ],
)
def test_policy_edge_cases(password, expected):
    assert codes(password) == expected


def test_exactly_the_bounds_are_allowed():
    assert codes("abc" * 4) == []  # 12 characters
    assert codes(("abc" * 86)[:MAX_LENGTH]) == []  # 256 characters


def test_the_password_must_differ_from_the_account():
    account = ["jana.vzorova@obec-boldog.sk", "jana.vzorova", "Jana Vzorová"]
    assert codes("Jana.Vzorova@obec-boldog.SK", account=account) == ["password_like_account"]
    assert codes("JANA.VZOROVA", account=account) == ["password_like_account"]
    assert codes("jana.vzorova!", account=account) == []


def test_check_names_the_field():
    with pytest.raises(ValidationFailed) as caught:
        POLICY.check("short", field="new_password")
    assert [(e.field, e.code) for e in caught.value.errors] == [
        ("new_password", "password_too_short")
    ]
    POLICY.check("a sound passphrase")


def test_the_bundled_list_is_loaded_and_case_folded():
    common = common_passwords()
    assert len(common) > 30000
    assert all(len(p) >= 12 for p in common)
    assert "password1234" in common
    assert "heslo123456789" in common  # from the Slovak additions
    policy = default_policy()
    assert policy.problems("Password1234") == ["password_common"]
    assert policy.problems("Vŕba-pri-potoku-2026") == []


@pytest.fixture(scope="module")
def hasher():
    return Argon2Hasher.fast()


def test_hashing_and_verifying(hasher):
    digest = hasher.hash("a sound passphrase")
    assert digest.startswith("$argon2id$")
    assert hasher.verify(digest, "a sound passphrase")
    assert not hasher.verify(digest, "a sound passphrasE")
    assert hasher.hash("a sound passphrase") != digest  # salted


def test_a_malformed_hash_does_not_verify(hasher):
    assert not hasher.verify("not a hash", "anything at all")
    assert not hasher.verify("", "anything at all")
    assert hasher.needs_rehash("not a hash")


def test_weaker_parameters_need_a_rehash(hasher):
    digest = hasher.hash("a sound passphrase")
    assert not hasher.needs_rehash(digest)
    assert Argon2Hasher().needs_rehash(digest)


def test_the_default_parameters_are_argon2id_with_64_mib():
    digest = Argon2Hasher().hash("a sound passphrase")
    assert digest.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
