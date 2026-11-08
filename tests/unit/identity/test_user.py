"""The `User` aggregate: its status machine, locking, purging, and the membership invariants."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.identity.domain import (
    TRANSITIONS,
    Email,
    Membership,
    MembershipScope,
    Role,
    ScopeKind,
    User,
    UserStatus,
)
from riso.shared import Conflict, InvalidState, NotFound, ValidationFailed, clean_name

T0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)
CUSTOMER = MembershipScope.customer("c1")
OTHER_CUSTOMER = MembershipScope.customer("c2")
PROVIDER = MembershipScope.provider("p1")
PLATFORM = MembershipScope.platform()


def invited(**kwargs) -> User:
    return User.invite("u1", "  Jana   Vzorová ", Email("jana@obec.sk"), T0, **kwargs)


def active() -> User:
    user = invited()
    user.set_password("hash", T0)
    return user


def deleted() -> User:
    user = active()
    user.delete(T0)
    return user


def purged() -> User:
    user = deleted()
    user.purge(T0)
    return user


def test_an_invitation_starts_without_a_password():
    user = invited()
    assert user.name == "Jana Vzorová"
    assert user.status is UserStatus.INVITED
    assert not user.can_log_in
    assert user.mail_address == Email("jana@obec.sk")


def test_setting_the_password_activates_an_invited_user():
    user = invited()
    user.set_password("h1", T0)
    assert user.status is UserStatus.ACTIVE
    assert user.can_log_in
    user.set_password("h2", T0 + timedelta(days=1))
    assert (user.password_hash, user.password_changed_at) == ("h2", T0 + timedelta(days=1))


# Every status transition the methods can make, as (from, method, to).
MOVES = [
    (UserStatus.INVITED, lambda u: u.set_password("h", T0), UserStatus.ACTIVE),
    (UserStatus.INVITED, lambda u: u.delete(T0), UserStatus.DELETED),
    (UserStatus.ACTIVE, lambda u: u.delete(T0), UserStatus.DELETED),
    (UserStatus.DELETED, lambda u: u.purge(T0), UserStatus.PURGED),
]
MAKERS = {
    UserStatus.INVITED: invited,
    UserStatus.ACTIVE: active,
    UserStatus.DELETED: deleted,
    UserStatus.PURGED: purged,
}


def test_the_transition_table_is_exactly_what_the_methods_do():
    restores = {(UserStatus.DELETED, UserStatus.ACTIVE), (UserStatus.DELETED, UserStatus.INVITED)}
    assert {(f, t) for f, _, t in MOVES} | restores == TRANSITIONS


@pytest.mark.parametrize(("start", "move", "end"), MOVES)
def test_each_allowed_transition(start, move, end):
    user = MAKERS[start]()
    move(user)
    assert user.status is end


@pytest.mark.parametrize("start", list(UserStatus))
@pytest.mark.parametrize(
    "method",
    [
        lambda u: u.set_password("h", T0),
        lambda u: u.delete(T0),
        lambda u: u.restore(),
        lambda u: u.purge(T0),
        lambda u: u.lock(T0),
        lambda u: u.rename("New Name"),
        lambda u: u.change_email(Email("new@obec.sk")),
        lambda u: u.grant("m9", OTHER_CUSTOMER, Role.CUSTOMER_USER, T0),
    ],
    ids=["set_password", "delete", "restore", "purge", "lock", "rename", "change_email", "grant"],
)
def test_every_other_transition_is_refused(start, method):
    user = MAKERS[start]()
    before = user.status
    try:
        method(user)
    except InvalidState:
        assert user.status is before
    else:
        assert (before, user.status) in TRANSITIONS or user.status is before


def test_restore_brings_back_the_status_from_before():
    user = deleted()
    user.restore()
    assert user.status is UserStatus.ACTIVE and user.deleted_at is None
    never_accepted = invited()
    never_accepted.delete(T0)
    never_accepted.restore()
    assert never_accepted.status is UserStatus.INVITED


def test_deleted_and_purged_users_cannot_change_or_log_in():
    for user in (deleted(), purged()):
        assert not user.can_log_in
        for change in (
            lambda u: u.set_password("h", T0),
            lambda u: u.rename("x y"),
            lambda u: u.lock(T0),
            lambda u: u.set_notification_email(None),
        ):
            with pytest.raises(InvalidState):
                change(user)


def test_purging_anonymises_and_keeps_the_id():
    user = active()
    user.grant("m1", CUSTOMER, Role.CUSTOMER_USER, T0)
    user.set_notification_email(Email("notify@obec.sk"))
    user.delete(T0)
    user.purge(T0 + timedelta(days=1))
    assert user.id == "u1"
    assert (user.name, user.email, user.notification_email, user.password_hash) == (
        "",
        None,
        None,
        None,
    )
    assert user.memberships == []
    assert user.purged_at == T0 + timedelta(days=1)
    with pytest.raises(InvalidState):
        user.restore()


def test_purging_needs_a_deleted_user_first():
    with pytest.raises(InvalidState):
        active().purge(T0)


def test_locking_is_separate_from_the_status():
    user = active()
    user.lock(T0)
    assert user.status is UserStatus.ACTIVE and not user.can_log_in
    with pytest.raises(InvalidState):
        user.lock(T0)
    user.unlock()
    assert user.can_log_in
    with pytest.raises(InvalidState):
        user.unlock()


def test_the_notification_email_equal_to_the_login_email_is_dropped():
    user = active()
    user.set_notification_email(Email("other@obec.sk"))
    assert user.mail_address == Email("other@obec.sk")
    user.set_notification_email(Email("jana@obec.sk"))
    assert user.notification_email is None
    assert user.mail_address == Email("jana@obec.sk")


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, "Jana\x00", "a\x07b"])
def test_names_are_validated(name):
    with pytest.raises(ValidationFailed):
        clean_name(name)


def test_names_are_normalised():
    assert clean_name(" Jána   Vzorová\t") == "Jána Vzorová"


# Memberships ------------------------------------------------------------------------------


def test_one_role_per_user_and_scope():
    user = active()
    user.grant("m1", CUSTOMER, Role.CUSTOMER_VIEWER, T0)
    with pytest.raises(Conflict):
        user.grant("m2", CUSTOMER, Role.CUSTOMER_USER, T0)
    user.grant("m3", OTHER_CUSTOMER, Role.CUSTOMER_USER, T0)
    user.grant("m4", PROVIDER, Role.PROVIDER_STAFF, T0)
    user.grant("m5", PLATFORM, Role.PLATFORM_ADMIN, T0)
    with pytest.raises(Conflict):
        user.grant("m6", PLATFORM, Role.PLATFORM_ADMIN, T0)
    assert [m.id for m in user.memberships] == ["m1", "m3", "m4", "m5"]


def test_an_inactive_membership_still_blocks_a_second_grant():
    user = active()
    user.grant("m1", CUSTOMER, Role.CUSTOMER_USER, T0)
    user.deactivate_membership(CUSTOMER, T0)
    with pytest.raises(Conflict):
        user.grant("m2", CUSTOMER, Role.CUSTOMER_VIEWER, T0)


@pytest.mark.parametrize(
    ("scope", "role"),
    [
        (CUSTOMER, Role.PROVIDER_STAFF),
        (CUSTOMER, Role.PLATFORM_ADMIN),
        (PROVIDER, Role.CUSTOMER_USER),
        (PROVIDER, Role.CUSTOMER_VIEWER),
        (PLATFORM, Role.CUSTOMER_USER),
        (PLATFORM, Role.PROVIDER_STAFF),
    ],
)
def test_the_role_must_belong_to_the_scope(scope, role):
    with pytest.raises(ValidationFailed) as caught:
        active().grant("m1", scope, role, T0)
    assert caught.value.errors[0].code == "role_scope"


def test_scopes_need_an_id_except_the_platform():
    with pytest.raises(ValueError):
        MembershipScope(ScopeKind.CUSTOMER, None)
    with pytest.raises(ValueError):
        MembershipScope(ScopeKind.PLATFORM, "x")
    assert MembershipScope.platform() == MembershipScope(ScopeKind.PLATFORM, None)


def test_deactivating_and_reactivating_a_membership():
    user = active()
    user.grant("m1", CUSTOMER, Role.CUSTOMER_USER, T0)
    membership = user.deactivate_membership(CUSTOMER, T0 + timedelta(hours=1))
    assert not membership.active and membership.deactivated_at == T0 + timedelta(hours=1)
    assert user.active_memberships() == []
    with pytest.raises(InvalidState):
        user.deactivate_membership(CUSTOMER, T0)
    user.reactivate_membership(CUSTOMER)
    assert user.active_memberships(ScopeKind.CUSTOMER) == [membership]
    with pytest.raises(InvalidState):
        user.reactivate_membership(CUSTOMER)
    with pytest.raises(NotFound):
        user.deactivate_membership(OTHER_CUSTOMER, T0)


def test_is_admin_needs_an_active_platform_membership():
    user = active()
    assert not user.is_admin
    user.grant("m1", PLATFORM, Role.PLATFORM_ADMIN, T0)
    assert user.is_admin
    user.deactivate_membership(PLATFORM, T0)
    assert not user.is_admin


def test_a_membership_checks_its_role_on_construction():
    with pytest.raises(ValidationFailed):
        Membership("m1", PROVIDER, Role.CUSTOMER_USER, T0)
