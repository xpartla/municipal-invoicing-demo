"""A customer's lists checked against the global lists of the same year (plan §6.3).

| Check | Severity |
|---|---|
| a budget position's EK is not in the year's EK list | error |
| a budget position names a položka that has podpoložky (`612000`) | warning |
| a budget position's zdroj is not among the funding sources | error |
| a position's oddiel and trieda are not in COFOG | error |
| an account's SU is not in the framework chart | warning |

A missing global list cannot check anything; it gives one warning per list it would have
checked. Inactive rows are not checked: the engine never sees them.

EK codes. The classification goes down to the položka (three digits) and, where it has
them, the podpoložka (six). A budget writes six digits, so a položka without podpoložky is
written with `000` (`611000` for položka 611). Main categories and categories (`600`,
`630`) end in zero, položky never do, so `630000` is not a valid EK. A položka that has
podpoložky written with `000` (`612000` for 612, which has 612001 and 612002) names a real
položka without the detail the classification asks for: a warning, not an error (2026-11-08,
pending the user's confirmation).

Synthetic accounts. The framework chart leaves some classes and groups for the entity to fill
(class 8, groups 75 to 79 and 90 to 99 list no accounts), so any account in such a class or
group is known.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from riso.codelists.domain.entries import (
    AccountEntry,
    BudgetEntry,
    CofogEntry,
    EkEntry,
    FrameworkAccountEntry,
    FundingSourceEntry,
)
from riso.codelists.domain.kinds import ListKind
from riso.codelists.domain.version import CodeListVersion


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class FindingCode(StrEnum):
    UNKNOWN_EK = "unknown_ek"
    EK_NOT_DETAILED = "ek_not_detailed"
    """A položka with podpoložky, written with `000`."""
    UNKNOWN_ZDROJ = "unknown_zdroj"
    UNKNOWN_FUNCTION = "unknown_function"
    UNKNOWN_SYNTHETIC_ACCOUNT = "unknown_synthetic_account"
    GLOBAL_LIST_MISSING = "global_list_missing"


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    code: FindingCode
    kind: ListKind
    """The customer's list the finding is in."""
    key: str | None
    """The entry's key; None for a finding about the whole list."""
    field: str | None
    value: str | None
    """The offending code, or the missing global list's kind."""

    @property
    def message(self) -> str:
        if self.code is FindingCode.GLOBAL_LIST_MISSING:
            return f"no active {self.value} list for the year; {self.field} not checked"
        if self.code is FindingCode.EK_NOT_DETAILED:
            return f"{self.kind} {self.key}: EK {self.value} names a položka that has podpoložky"
        return f"{self.kind} {self.key}: {self.field} {self.value} is not in the global list"


@dataclass(frozen=True, slots=True)
class GlobalLists:
    """The codes of the year's global lists; None for a list the year does not have."""

    year: int
    ek: frozenset[str] | None = None
    cofog: frozenset[tuple[str, str]] | None = None
    """(oddiel, trieda) as a budget key writes them."""
    funding_sources: frozenset[str] | None = None
    framework_accounts: frozenset[str] | None = None
    """Every code of the chart: classes (one digit), groups (two), synthetic accounts (three)."""

    @classmethod
    def of(cls, year: int, versions: Mapping[ListKind, CodeListVersion]) -> "GlobalLists":
        """From the year's active global versions; a kind not in `versions` is missing."""

        def active(kind: ListKind) -> list[object] | None:
            version = versions.get(kind)
            if version is None:
                return None
            if version.year != year or version.customer_id is not None:
                raise ValueError(f"version {version.id} is not a global list of {year}")
            return list(version.active_entries())

        ek = active(ListKind.EK)
        cofog = active(ListKind.COFOG)
        sources = active(ListKind.FUNDING_SOURCES)
        framework = active(ListKind.FRAMEWORK_ACCOUNTS)
        return cls(
            year=year,
            ek=None if ek is None else frozenset(e.code for e in ek if isinstance(e, EkEntry)),
            cofog=None
            if cofog is None
            else frozenset(
                (e.oddiel, e.trieda)
                for e in cofog
                if isinstance(e, CofogEntry) and e.trieda is not None
            ),
            funding_sources=None
            if sources is None
            else frozenset(e.code for e in sources if isinstance(e, FundingSourceEntry)),
            framework_accounts=None
            if framework is None
            else frozenset(e.code for e in framework if isinstance(e, FrameworkAccountEntry)),
        )

    def _polozka_of(self, ek: str) -> str | None:
        """The položka a six-digit EK ending in `000` names, when the list has it."""
        codes = self.ek or frozenset()
        polozka = ek[:3]
        if ek.endswith("000") and polozka in codes and polozka[2] != "0":
            return polozka
        return None

    def _has_podpolozky(self, polozka: str) -> bool:
        return any(len(code) == 6 and code.startswith(polozka) for code in self.ek or ())

    def knows_ek(self, ek: str) -> bool:
        """Whether a six-digit budget EK is in the list (see the module's note)."""
        if ek in (self.ek or ()):
            return True
        polozka = self._polozka_of(ek)
        return polozka is not None and not self._has_podpolozky(polozka)

    def lacks_podpolozka(self, ek: str) -> bool:
        """Whether the EK names a položka that has podpoložky (`612000`)."""
        polozka = self._polozka_of(ek)
        return polozka is not None and self._has_podpolozky(polozka)

    def knows_su(self, su: str) -> bool:
        """Whether a synthetic account is in the chart, or in a class or group the chart
        leaves to the entity."""
        codes = self.framework_accounts or frozenset()
        if su in codes:
            return True
        group, cls = su[:2], su[:1]
        if group in codes:
            return not any(len(code) == 3 and code.startswith(group) for code in codes)
        return cls in codes and not any(len(code) > 1 and code.startswith(cls) for code in codes)


def _missing(kind: ListKind, field: str, global_kind: ListKind) -> Finding:
    return Finding(
        Severity.WARNING, FindingCode.GLOBAL_LIST_MISSING, kind, None, field, str(global_kind)
    )


def _budget(version: CodeListVersion, lists: GlobalLists) -> list[Finding]:
    kind = version.kind
    found: list[Finding] = []
    if lists.ek is None:
        found.append(_missing(kind, "ek", ListKind.EK))
    if lists.funding_sources is None:
        found.append(_missing(kind, "zdroj", ListKind.FUNDING_SOURCES))
    has_function = any(
        isinstance(e, BudgetEntry) and e.oddiel is not None for e in version.active_entries()
    )
    if lists.cofog is None and has_function:
        found.append(_missing(kind, "function", ListKind.COFOG))
    for entry in version.active_entries():
        assert isinstance(entry, BudgetEntry)
        if lists.ek is not None and lists.lacks_podpolozka(entry.ek):
            found.append(
                Finding(
                    Severity.WARNING,
                    FindingCode.EK_NOT_DETAILED,
                    kind,
                    entry.key,
                    "ek",
                    entry.ek,
                )
            )
        elif lists.ek is not None and not lists.knows_ek(entry.ek):
            found.append(
                Finding(Severity.ERROR, FindingCode.UNKNOWN_EK, kind, entry.key, "ek", entry.ek)
            )
        if lists.funding_sources is not None and entry.zdroj not in lists.funding_sources:
            found.append(
                Finding(
                    Severity.ERROR, FindingCode.UNKNOWN_ZDROJ, kind, entry.key, "zdroj", entry.zdroj
                )
            )
        if (
            lists.cofog is not None
            and entry.oddiel is not None
            and entry.trieda is not None
            and (entry.oddiel, entry.trieda) not in lists.cofog
        ):
            found.append(
                Finding(
                    Severity.ERROR,
                    FindingCode.UNKNOWN_FUNCTION,
                    kind,
                    entry.key,
                    "function",
                    entry.function,
                )
            )
    return found


def _accounts(version: CodeListVersion, lists: GlobalLists) -> list[Finding]:
    if lists.framework_accounts is None:
        return [_missing(version.kind, "su", ListKind.FRAMEWORK_ACCOUNTS)]
    found = []
    for entry in version.active_entries():
        assert isinstance(entry, AccountEntry)
        if not lists.knows_su(entry.su):
            found.append(
                Finding(
                    Severity.WARNING,
                    FindingCode.UNKNOWN_SYNTHETIC_ACCOUNT,
                    version.kind,
                    entry.key,
                    "su",
                    entry.su,
                )
            )
    return found


def validate_list(version: CodeListVersion, lists: GlobalLists) -> list[Finding]:
    """The findings of one customer list against the global lists of its year."""
    if version.customer_id is None:
        raise ValueError(f"version {version.id} is a global list")
    if version.year != lists.year:
        raise ValueError(f"version {version.id} is for {version.year}, the lists for {lists.year}")
    if version.kind in (ListKind.BUDGET_EXPENSE, ListKind.BUDGET_INCOME):
        return _budget(version, lists)
    if version.kind is ListKind.ACCOUNTS:
        return _accounts(version, lists)
    return []


def validate_lists(versions: Iterable[CodeListVersion], lists: GlobalLists) -> list[Finding]:
    return [finding for version in versions for finding in validate_list(version, lists)]


def has_errors(findings: Iterable[Finding]) -> bool:
    return any(f.severity is Severity.ERROR for f in findings)
