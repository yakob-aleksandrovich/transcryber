"""Transcript persistence via SQLAlchemy. All operations are scoped to a user."""

import json
import uuid

from .db import SessionLocal, Transcript


def _iso(dt):
    return dt.isoformat() if dt else None


def save_transcript(
    user_id, original_name, text, language, duration, segments, processing_seconds=None
) -> dict:
    tid = uuid.uuid4().hex
    with SessionLocal() as session:
        rec = Transcript(
            id=tid,
            user_id=user_id,
            original_name=original_name,
            language=language,
            duration=duration,
            processing_seconds=processing_seconds,
            text=text,
            segments=json.dumps(segments, ensure_ascii=False),
        )
        session.add(rec)
        session.commit()
        return {"id": tid, "created_at": _iso(rec.created_at)}


def list_transcripts(user_id) -> list[dict]:
    with SessionLocal() as session:
        rows = (
            session.query(Transcript)
            .filter(Transcript.user_id == user_id)
            .order_by(Transcript.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "original_name": r.original_name,
                "created_at": _iso(r.created_at),
                "language": r.language,
                "duration": r.duration,
                "processing_seconds": r.processing_seconds,
                "preview": (r.text or "")[:160],
            }
            for r in rows
        ]


def load_transcript(user_id, tid) -> dict | None:
    with SessionLocal() as session:
        r = (
            session.query(Transcript)
            .filter(Transcript.id == tid, Transcript.user_id == user_id)
            .first()
        )
        if not r:
            return None
        return {
            "id": r.id,
            "original_name": r.original_name,
            "created_at": _iso(r.created_at),
            "language": r.language,
            "duration": r.duration,
            "processing_seconds": r.processing_seconds,
            "text": r.text,
            "segments": json.loads(r.segments) if r.segments else [],
        }


def delete_transcript(user_id, tid) -> bool:
    with SessionLocal() as session:
        deleted = (
            session.query(Transcript)
            .filter(Transcript.id == tid, Transcript.user_id == user_id)
            .delete()
        )
        session.commit()
        return deleted > 0
