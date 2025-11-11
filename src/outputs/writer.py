thonfrom __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from extractors.helpers import ensure_dir, get_logger, safe_filename

log = get_logger(__name__)

def write_json(path: str, data: Any) -> None:
    ensure_dir(str(Path(path).parent))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("Wrote JSON output to %s", path)

def write_transcripts(results: Iterable[Dict[str, Any]], base_dir: str) -> List[str]:
    base = Path(base_dir)
    ensure_dir(str(base))
    written: List[str] = []

    for item in results:
        title = item.get("title") or item.get("videoId") or "video"
        platform = item.get("platform") or "video"
        filename_base = safe_filename(f"{platform}_{title}")
        vtt = item.get("transcript")
        txt = item.get("transcript_only_text")

        if vtt:
            vtt_path = base / f"{filename_base}.vtt"
            with open(vtt_path, "w", encoding="utf-8") as f:
                f.write(vtt)
            written.append(str(vtt_path))
            log.debug("Wrote VTT transcript for %s to %s", title, vtt_path)

        if txt:
            txt_path = base / f"{filename_base}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(txt)
            written.append(str(txt_path))
            log.debug("Wrote plain-text transcript for %s to %s", title, txt_path)

    if written:
        log.info("Wrote %d transcript files into %s", len(written), base_dir)
    else:
        log.info("No transcript files written (no transcript fields present).")
    return written