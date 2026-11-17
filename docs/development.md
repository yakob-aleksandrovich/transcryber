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
- **Storage:** SQLAlchemy models (`users`, `transcripts`) on MySQL or SQLite.
  Each transcript belongs to one user. The uploaded file is deleted when the job
  finishes.
- **Frontend:** a single static page in `app/static/` (login, upload, progress,
  list, view, download, copy, delete).
- **Container:** [Wolfi](https://github.com/wolfi-dev/os) base image, pinned by
  digest for a small CVE surface; runs as nonroot. See the comments in the
  `Dockerfile` for details.

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
