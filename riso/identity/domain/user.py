"""The `User` aggregate: a person who logs in (plan §3, §5.3, §5.6).

    invited ──set_password──> active
       │                        │
       └──────delete──────> deleted ──purge──> purged
                               │
                             restore ──> active (or invited, without a password)

Locking is separate from the status: an admin locks and unlocks an account, and a locked
account cannot log in whatever its status. Purging anonymises the row (plan §2 decision 51):
the ID stays, so the audit log and later references remain valid, while the name, the
addresses, the password hash and the memberships go.

The user owns its memberships, so the rule "one role per user and scope" lives here.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from riso.identity.domain.email import Email
from riso.identity.domain.membership import Membership, MembershipScope
from riso.identity.domain.permissions import Role, ScopeKind
from riso.shared.errors import Conflict, InvalidState, NotFound
from riso.shared.events import DomainEvent
from riso.shared.values import clean_name


class UserStatus(StrEnum):
    INVITED = "invited"
    """Invited, with no password yet."""
    ACTIVE = "active"
    DELETED = "deleted"
    """Soft-deleted; an admin can restore it."""
    PURGED = "purged"
    """Anonymised for good."""


TRANSITIONS: frozenset[tuple[UserStatus, UserStatus]] = frozenset(
    {
        (UserStatus.INVITED, UserStatus.ACTIVE),  # set_password
        (UserStatus.INVITED, UserStatus.DELETED),
        (UserStatus.ACTIVE, UserStatus.DELETED),
        (UserStatus.DELETED, UserStatus.ACTIVE),  # restore, with a password
        (UserStatus.DELETED, UserStatus.INVITED),  # restore, without one
        (UserStatus.DELETED, UserStatus.PURGED),
    }
)


@dataclass(slots=True)
class User:
    id: str
    name: str
    email: Email | None
    """The login email; None once purged."""
    created_at: datetime
    status: UserStatus = UserStatus.INVITED
    notification_email: Email | None = None
    """Where mail goes when it differs from the login email."""
    password_hash: str | None = None
    password_changed_at: datetime | None = None
    locked_at: datetime | None = None
    deleted_at: datetime | None = None
    purged_at: datetime | None = None
    memberships: list[Membership] = field(default_factory=list)
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def invite(cls, user_id: str, name: str, email: Email, at: datetime) -> "User":
        return cls(id=user_id, name=clean_name(name), email=email, created_at=at)

    # Status ------------------------------------------------------------------------------

    def _transition(self, to: UserStatus) -> None:
        if (self.status, to) not in TRANSITIONS:
            raise InvalidState(f"user {self.id} is {self.status}, cannot become {to}")
        self.status = to

    def _require_present(self) -> None:
        """Deleted and purged accounts change only through restore and purge."""
        if self.status in (UserStatus.DELETED, UserStatus.PURGED):
            raise InvalidState(f"user {self.id} is {self.status}")

    @property
    def can_log_in(self) -> bool:
        return (
            self.status is UserStatus.ACTIVE
            and self.locked_at is None
            and self.password_hash is not None
        )

    @property
    def is_admin(self) -> bool:
        return any(m.active and m.role is Role.PLATFORM_ADMIN for m in self.memberships)

    @property
    def mail_address(self) -> Email | None:
        """Where mail for this user goes: the notification email, else the login email."""
        return self.notification_email or self.email

    def set_password(self, password_hash: str, at: datetime) -> None:
        """Sets or changes the password; an invited user becomes active."""
        self._require_present()
        if self.status is UserStatus.INVITED:
            self._transition(UserStatus.ACTIVE)
        self.password_hash = password_hash
        self.password_changed_at = at

    def replace_hash(self, password_hash: str) -> None:
        """Stores a new hash of the same password (stronger parameters after a login); the
        password itself did not change, so `password_changed_at` stays."""
        self._require_present()
        if self.password_hash is None:
            raise InvalidState(f"user {self.id} has no password")
        self.password_hash = password_hash

    def rename(self, name: str) -> None:
        self._require_present()
        self.name = clean_name(name)

    def change_email(self, email: Email) -> None:
        self._require_present()
        self.email = email

    def set_notification_email(self, email: Email | None) -> None:
        self._require_present()
        self.notification_email = None if email == self.email else email

    def lock(self, at: datetime) -> None:
        self._require_present()
        if self.locked_at is not None:
            raise InvalidState(f"user {self.id} is already locked")
        self.locked_at = at

    def unlock(self) -> None:
        self._require_present()
        if self.locked_at is None:
            raise InvalidState(f"user {self.id} is not locked")
        self.locked_at = None

    def delete(self, at: datetime) -> None:
        self._transition(UserStatus.DELETED)
        self.deleted_at = at

    def restore(self) -> None:
        if self.status is not UserStatus.DELETED:
            raise InvalidState(f"user {self.id} is {self.status}, not deleted")
        self._transition(UserStatus.ACTIVE if self.password_hash else UserStatus.INVITED)
        self.deleted_at = None

    def purge(self, at: datetime) -> None:
        """Anonymises a deleted user (plan §2 decision 51)."""
        self._transition(UserStatus.PURGED)
        self.name = ""
        self.email = None
        self.notification_email = None
        self.password_hash = None
        self.password_changed_at = None
        self.locked_at = None
        self.memberships.clear()
        self.purged_at = at

    # Memberships -------------------------------------------------------------------------

    def membership_in(self, scope: MembershipScope) -> Membership | None:
        return next((m for m in self.memberships if m.scope == scope), None)

    def grant(
        self, membership_id: str, scope: MembershipScope, role: Role, at: datetime
    ) -> Membership:
        """Gives the user a role in a scope. A user has one role per scope, so a second
        grant in the same scope is a conflict, active or not (reactivate an inactive one)."""
        self._require_present()
        if self.membership_in(scope) is not None:
            raise Conflict(f"user {self.id} already has a membership in this {scope.kind}")
        membership = Membership(membership_id, scope, role, at)
        self.memberships.append(membership)
        return membership

    def _membership(self, scope: MembershipScope) -> Membership:
        membership = self.membership_in(scope)
        if membership is None:
            raise NotFound(f"user {self.id} has no membership in this {scope.kind}")
        return membership

    def deactivate_membership(self, scope: MembershipScope, at: datetime) -> Membership:
        membership = self._membership(scope)
        membership.deactivate(at)
        return membership

    def remove_membership(self, scope: MembershipScope) -> Membership:
        """Forgets the membership (a staff member taken off a provider, a purged customer);
        the audit keeps its history."""
        membership = self._membership(scope)
        self.memberships.remove(membership)
        return membership

    def reactivate_membership(self, scope: MembershipScope) -> Membership:
        self._require_present()
        membership = self._membership(scope)
        membership.reactivate()
        return membership

    def active_memberships(self, kind: ScopeKind | None = None) -> list[Membership]:
        return [m for m in self.memberships if m.active and (kind is None or m.scope.kind is kind)]
