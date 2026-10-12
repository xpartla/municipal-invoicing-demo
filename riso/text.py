"""Text normalisation shared by the knowledge base and the engine. Diacritics fold away and
matching works word by word, so 'Školská jedáleň' and 'skolska jedalen' are the same."""

import re
import unicodedata
from collections.abc import Iterable

_WORD = re.compile(r"[0-9A-Za-z]+")


def fold(text: str) -> str:
    """Diacritics removed, case kept."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def words(text: str) -> tuple[str, ...]:
    """Lower-case words without diacritics."""
    return tuple(word.lower() for word in _WORD.findall(fold(text)))


def cased_words(text: str) -> tuple[str, ...]:
    """Words without diacritics with their case kept, for abbreviations such as MŠ or VO."""
    return tuple(_WORD.findall(fold(text)))


def stems(tokens: Iterable[str], stopwords: frozenset[str], length: int = 5) -> frozenset[str]:
    """Word beginnings, for overlap that survives Slovak case endings: 'rozpočtovej' and
    'rozpočetovníctvo' share 'rozpo'."""
    return frozenset(
        token[:length]
        for token in tokens
        if len(token) >= 3 and token not in stopwords and not token.isdigit()
    )


def coverage(part: frozenset[str], whole: frozenset[str]) -> float:
    """Share of `part` found in `whole`; 0 when `part` is empty."""
    return len(part & whole) / len(part) if part else 0.0
