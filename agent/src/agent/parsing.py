"""Product-line detection from free text (English + Taglish keywords).

Answer parsing for specific questions lives with the discriminators
(agent/discriminators.py) — questions and parsers stay together there.
"""

from shared import ProductLine

_LINE_KEYWORDS: dict[ProductLine, list[str]] = {
    ProductLine.LIFE: ["life", "income protection", "buhay", "family income", "death benefit"],
    ProductLine.HEALTH: ["health", "hmo", "medical", "hospital", "kalusugan"],
    ProductLine.TRAVEL: ["travel", "trip", "flight", "vacation", "biyahe", "abroad"],
    ProductLine.PET: ["pet", "dog", "cat", "aso", "pusa", "puppy", "kitten"],
}


def detect_product_lines(text: str) -> list[ProductLine]:
    lowered = text.lower()
    return [
        line
        for line, keywords in _LINE_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    ]
