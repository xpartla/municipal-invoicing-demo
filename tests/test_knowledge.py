import pytest
from pydantic import ValidationError

from riso.checks import knowledge_errors
from riso.knowledge import (
    Conventions,
    KnowledgeBase,
    knowledge_for,
    load_conventions,
    load_knowledge,
    merge,
    read_conventions,
)
from riso.knowledge.terms import Term, TermIndex
from riso.text import cased_words, fold, words

BOLDOG = "00305863"


@pytest.fixture(scope="module")
def knowledge():
    """Boldog's: the global knowledge with its conventions."""
    return knowledge_for(BOLDOG, 2026)


def test_text_folds_diacritics_and_splits_into_words():
    assert fold("Školská jedáleň") == "Skolska jedalen"
    assert words("výkon zodp.osoby, MŠ") == ("vykon", "zodp", "osoby", "ms")
    assert cased_words("Ver.osvetlenie VO") == ("Ver", "osvetlenie", "VO")


def test_a_term_matches_whole_words_or_any_ending():
    index = TermIndex([("psik*", "dogs"), ("zodp* osob*", "dpo"), ("fax", "telecom")])

    def found(text: str) -> set[str]:
        return {meaning for _, meaning in index.search(words(text))}

    assert found("OZ Pomoc psíkom") == {"dogs"}
    assert found("výkon zodp.osoby") == {"dpo"}
    assert found("telefon,fax") == {"telecom"}
    assert found("faxovanie, osoby") == set()


def test_a_term_needs_whole_words_and_endings_on_real_stems():
    with pytest.raises(ValueError, match="too short"):
        Term.parse("a*")
    with pytest.raises(ValueError, match="single word"):
        Term.parse("zodp.osoby")


def test_the_knowledge_base_fits_the_dictionaries(knowledge, index):
    assert knowledge_errors(knowledge, index) == []


def test_the_longest_ek_prefix_wins(knowledge):
    assert knowledge.su_for("633013").su == "518"  # software, not material
    assert knowledge.su_for("633006").su == "501"
    assert knowledge.su_for("717001").su == "042"
    assert knowledge.su_for("611000") is None  # wages never come on a supplier invoice


def test_abbreviations_keep_their_case(knowledge):
    assert knowledge.abbreviations["VO"] == "06 400"
    assert "vo" not in knowledge.abbreviations  # the preposition


def test_grant_sources_expect_a_transfer(knowledge):
    grant_rows = frozenset({"45", "71"})
    assert knowledge.expects_transfer("11H", grant_rows)
    assert knowledge.expects_transfer("45", grant_rows)
    assert not knowledge.expects_transfer("41", grant_rows)
    assert not knowledge.expects_transfer("72f", grant_rows)


def test_rules_may_only_name_concepts_of_the_lexicon(knowledge):
    authored = knowledge.model_dump()
    authored["canteen"]["concepts"] = ["groceries"]

    with pytest.raises(ValidationError, match="groceries"):
        KnowledgeBase.model_validate(authored)


def test_the_global_knowledge_carries_no_customers_conventions():
    base = load_knowledge(2026)
    assert base.au_rules.debit == {} and base.au_rules.credit == {}
    assert base.canteen is None
    assert "municipal_company" not in base.lexicon.concepts


def test_boldogs_conventions_add_its_rules_and_concepts(knowledge):
    base = load_knowledge(2026)
    conventions = load_conventions(BOLDOG, 2026)
    assert set(knowledge.au_rules.debit) == {"501", "502", "518", "527", "548", "042"}
    assert knowledge.au_rules.credit["321"].rules[0].zdroj == ["1BA1", "1BA2"]
    assert knowledge.canteen is not None and knowledge.canteen.md == "501 080"
    assert set(knowledge.lexicon.concepts) == set(base.lexicon.concepts) | {"municipal_company"}
    assert knowledge.transfer_rules == base.transfer_rules  # Boldog overrides nothing
    assert knowledge.bridge == base.bridge and knowledge.functions == base.functions
    assert merge(base, conventions) == knowledge


def test_a_customer_without_conventions_codes_with_the_global_knowledge():
    assert load_conventions("99900017", 2026) == Conventions()
    assert knowledge_for("99900017", 2026) == load_knowledge(2026)


def test_conventions_reject_unknown_keys_and_concepts_outside_the_lexicon():
    with pytest.raises(ValidationError):
        read_conventions("au_rule: {}\n")
    unknown = read_conventions(
        'au_rules: {debit: {"518": {default: "000", rules: [{au: "003", concepts: [x]}]}}}\n'
    )
    with pytest.raises(ValidationError, match="x"):
        merge(load_knowledge(2026), unknown)
    assert read_conventions("") == Conventions()


def test_conventions_may_not_redefine_a_global_concept_nor_merge_twice(knowledge):
    shadow = Conventions.model_validate({"concepts": {"telecom": {"terms": ["telefon*"]}}})
    with pytest.raises(ValueError, match="telecom"):
        merge(load_knowledge(2026), shadow)
    with pytest.raises(ValueError, match="holds customer conventions"):
        merge(knowledge, Conventions())


def test_transfer_overrides_add_to_the_global_rule():
    conventions = Conventions.model_validate({"transfers": {"never": ["111", "41"]}})
    merged = merge(load_knowledge(2026), conventions)
    assert merged.transfer_rules.never == ["41", "43", "52", "72f", "111"]
    assert not merged.expects_transfer("111", frozenset())


def test_riso_check_catches_a_convention_naming_a_missing_account(index):
    broken = Conventions.model_validate(
        {"au_rules": {"debit": {"518": {"default": "000", "rules": [{"au": "099"}]}}}}
    )
    assert knowledge_errors(merge(load_knowledge(2026), broken), index) == [
        "AU rules: debit account 518 099 is not in the chart"
    ]
