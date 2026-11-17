# User management

There is no open sign-up: an admin creates every account. There are two ways to
manage users, and they work together:

- the **admin CLI**, to manage users while the app runs;
- a **`users:` list in `config.yaml`**, applied on every startup.

## Admin CLI

```bash
docker compose exec transcryber python -m app.cli create-user <name>
docker compose exec transcryber python -m app.cli list-users
docker compose exec transcryber python -m app.cli set-password <name>
docker compose exec transcryber python -m app.cli delete-user <name>   # also deletes their transcripts
docker compose exec transcryber python -m app.cli hash-password        # print a hash for config.yaml
```

`create-user` and `set-password` take the password in three ways:

- **Interactive (default):** asks twice, with hidden input.
  ```bash
  docker compose exec transcryber python -m app.cli create-user alice
  ```
- **From stdin (`--password-stdin`):** does not show up in shell history or `ps`.
  One trailing newline is removed, so `echo` and `printf` both work.
  ```bash
  printf '%s' 's3cret' | docker compose exec -T transcryber \
    python -m app.cli create-user alice --password-stdin
  ```
  Note the `-T` on `exec`: it turns off the pseudo-TTY so the pipe reaches stdin.
- **Flag (`--password`):** easy, but visible in shell history and `ps`. Use it
  only on a trusted, single-user machine.

## Users in `config.yaml`

```yaml
users:
  - username: alice
    password_hash: "$2b$12$...."
```

On **every startup**:

- a listed user is created if missing;
- an existing listed user's password is **reset to the hash in the file**;
- users **not** listed are left alone (never deleted).

So if a user is listed in `config.yaml`, a CLI `set-password` for them is undone
on the next restart. Manage such users in the file, or remove them from the file
to manage them with the CLI only.

### Generating a password hash

Passwords are stored as bcrypt hashes. Generate one with the app:

```bash
docker compose run --rm transcryber python -m app.cli hash-password
```

Or, without the image, with `htpasswd` (from `apache2-utils`). `-C 12` matches
the cost the app uses:

```bash
htpasswd -bnBC 12 "" 'your-password' | tr -d ':\n'
```
