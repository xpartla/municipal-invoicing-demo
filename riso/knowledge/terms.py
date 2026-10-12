"""Term matching. A term is a sequence of words; a word ending in * matches any ending, so
'psik*' finds 'psíkom' and 'zodp* osob*' finds 'zodp.osoby'."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from riso.text import words


@dataclass(frozen=True)
class Term:
    text: str
    parts: tuple[tuple[str, bool], ...]  # (word, whether any ending matches)

    @classmethod
    def parse(cls, text: str) -> "Term":
        parts = []
        for raw in text.split():
            folded = words(raw.rstrip("*"))
            if len(folded) != 1:
                raise ValueError(f"term {text!r}: {raw!r} is not a single word")
            prefix = raw.endswith("*")
            if prefix and len(folded[0]) < 2:
                raise ValueError(f"term {text!r}: {raw!r} is too short to match endings")
            parts.append((folded[0], prefix))
        if not parts:
            raise ValueError("a term needs at least one word")
        return cls(text=text, parts=tuple(parts))

    def matches_at(self, tokens: Sequence[str], start: int) -> bool:
        if start + len(self.parts) > len(tokens):
            return False
        return all(
            tokens[start + i].startswith(word) if prefix else tokens[start + i] == word
            for i, (word, prefix) in enumerate(self.parts)
        )


class TermIndex:
    """Finds which of many terms occur in a sequence of words. Each term names what it
    stands for: a concept, a function code, a marker."""

    def __init__(self, entries: Iterable[tuple[str, str]]) -> None:
        self._exact: dict[str, list[tuple[Term, str]]] = defaultdict(list)
        self._prefix: dict[str, list[tuple[Term, str]]] = defaultdict(list)
        for text, meaning in entries:
            term = Term.parse(text)
            first, prefix = term.parts[0]
            (self._prefix[first[:2]] if prefix else self._exact[first]).append((term, meaning))

    def search(self, tokens: Sequence[str]) -> list[tuple[Term, str]]:
        """Each (term, meaning) that occurs, once, in order of first occurrence."""
        found: dict[tuple[str, str], tuple[Term, str]] = {}
        for i, token in enumerate(tokens):
            for term, meaning in (*self._exact.get(token, ()), *self._prefix.get(token[:2], ())):
                if (term.text, meaning) not in found and term.matches_at(tokens, i):
                    found[(term.text, meaning)] = (term, meaning)
        return list(found.values())
