# Running in production

## Security

- Set a strong, stable **`secret_key`** in `config.yaml`, and keep `config.yaml`
  private (it is gitignored by default).
- Transcripts are private per user, but this is a small app. It has no rate
  limiting, password reset or email verification. If you open it beyond a
  trusted network, put it behind HTTPS and consider adding those.
- Behind HTTPS, you may want to make the session cookie secure-only. This is set
  in `SessionMiddleware` in `app/main.py`.
- The app container runs as a nonroot user, with all Linux capabilities dropped
  (`cap_drop: ALL`) and `no-new-privileges`. The bundled MySQL deliberately keeps
  its default capabilities, because its entrypoint needs them to set up the data
  directory. Do not add `cap_drop: ALL` to the `db` service.

## Reverse proxy and upload size

The app listens on port 8000 over plain HTTP. For HTTPS, put a reverse proxy
(nginx, Caddy, Traefik, …) in front of it.

The app sets **no upload size limit**, and video files can be large. Your proxy
usually has its own limit. For example, nginx's `client_max_body_size` defaults
to 1 MB. Raise it to fit the files you expect:

```nginx
client_max_body_size 2G;
```

## Data and volumes

State is kept in **named Docker volumes**, not host directories:

| Volume                    | Contents                                         |
|---------------------------|--------------------------------------------------|
| `transcryber_data`        | SQLite database (if used) and uploads in progress |
| `transcryber_models`      | downloaded speech models                         |
| `transcryber_mysql-data`  | bundled MySQL data (if used)                     |

List them with `docker volume ls | grep transcryber`. `docker compose down -v`
**removes** them, including all users and transcripts.

To back up, back up `transcryber_data` (SQLite) or `transcryber_mysql-data` /
your external MySQL database. The models volume can always be downloaded again.

Uploaded files are deleted as soon as their transcription finishes, whether it
succeeded or failed. If the container stops in the middle of a job, that one
file can stay behind in the uploads folder.

### Why named volumes?

The container runs as nonroot (uid 65532). Named volumes take the image's
ownership on first use, so the app can write to them with no extra steps. A host
bind mount would be owned by root, and the app could not write to it. If you
prefer bind mounts, create the directories first and run
`chown -R 65532:65532` on them.

## Updating

```bash
git pull && docker compose up -d --build
```

When a new version changes the database, the app updates the database
automatically at startup. You see lines like
`Running upgrade 0001 -> 0002` in the logs (`docker compose logs transcryber`).

**Back up the database before you update.** A database update cannot be undone
by going back to an older version of the app.

## Processing

Transcription runs in a background worker, **one file at a time**. Other uploads
wait in a queue. This keeps a small machine from being overloaded.
