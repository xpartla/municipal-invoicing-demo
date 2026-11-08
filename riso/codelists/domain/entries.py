"""The typed entries of each kind of code list (plan §6.2).

A customer list's entries mirror the reference bundle's contracts (`Account`,
`BudgetPosition`, `DocumentSeries`, `Transfer`, `CostCentre`) and validate through them, so
their rules (code patterns, a key matching its parts) are exactly the contracts'. Budget
positions add optional amounts; every entry has an `active` flag (plan §2 decision 57: a
deactivated row stays in the version, the engine never sees it).

The global lists' entries are a code and a name each:

- EK: the položka (three digits, `632`) or the podpoložka (six, `632001`); the main
  categories and categories (`600`, `630`) are three-digit codes too;
- COFOG: the official dotted notation, `01`, `01.1`, `01.1.1`, `09.6.0.1`;
- funding sources: `41`, `111`, `1AD1`, `72f`, and their groups (`1`, `11`);
- framework chart: a class (`5`), a group (`51`) or a synthetic account (`518`).
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from riso.codelists.domain.kinds import ListKind
from riso.contracts import Account, BudgetPosition, CostCentre, DocumentSeries, Transfer
from riso.contracts.reference import AccountType, budget_key
from riso.shared.errors import FieldError, ValidationFailed

CENT = Decimal("0.01")
MAX_NAME = 500


def _validated[M: BaseModel](model: type[M], values: Mapping[str, Any]) -> M:
    try:
        return model.model_validate(dict(values))
    except ValidationError as exc:
        raise ValidationFailed.from_pydantic("invalid entry", exc.errors()) from exc


def _only(values: Mapping[str, Any], allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValidationFailed(
            "invalid entry",
            [FieldError(name, "not a field of this list", "extra_forbidden") for name in unknown],
        )


def _flag(values: Mapping[str, Any]) -> bool:
    active = values.get("active", True)
    if not isinstance(active, bool):
        raise ValidationFailed.on("active", "true or false", "bool_type")
    return active


def _amount(values: Mapping[str, Any], field: str) -> Decimal | None:
    value = values.get(field)
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValidationFailed.on(field, "not an amount", "decimal_parsing") from None
    if not amount.is_finite() or amount != amount.quantize(CENT):
        raise ValidationFailed.on(field, "at most two decimals", "decimal_max_places")
    return amount.quantize(CENT)


def _text(values: Mapping[str, Any], field: str, *, required: bool) -> str | None:
    value = values.get(field)
    if value is None:
        if required:
            raise ValidationFailed.on(field, "required", "missing")
        return None
    if not isinstance(value, str):
        raise ValidationFailed.on(field, "text", "string_type")
    text = " ".join(value.split())
    if required and not text:
        raise ValidationFailed.on(field, "required", "missing")
    if len(text) > MAX_NAME:
        raise ValidationFailed.on(field, f"at most {MAX_NAME} characters", "string_too_long")
    return text or None


def _code(values: Mapping[str, Any], pattern: re.Pattern[str], what: str) -> str:
    value = values.get("code")
    if not isinstance(value, str) or not value.strip():
        raise ValidationFailed.on("code", "required", "missing")
    code = value.strip()
    if not pattern.fullmatch(code):
        raise ValidationFailed.on("code", f"not a valid {what}", "string_pattern_mismatch")
    return code


# --- A customer's lists ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountEntry:
    """An account of the customer's chart: synthetic account (SU) and analytic account (AU)."""

    su: str
    au: str
    type: AccountType
    activity: str | None = None
    description: str | None = None
    row: int | None = None
    """The row in the file it was imported from."""
    active: bool = True

    FIELDS = ("su", "au", "type", "activity", "description", "row", "active", "key")

    @property
    def key(self) -> str:
        return f"{self.su} {self.au}"

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "AccountEntry":
        _only(values, cls.FIELDS)
        active = _flag(values)
        data = {k: v for k, v in values.items() if k != "active"}
        data.setdefault("key", f"{data.get('su')} {data.get('au')}")
        return cls.of(_validated(Account, data), active=active)

    @classmethod
    def of(cls, account: Account, *, active: bool = True) -> "AccountEntry":
        return cls(
            su=account.su,
            au=account.au,
            type=account.type,
            activity=account.activity,
            description=account.description,
            row=account.row,
            active=active,
        )

    def to_contract(self) -> Account:
        return Account(
            key=self.key,
            su=self.su,
            au=self.au,
            type=self.type,
            activity=self.activity,
            description=self.description,
            row=self.row,
        )


@dataclass(frozen=True, slots=True)
class BudgetEntry:
    """A budget position: EK, zdroj, the function (oddiel and trieda; never on income
    positions in TOPSET) and the analytika, with the budgeted amounts when an import carries
    them."""

    ek: str
    zdroj: str
    analytika: str
    oddiel: str | None = None
    trieda: str | None = None
    description: str | None = None
    aliases: tuple[str, ...] = ()
    rows: tuple[int, ...] = ()
    approved: Decimal | None = None
    """Schválený rozpočet."""
    adjusted: Decimal | None = None
    """Upravený rozpočet."""
    active: bool = True

    FIELDS = (
        "ek",
        "zdroj",
        "oddiel",
        "trieda",
        "analytika",
        "description",
        "aliases",
        "rows",
        "approved",
        "adjusted",
        "active",
        "key",
    )

    @property
    def key(self) -> str:
        return budget_key(self.ek, self.zdroj, self.oddiel, self.trieda, self.analytika)

    @property
    def function(self) -> str | None:
        """'oddiel trieda', e.g. '01 110'."""
        return None if self.oddiel is None else f"{self.oddiel} {self.trieda}"

    @classmethod
    def parse(cls, values: Mapping[str, Any], *, expense: bool) -> "BudgetEntry":
        _only(values, cls.FIELDS)
        active = _flag(values)
        approved = _amount(values, "approved")
        adjusted = _amount(values, "adjusted")
        data = {k: v for k, v in values.items() if k not in ("active", "approved", "adjusted")}
        data.setdefault(
            "key",
            budget_key(
                str(data.get("ek")),
                str(data.get("zdroj")),
                data.get("oddiel"),
                data.get("trieda"),
                str(data.get("analytika")),
            ),
        )
        data.setdefault("rows", [])
        position = _validated(BudgetPosition, data)
        if expense and position.oddiel is None:
            raise ValidationFailed.on("oddiel", "an expense position needs its function", "missing")
        return cls.of(position, active=active, approved=approved, adjusted=adjusted)

    @classmethod
    def of(
        cls,
        position: BudgetPosition,
        *,
        active: bool = True,
        approved: Decimal | None = None,
        adjusted: Decimal | None = None,
    ) -> "BudgetEntry":
        return cls(
            ek=position.ek,
            zdroj=position.zdroj,
            analytika=position.analytika,
            oddiel=position.oddiel,
            trieda=position.trieda,
            description=position.description,
            aliases=tuple(position.aliases),
            rows=tuple(position.rows),
            approved=approved,
            adjusted=adjusted,
            active=active,
        )

    def to_contract(self) -> BudgetPosition:
        return BudgetPosition(
            key=self.key,
            ek=self.ek,
            zdroj=self.zdroj,
            oddiel=self.oddiel,
            trieda=self.trieda,
            analytika=self.analytika,
            description=self.description,
            aliases=list(self.aliases),
            rows=list(self.rows),
        )


@dataclass(frozen=True, slots=True)
class SeriesEntry:
    """A document series (`FD`, `FDŠJ`) with its pattern."""

    code: str
    series_id: str
    pattern: str
    description: str
    bank_account: str | None = None
    active: bool = True

    FIELDS = ("code", "series_id", "pattern", "description", "bank_account", "active")

    @property
    def key(self) -> str:
        return self.code

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "SeriesEntry":
        _only(values, cls.FIELDS)
        active = _flag(values)
        series = _validated(DocumentSeries, {k: v for k, v in values.items() if k != "active"})
        if not series.code.strip():
            raise ValidationFailed.on("code", "required", "missing")
        return cls.of(series, active=active)

    @classmethod
    def of(cls, series: DocumentSeries, *, active: bool = True) -> "SeriesEntry":
        return cls(
            code=series.code,
            series_id=series.series_id,
            pattern=series.pattern,
            description=series.description,
            bank_account=series.bank_account,
            active=active,
        )

    def to_contract(self) -> DocumentSeries:
        return DocumentSeries(
            code=self.code,
            series_id=self.series_id,
            pattern=self.pattern,
            description=self.description,
            bank_account=self.bank_account,
        )


@dataclass(frozen=True, slots=True)
class TransferEntry:
    """A transfer (an income-side key a grant comes from)."""

    id: str
    name: str
    zdroj: str
    mock: bool = False
    """Derived from the income side because the real list was not exported."""
    active: bool = True

    FIELDS = ("id", "name", "zdroj", "mock", "active")

    @property
    def key(self) -> str:
        return self.id

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "TransferEntry":
        _only(values, cls.FIELDS)
        active = _flag(values)
        data = {k: v for k, v in values.items() if k != "active"}
        data.setdefault("mock", False)
        transfer = _validated(Transfer, data)
        if not transfer.id.strip():
            raise ValidationFailed.on("id", "required", "missing")
        return cls.of(transfer, active=active)

    @classmethod
    def of(cls, transfer: Transfer, *, active: bool = True) -> "TransferEntry":
        return cls(
            id=transfer.id,
            name=transfer.name,
            zdroj=transfer.zdroj,
            mock=transfer.mock,
            active=active,
        )

    def to_contract(self) -> Transfer:
        return Transfer(id=self.id, name=self.name, zdroj=self.zdroj, mock=self.mock)


@dataclass(frozen=True, slots=True)
class CostCentreEntry:
    """A cost centre (stredisko)."""

    code: str
    name: str
    active: bool = True

    FIELDS = ("code", "name", "active")

    @property
    def key(self) -> str:
        return self.code

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "CostCentreEntry":
        _only(values, cls.FIELDS)
        active = _flag(values)
        centre = _validated(CostCentre, {k: v for k, v in values.items() if k != "active"})
        if not centre.code.strip():
            raise ValidationFailed.on("code", "required", "missing")
        return cls.of(centre, active=active)

    @classmethod
    def of(cls, centre: CostCentre, *, active: bool = True) -> "CostCentreEntry":
        return cls(code=centre.code, name=centre.name, active=active)

    def to_contract(self) -> CostCentre:
        return CostCentre(code=self.code, name=self.name)


# --- The global lists ------------------------------------------------------------------------

_EK = re.compile(r"\d{3}(\d{3})?")
_COFOG = re.compile(r"\d{2}(\.\d(\.\d(\.\d)?)?)?")
_ZDROJ = re.compile(r"\d[0-9A-Za-z]{0,3}")
_FRAMEWORK = re.compile(r"\d{1,3}")


@dataclass(frozen=True, slots=True)
class EkEntry:
    code: str
    name: str
    active: bool = True

    FIELDS = ("code", "name", "active")

    @property
    def key(self) -> str:
        return self.code

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "EkEntry":
        _only(values, cls.FIELDS)
        name = cast(str, _text(values, "name", required=True))
        return cls(_code(values, _EK, "EK code"), name, _flag(values))


@dataclass(frozen=True, slots=True)
class CofogEntry:
    code: str
    """Dotted, as the classification writes it: `09.6.0.1`."""
    name: str
    active: bool = True

    FIELDS = ("code", "name", "active")

    @property
    def key(self) -> str:
        return self.code

    @property
    def oddiel(self) -> str:
        return self.code[:2]

    @property
    def trieda(self) -> str | None:
        """The three digits after the oddiel as a budget key writes them (`01.1.1` is
        `01 110`, `09.6.0.1` is `09 601`); None for an oddiel itself."""
        digits = self.code[3:].replace(".", "")
        return digits.ljust(3, "0") if digits else None

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "CofogEntry":
        _only(values, cls.FIELDS)
        name = cast(str, _text(values, "name", required=True))
        return cls(_code(values, _COFOG, "COFOG code"), name, _flag(values))


@dataclass(frozen=True, slots=True)
class FundingSourceEntry:
    code: str
    name: str
    active: bool = True

    FIELDS = ("code", "name", "active")

    @property
    def key(self) -> str:
        return self.code

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "FundingSourceEntry":
        _only(values, cls.FIELDS)
        name = cast(str, _text(values, "name", required=True))
        return cls(_code(values, _ZDROJ, "funding source code"), name, _flag(values))


@dataclass(frozen=True, slots=True)
class FrameworkAccountEntry:
    code: str
    """A class (one digit), a group (two) or a synthetic account (three)."""
    name: str
    active: bool = True

    FIELDS = ("code", "name", "active")

    @property
    def key(self) -> str:
        return self.code

    @classmethod
    def parse(cls, values: Mapping[str, Any]) -> "FrameworkAccountEntry":
        _only(values, cls.FIELDS)
        name = cast(str, _text(values, "name", required=True))
        return cls(_code(values, _FRAMEWORK, "framework account"), name, _flag(values))


Entry = (
    AccountEntry
    | BudgetEntry
    | SeriesEntry
    | TransferEntry
    | CostCentreEntry
    | EkEntry
    | CofogEntry
    | FundingSourceEntry
    | FrameworkAccountEntry
)

ENTRY_TYPES: dict[ListKind, type[Entry]] = {
    ListKind.ACCOUNTS: AccountEntry,
    ListKind.BUDGET_EXPENSE: BudgetEntry,
    ListKind.BUDGET_INCOME: BudgetEntry,
    ListKind.DOCUMENT_SERIES: SeriesEntry,
    ListKind.TRANSFERS: TransferEntry,
    ListKind.COST_CENTRES: CostCentreEntry,
    ListKind.EK: EkEntry,
    ListKind.COFOG: CofogEntry,
    ListKind.FUNDING_SOURCES: FundingSourceEntry,
    ListKind.FRAMEWORK_ACCOUNTS: FrameworkAccountEntry,
}

_PARSERS: dict[ListKind, Callable[[Mapping[str, Any]], Entry]] = {
    ListKind.ACCOUNTS: AccountEntry.parse,
    ListKind.BUDGET_EXPENSE: lambda values: BudgetEntry.parse(values, expense=True),
    ListKind.BUDGET_INCOME: lambda values: BudgetEntry.parse(values, expense=False),
    ListKind.DOCUMENT_SERIES: SeriesEntry.parse,
    ListKind.TRANSFERS: TransferEntry.parse,
    ListKind.COST_CENTRES: CostCentreEntry.parse,
    ListKind.EK: EkEntry.parse,
    ListKind.COFOG: CofogEntry.parse,
    ListKind.FUNDING_SOURCES: FundingSourceEntry.parse,
    ListKind.FRAMEWORK_ACCOUNTS: FrameworkAccountEntry.parse,
}


def parse_entry(kind: ListKind, values: Mapping[str, Any]) -> Entry:
    """An entry of the kind from its fields, validated; raises `ValidationFailed`."""
    return _PARSERS[kind](values)


def entry_fields(kind: ListKind) -> tuple[str, ...]:
    """The fields an entry of the kind is given as (`key` is derived, never stored)."""
    return tuple(name for name in ENTRY_TYPES[kind].FIELDS if name != "key")


def deactivated(entry: Entry) -> Entry:
    return replace(entry, active=False)
