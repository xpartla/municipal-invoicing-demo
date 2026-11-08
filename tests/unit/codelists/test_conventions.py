"""A customer's conventions: revisions, and the use cases with in-memory fakes."""

from datetime import UTC, datetime

import pytest

from riso.codelists import customer_knowledge, get_conventions, set_conventions
from riso.codelists.application.conventions import KnowledgeCache
from riso.codelists.domain import ConventionsChanged, CustomerConventions
from riso.knowledge import Conventions, knowledge_for, load_conventions, load_knowledge
from riso.shared import (
    AllowAll,
    Conflict,
    DenyAll,
    InvalidState,
    PermissionDenied,
    RequestContext,
    ValidationFailed,
)
from tests.fakes.codelists import InMemoryCodelistsUnitOfWork

AT = datetime(2026, 11, 8, tzinfo=UTC)
CTX = RequestContext(request_id="r1", actor_id="u1", policy=AllowAll())
BOLDOG = load_conventions("00305863", 2026)
SMALL = {
    "au_rules": {"debit": {"518": {"default": "000", "rules": [{"au": "003", "ek": ["632005"]}]}}}
}


def test_a_change_raises_the_revision_and_an_equal_document_does_not():
    conventions = CustomerConventions.create("c1", 2026, Conventions(), AT, None)
    assert conventions.revision == 1 and conventions.events == [ConventionsChanged("c1", 2026, 1)]
    assert not conventions.replace(Conventions(), AT, "u1")
    assert conventions.replace(BOLDOG, AT, "u1", expected_revision=1)
    assert (conventions.revision, conventions.updated_by) == (2, "u1")
    with pytest.raises(Conflict):
        conventions.replace(Conventions(), AT, "u1", expected_revision=1)


def test_a_customer_without_conventions_reads_as_revision_0():
    view = get_conventions(CTX, InMemoryCodelistsUnitOfWork(), "c1", 2026)
    assert (view.revision, view.updated_at) == (0, None)
    assert Conventions.model_validate(view.document) == Conventions()


def test_setting_conventions_is_audited_with_before_and_after():
    uow = InMemoryCodelistsUnitOfWork()
    first = set_conventions(CTX, uow, "c1", 2026, SMALL, expected_revision=0)
    assert first.revision == 1
    second = set_conventions(
        CTX, uow, "c1", 2026, BOLDOG.model_dump(mode="json"), expected_revision=1
    )
    assert second.revision == 2
    entries = [e for e in uow.audit.entries if e["action"] == "conventions.updated"]
    assert [e["details"]["revision"] for e in entries] == [1, 2]
    assert entries[0]["details"]["before"] is None
    assert entries[1]["details"]["before"] == first.document
    assert entries[1]["details"]["after"] == second.document
    assert entries[1]["customer_id"] == "c1" and entries[1]["actor_id"] == "u1"
    unchanged = set_conventions(CTX, uow, "c1", 2026, BOLDOG.model_dump(mode="json"))
    assert unchanged.revision == 2 and len(uow.audit.entries) == 2


def test_a_stale_revision_is_a_conflict():
    uow = InMemoryCodelistsUnitOfWork()
    set_conventions(CTX, uow, "c1", 2026, SMALL)
    with pytest.raises(Conflict):
        set_conventions(CTX, uow, "c1", 2026, {}, expected_revision=0)
    with pytest.raises(InvalidState):
        set_conventions(CTX, uow, "c2", 2026, SMALL, expected_revision=3)


@pytest.mark.parametrize(
    ("document", "field"),
    [
        ({"au_rule": {}}, "au_rule"),
        ({"au_rules": {"debit": {"518": {"default": "3"}}}}, "au_rules.debit.518.default"),
        (
            {
                "au_rules": {
                    "debit": {
                        "518": {"default": "000", "rules": [{"au": "003", "concepts": ["nope"]}]}
                    }
                }
            },
            "concepts",
        ),
        ({"concepts": {"telecom": {"terms": ["telefon*"]}}}, "concepts"),
    ],
)
def test_an_invalid_document_names_the_field(document, field):
    with pytest.raises(ValidationFailed) as caught:
        set_conventions(CTX, InMemoryCodelistsUnitOfWork(), "c1", 2026, document)
    assert field in [e.field for e in caught.value.errors]


def test_a_year_without_global_knowledge_is_refused():
    with pytest.raises(InvalidState):
        set_conventions(CTX, InMemoryCodelistsUnitOfWork(), "c1", 2031, {})


def test_reading_needs_read_access_and_writing_the_edit_permission():
    denied = RequestContext(request_id="r1", actor_id="u1", policy=DenyAll())
    with pytest.raises(PermissionDenied):
        get_conventions(denied, InMemoryCodelistsUnitOfWork(), "c1", 2026)
    with pytest.raises(PermissionDenied):
        set_conventions(denied, InMemoryCodelistsUnitOfWork(), "c1", 2026, {})


def test_the_customers_knowledge_merges_its_stored_conventions():
    uow = InMemoryCodelistsUnitOfWork()
    cache = KnowledgeCache()
    knowledge, revision = customer_knowledge(CTX, uow, "c1", 2026, cache=cache)
    assert (knowledge, revision) == (load_knowledge(2026), 0)
    set_conventions(CTX, uow, "c1", 2026, BOLDOG.model_dump(mode="json"))
    knowledge, revision = customer_knowledge(CTX, uow, "c1", 2026, cache=cache)
    assert revision == 1 and knowledge == knowledge_for("00305863", 2026)
    assert customer_knowledge(CTX, uow, "c1", 2026, cache=cache)[0] is knowledge
