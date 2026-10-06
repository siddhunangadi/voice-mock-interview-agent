# Voice Mock Interview Agent — resume bullets

- **Built and deployed** a voice mock interview application on AWS, integrating FastAPI, Gemini, Vapi, and Supabase Postgres to tailor questions to resumes and job descriptions and generate structured interview feedback.
- **Engineered** a stateful interview controller that combines validated model decisions with Python rules for contextual follow-ups, topic progression, repetition checks, and interview completion.
- **Implemented** transactional answer persistence and request deduplication to preserve received answers across model failures and prevent completed request retries from advancing the interview twice.
