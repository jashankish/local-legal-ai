"""Lightweight legal entity extraction and follow-up question suggestions.

Pattern-based so it runs anywhere without an NLP model download. Used to
annotate answers with the parties, amounts, deadlines and governing law found
in the cited passages, and to propose sensible next questions.
"""

import re
from typing import Dict, Iterable, List

ORG_SUFFIX = r"(?:LLC|L\.L\.C\.|Inc\.?|Incorporated|Corporation|Corp\.?|LLP|PLLC|Ltd\.?|LP|Co\.)"
ORGANIZATION = re.compile(rf"\b((?:[A-Z][A-Za-z&'\-]+\s){{1,5}}{ORG_SUFFIX})(?=[\s,.;)]|$)")
DEFINED_TERM = re.compile(r'\(\s*(?:the\s+)?["“]([A-Z][A-Za-z\s\-]{1,40})["”]\s*\)')
MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?(?:\s?(?:million|billion|thousand))?", re.IGNORECASE)
DURATION = re.compile(
    r"\b(?:[a-z\-]+\s)?\(\d+\)\s(?:business\s|calendar\s)?(?:day|week|month|year)s?\b"
    r"|\b\d+\s(?:business\s|calendar\s)?(?:day|week|month|year)s?\b",
    re.IGNORECASE,
)
PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?%|\b(?:[a-z\-]+\s)?\(\d+(?:\.\d+)?%\)\s?percent|\b\d+(?:\.\d+)?\spercent\b",
                     re.IGNORECASE)
DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s\d{1,2},\s\d{4}\b|\b\d{1,2}/\d{1,2}/\d{4}\b"
)
GOVERNING_LAW = re.compile(r"laws of the (State|Commonwealth) of ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)")
CITATION = re.compile(
    r"\b\d+\s+U\.S\.C\.?\s*§+\s*\d+[a-z]?\b"           # 42 U.S.C. § 1983
    r"|\b\d+\s+C\.?F\.?R\.?\s+\d+(?:\.\d+)?\b"           # 29 CFR 1630.2
    r"|\b[A-Z][A-Za-z]+\s+v\.\s+[A-Z][A-Za-z]+,\s+\d+\s+[A-Z][A-Za-z.\d]*\s+\d+"  # Smith v. Jones, 123 F.3d 456
)

ENTITY_PATTERNS = {
    "organizations": ORGANIZATION,
    "defined_terms": DEFINED_TERM,
    "monetary_amounts": MONEY,
    "durations": DURATION,
    "percentages": PERCENT,
    "dates": DATE,
    "citations": CITATION,
}


def _unique(values: Iterable[str], limit: int = 12) -> List[str]:
    seen, result = set(), []
    for value in values:
        value = re.sub(r"\s+", " ", value).strip(" ,.;")
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
        if len(result) == limit:
            break
    return result


def extract_legal_entities(text: str) -> Dict[str, List[str]]:
    """Return entity lists keyed by type; empty types are omitted."""
    entities: Dict[str, List[str]] = {}
    for name, pattern in ENTITY_PATTERNS.items():
        found = _unique(m.group(1) if pattern.groups and name in ("organizations", "defined_terms") else m.group(0)
                        for m in pattern.finditer(text))
        if found:
            entities[name] = found
    laws = _unique(f"{m.group(1)} of {m.group(2)}" for m in GOVERNING_LAW.finditer(text))
    if laws:
        entities["governing_law"] = laws
    return entities


FOLLOW_UPS_BY_TYPE = {
    "contract": [
        "What are the payment terms and late-payment consequences?",
        "How can either party terminate the agreement?",
        "What is the cap on each party's liability?",
        "Which law governs the agreement and how are disputes resolved?",
    ],
    "nda": [
        "What information is excluded from confidentiality?",
        "How long do the confidentiality obligations last?",
        "What must happen to confidential materials when the agreement ends?",
        "What remedies are available for unauthorized disclosure?",
    ],
    "lease": [
        "What is the base rent and how does it escalate?",
        "Can the tenant terminate the lease early, and at what cost?",
        "Who is responsible for maintenance and repairs?",
        "What are the conditions for assigning or subletting?",
    ],
    "employment": [
        "What is the compensation and bonus structure?",
        "What severance is owed on termination without cause?",
        "What non-solicitation or non-compete restrictions apply?",
        "Who owns inventions created during employment?",
    ],
}
GENERIC_FOLLOW_UPS = [
    "Summarize the key obligations of each party.",
    "What deadlines or notice periods appear in these documents?",
    "What risks should a reviewing attorney flag?",
]


def suggest_follow_ups(question: str, document_types: Iterable[str], limit: int = 4) -> List[str]:
    """Propose next questions for the document types behind an answer, skipping near-duplicates."""
    asked = set(re.findall(r"[a-z]{4,}", question.lower()))
    candidates: List[str] = []
    for doc_type in document_types:
        candidates.extend(FOLLOW_UPS_BY_TYPE.get((doc_type or "").lower(), []))
    candidates.extend(GENERIC_FOLLOW_UPS)

    suggestions = []
    for candidate in _unique(candidates, limit=50):
        words = set(re.findall(r"[a-z]{4,}", candidate.lower()))
        if words and len(words & asked) / len(words) >= 0.5:
            continue  # essentially the question just asked
        suggestions.append(candidate)
        if len(suggestions) == limit:
            break
    return suggestions
