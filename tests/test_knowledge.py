import pytest
from pydantic import ValidationError

from riso.checks import knowledge_errors
from riso.knowledge import KnowledgeBase, load_knowledge
from riso.knowledge.terms import Term, TermIndex
from riso.text import cased_words, fold, words


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(2026)


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
