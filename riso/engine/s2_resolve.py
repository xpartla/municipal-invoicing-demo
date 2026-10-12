"""S2, resolution: the supplier's precedents, the series (FD, or FDŠJ for the canteen), the
document number and the booking date from the handwritten note, and the counter's next number
only when the handwritten number is missing."""

from riso.contracts import Counters, EntityContext, ReferenceBundle, SupplierMemory
from riso.engine.models import NormalisedInvoice, ResolvedContext


def resolve(
    invoice: NormalisedInvoice,
    *,
    entity: EntityContext,
    bundle: ReferenceBundle,
    memory: SupplierMemory,
    counters: Counters,
) -> ResolvedContext:
    raise NotImplementedError("S2, resolution, is built in M1")
