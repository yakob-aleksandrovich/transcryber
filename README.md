# Transcryber

A self-hosted web app that transcribes audio files **locally** — no cloud, no
API keys for transcription. Each user signs in and sees only their own
transcripts. Upload a file, get a transcript, keep it or delete it.

Transcription runs on [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(a fast CTranslate2 reimplementation of OpenAI Whisper), defaulting to a light
`small` model on CPU with `int8` quantization.

- **Accounts:** multi-user, with per-user private transcripts. Users are created
  by an admin via a CLI (no open sign-up).
- **Database:** MySQL or SQLite, selected by `database_url` in `config.yaml`.
- **Container:** [Wolfi](https://github.com/wolfi-dev/os) base (small CVE surface,
  digest-pinned), runs as a **nonroot** user with **all Linux capabilities
  dropped**.

## Quick start (Docker + bundled MySQL)

```bash
cp config.example.yaml config.yaml      # all app settings live here
cp .env.example .env                     # only the bundled-MySQL password

# 1) generate a session key and put it in config.yaml (secret_key:)
python -c "import secrets; print(secrets.token_hex(32))"

# 2) generate a bcrypt hash for your first user and add it under users: in config.yaml
docker compose run --rm transcryber python -m app.cli hash-password
#    ...or, without the image, with htpasswd (apache2-utils); -C 12 matches the app's cost:
#    htpasswd -bnBC 12 "" 'your-password' | tr -d ':\n'

# 3) point database_url in config.yaml at the bundled MySQL (and match MYSQL_PASSWORD in .env):
#    database_url: "mysql+pymysql://transcryber:<MYSQL_PASSWORD>@db:3306/transcryber"

docker compose --profile bundled-db up --build
```

Users listed in `config.yaml` are created automatically on startup, so just open
<http://localhost:8000> and sign in. (You can also add users at runtime with the
CLI — see below.)

> **Note the `--profile bundled-db` flag** — it starts the bundled MySQL
> container. Without it, no database container runs (use that mode for an
> external DB or SQLite; see below).

- The first transcription downloads the model (cached so it only happens once):
  ~460 MB for `small`, ~1.5 GB for the `medium` default in `docker-compose.yml`.
- State persists in **named Docker volumes** (`transcryber_data`,
  `transcryber_models`, `transcryber_mysql-data`), not host directories. List them
  with `docker volume ls`; remove them with `docker compose down -v`.

To stop: `docker compose --profile bundled-db down`.

## Database options

Set `database_url` in `config.yaml`.

| Mode              | How to run                                   | `database_url`                                            |
|-------------------|----------------------------------------------|----------------------------------------------------------|
| Bundled MySQL     | `docker compose --profile bundled-db up`     | `mysql+pymysql://transcryber:<MYSQL_PASSWORD>@db:3306/transcryber` |
| External MySQL    | `docker compose up`                          | `mysql+pymysql://user:pass@host:3306/transcryber`        |
| SQLite            | `docker compose up`                          | `sqlite:////app/data/transcryber.db`                     |

For the bundled MySQL, the password in `database_url` must match `MYSQL_PASSWORD`
in `.env`. The app waits/retries on startup until the database is reachable, so
startup order with the bundled MySQL is handled automatically.

## User management

There are two ways to manage users; they work together.

### Preseed in `config.yaml` (declarative)

```yaml
users:
  - username: alice
    password_hash: "$2b$12$...."   # from `app.cli hash-password`
```

On **every startup**: a listed user is created if missing, and an existing user's
password is **updated to match** the hash in the file. Users **not** listed are
left untouched (never deleted). Generate a hash with:

```bash
docker compose run --rm transcryber python -m app.cli hash-password
```

### Admin CLI (imperative, runtime)

```bash
docker compose exec transcryber python -m app.cli create-user <name>
docker compose exec transcryber python -m app.cli list-users
docker compose exec transcryber python -m app.cli set-password <name>
docker compose exec transcryber python -m app.cli delete-user <name>   # also deletes their transcripts
docker compose exec transcryber python -m app.cli hash-password        # print a hash for config.yaml
```

> Note: if a user is listed in `config.yaml`, a CLI `set-password` for them is
> reverted to the config hash on the next restart. Manage such users in the file,
> or remove them from the file to manage them purely via the CLI.

`create-user` and `set-password` take the password three ways:

- **Interactive (default):** prompts twice with hidden input.
  ```bash
  docker compose exec transcryber python -m app.cli create-user alice
  ```
- **From stdin (`--password-stdin`):** no shell-history or `ps` exposure. A single
  trailing newline is stripped, so `echo` and `printf` both work.
  ```bash
  printf '%s' 's3cret' | docker compose exec -T transcryber \
    python -m app.cli create-user alice --password-stdin
  ```
  (Note the `-T` on `exec` — it disables the pseudo-TTY so the pipe reaches stdin.)
- **Flag (`--password`):** convenient but visible in shell history and `ps`; use
  only on a trusted, single-user machine.

## Configuration

All app settings live in **`config.yaml`** (copy `config.example.yaml`). It is
mounted read-only into the container at `/app/config.yaml` and is **gitignored**
because it holds secrets and user password hashes. The only environment variables
left are the bundled MySQL's own credentials (in `.env`) and two infra paths baked
into the image (`DATA_DIR`, `HF_HOME`). To load the file from another path, set
`CONFIG_FILE`.

```yaml
secret_key: "..."                 # session cookie signing; set a stable value
database_url: "mysql+pymysql://transcryber:pass@db:3306/transcryber"

whisper:
  model: medium                   # tiny | base | small | medium | large-v3
  device: cpu                     # cpu | cuda
  compute_type: int8              # int8 (cpu) | float16 (gpu)
  beam_size: 5                    # lower = faster, slightly less accurate

huggingface:
  token: ""                       # optional (see below)

users:                            # see "User management"
  - username: alice
    password_hash: "$2b$12$...."
```

If `config.yaml` is missing, the app falls back to safe defaults (SQLite, no
users, an ephemeral `secret_key` with a warning).

### HuggingFace token (optional)

The default faster-whisper models are **public** and need no token. Provide one
only for **gated/private models** or to avoid anonymous download rate limits.
Create a read-only token at <https://huggingface.co/settings/tokens> and set it as
`huggingface.token` in `config.yaml`. The value is never logged — only whether one
is configured (visible at `/api/status`).

### Model size guidance (CPU)

| Model  | Size    | Speed    | Use when…                          |
|--------|---------|----------|------------------------------------|
| tiny   | ~75 MB  | fastest  | quick drafts                       |
| base   | ~140 MB | fast     | good balance                       |
| small  | ~460 MB | moderate | **default — better accuracy**      |

## How it works

- **Backend:** FastAPI. Uploads are transcribed in a background worker (one at a
  time), so the UI stays responsive and the machine isn't overloaded.
- **Auth:** signed session cookies (Starlette `SessionMiddleware`); passwords
  hashed with bcrypt. Every `/api/*` route requires a logged-in user.
- **Storage:** SQLAlchemy models (`users`, `transcripts`) on MySQL or SQLite.
  Each transcript is owned by a user; the uploaded audio is deleted once
  transcription finishes.
- **Frontend:** a single static page (login, upload, progress, list, view,
  download, copy, delete).
- **Container:** Wolfi base (digest-pinned), nonroot user, `cap_drop: ALL` +
  `no-new-privileges` on the app; audio decoded via PyAV's bundled ffmpeg
  libraries (no system ffmpeg package).

## API

All `/api/*` routes except `login` require authentication (session cookie).

| Method | Path                               | Purpose                     |
|--------|------------------------------------|-----------------------------|
| POST   | `/api/login`                       | Sign in                     |
| POST   | `/api/logout`                      | Sign out                    |
| GET    | `/api/me`                          | Current user                |
| POST   | `/api/transcribe`                  | Upload a file, start a job  |
| GET    | `/api/jobs/{id}`                   | Job status (owner only)     |
| GET    | `/api/transcripts`                 | List your transcripts       |
| GET    | `/api/transcripts/{id}`            | Full transcript (owner only)|
| GET    | `/api/transcripts/{id}/download`   | Download as `.txt`          |
| DELETE | `/api/transcripts/{id}`            | Delete a transcript         |
| GET    | `/api/status`                      | Model / device info         |

## Security notes

- Set a strong, stable **`secret_key`** in `config.yaml` (session cookie signing),
  and keep `config.yaml` private (it is gitignored by default).
- Transcripts are isolated per user, but this is still a small app without
  rate limiting, password reset, or email verification. If you expose it beyond
  a trusted network, put it behind HTTPS (a reverse proxy) and consider those
  additions.
- When served over HTTPS, you may want to make the session cookie secure-only
  (set in `SessionMiddleware`).
- The app container already runs nonroot with all Linux capabilities dropped.
  The bundled MySQL deliberately keeps its default capabilities — its entrypoint
  needs them to initialise the data dir — so do not add `cap_drop: ALL` there.

## Local development (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml       # defaults to a local SQLite file
python -m app.cli create-user alice      # or preseed under users: in config.yaml
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The app reads `config.yaml` from the working directory (override with `CONFIG_FILE`).

No system `ffmpeg` is required — the `av` (PyAV) wheel bundles its own ffmpeg
libraries, which faster-whisper uses for decoding.
