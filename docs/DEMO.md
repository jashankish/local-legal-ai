# Local demo and testing environment

Everything the product does, running on your machine, in one command.

```bash
python scripts/demo.py up            # add --with-model for generated answers
```

Then open **http://localhost:8511**.

It starts the API, the web interface and a stand-in for Slack/n8n, loads a
fictional firm, and prints a walkthrough. All of its state lives in `.demo/`
(git-ignored) on ports that don't clash with a real instance, so it never
touches your own `data/` and you can run both at once.

| Command | What it does |
|---|---|
| `up` | start everything and load the sample firm |
| `up --with-model` | also run a local language model, so answers are generated rather than quoted |
| `verify` | health, every page rendered, and a real question answered |
| `status` | what is running, on which ports |
| `reset` | wipe the library, users and history, then reload the samples |
| `down` | stop everything |
| `tour` | print the walkthrough again |
| `logs api -f` | follow a service log (`api`, `ui`, `model`, `events`) |

## Sign in as

The admin login is simply `admin` / `admin`. That is safe here and only here: the
environment holds fictional sample agreements, binds to `127.0.0.1`, and starts the
API with `DEMO_MODE=true`, which relaxes the password rules. The API refuses demo mode
on any other address. A demo created by an earlier version is moved onto the new
password automatically on the next `up`.

| Account | Password | What it shows |
|---|---|---|
| `admin` | `admin` | everything, including Users, Analytics, Audit Log and Integrations |
| `associate` | `associate-demo-1` | a lawyer: documents and questions, no admin pages |
| `paralegal` | `paralegal-demo-1` | a standard user |
| `new.hire` | `Welcome-temp-1` | forced to choose a password before anything else works |
| `former.counsel` | — | disabled; sign-in is refused |

## The tour

1. **Ask a question.** "Can the tenant terminate the lease early, and what does
   it cost?" Every sentence cites the passage it came from, and the sources are
   listed underneath, marked as cited or merely retrieved.
2. **Ask something your documents don't cover.** "What is the capital of
   France?" It declines. Answers only ever come from your library, never the
   model's general knowledge — the model isn't even asked.
3. **Browse the library.** Search, filter by category, open a document, export
   the register as CSV.
4. **Upload something.** A PDF, a Word file, or a photo of a page — images and
   scanned PDFs are read with OCR.
5. **Drop a file in the watched folder.** Put anything into
   `.demo/data/inbox/contracts/` and it is indexed within a few seconds, filed
   under that category. Rejected files land in `inbox/failed/` with a note
   explaining why.
6. **Manage the team.** As admin, open Users: add someone with a temporary
   password, change a role, disable an account. Disabling signs that person out
   everywhere, immediately.
7. **Get locked out on purpose.** Sign in wrongly five times. The account locks
   for fifteen minutes, the lockout is audited, and a notification is sent.
8. **Check the audit trail.** Audit Log → Verify chain. Every sign-in, upload,
   question and deletion is hash-chained, so any edit or deletion is detectable.
   Filter it, export it as CSV.
9. **Look at the analytics.** Usage over time, question topics, response times,
   retrieval quality, document similarity, and who did what.
10. **Watch the notifications.** Open <http://127.0.0.1:8012> and keep it beside
    you. Uploads, deletions, failed sign-ins and lockouts arrive as you work,
    with their signature verified. This is what a firm would wire into Slack or
    n8n.

## Generated vs. quoted answers

Without a language model the assistant answers **extractively**: the most
relevant sentences from your documents, each cited. That is fully functional and
needs no GPU or download.

With `--with-model` it runs Qwen2.5-1.5B under llama.cpp locally and **generates**
answers from the retrieved passages, still cited. The first run downloads about
1 GB and builds llama.cpp, which takes a few minutes; after that it starts in
seconds. Every answer is labelled with which mode produced it.

```bash
python scripts/demo.py down
python scripts/demo.py up --with-model
```

## Scanned documents

The sample set includes a scanned, image-only lease amendment. Reading it needs
Tesseract:

```bash
brew install tesseract          # macOS
sudo apt-get install tesseract-ocr tesseract-ocr-eng   # Debian/Ubuntu
python scripts/demo.py reset
```

Without it the demo still runs; that one sample is quarantined in
`inbox/failed/` with an explanation, which is itself worth seeing.

## Using it for testing

`verify` is the quick confidence check — it confirms the services are healthy,
renders all nine pages looking for exceptions, and asks a real question,
expecting a generated answer when a model is running and cited excerpts when one
isn't. CI runs `up → status → verify → down` on every push.

For a clean slate between test runs, `reset` wipes the library, users, audit
trail and notification history, then reloads the samples — so every run starts
from the same known state.

Ports can be moved with `--api-port` / `--ui-port`, and the whole environment
relocated with `--dir`, if you want more than one at a time.

## Troubleshooting

- **A port is in use.** `demo.py` says which, and `--api-port` / `--ui-port`
  move it.
- **Something won't start.** `python scripts/demo.py logs api` (or `ui`,
  `model`, `events`); add `-f` to follow.
- **Answers are quoted, not generated.** The model isn't running: `status` will
  show it, and `.demo/logs/model.log` says why.
- **Start completely fresh.** `python scripts/demo.py down && rm -rf .demo`.
