# n8n automations for Local Legal AI

Three ready-to-import workflows. Each file is a standalone n8n workflow.

| Workflow | Trigger | What it does |
|---|---|---|
| [`legal-ai-alerts.json`](flows/legal-ai-alerts.json) | Webhook `POST /webhook/legal-ai-events` | Receives events from Local Legal AI, verifies the `X-LegalAI-Signature` HMAC, drops anything unsigned or forged, and posts a readable message to Slack |
| [`legal-ai-dropzone-ingest.json`](flows/legal-ai-dropzone-ingest.json) | New file in `/files/dropzone` | Signs in as a service account and uploads the file through the API (useful for a synced SharePoint/Dropbox folder or a scanner share) |
| [`legal-ai-daily-digest.json`](flows/legal-ai-daily-digest.json) | Weekdays 08:00 (or *Run now*) | Posts a summary of questions, top topics, new documents and failed/denied actions to Slack |

> Local Legal AI also has a **built-in inbox** (`data/inbox/`) that indexes dropped
> files without n8n. Use the n8n drop-zone workflow when files arrive somewhere
> the API host can't see directly.

## Events

When `N8N_WEBHOOK_URL` is set in the Local Legal AI `.env`, these events are
POSTed as JSON (only metadata — never document text or questions):

`document.indexed`, `document.ingest_failed`, `document.deleted`,
`security.login_failed`, `security.login_denied`, `security.login_locked`, `security.ip_denied`,
`security.audit_tamper_detected`, `user.created`, `user.updated`,
`user.password_reset`, `integration.test`

```json
{
  "event": "document.indexed",
  "timestamp": "2026-10-20T23:55:10+00:00",
  "source": "Local Legal AI",
  "actor": "admin",
  "resource": "352aae473c6d471c",
  "status": "success",
  "ip": "127.0.0.1",
  "details": {"filename": "msa.txt", "title": "MSA", "category": "contracts",
              "chunks": 9, "channel": "upload", "size_bytes": 2611, "document_type": "contract"}
}
```

With `WEBHOOK_SECRET` set, each request carries
`X-LegalAI-Signature: sha256=<hex HMAC-SHA256 of the raw body>`. Limit the events
sent with `NOTIFY_EVENTS` (comma-separated). Set `SLACK_WEBHOOK_URL` in the
Local Legal AI `.env` instead if you want Slack alerts without n8n.

## Setup

1. In Local Legal AI, create a service account on the 👥 Users page (role *admin*
   if you use the digest, otherwise *user*; untick "Require a new password").
2. In the Local Legal AI `.env`:
   ```env
   N8N_WEBHOOK_URL=http://localhost:5678/webhook/legal-ai-events
   WEBHOOK_SECRET=<a long random string>
   ```
3. Here: `cp n8n.env.example n8n.env` and fill in the same secret, the service
   account and your Slack webhook.
4. Start n8n and import the workflows:
   ```bash
   docker compose up -d
   docker compose exec n8n n8n import:workflow --separate --input=/workflows
   ```
   (Without Docker: `npx n8n@1 import:workflow --input=<file>` for each file,
   with the variables from `n8n.env` and the ones listed in `docker-compose.yml`
   exported.)
5. Open http://localhost:5678, activate *Event alerts* and *Drop-zone ingestion*,
   then use **Send test event** on the 🔌 Integrations page in Local Legal AI.

## Verification

All three workflows were imported into n8n 1.123 and run end to end against a
live API: backend events arrived in Slack via the alerts workflow with valid
signatures, a forged and an unsigned request were both dropped, a DOCX dropped
in the watched folder was uploaded and indexed by the service account, and the
digest workflow posted its summary.
