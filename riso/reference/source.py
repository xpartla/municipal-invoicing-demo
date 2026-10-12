"""Where the engine gets reference data. The demo reads the JSON written by `riso ingest`;
a database or the accounting software's API can stand behind the same interface later."""

from pathlib import Path
from typing import Protocol

from riso import paths
from riso.contracts import EntityContext, ReferenceBundle


class UnknownEntity(LookupError):
    pass


class ReferenceSource(Protocol):
    def entities(self) -> list[str]:
        """IČO of every entity with reference data."""
        ...

    def bundle(self, ico: str, period: str | None = None) -> ReferenceBundle:
        """The entity's bundle for the period, the newest one when no period is given."""
        ...

    def context(self, ico: str) -> EntityContext: ...


class LocalReferenceSource:
    """Bundles at <bundles>/<IČO>/<period>.json, entity settings at <entities>/<IČO>.json."""

    def __init__(
        self, bundles_dir: Path = paths.BUNDLES_DIR, entities_dir: Path = paths.ENTITIES_DIR
    ) -> None:
        self.bundles_dir = bundles_dir
        self.entities_dir = entities_dir
        self._bundles: dict[Path, ReferenceBundle] = {}

    def entities(self) -> list[str]:
        if not self.bundles_dir.is_dir():
            return []
        return sorted(
            d.name for d in self.bundles_dir.iterdir() if d.is_dir() and any(d.glob("*.json"))
        )

    def periods(self, ico: str) -> list[str]:
        return sorted(p.stem for p in (self.bundles_dir / ico).glob("*.json"))

    def bundle(self, ico: str, period: str | None = None) -> ReferenceBundle:
        periods = self.periods(ico)
        if not periods:
            raise UnknownEntity(f"no reference bundle for IČO {ico}")
        chosen = period or periods[-1]
        if chosen not in periods:
            raise UnknownEntity(f"no reference bundle for IČO {ico} and period {chosen}")
        path = self.bundles_dir / ico / f"{chosen}.json"
        if path not in self._bundles:
            self._bundles[path] = ReferenceBundle.model_validate_json(path.read_bytes())
        return self._bundles[path]

    def context(self, ico: str) -> EntityContext:
        path = self.entities_dir / f"{ico}.json"
        if not path.is_file():
            raise UnknownEntity(f"no entity settings for IČO {ico}")
        return EntityContext.model_validate_json(path.read_bytes())
