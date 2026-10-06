# Voice Mock Interview — repair and verification report

The app runs as one FastAPI process serving HTML/CSS/vanilla JavaScript. Gemini analyzes resume/JD, assesses answers and generates structured questions/evaluations. Python determines legal topic transitions, follow-up limits, coverage and completion. Supabase persists context, turns, state and one final evaluation. Vapi handles browser audio, transcription and speech playback.

## Files and size
```
app/              main.py, interview.py
frontend/         index.html, style.css, app.js
scripts/          setup_vapi.py
tests/            test_api.py, test_interview.py, test_persistence.py, frontend.test.cjs
schema.sql
requirements.txt
.env.example
.gitignore
README.md
.astra/           PLAN.md, DECISIONS.md, RESEARCH.md, PROGRESS.md, VERIFICATION.md
```
Physical LOC including blank lines: runtime Python 471; setup Python 75; total production/setup Python 546; frontend 251. No frontend build pipeline.

## Dependencies
- FastAPI: HTTP routing and validation integration.
- Pydantic: input and Gemini output contracts.
- Uvicorn: ASGI server.
- httpx: Gemini/Vapi REST calls and API tests.
- psycopg[binary]: Postgres transactions and row locking.
- python-dotenv: local environment loading and setup writes.
- Vapi Web SDK 2.7.1: browser voice transport. Deepgram nova-3 is Vapi's managed transcription option, not another application LLM or dependency.
- unittest and Node's built-in vm/assert: tests only. ngrok: local development HTTPS transport only.

## Database and API
Two tables: interviews (context/state/status/evaluation), interview_turns (ordered speech text, assessment and replay key). RLS enabled; backend uses its private database connection. No browser database credentials.

GET / and /health; POST /api/interviews; GET /api/interviews/{id}; POST /api/interviews/{id}/finish; POST /voice/call/web; POST /vapi/chat/completions; POST /vapi/events.

## Verification
12 local Python tests passed; 8 live Supabase persistence tests passed; frontend stability regression passed. Actual Gemini/Supabase integration completed four technical answer turns and final evaluation. Browser submission, grounded opening question and refresh restoration passed. Actual Vapi speech events, incoming speech, authenticated model/event callbacks, multiple stored turns, ending and rendered final feedback were observed. Voice-test replies were mainly short test utterances, so they validate transport rather than nuanced interview quality. Earlier real model/backend technical turns took 4.6–5.3 seconds. Secret-value scan found none in source/docs.

Fixed: missing callback auth, wrong Vapi key type, wrong tunnel listener, microphone preflight, unstable status/question rendering, transcript fragments, automatic feedback on disconnect, request retries, continued pending speech, repeat requests consuming question budget, and unsupported scores for non-answers. Corrected the known audio-test's cached zero-score evaluation.

## Boundaries and tradeoffs
Vapi stops at audio/transcription and delivering text requests. Application logic begins at validating call ownership and deciding the next interview action. This is more than a provider wrapper: it owns grounded context, question limits, coverage, durable state, replay handling and evidence-based evaluation.

Kept two tables, direct SQL and two runtime Python files. Gave up file uploads, seamless call reconnection and semantic duplicate detection for a small understandable implementation. Model output remains probabilistic. Prompt-injection defenses constrain data/control boundaries but cannot guarantee perfect model behavior.

Cleanup removed temporary diagnostics, polling-driven overwrites, fragmented question rendering, automatic evaluation on disconnect and redundant whitespace checks. No repositories, factories, ORM, task queues or AI frameworks were added.

Production needs real user authentication, abuse/rate limits, stable HTTPS hosting, retention/deletion controls, database pooling, shorter transaction lock intervals, operational monitoring and wider interruption/concurrency/load tests. A local ngrok tunnel is not a production deployment. Microphone/speaker permissions and provider latency still depend on the user's browser and environment. No additional credentials currently require user action.

## Start
From the project directory:
```
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Keep an HTTPS tunnel to http://127.0.0.1:8000 running for Vapi callbacks. Update PUBLIC_BASE_URL and rerun `.venv/bin/python scripts/setup_vapi.py` if the address changes. Setup details and environment names are in README.md. Current app and tunnel were left running.

## Latest revision — 2026-09-25
Replaced the rejected fixed eight-question/four-section policy with evidence-led progression informed by Oxford careers guidance and employer interview guidance. The opening introduces the practice conversation and asks about relevant background; optional probes explore missing evidence, role reasoning and personal contribution. Python preserves coverage, bounds repetitive probing and invites final additions before feedback. Two to four competency areas are selected for this compact practice format; twelve questions is a safety ceiling, not a target.

22 Python checks passed with live Supabase persistence; frontend checks include stale-response protection. Actual Gemini/Supabase creation, four answer turns and final evaluation passed. Prompts were then tightened following observed compound questions. A new spoken session is still needed to assess conversational quality and display/audio timing after these changes.
