"""Password hashing with argon2id (plan §5.3), and the bundled common-password list."""

from functools import cache
from pathlib import Path

from argon2 import PasswordHasher as Argon2
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from riso.identity.domain import PasswordPolicy

COMMON_PASSWORDS = Path(__file__).resolve().parent / "data" / "common-passwords.txt"


class Argon2Hasher:
    """argon2id with argon2-cffi's defaults (RFC 9106's second recommended option: 3
    passes, 64 MiB, 4 lanes). Tests pass cheaper parameters through `fast()`."""

    def __init__(
        self, *, time_cost: int = 3, memory_cost: int = 65536, parallelism: int = 4
    ) -> None:
        self._argon2 = Argon2(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            type=Type.ID,
        )

    @classmethod
    def fast(cls) -> "Argon2Hasher":
        """Cheap parameters, for tests only: still argon2id, far from safe."""
        return cls(time_cost=1, memory_cost=8, parallelism=1)

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._argon2.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


@cache
def common_passwords(path: Path = COMMON_PASSWORDS) -> frozenset[str]:
    """The bundled list, case-folded; comment lines start with #."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return frozenset(line.casefold() for line in lines if line and not line.startswith("#"))


def default_policy() -> PasswordPolicy:
    return PasswordPolicy(common=common_passwords())
