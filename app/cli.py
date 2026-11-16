"""Admin CLI for user management.

Usage (inside the container):
  docker compose exec transcryber python -m app.cli create-user alice
  docker compose exec transcryber python -m app.cli list-users
  docker compose exec transcryber python -m app.cli set-password alice
  docker compose exec transcryber python -m app.cli delete-user alice
"""

import argparse
import getpass
import sys

from .auth import hash_password
from .db import SessionLocal, User, init_db


def _prompt_password() -> str:
    pw1 = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)
    if not pw1:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    return pw1


def _resolve_password(args) -> str:
    """Password from --password-stdin, then --password, else an interactive prompt."""
    if args.password_stdin and args.password:
        print("Use either --password or --password-stdin, not both.", file=sys.stderr)
        sys.exit(1)
    if args.password_stdin:
        # Read from the pipe; drop only the trailing newline a shell may add.
        pw = sys.stdin.read().rstrip("\r\n")
        if not pw:
            print("No password received on stdin.", file=sys.stderr)
            sys.exit(1)
        return pw
    if args.password:
        return args.password
    return _prompt_password()


def cmd_create_user(args):
    password = _resolve_password(args)
    with SessionLocal() as session:
        if session.query(User).filter(User.username == args.username).first():
            print(f"User '{args.username}' already exists.", file=sys.stderr)
            sys.exit(1)
        session.add(User(username=args.username, password_hash=hash_password(password)))
        session.commit()
    print(f"Created user '{args.username}'.")


def cmd_list_users(_args):
    with SessionLocal() as session:
        users = session.query(User).order_by(User.id).all()
        if not users:
            print("(no users)")
            return
        for u in users:
            print(f"{u.id}\t{u.username}\t{u.created_at:%Y-%m-%d %H:%M}")


def cmd_set_password(args):
    password = _resolve_password(args)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"User '{args.username}' not found.", file=sys.stderr)
            sys.exit(1)
        user.password_hash = hash_password(password)
        session.commit()
    print(f"Updated password for '{args.username}'.")


def cmd_hash_password(args):
    """Print a bcrypt hash to paste into config.yaml (no DB access)."""
    password = _resolve_password(args)
    print(hash_password(password))


def cmd_delete_user(args):
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"User '{args.username}' not found.", file=sys.stderr)
            sys.exit(1)
        session.delete(user)  # cascades to the user's transcripts
        session.commit()
    print(f"Deleted user '{args.username}' and their transcripts.")


def main():
    parser = argparse.ArgumentParser(prog="app.cli", description="Transcryber admin")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-user", help="Create a new user")
    p.add_argument("username")
    p.add_argument("--password", help="Set non-interactively (visible in ps/history)")
    p.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from stdin (no shell-history/ps exposure)",
    )
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("list-users", help="List users")
    p.set_defaults(func=cmd_list_users)

    p = sub.add_parser("set-password", help="Change a user's password")
    p.add_argument("username")
    p.add_argument("--password", help="Set non-interactively (visible in ps/history)")
    p.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from stdin (no shell-history/ps exposure)",
    )
    p.set_defaults(func=cmd_set_password)

    p = sub.add_parser("delete-user", help="Delete a user and their transcripts")
    p.add_argument("username")
    p.set_defaults(func=cmd_delete_user)

    p = sub.add_parser(
        "hash-password",
        help="Print a bcrypt hash for config.yaml (no database access)",
    )
    p.add_argument("--password", help="Hash non-interactively (visible in ps/history)")
    p.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from stdin (no shell-history/ps exposure)",
    )
    p.set_defaults(func=cmd_hash_password, needs_db=False)

    args = parser.parse_args()
    if getattr(args, "needs_db", True):
        init_db()  # ensure tables exist before any DB command
    args.func(args)


if __name__ == "__main__":
    main()
