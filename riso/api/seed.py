"""`riso seed`: the demo's database (plan §4.5, decisions 45 and 52). Development and tests only.

It creates:

- Obec Boldog (00305863), with its 2026 parameters from `data/entities/00305863.json`, the
  address of its municipal office, version 1 of each of its 2026 code lists from the
  committed bundle `data/bundles/00305863/2026-08.json`, and its 2026 conventions from
  `data/conventions/00305863/2026.yaml`;
- the made-up provider "Účtovníctvo Vzor, s.r.o.", to which Boldog is assigned;
- a second, made-up municipality assigned to the provider, so staff can switch customers;
- a third, made-up municipality with no provider, for the isolation checks;
- version 1 of each global list (EK, COFOG, funding sources, framework chart) of every year
  in `data/global/`, imported through the import tool with the built-in templates (an
  import run each, its file in the store);
- one user per role: an admin, a staff member of the provider, a user and a viewer of Boldog.

The made-up municipalities carry placeholder IČOs that pass the check digit and are absent
from the register of legal entities (RPO, checked on 2026-11-08). The people are made up, with
addresses under the reserved `.test` domain.

IDs and timestamps come from a fixed clock and a seeded generator, so two seeds give the same
rows and the customer URLs (`/c/<id>`) survive a `--reset`. Only the password hashes differ
(they are salted).
"""

import json
import random
import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine.url import make_url

from riso import paths
from riso.api.composition import build_services
from riso.api.importing import first_error, run_import
from riso.api.uow import AppUnitOfWork
from riso.codelists import versions_from_bundle
from riso.codelists.domain import CustomerConventions
from riso.contracts import ReferenceBundle
from riso.exchange.domain.mapping import ImportType
from riso.exchange.domain.run import RunState
from riso.exchange.domain.templates import BUILTIN
from riso.identity.domain import Email, MembershipScope, PasswordPolicy, Role, User
from riso.identity.infrastructure.hashing import Argon2Hasher, default_policy
from riso.identity.infrastructure.orm import UserRow
from riso.knowledge import load_conventions
from riso.platform.db import Database
from riso.platform.migrations import downgrade, upgrade
from riso.platform.settings import Settings
from riso.shared.clock import FixedClock
from riso.shared.context import RequestContext
from riso.shared.errors import ValidationFailed
from riso.shared.ids import IdGenerator, UuidV7Generator
from riso.shared.values import Ico
from riso.tenancy.domain import Address, Customer, CustomerParameters, ServiceProvider

SEEDED_AT = datetime(2026, 1, 1, 7, 0, tzinfo=UTC)
BOLDOG_ICO = "00305863"
PROVIDER_NAME = "Účtovníctvo Vzor, s.r.o."
SECOND_CUSTOMER = ("Obec Vzorová Lehota", "99900017")
UNASSIGNED_CUSTOMER = ("Obec Nezávislá", "99900025")
BOLDOG_BUNDLE = "2026-08"
BOLDOG_ADDRESS = ("Boldog 89", "Boldog", "92526")
"""The municipal office, as the chart of accounts' title names it (public)."""


@dataclass(frozen=True, slots=True)
class SeedUser:
    key: str
    name: str
    email: str
    role: Role


USERS = (
    SeedUser("admin", "Alena Správcová", "admin@riso.test", Role.PLATFORM_ADMIN),
    SeedUser("staff", "Peter Účtovník", "peter.uctovnik@vzor.test", Role.PROVIDER_STAFF),
    SeedUser("user", "Jana Vzorová", "jana.vzorova@boldog.test", Role.CUSTOMER_USER),
    SeedUser("viewer", "Ivan Čitateľ", "ivan.citatel@boldog.test", Role.CUSTOMER_VIEWER),
)


class SeedRefused(Exception):
    """The environment or the database does not allow a seed; the message says why."""


@dataclass
class Seeded:
    customers: dict[str, str] = field(default_factory=dict)
    """Name → ID."""
    provider_id: str = ""
    users: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    """Key → (ID, email, password)."""
    generated_passwords: bool = False


def seed(
    settings: Settings,
    *,
    reset: bool = False,
    password: str | None = None,
    hasher: Argon2Hasher | None = None,
    policy: PasswordPolicy | None = None,
    entities_dir: Path = paths.ENTITIES_DIR,
    bundles_dir: Path = paths.BUNDLES_DIR,
    global_dir: Path = paths.GLOBAL_DIR,
    conventions_dir: Path = paths.CONVENTIONS_DIR,
) -> Seeded:
    """Migrates and seeds the database of `settings`. Refuses outside `dev` and `test`, and
    on a database that has users already unless `reset` drops it first."""
    if settings.env not in ("dev", "test"):
        raise SeedRefused("riso seed runs only with RISO_ENV=dev or RISO_ENV=test")
    policy = policy or default_policy()
    if password is not None:
        try:
            policy.check(password, field="RISO_SEED_PASSWORD")
        except ValidationFailed as exc:
            reasons = ", ".join(e.message for e in exc.errors)
            raise SeedRefused(f"RISO_SEED_PASSWORD is not accepted: {reasons}") from exc
    if reset:
        _drop(settings)
    upgrade(settings.db_url)
    db = Database(settings.db_url)
    try:
        with db.session() as session:
            if session.scalar(select(func.count()).select_from(UserRow)):
                raise SeedRefused("the database has users already; run `riso seed --reset`")
        return _fill(
            db,
            settings,
            password,
            hasher or Argon2Hasher(),
            entities_dir,
            bundles_dir,
            global_dir,
            conventions_dir,
        )
    finally:
        db.dispose()


def _drop(settings: Settings) -> None:
    url = make_url(settings.db_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        for suffix in ("", "-wal", "-shm"):
            Path(f"{url.database}{suffix}").unlink(missing_ok=True)
    else:
        downgrade(settings.db_url, "base")
    if settings.files_dir.is_dir():
        shutil.rmtree(settings.files_dir)


def _fill(
    db: Database,
    settings: Settings,
    password: str | None,
    hasher: Argon2Hasher,
    entities: Path,
    bundles: Path,
    global_root: Path,
    conventions_root: Path,
) -> Seeded:
    clock = FixedClock(SEEDED_AT)
    ids = UuidV7Generator(clock, random.Random(20260101).getrandbits)
    result = Seeded(generated_passwords=password is None)
    choose: Callable[[], str] = (lambda: password) if password else _generated
    with AppUnitOfWork(db, clock=clock, ids=ids) as uow:
        now = clock.now()
        provider = ServiceProvider.create(ids.new(), PROVIDER_NAME, now)
        uow.providers.add(provider)
        result.provider_id = provider.id

        boldog_settings = json.loads((entities / f"{BOLDOG_ICO}.json").read_text(encoding="utf-8"))
        boldog = Customer.create(ids.new(), boldog_settings["name"], Ico(BOLDOG_ICO), now)
        second = Customer.create(ids.new(), SECOND_CUSTOMER[0], Ico(SECOND_CUSTOMER[1]), now)
        alone = Customer.create(ids.new(), UNASSIGNED_CUSTOMER[0], Ico(UNASSIGNED_CUSTOMER[1]), now)
        boldog.update_contact(Address.parse(*BOLDOG_ADDRESS), None)
        boldog.assign_to(provider)
        second.assign_to(provider)
        for customer in (boldog, second, alone):
            uow.customers.add(customer)
            result.customers[customer.name] = customer.id
        values = {k: boldog_settings[k] for k in CustomerParameters.FIELDS}
        uow.parameters.save(
            CustomerParameters.parse(boldog.id, boldog_settings["budget_year"], values)
        )

        scope_of = {
            Role.PLATFORM_ADMIN: MembershipScope.platform(),
            Role.PROVIDER_STAFF: MembershipScope.provider(provider.id),
            Role.CUSTOMER_USER: MembershipScope.customer(boldog.id),
            Role.CUSTOMER_VIEWER: MembershipScope.customer(boldog.id),
        }
        for spec in USERS:
            secret = choose()
            user = User.invite(ids.new(), spec.name, Email.parse(spec.email), now)
            user.set_password(hasher.hash(secret), now)
            user.grant(ids.new(), scope_of[spec.role], spec.role, now)
            uow.users.add(user)
            result.users[spec.key] = (user.id, spec.email, secret)

        # After the users, so their IDs stay what earlier seeds gave them.
        bundle = ReferenceBundle.model_validate_json(
            (bundles / BOLDOG_ICO / f"{BOLDOG_BUNDLE}.json").read_bytes()
        )
        for version in versions_from_bundle(bundle, boldog.id, ids, now):
            uow.codelists.add(version)
        year = boldog_settings["budget_year"]
        uow.conventions.save(
            CustomerConventions.create(
                boldog.id, year, load_conventions(BOLDOG_ICO, year, conventions_root), now, None
            )
        )
        uow.commit()
    _import_global_lists(settings, clock, ids, global_root)
    return result


GLOBAL_FILES: dict[ImportType, str] = {
    ImportType.EK: "ek.csv",
    ImportType.COFOG: "cofog.csv",
    ImportType.FUNDING_SOURCES: "funding_sources.csv",
    ImportType.FRAMEWORK_ACCOUNTS: "framework_accounts.csv",
}
"""The files of `data/global/<year>/`, header `code,name` (see its README for the sources)."""


def global_years(root: Path) -> list[int]:
    if not root.is_dir():
        return []
    return sorted(int(d.name) for d in root.iterdir() if d.is_dir() and d.name.isdigit())


def _import_global_lists(
    settings: Settings, clock: FixedClock, ids: IdGenerator, root: Path
) -> None:
    """Each global list of each year through the import tool, with its built-in template.
    A file that does not import stops the seed, naming the file and the row."""
    services = build_services(settings, clock=clock, ids=ids)
    ctx = RequestContext.system("seed")
    try:
        for year in global_years(root):
            for import_type, name in GLOBAL_FILES.items():
                path = root / str(year) / name
                if not path.is_file():
                    continue
                template = BUILTIN[f"builtin:global-{import_type.value}"]
                try:
                    data = path.read_bytes()
                    run = run_import(
                        services, ctx, None, import_type, year, name, data, template=template
                    )
                except ValidationFailed as exc:
                    raise SeedRefused(f"{path}: {exc.message}") from exc
                if run.state is not RunState.APPLIED:
                    raise SeedRefused(f"{path.parent}/{first_error(run)}")
    finally:
        services.close()


def _generated() -> str:
    return secrets.token_urlsafe(12)
