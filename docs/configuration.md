# Configuration

All app settings live in **`config.yaml`**. Create it by copying
`config.example.yaml`. In Docker it is mounted read-only at `/app/config.yaml`.
It is **gitignored**, because it holds secrets and password hashes.

The only other settings are:

- the bundled MySQL's own credentials, in `.env` (only if you use the bundled
  MySQL, see below);
- two paths baked into the image: `DATA_DIR` and `HF_HOME`;
- `CONFIG_FILE`, to load the config from another path.

If `config.yaml` is missing, the app falls back to safe defaults: SQLite, no
users, and a temporary `secret_key` (everyone is signed out on each restart; the
app logs a warning).

## Full example

```yaml
secret_key: "..."                 # session cookie signing; set a stable value
database_url: "sqlite:////app/data/transcryber.db"

whisper:
  model: small                    # tiny | base | small | medium | large-v3
  device: cpu                     # cpu | cuda
  compute_type: int8              # int8 (cpu) | float16 (gpu)
  beam_size: 5                    # lower = faster, slightly less accurate

huggingface:
  token: ""                       # optional, see below

users:                            # optional, see user-management.md
  - username: alice
    password_hash: "$2b$12$...."
```

## Secret key

`secret_key` signs the session cookie. Set a long random value and keep it
stable; if it changes, everyone is signed out. Generate one with either:

```bash
openssl rand -hex 32
python -c "import secrets; print(secrets.token_hex(32))"
```

## Database

Set `database_url` in `config.yaml`.

| Mode           | How to run                                   | `database_url`                                                     |
|----------------|----------------------------------------------|--------------------------------------------------------------------|
| SQLite         | `docker compose up -d --build`               | `sqlite:////app/data/transcryber.db` (the default)                 |
| Bundled MySQL  | `docker compose --profile bundled-db up -d --build` | `mysql+pymysql://transcryber:<MYSQL_PASSWORD>@db:3306/transcryber` |
| External MySQL | `docker compose up -d --build`               | `mysql+pymysql://user:pass@host:3306/transcryber`                  |

**SQLite** is the simplest: no extra container and no `.env`. It is a good fit
for a small team.

**Bundled MySQL** runs a MySQL 8 container next to the app:

1. `cp .env.example .env` and set `MYSQL_PASSWORD` and `MYSQL_ROOT_PASSWORD`.
2. Put the same `MYSQL_PASSWORD` in `database_url` in `config.yaml`.
3. Start with the `--profile bundled-db` flag. Without the flag, no database
   container runs. Use the same flag to stop it:
   `docker compose --profile bundled-db down`.

On startup the app waits and retries until the database is reachable, so the
start order is handled for you.

## Speech model

`whisper.model` picks the model size. Bigger models are more accurate but slower
and need more memory. The model is downloaded on the first transcription and
then cached in the `transcryber_models` volume.

| Model    | Download | Speed (CPU) | Use when…                            |
|----------|----------|-------------|--------------------------------------|
| tiny     | ~75 MB   | fastest     | quick drafts                         |
| base     | ~140 MB  | fast        | good balance                         |
| small    | ~460 MB  | moderate    | **default**, good accuracy           |
| medium   | ~1.5 GB  | slow        | better accuracy, enough RAM and time |
| large-v3 | ~3 GB    | slowest     | best accuracy; a GPU is advised      |

Other `whisper` settings:

- `device`: `cpu` (default) or `cuda` for an NVIDIA GPU.
- `compute_type`: `int8` for CPU, `float16` for GPU.
- `beam_size`: default 5. Lower is faster and slightly less accurate.

The current model and device are shown at `/api/status`.

## HuggingFace token (optional)

The default models are **public** and need no token. Set one only for
**gated or private models**, or to avoid anonymous download rate limits. Create a
read-only token at <https://huggingface.co/settings/tokens> and set it as
`huggingface.token` in `config.yaml`. The token value is never logged; only
whether one is set (visible at `/api/status`).
