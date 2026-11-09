import re
lazy import unicodedata

AREAS: dict[str, tuple[str, ...]] = {
    "Andheri West": ("andheri west", "andheri (w)", "andheri w", "andheri"),
    "Bandra West": ("bandra west", "bandra (w)", "bandra w", "bandra"),
    "Powai": ("powai",),
    "Lower Parel": ("lower parel",),
    "Dadar": ("dadar west", "dadar (w)", "dadar"),
}
TOKEN_SYNONYMS = {
    "biriyani": "biryani",
    "briyani": "biryani",
    "biriani": "biryani",
    "momo": "momos",
    "roll": "rolls",
}
RESTAURANT_STOPWORDS = frozenset({"the", "restaurant"})

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_POSSESSIVE = re.compile(r"['’]s\b")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def name_tokens(text: str) -> list[str]:
    value = _BRACKETS.sub(" ", fold(text)).replace("&", " and ")
    value = _POSSESSIVE.sub("s", value)
    return [TOKEN_SYNONYMS.get(token, token) for token in _NON_ALNUM.sub(" ", value).split()]


def contains_phrase(haystack: list[str], phrase: list[str]) -> bool:
    size = len(phrase)
    return size > 0 and any(
        haystack[i : i + size] == phrase for i in range(len(haystack) - size + 1)
    )


def canonical_area(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    folded = " ".join(fold(text).split())
    for canonical, aliases in AREAS.items():
        if folded == canonical.lower() or folded in aliases:
            return canonical
    return text.strip()
