"""S8, feedback: an accepted or corrected coding goes into supplier memory and its document
number is recorded as used. Appending the case to the evaluation set is the store's job."""

from riso.contracts import Counters, Feedback, SupplierMemory


def apply_feedback(
    feedback: Feedback, memory: SupplierMemory, counters: Counters
) -> tuple[SupplierMemory, Counters]:
    raise NotImplementedError("S8, feedback, is built in M1")
