# Repository Guidelines

ChoirParts turns an uploaded choral score (PDF/image) into per-voice (SATB) practice tracks. A Python/FastAPI backend runs the OMR pipeline; a React/Vite frontend uploads, polls progress, handles manual correction, and plays results.

## Project Structure & Module Organization

- `backend/app/` — FastAPI app. `main.py` (HTTP endpoints), `models.py` (Pydantic schemas + `Stage`/`JobStatus`/`VoicePart` enums), `config.py` (env-driven `Settings`), `jobs.py` (job store), `queue.py` (dispatch), `celery_app.py` (Celery tasks), `storage.py` (storage layer).
- `backend/app/pipeline/` — the staged pipeline orchestrated by `runner.py`: `preprocess.py` (PDF→images, deskew/denoise) → `omr.py` → `parts.py` (music21 voice split + MIDI) → `synth.py` (FluidSynth+ffmpeg→MP3). `sample.py` is a deterministic SATB fallback.
- `frontend/src/` — `App.tsx` drives screen state from job status; `components/` are the screens; `hooks/useJobStatus.ts` polls; `api.ts` wraps endpoints; `types.ts` mirrors backend schemas.

Two runtime modes are wired through `USE_CELERY`: in-process `ThreadPoolExecutor` + `InMemoryJobStore` for dev, or Celery worker + `RedisJobStore` for prod. `STORAGE_BACKEND` selects local-disk vs S3. The OMR engine is a cascade (Audiveris → GPT-4o Vision → sample), falling back to the manual-correction UI when confidence is below `OMR_MANUAL_THRESHOLD`.

## Build, Test, and Development Commands

- Full stack: `docker compose up --build` (frontend on `:80`, backend on `:8000`, Redis, worker).
- Backend dev: `cd backend && pip install -r requirements.txt`, then `uvicorn app.main:app --reload`. Run a worker with `celery -A app.celery_app.celery worker --loglevel=info` (needs `USE_CELERY=true`).
- Frontend dev: `cd frontend && npm install && npm run dev` (Vite `:5173`, proxies `/api` and `/files` to `:8000`).
- Frontend build: `npm run build`; type-check only: `npm run lint`.

Copy `backend/.env.example` to `backend/.env` before running locally.

## Coding Style & Naming Conventions

- Python: 4-space indent, `from __future__ import annotations`, type hints throughout, module-level docstrings; no enforced linter/formatter is configured.
- TypeScript: strict mode with `noUnusedLocals`/`noUnusedParameters` (`tsconfig.json`); React function components in PascalCase files; styling via Tailwind utility classes.

## Testing Guidelines

No test suite or framework is currently configured.
