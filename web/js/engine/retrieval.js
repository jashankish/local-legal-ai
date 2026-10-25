// Retrieval for the static demo: a TF-IDF vector space over the indexed
// passages, scored by cosine similarity.
//
// The product itself embeds passages with MiniLM in ChromaDB and, when a local
// model is connected, has that model write the answer from the retrieved
// passages. Neither can run in a visitor's browser, so the demo uses the same
// TF-IDF fallback the product ships (rag/simple_embedder.py) and composes the
// answer extractively — which is exactly what the real system does when no
// local model is connected. Questions are answered live against the real
// passages, so anything in the library can be asked about.

const STOP_WORDS = new Set((
  "a an the and or but if then than that this these those of in on at to for from by with without " +
  "is are was were be been being am do does did doing have has had having will would shall should " +
  "may might must can could as it its it's they them their there here what which who whom whose " +
  "when where why how all any both each few more most other some such no nor not only own same so " +
  "too very s t just don now i you he she we us our your my me"
).split(" "));

// Pairs that mean the same thing in a contract but share no word stem, so a
// question phrased in plain English still reaches the clause that answers it.
const SYNONYMS = {
  cost: ["fee", "fees", "price", "payment"],
  pay: ["payment", "fee", "invoice", "retainer"],
  salary: ["compensation", "base", "pay"],
  cancel: ["terminate", "termination"],
  quit: ["terminate", "termination", "resign"],
  end: ["terminate", "termination", "expiration"],
  break: ["terminate", "breach"],
  secret: ["confidential", "confidentiality"],
  nda: ["confidential", "confidentiality", "disclosure"],
  rent: ["rent", "lease", "base"],
  late: ["late", "overdue", "default"],
  sue: ["dispute", "arbitration", "claim", "liability"],
  law: ["governing", "governed", "jurisdiction"],
  fired: ["terminated", "termination", "cause", "severance"],
  notice: ["notice", "written", "days"],
  renew: ["renewal", "renews", "successive", "term"],
  owner: ["landlord", "licensor", "company"],
  bonus: ["bonus", "compensation", "incentive"],
};

export function tokenize(text) {
  const words = String(text || "").toLowerCase().match(/[a-z][a-z'-]{1,}/g) || [];
  return words.filter((word) => word.length > 2 && !STOP_WORDS.has(word)).map(stem);
}

// A deliberately small suffix stripper: enough to match "terminate"/"termination"
// and "pay"/"payment", without the weight of a real Porter stemmer.
function stem(word) {
  for (const suffix of ["ations", "ation", "ments", "ment", "ities", "ity", "ing", "ies", "es", "ed", "s"]) {
    if (word.length > suffix.length + 3 && word.endsWith(suffix)) {
      return word.slice(0, -suffix.length);
    }
  }
  return word;
}

function expand(terms) {
  const expanded = [...terms];
  for (const term of terms) {
    for (const [key, values] of Object.entries(SYNONYMS)) {
      if (stem(key) === term) expanded.push(...values.map(stem));
    }
  }
  return expanded;
}

/**
 * Build the searchable index once, from the passages shipped in web/demo/.
 *
 * A passage may carry `searchText` — its own words plus the document's title,
 * category and clause heading. Every agreement has a governing-law clause, so
 * without the title "which law governs the services agreement?" cannot tell
 * them apart; the title is what makes the question answerable. Only `text` is
 * ever displayed.
 */
export function buildIndex(passages) {
  const documentFrequency = new Map();
  const contextTerms = passages.map((passage) => new Set(tokenize(passage.contextText || "")));
  const vectors = passages.map((passage) => {
    const counts = new Map();
    for (const term of tokenize(passage.searchText || passage.text)) {
      counts.set(term, (counts.get(term) || 0) + 1);
    }
    for (const term of counts.keys()) {
      documentFrequency.set(term, (documentFrequency.get(term) || 0) + 1);
    }
    return counts;
  });

  const total = passages.length || 1;
  const weighted = vectors.map((counts) => {
    const vector = new Map();
    let norm = 0;
    for (const [term, count] of counts) {
      const idf = Math.log((total + 1) / ((documentFrequency.get(term) || 0) + 1)) + 1;
      const weight = (1 + Math.log(count)) * idf;
      vector.set(term, weight);
      norm += weight * weight;
    }
    norm = Math.sqrt(norm) || 1;
    for (const [term, weight] of vector) vector.set(term, weight / norm);
    return vector;
  });

  return { passages, vectors: weighted, contextTerms, documentFrequency, total };
}

/**
 * Rank passages against a question, best first.
 *
 * The score reported as "relevance" is idf-weighted *coverage*: how much of
 * what the question asks about this passage actually contains. Plain cosine
 * similarity is used only to break ties. Coverage is the right measure here
 * because a question is a handful of words and a clause is a few hundred: their
 * cosine is near zero even for a perfect match, which would show a visitor
 * "relevance 0.25" for the clause that answers them exactly.
 */
export function search(index, question, limit = 5) {
  const terms = expand(tokenize(question));
  if (!terms.length) return [];

  const counts = new Map();
  for (const term of terms) counts.set(term, (counts.get(term) || 0) + 1);

  const idfOf = (term) =>
    Math.log((index.total + 1) / ((index.documentFrequency.get(term) || 0) + 1)) + 1;

  const query = new Map();
  let norm = 0;
  let totalWeight = 0;
  for (const [term, count] of counts) {
    const idf = idfOf(term);
    const weight = (1 + Math.log(count)) * idf;
    query.set(term, weight);
    norm += weight * weight;
    totalWeight += idf;
  }
  norm = Math.sqrt(norm) || 1;
  totalWeight = totalWeight || 1;

  const scored = index.vectors.map((vector, position) => {
    const context = index.contextTerms[position] || EMPTY_SET;
    let cosine = 0;
    let covered = 0;
    let named = 0;
    for (const [term, weight] of query) {
      const other = vector.get(term);
      if (other) {
        cosine += (weight / norm) * other;
        covered += idfOf(term);
      }
      // Words from the document's own title and type: the question naming the
      // document it means ("the services agreement") is strong evidence, and
      // without this a clause every agreement has — governing law, notice,
      // liability — is a coin toss between documents.
      if (context.has(term)) named += idfOf(term);
    }
    const coverage = Math.min(1, (covered + TITLE_WEIGHT * named) / totalWeight);
    return { position, coverage, cosine };
  });

  return scored
    .filter((row) => row.coverage > 0.08)
    .sort((a, b) => (b.coverage - a.coverage) || (b.cosine - a.cosine))
    .slice(0, limit)
    .map((row) => ({
      passage: index.passages[row.position],
      similarity: round(row.coverage),
      cosine: round(row.cosine),
    }));
}

const EMPTY_SET = new Set();

// How much a title match counts next to a body match. High enough to settle
// which document a question is about, low enough that it cannot outweigh a
// clause that genuinely answers it.
const TITLE_WEIGHT = 0.6;

function round(value) { return Math.round(value * 1000) / 1000; }

// "Section 8. Governing Law and Disputes." — structure, not prose. Left in, a
// heading reads as a very on-topic "sentence" and gets quoted as the answer.
const CLAUSE_HEADING = /^\s*(?:Section|Article|Chapter|Part)\s+\d+\.\s*(?:[A-Z][A-Za-z]*(?:[ ,'&/-]+[A-Za-z][A-Za-z]*)*\.\s*)?/;

// A leftover heading ("Term and Termination", "Limitation of Liability"): a
// short run of capitalised words with no lower-case connective prose.
function isHeading(sentence) {
  const words = sentence.replace(/[.;:]$/, "").split(/\s+/);
  return words.length <= 7 && words.every((word) => /^[A-Z(]|^(?:and|or|of|the|to|for)$/.test(word));
}

function sentences(text) {
  return text
    .replace(/\s+/g, " ")
    .replace(CLAUSE_HEADING, "")
    .split(/(?<=[.;:])\s+(?=[A-Z(])/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 40 && !isHeading(sentence));
}

/**
 * Compose an extractive answer: the sentences from the retrieved passages that
 * actually bear on the question, each carrying the citation of the passage it
 * came from. This is the product's behaviour with no local model connected.
 */
export function composeAnswer(question, hits) {
  if (!hits.length) {
    return {
      answer: "No passage in the library matches that question, so no answer was produced — " +
        "answers here never come from outside your documents. Try rephrasing, or ask about " +
        "termination, fees, confidentiality, liability or governing law.",
      citations: [],
      mode: "no_match",
    };
  }

  const queryTerms = new Set(expand(tokenize(question)));
  const candidates = [];
  // Only the clauses the retriever actually ranked at the top are quotable.
  // Drawing from further down produces answers assembled out of whichever
  // clause happened to share a word with the question.
  hits.slice(0, 2).forEach((hit, hitIndex) => {
    for (const sentence of sentences(hit.passage.text)) {
      const terms = tokenize(sentence);
      if (!terms.length) continue;
      const overlap = terms.filter((term) => queryTerms.has(term)).length;
      if (!overlap) continue;
      candidates.push({
        sentence,
        citation: hitIndex + 1,
        // Density of the question's terms, scaled by how well the retriever
        // rated the clause — so the best clause's sentences win outright.
        score: (overlap / Math.sqrt(terms.length)) * (hit.similarity ** 2),
      });
    }
  });

  candidates.sort((a, b) => b.score - a.score);

  // Keep only sentences that are nearly as on-point as the best one. Without
  // this an answer trails off into preambles and unrelated clauses that happen
  // to share a word with the question.
  const threshold = candidates.length ? candidates[0].score * 0.7 : 0;
  const chosen = [];
  const seen = new Set();
  for (const candidate of candidates) {
    if (candidate.score < threshold) break;
    const key = candidate.sentence.slice(0, 60).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    chosen.push(candidate);
    // Two clauses is the most that still reads as an answer rather than a dump.
    if (chosen.length === 2) break;
  }

  if (!chosen.length) {
    // Nothing in the top clauses reads as a sentence about the question (a
    // definitions list, a signature block): quote the best clause as it stands.
    const first = hits[0];
    const body = first.passage.text.replace(/\s+/g, " ").trim();
    return { answer: `${body} [1]`, citations: [1], mode: "extractive" };
  }

  // Read in the order the clauses appear, not in score order.
  chosen.sort((a, b) => a.citation - b.citation);
  const answer = chosen
    .map((candidate) => `${candidate.sentence.replace(/\s*$/, "")} [${candidate.citation}]`)
    .join(" ");

  return {
    answer,
    citations: [...new Set(chosen.map((candidate) => candidate.citation))].sort((a, b) => a - b),
    mode: "extractive",
  };
}
