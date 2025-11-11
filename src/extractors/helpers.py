thonimport json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

_LOGGER_CONFIGURED = False

def _configure_root_logger(level: str = "INFO") -> None:
    global _LOGGER_CONFIGURED
    if _LOGGER_CONFIGURED:
        return
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    _LOGGER_CONFIGURED = True

def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    _configure_root_logger(level)
    return logging.getLogger(name)

def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)

def safe_filename(name: str, max_length: int = 150) -> str:
    name = name.strip().replace(os.path.sep, "_")
    name = re.sub(r"[^\w\-.]+", "_", name)
    if len(name) > max_length:
        base, _, ext = name.rpartition(".")
        if not base:
            base = name
            ext = ""
        trimmed = base[: max_length - len(ext) - 1]
        name = f"{trimmed}.{ext}" if ext else trimmed
    return name or "file"

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data: Any) -> None:
    ensure_dir(str(Path(path).parent))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def http_get(
    url: str,
    proxies: Optional[Dict[str, Optional[str]]] = None,
    timeout: int = 20,
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    logger: Optional[logging.Logger] = None,
) -> requests.Response:
    log = logger or get_logger("http_get")
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max_retries:
        try:
            log.debug("HTTP GET %s (attempt %d)", url, attempt + 1)
            resp = requests.get(
                url,
                timeout=timeout,
                proxies={k: v for k, v in (proxies or {}).items() if v},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0 Safari/537.36"
                    )
                },
            )
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            attempt += 1
            sleep_for = backoff_factor**attempt
            log.warning(
                "HTTP GET failed for %s: %s (attempt %d/%d, sleeping %.1fs)",
                url,
                exc,
                attempt,
                max_retries,
                sleep_for,
            )
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc

def parse_youtube_video_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.netloc in {"youtu.be"}:
        return parsed.path.lstrip("/").split("/")[0] or None
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            return qs["v"][0]
        parts = parsed.path.split("/")
        if "embed" in parts:
            idx = parts.index("embed")
            if idx + 1 < len(parts):
                return parts[idx + 1] or None
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", url):
        return url
    return None

def strip_vtt_to_plain_text(vtt: str) -> str:
    lines = vtt.splitlines()
    filtered: List[str] = []
    ts_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> ")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.upper() == "WEBVTT":
            continue
        if ts_pattern.match(line):
            continue
        if line.isdigit():
            continue
        filtered.append(line)
    return " ".join(filtered)

def segments_to_webvtt(segments: Iterable[Dict[str, Any]]) -> str:
    def fmt_ts(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    cues: List[str] = ["WEBVTT", ""]
    for idx, seg in enumerate(segments, start=1):
        start = float(seg.get("start", 0.0))
        duration = float(seg.get("duration", 0.0))
        end = start + duration
        text = (seg.get("text") or "").replace("\n", " ").strip()
        if not text:
            continue
        cues.append(str(idx))
        cues.append(f"{fmt_ts(start)} --> {fmt_ts(end)}")
        cues.append(text)
        cues.append("")
    return "\n".join(cues).strip() + "\n"

def guess_platform_from_url(url: str) -> str:
    low = url.lower()
    if "tiktok.com" in low:
        return "tiktok"
    if "youtube.com" in low or "youtu.be" in low:
        return "youtube"
    return "unknown"

def build_proxies(proxy_cfg: Optional[Dict[str, Optional[str]]]) -> Dict[str, Optional[str]]:
    return proxy_cfg or {}