# Voice Mock Interview Agent

Live AWS deployment: [Open the voice interview app](https://d26nujzw03owfm.cloudfront.net).

A resume- and job-grounded voice interview. FastAPI decides topic coverage and follow-up limits, Gemini assesses each answer and drafts the next question, Vapi carries the live audio, and Supabase Postgres preserves turns and feedback.

## Stack and boundaries

HTML/CSS/vanilla JavaScript with the Vapi Web SDK; Python 3.12, FastAPI, Pydantic, httpx and psycopg; Supabase Postgres; Gemini REST API. Vapi handles microphone transport, transcription, voice synthesis and interruption. The backend selects topics, validates each decision, stores evidence, and controls completion. No other application LLM runs in Vapi.

The browser receives an opaque ownership cookie and a Vapi call URL. It never receives the Vapi private key, Gemini key, database URL or Vapi server token. This local-demo ownership model keeps an interview in the browser that created it. Add real user authentication, rate limits, retention controls and privacy terms before public deployment.

## Setup

1. Install Python 3.12 and `uv`; run `uv venv --python 3.12 .venv` then `uv pip install --python .venv/bin/python -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill `DATABASE_URL` from your Supabase project's **Connect → Session pooler** (or a working direct connection), and `GEMINI_API_KEY` from Google AI Studio. Keep `.env` local. `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`.
3. Run `schema.sql` in Supabase SQL Editor. It creates `interviews` and `interview_turns`. The single final evaluation lives on `interviews`; no third table is needed. Both tables have RLS enabled with no anonymous access. The backend connects with the private Postgres URL.
4. Add the Vapi private API key as `VAPI_PRIVATE_KEY` and the public integration key as `VAPI_PUBLIC_KEY`. Both stay in backend configuration; Vapi requires the public key specifically for `/call/web`. Start a public HTTPS tunnel to `http://127.0.0.1:8000` (explicit IPv4 avoids another localhost listener), set its base URL as `PUBLIC_BASE_URL`, then run `.venv/bin/python scripts/setup_vapi.py`. It creates separate Custom LLM and webhook bearer credentials plus one saved assistant. IDs and the generated server token are written to `.env`; reruns reuse credentials and update the saved assistant. If the tunnel URL changes, update `PUBLIC_BASE_URL` and rerun the script.
5. Run `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`. Open `http://127.0.0.1:8000`. An HTTPS origin is needed when accessing the app remotely and for microphone permissions; localhost is permitted locally.

Use the same server instance behind the HTTPS tunnel so Vapi can call `/vapi/chat/completions` and `/vapi/events`. A disposable tunnel URL needs a matching saved assistant configuration each time. Do not embed keys in the frontend or commit `.env`.

## Flow

Paste the JD and either paste your resume or upload a PDF/DOCX (up to 5 MB), review the extracted text, and prepare the interview, then click **Start voice**. The opening is always “Tell me about yourself.” Python then asks about role motivation and a broad project overview before adaptive questions grounded in both inputs. The interview opens with a welcome and relevant background question, then explores prioritized role competencies through experience, reasoning and behavioral evidence. Follow-ups are optional and depend on missing evidence in the answer, not a per-section quota. Python prevents skipping remaining competencies, limits consecutive probes to two, and uses a eighteen-question safety ceiling (not a target). It invites final additions before closing. Each candidate answer is stored before Gemini assesses it, so a provider failure can be retried without losing speech. Finish to receive feedback; an interrupted interview can also be finalized. Refresh shows stored progress but does not silently reconnect the microphone.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/`, `/health` | UI, liveness |
| POST | `/api/interviews` | Analyze inputs and create interview |
| GET | `/api/interviews/{id}` | Browser-owned state, turns, evaluation |
| POST | `/api/interviews/{id}/finish` | End and generate/retry evaluation |
| POST | `/voice/call/web` | Browser SDK proxy to saved Vapi assistant |
| POST | `/vapi/chat/completions` | Authenticated Vapi Custom LLM request |
| POST | `/vapi/events` | Authenticated call end/status events |

Browser endpoints use a same-site HttpOnly cookie and origin check. Provider endpoints require the separate Vapi bearer token. Candidate-supplied text is treated as data, never as system instructions; model output is validated with Pydantic and rendered as text.

## Testing

Run `.venv/bin/python -m unittest discover -s tests -v`. The suite checks controller transitions, duplicate questions, follow-up limits, validation and unauthenticated provider access. Local integration requires configured Supabase, Gemini, Vapi and a public HTTPS callback.

## Design limits

A single FastAPI process and per-request Postgres connections keep the implementation small. For higher traffic, add a connection pool and move slow Gemini calls out of row-lock intervals. The lexical question-repeat guard may miss semantic paraphrases. PDFs and DOCX files become editable text; image-only scans and legacy `.doc` files are unsupported. Voice latency depends on Gemini and Vapi response times. The app does not make employment decisions.

For an ngrok development tunnel, provide `NGROK_AUTHTOKEN` to the ngrok process and run `ngrok http http://127.0.0.1:8000 --inspect=false`. Keep that process and Uvicorn running. The tunnel terminates HTTPS and therefore handles callback credentials and interview text in transit. Use a controlled HTTPS deployment for production. The saved assistant uses an explicit Authorization header because credential-reference-only webhook requests arrived unauthenticated during live testing.

Voice controls distinguish connecting, interviewer speaking and your turn. The interviewer speaks through Vapi; the displayed question is a companion to the audio. A disconnected call stays on the interview screen; click **Finish interview** to request feedback. Short repeat requests replay the question without scoring or consuming the question budget. Sessions without substantive answers are not scored.

Additional checks: `LIVE_DATABASE=1 .venv/bin/python -m unittest discover -s tests -v` creates and deletes synthetic Supabase records; `node tests/frontend.test.cjs` checks display stability using Node's built-in test utilities (development only, no package installation). Gemini/Vapi usage is incurred by live testing.

Environment: `DATABASE_URL` (private Postgres connection), `GEMINI_API_KEY`, optional `GEMINI_MODEL`, `VAPI_PRIVATE_KEY` (setup), `VAPI_PUBLIC_KEY` (backend web-call proxy), `PUBLIC_BASE_URL` (HTTPS callback origin), optional development `NGROK_AUTHTOKEN`. Setup fills `VAPI_SERVER_TOKEN`, `VAPI_ASSISTANT_ID`, `VAPI_MODEL_CREDENTIAL_ID`, and `VAPI_WEBHOOK_CREDENTIAL_ID`.

### AWS deployment
Elastic Beanstalk runs the packaged app through the included `Procfile`. Its generated URL is HTTP-only, so place CloudFront in front and use its HTTPS domain as `PUBLIC_BASE_URL`; rerun `scripts/setup_vapi.py` after changing that URL. Configure only runtime values in Elastic Beanstalk: `DATABASE_URL`, `GEMINI_API_KEY`, optional `GEMINI_MODEL`, `VAPI_PUBLIC_KEY`, `VAPI_SERVER_TOKEN`, `VAPI_ASSISTANT_ID`, and `PUBLIC_BASE_URL`. Keep `VAPI_PRIVATE_KEY` only on the trusted machine used to configure Vapi.

### Resume uploads
`POST /api/resume-text?kind=pdf|docx` accepts raw file bytes and returns editable text. Files are parsed in memory and are not saved. `pypdf` extracts PDF text; Python ZIP/XML parsing reads DOCX paragraphs, tables, headers and footers. Limits: 5 MB upload, 20 PDF pages, 20,000 extracted characters. Password-protected PDFs, unreadable files and image-only scans are rejected with recovery guidance; OCR and legacy `.doc` are not supported. Review multi-column PDF extraction before continuing. Parser isolation/resource limits and upload rate limits are needed before hostile public-scale traffic.

When no employment/internship is stated, Python plans separate discussions for up to five listed projects before remaining role competencies. The first two transitions run without Gemini. Vapi uses Godfrey V2, with a 0.3s playback wait and conservative candidate pause detection. Existing databases upgrading from the earlier schema must replace interview_turns_topic_check with CHECK (topic BETWEEN 0 AND 6).
