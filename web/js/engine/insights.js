// Key-term extraction and follow-up suggestions.
//
// A direct port of rag/legal_insights.py so the demo annotates answers with the
// same parties, amounts, periods and governing law the product does — including
// for a document the visitor uploads here, which the Python side never sees.
// tools/selftest.mjs checks this port against web/demo/entities.json, which the
// Python extractor generated, so the two cannot drift apart silently.

const ORG_SUFFIX = "(?:LLC|L\\.L\\.C\\.|Inc\\.?|Incorporated|Corporation|Corp\\.?|LLP|PLLC|Ltd\\.?|LP|Co\\.)";
const ORGANIZATION = new RegExp(`\\b((?:[A-Z][A-Za-z&'\\-]+\\s){1,5}${ORG_SUFFIX})(?=[\\s,.;)]|$)`, "g");
const DEFINED_TERM = /\(\s*(?:the\s+)?["“]([A-Z][A-Za-z\s-]{1,40})["”]\s*\)/g;
const MONEY = /\$\s?\d[\d,]*(?:\.\d{2})?(?:\s?(?:million|billion|thousand))?/gi;
const DURATION = new RegExp(
  "\\b(?:[a-z-]+\\s)?\\(\\d+\\)\\s(?:business\\s|calendar\\s)?(?:day|week|month|year)s?\\b" +
  "|\\b\\d+\\s(?:business\\s|calendar\\s)?(?:day|week|month|year)s?\\b",
  "gi",
);
const PERCENT = /\b\d+(?:\.\d+)?\s?%|\b(?:[a-z-]+\s)?\(\d+(?:\.\d+)?%\)\s?percent|\b\d+(?:\.\d+)?\spercent\b/gi;
const DATE = new RegExp(
  "\\b(?:January|February|March|April|May|June|July|August|September|October|November|December)" +
  "\\s\\d{1,2},\\s\\d{4}\\b|\\b\\d{1,2}/\\d{1,2}/\\d{4}\\b",
  "g",
);
const GOVERNING_LAW = /laws of the (State|Commonwealth) of ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)/g;
const CITATION = new RegExp(
  "\\b\\d+\\s+U\\.S\\.C\\.?\\s*§+\\s*\\d+[a-z]?\\b" +
  "|\\b\\d+\\s+C\\.?F\\.?R\\.?\\s+\\d+(?:\\.\\d+)?\\b" +
  "|\\b[A-Z][A-Za-z]+\\s+v\\.\\s+[A-Z][A-Za-z]+,\\s+\\d+\\s+[A-Z][A-Za-z.\\d]*\\s+\\d+",
  "g",
);

// Ordered as in the Python module, so entities.json compares key for key.
const ENTITY_PATTERNS = [
  ["organizations", ORGANIZATION, 1],
  ["defined_terms", DEFINED_TERM, 1],
  ["monetary_amounts", MONEY, 0],
  ["durations", DURATION, 0],
  ["percentages", PERCENT, 0],
  ["dates", DATE, 0],
  ["citations", CITATION, 0],
];

export const ENTITY_LABELS = {
  organizations: "🏢 Parties",
  defined_terms: "📖 Defined terms",
  monetary_amounts: "💵 Amounts",
  durations: "⏱️ Periods",
  percentages: "📈 Rates",
  dates: "📅 Dates",
  governing_law: "⚖️ Governing law",
  citations: "📚 Citations",
};

function unique(values, limit = 12) {
  const seen = new Set();
  const result = [];
  for (const raw of values) {
    const value = String(raw).replace(/\s+/g, " ").replace(/^[\s,.;]+|[\s,.;]+$/g, "");
    const key = value.toLowerCase();
    if (value && !seen.has(key)) {
      seen.add(key);
      result.push(value);
    }
    if (result.length === limit) break;
  }
  return result;
}

function matches(pattern, text, group) {
  pattern.lastIndex = 0;
  const found = [];
  let match;
  while ((match = pattern.exec(text)) !== null) {
    found.push(match[group] ?? match[0]);
    if (match[0] === "") pattern.lastIndex += 1; // never spin on a zero-width match
  }
  return found;
}

/** Entity lists keyed by type; types with no hits are omitted. */
export function extractLegalEntities(text) {
  const entities = {};
  for (const [name, pattern, group] of ENTITY_PATTERNS) {
    const found = unique(matches(pattern, text, group));
    if (found.length) entities[name] = found;
  }
  GOVERNING_LAW.lastIndex = 0;
  const laws = [];
  let match;
  while ((match = GOVERNING_LAW.exec(text)) !== null) laws.push(`${match[1]} of ${match[2]}`);
  const uniqueLaws = unique(laws);
  if (uniqueLaws.length) entities.governing_law = uniqueLaws;
  return entities;
}

const FOLLOW_UPS_BY_TYPE = {
  contract: [
    "What are the payment terms and late-payment consequences?",
    "How can either party terminate the agreement?",
    "What is the cap on each party's liability?",
    "Which law governs the agreement and how are disputes resolved?",
  ],
  nda: [
    "What information is excluded from confidentiality?",
    "How long do the confidentiality obligations last?",
    "What must happen to confidential materials when the agreement ends?",
    "What remedies are available for unauthorized disclosure?",
  ],
  lease: [
    "What is the base rent and how does it escalate?",
    "Can the tenant terminate the lease early, and at what cost?",
    "Who is responsible for maintenance and repairs?",
    "What are the conditions for assigning or subletting?",
  ],
  employment: [
    "What is the compensation and bonus structure?",
    "What severance is owed on termination without cause?",
    "What non-solicitation or non-compete restrictions apply?",
    "Who owns inventions created during employment?",
  ],
  license: [
    "What does the license permit, and how many users does it cover?",
    "What are the support and response-time commitments?",
    "How is customer data protected, and when must a breach be reported?",
    "What warranty is given and what is the remedy if it is broken?",
  ],
};

const GENERIC_FOLLOW_UPS = [
  "Summarize the key obligations of each party.",
  "What deadlines or notice periods appear in these documents?",
  "What risks should a reviewing attorney flag?",
];

/** Next questions for the document types behind an answer, skipping near-duplicates. */
export function suggestFollowUps(question, documentTypes, limit = 4) {
  const asked = new Set(String(question).toLowerCase().match(/[a-z]{4,}/g) || []);
  const candidates = [];
  for (const type of documentTypes) {
    candidates.push(...(FOLLOW_UPS_BY_TYPE[String(type || "").toLowerCase()] || []));
  }
  candidates.push(...GENERIC_FOLLOW_UPS);

  const suggestions = [];
  for (const candidate of unique(candidates, 50)) {
    const words = new Set(candidate.toLowerCase().match(/[a-z]{4,}/g) || []);
    if (words.size) {
      const shared = [...words].filter((word) => asked.has(word)).length;
      if (shared / words.size >= 0.5) continue; // essentially the question just asked
    }
    suggestions.push(candidate);
    if (suggestions.length === limit) break;
  }
  return suggestions;
}
