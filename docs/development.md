# Development

## How it works

- **Backend:** FastAPI. Uploads are transcribed in a background worker, one at a
  time, so the UI stays responsive and the machine isn't overloaded.
- **Transcription:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  a fast CTranslate2 reimplementation of OpenAI Whisper. Default: the `small`
  model on CPU with `int8` quantization.
- **Audio decoding:** PyAV, whose wheel bundles its own ffmpeg libraries. It also
  extracts the audio track from video files. No system `ffmpeg` is needed. Before
  transcribing, the app checks that the file has an audio stream and rejects it
  with a clear message if not.
- **Auth:** signed session cookies (Starlette `SessionMiddleware`); passwords
  hashed with bcrypt. Every `/api/*` route except `login` needs a signed-in user.
- **Storage:** SQLAlchemy models (`users`, `transcripts`) on MySQL or SQLite,
  with Alembic migrations (see below).
  Each transcript belongs to one user. The uploaded file is deleted when the job
  finishes.
- **Frontend:** a single static page in `app/static/` (login, upload, progress,
  list, view, download, copy, delete).
- **Container:** [Wolfi](https://github.com/wolfi-dev/os) base image, pinned by
  digest for a small CVE surface; runs as nonroot. See the comments in the
  `Dockerfile` for details.

## Database migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/). The
migrations live in `app/migrations/versions/`, and the app applies them
**automatically at startup** (`init_db()` in `app/db.py`). Admins never run a
migration command by hand.

At startup the app:

1. waits until the database is reachable (it retries for about 90 seconds);
2. if the database has tables but no migration history (it was created before
   migrations were added), marks it as the baseline revision `0001`;
3. applies every newer migration (`upgrade head`).

### Changing the schema

1. Change the model in `app/db.py`.
2. Generate a migration from the repository root. Point `CONFIG_FILE` at a
   config whose database is at the latest revision (a throwaway SQLite file is
   fine; run `alembic upgrade head` on it first):
   ```bash
   alembic upgrade head
   alembic revision --autogenerate --rev-id 0003 -m "short description"
   ```
3. **Read the generated file** in `app/migrations/versions/` and fix it if
   needed. Autogenerate does not detect everything (for example, renamed
   columns look like a drop plus an add).
4. Test it on **both SQLite and MySQL**, on a fresh database and on a copy of an
   existing one. `alembic check` confirms the models and the database match.

Notes:

- Number revisions in order (`0001`, `0002`, …), so the history is easy to read.
- Migrations use Alembic's "batch mode", because SQLite cannot alter most
  columns in place. Batch mode copies the table, which is slow on very large
  tables.
- `alembic.ini` in the repository root is only for these developer commands.
  The app does not use it.

## HTTP API

All `/api/*` routes except `login` need a session cookie.

| Method | Path                               | Purpose                      |
|--------|------------------------------------|------------------------------|
| POST   | `/api/login`                       | Sign in                      |
| POST   | `/api/logout`                      | Sign out                     |
| GET    | `/api/me`                          | Current user                 |
| POST   | `/api/transcribe`                  | Upload a file, start a job   |
| GET    | `/api/jobs/{id}`                   | Job status (owner only)      |
| GET    | `/api/transcripts`                 | List your transcripts        |
| GET    | `/api/transcripts/{id}`            | Full transcript (owner only) |
| GET    | `/api/transcripts/{id}/download`   | Download as `.txt`           |
| DELETE | `/api/transcripts/{id}`            | Delete a transcript          |
| GET    | `/api/status`                      | Model and device info        |

## Running without Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml       # defaults to a local SQLite file
python -m app.cli create-user alice      # or list users in config.yaml
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The app reads `config.yaml` from the working directory (override with
`CONFIG_FILE`).
