# Transcryber

Transcryber turns speech into text. Upload an audio or video file, and you get a
written transcript you can read, copy or download.

It runs on **your own server**. Your recordings never leave it: there is no cloud
service and no paid API. The speech recognition is
[Whisper](https://github.com/SYSTRAN/faster-whisper), running locally.

## What you can do

- **Transcribe audio:** mp3, m4a, wav, ogg, flac and more.
- **Transcribe video:** mp4, mov, mkv, webm and more. Transcryber takes the sound
  from the video and transcribes that.
- **Use it in many languages:** Whisper detects the spoken language by itself.
- **Keep your transcripts private:** each person signs in with their own account
  and sees only their own transcripts.
- **Keep, copy, download or delete** each transcript. The uploaded file itself is
  deleted as soon as the transcript is ready.

## Deploy

You need a machine with [Docker](https://docs.docker.com/get-docker/) and Docker
Compose. A normal CPU is enough; no graphics card is needed.

**1. Get the code and create your config file**

```bash
git clone https://github.com/yakob-aleksandrovich/transcryber.git
cd transcryber
cp config.example.yaml config.yaml
```

**2. Set a secret key**

Generate a random key:

```bash
openssl rand -hex 32
```

Paste it into `config.yaml`:

```yaml
secret_key: "paste-the-key-here"
```

This key keeps people signed in. Keep `config.yaml` private.

**3. Start Transcryber**

```bash
docker compose up -d --build
```

**4. Create your first user**

```bash
docker compose exec transcryber python -m app.cli create-user <your-name>
```

It asks for a password twice.

**5. Open it**

Go to <http://localhost:8000> (or your server's address on port 8000) and sign in.

The first transcription is slower than the rest: Transcryber first downloads the
speech model (about 460 MB). After that, the model is stored and reused.

### Stop and update

```bash
docker compose down                           # stop
git pull && docker compose up -d --build      # update to the latest version
```

Your transcripts, users and the downloaded model are kept in Docker volumes, so
they survive stops and updates.

### Before you open it to the internet

Put Transcryber behind HTTPS (a reverse proxy), and raise the proxy's upload size
limit so video files fit. See [Running in production](docs/operations.md).

## More documentation

- [Configuration](docs/configuration.md): database (SQLite or MySQL), speech
  model size and accuracy, all `config.yaml` settings.
- [User management](docs/user-management.md): add, list and remove users, change
  passwords, or define users in `config.yaml`.
- [Running in production](docs/operations.md): security, reverse proxy, upload
  size, data and backups.
- [Development](docs/development.md): how it works, the HTTP API, and running
  without Docker.
