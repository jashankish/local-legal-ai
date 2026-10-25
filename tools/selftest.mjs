// Self-test for the browser engine behind the static demo.
//
// Runs the same modules the page loads, with no browser involved:
//   1. the key-term extractor matches the Python one byte for byte
//      (web/demo/entities.json is the Python extractor's own output);
//   2. realistic questions retrieve the clause that actually answers them;
//   3. the composed answer cites the passage it quoted;
//   4. clause splitting reproduces the passage counts in the shipped library.
//
//   node tools/selftest.mjs

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = join(ROOT, "web");

const { buildIndex, search, composeAnswer } = await import(join(WEB, "js/engine/retrieval.js"));
const { extractLegalEntities, suggestFollowUps } = await import(join(WEB, "js/engine/insights.js"));
const { splitIntoClauses, sectionTitle, searchablePassages } = await import(join(WEB, "js/api.js"));

const readJson = async (name) => JSON.parse(await readFile(join(WEB, "demo", name), "utf8"));

let failures = 0;
function check(name, condition, detail = "") {
  if (condition) {
    console.log(`  ok    ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL  ${name}${detail ? `\n          ${detail}` : ""}`);
  }
}

const library = await readJson("library.json");
const entities = await readJson("entities.json");

console.log("\nKey-term extraction matches the Python extractor");
{
  let mismatched = 0;
  let firstMismatch = "";
  for (const passage of library.passages) {
    const expected = JSON.stringify(entities[passage.id] ?? {});
    const actual = JSON.stringify(extractLegalEntities(passage.text));
    if (expected !== actual) {
      mismatched += 1;
      if (!firstMismatch) {
        firstMismatch = `${passage.id}\n          python: ${expected}\n          js:     ${actual}`;
      }
    }
  }
  check(`all ${library.passages.length} shipped passages extract identically`,
    mismatched === 0, firstMismatch);
}

console.log("\nClause splitting reproduces the indexed passages");
{
  const grouped = new Map();
  for (const passage of library.passages) {
    if (!grouped.has(passage.document_id)) grouped.set(passage.document_id, []);
    grouped.get(passage.document_id).push(passage);
  }
  for (const document of library.documents) {
    const passages = grouped.get(document.id) || [];
    check(`${document.filename}: ${document.chunk_count} passages indexed`,
      passages.length === document.chunk_count,
      `library says ${document.chunk_count}, found ${passages.length}`);
  }

  const rebuilt = splitIntoClauses(
    "PREAMBLE TEXT here, long enough to stand on its own as an opening paragraph.\n\n" +
    "Section 1. Services. Provider shall perform the services.\n\n" +
    "Section 2. Fees. Client shall pay $100.\n\n" +
    "Section 3. Term. Two (2) years.");
  check("a four-clause document splits into four passages", rebuilt.length === 4,
    `got ${rebuilt.length}: ${JSON.stringify(rebuilt.map((part) => part.slice(0, 24)))}`);
  check("clause headings are recovered",
    sectionTitle(rebuilt[1]) === "Section 1. Services", sectionTitle(rebuilt[1]));
}

console.log("\nRetrieval finds the clause that answers the question");
// Index exactly as the app does, title context included.
const index = buildIndex(searchablePassages(library.documents, library.passages));
const byId = new Map(library.documents.map((document) => [document.id, document]));

// question → the file it must cite, and a phrase the answer must contain.
const QUESTIONS = [
  ["Can the tenant terminate the lease early, and what does it cost?",
    "commercial_lease.pdf", "four (4) months of then-current base rent"],
  ["What notice period is required to terminate the services agreement for convenience?",
    "master_services_agreement.txt", "sixty (60) days written notice"],
  ["What is the monthly retainer and when is it invoiced?",
    "master_services_agreement.txt", "$15,000"],
  ["How long do the NDA confidentiality obligations survive?",
    "mutual_nda.docx", "three (3) years"],
  ["What severance is owed if the employee is terminated without cause?",
    "employment_agreement.txt", "three (3) months of base salary"],
  ["What is the base rent and how does it escalate?",
    "commercial_lease.pdf", "$18,900"],
  ["Which state's law governs the services agreement?",
    "master_services_agreement.txt", "New York"],
  ["How many named users does the software licence cover?",
    "software_license_agreement.txt", "150 named users"],
  ["What annual salary does the employee receive?",
    "employment_agreement.txt", "$210,000"],
  ["How quickly must a security breach be reported?",
    "software_license_agreement.txt", "seventy-two (72) hours"],
  ["What is the cap on liability under the services agreement?",
    "master_services_agreement.txt", "twelve (12) months preceding the claim"],
  ["What non-solicitation restrictions apply after employment ends?",
    "employment_agreement.txt", "twelve (12) months"],
  ["How much extra rent is due for the expansion space?",
    "scanned_lease_amendment.pdf", "$6,075"],
  ["What information is excluded from confidentiality under the NDA?",
    "mutual_nda.docx", "publicly available"],
  ["How much is the security deposit on the Market Street lease?",
    "commercial_lease.pdf", "$37,800"],
];

for (const [question, expectedFile, expectedPhrase] of QUESTIONS) {
  const hits = search(index, question, 5);
  const label = question.length > 58 ? `${question.slice(0, 58)}…` : question;

  if (!hits.length) {
    check(label, false, "no passages retrieved");
    continue;
  }

  const topFile = (byId.get(hits[0].passage.document_id) || {}).filename;
  const { answer, citations } = composeAnswer(question, hits);

  const citedFiles = citations.map((citation) =>
    (byId.get(hits[citation - 1].passage.document_id) || {}).filename);

  const problems = [];
  if (topFile !== expectedFile) problems.push(`top hit is ${topFile}, expected ${expectedFile}`);
  if (!answer.includes(expectedPhrase)) problems.push(`answer is missing "${expectedPhrase}"`);
  if (!citedFiles.includes(expectedFile)) problems.push(`nothing cited from ${expectedFile}`);
  if (hits[0].similarity < 0.4) problems.push(`top relevance only ${hits[0].similarity}`);
  // An answer that quotes three clauses to say one thing reads like a dump.
  if (citations.length > 2) problems.push(`${citations.length} clauses cited for one question`);

  check(label, problems.length === 0, `${problems.join("; ")}\n          answer: ${answer.slice(0, 200)}`);
}

console.log("\nAnswers never come from outside the library");
{
  const hits = search(index, "what is the airspeed velocity of an unladen swallow", 5);
  const { mode } = composeAnswer("what is the airspeed velocity of an unladen swallow", hits);
  check("an off-topic question returns no_match rather than a guess",
    hits.length === 0 || mode === "no_match", `mode=${mode}, hits=${hits.length}`);
}

console.log("\nFollow-up suggestions");
{
  const suggestions = suggestFollowUps("Can the tenant terminate the lease early?", ["lease"]);
  check("a lease question suggests other lease questions", suggestions.length >= 3,
    JSON.stringify(suggestions));
  check("it does not suggest the question just asked",
    !suggestions.some((suggestion) => suggestion.toLowerCase().includes("terminate the lease early")),
    JSON.stringify(suggestions));
}

console.log(failures ? `\n${failures} check(s) failed\n` : "\nAll checks passed\n");
process.exit(failures ? 1 : 0);
