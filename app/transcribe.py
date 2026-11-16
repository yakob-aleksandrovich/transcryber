"""Thin wrapper around faster-whisper.

The model is loaded lazily on first use and cached as a process-wide
singleton, so the (potentially slow) first load / download happens only once.
All tunables come from config.yaml (see app/config.py).
"""

import logging
import os
import threading
import time

from faster_whisper import WhisperModel

from . import config

try:
    # Maps a size name ("small") to its Hugging Face repo id.
    from faster_whisper.utils import _MODELS
except Exception:  # pragma: no cover - internal name may change
    _MODELS = {}

logger = logging.getLogger("transcryber.model")

_model = None
_model_lock = threading.Lock()
_token_configured = False


def _configure_hf_token() -> bool:
    """Expose the configured token to huggingface_hub via the env it reads.

    Returns True if a token is configured. Never logs the token value.
    """
    global _token_configured
    if config.HF_TOKEN:
        os.environ["HF_TOKEN"] = config.HF_TOKEN  # huggingface_hub reads this
        if not _token_configured:
            logger.info("HuggingFace token configured (downloads will be authenticated).")
            _token_configured = True
        return True
    return False


def _is_model_cached(name: str) -> bool:
    """Best-effort check: is the model already present locally (no download)?"""
    if os.path.isdir(name):  # a local path was given
        return True
    repo_id = _MODELS.get(name, name)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id, local_files_only=True)
        return True
    except Exception:
        return False


def get_model() -> WhisperModel:
    """Return the shared WhisperModel, loading it on first call."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _configure_hf_token()
                name = config.WHISPER_MODEL
                cached = _is_model_cached(name)
                if cached:
                    logger.info("Model '%s' is already available locally; loading…", name)
                else:
                    logger.info(
                        "Model '%s' is NOT cached — downloading now, this may take a while…",
                        name,
                    )

                start = time.time()
                _model = WhisperModel(
                    name,
                    device=config.WHISPER_DEVICE,
                    compute_type=config.WHISPER_COMPUTE_TYPE,
                )
                elapsed = time.time() - start

                if not cached:
                    logger.info("Model '%s' download finished.", name)
                logger.info(
                    "Model '%s' loaded and ready in %.1fs (device=%s, compute=%s).",
                    name,
                    elapsed,
                    config.WHISPER_DEVICE,
                    config.WHISPER_COMPUTE_TYPE,
                )
    return _model


def get_model_info() -> dict:
    return {
        "model": config.WHISPER_MODEL,
        "device": config.WHISPER_DEVICE,
        "compute_type": config.WHISPER_COMPUTE_TYPE,
        "beam_size": config.WHISPER_BEAM_SIZE,
        "loaded": _model is not None,
        "hf_token": bool(config.HF_TOKEN),
    }


def transcribe_file(path: str) -> dict:
    """Transcribe an audio file and return text, language, duration, segments."""
    model = get_model()
    segments, info = model.transcribe(path, beam_size=config.WHISPER_BEAM_SIZE)

    seg_list = []
    texts = []
    for seg in segments:  # generator — consuming it runs the transcription
        line = seg.text.strip()
        seg_list.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": line,
        })
        texts.append(line)

    return {
        "text": " ".join(texts).strip(),
        "language": info.language,
        "duration": round(info.duration, 2),
        "segments": seg_list,
    }
