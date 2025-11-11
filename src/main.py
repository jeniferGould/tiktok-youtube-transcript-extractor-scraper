thonfrom __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from extractors.helpers import (
    build_proxies,
    get_logger,
    guess_platform_from_url,
    load_json,
)
from extractors.tiktok_parser import TikTokExtractor
from extractors.youtube_parser import YouTubeExtractor
from outputs.writer import write_json, write_transcripts

log = get_logger(__name__)

def load_settings(config_path: str) -> Dict[str, Any]:
    if not os.path.exists(config_path):
        log.warning("Config file %s not found; using defaults.", config_path)
        return {
            "concurrency": 4,
            "default_youtube_language": "en",
            "timeout_seconds": 20,
            "max_retries": 3,
            "proxy": {"http": None, "https": None},
            "artifacts_dir": "artifacts",
            "log_level": "INFO",
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def process_item(
    item: Dict[str, Any],
    yt_extractor: YouTubeExtractor,
    tt_extractor: TikTokExtractor,
    default_language: str,
    proxy_cfg: Optional[Dict[str, Optional[str]]],
) -> Dict[str, Any]:
    url = item.get("url")
    if not url:
        return {"error": "Missing url in item", "item": item}

    platform = (item.get("platform") or guess_platform_from_url(url)).lower()
    language = item.get("language") or default_language
    proxies = build_proxies(item.get("proxy") or proxy_cfg)

    try:
        if platform == "youtube":
            result = yt_extractor.extract(url=url, language=language, proxies=proxies)
        elif platform == "tiktok":
            result = tt_extractor.extract(url=url, proxies=proxies)
        else:
            return {
                "url": url,
                "platform": platform,
                "error": f"Unsupported or unknown platform for URL: {url}",
            }
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to process %s: %s", url, exc)
        return {"url": url, "platform": platform, "error": str(exc)}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TikTok & YouTube Transcript Extractor Scraper",
    )
    parser.add_argument(
        "--input",
        "-i",
        default=str(Path("data") / "sample_input.json"),
        help="Path to input JSON file containing an array of URL descriptors.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=str(Path("data") / "sample_output.json"),
        help="Path to output JSON file that will contain transcript results.",
    )
    parser.add_argument(
        "--config",
        "-c",
        default=str(Path("src") / "config" / "settings.json"),
        help="Path to configuration JSON file.",
    )
    parser.add_argument(
        "--write-files",
        action="store_true",
        help="If set, write individual .vtt and .txt files for each transcript.",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    settings = load_settings(args.config)

    default_language: str = settings.get("default_youtube_language", "en")
    concurrency: int = int(settings.get("concurrency", 4))
    proxy_cfg: Optional[Dict[str, Optional[str]]] = settings.get("proxy")
    artifacts_dir: str = settings.get("artifacts_dir", "artifacts")
    log_level: str = settings.get("log_level", "INFO")

    log.info("Loading input from %s", args.input)
    items = load_json(args.input)
    if not isinstance(items, list):
        raise ValueError("Input JSON must be an array of URL descriptor objects.")

    yt_extractor = YouTubeExtractor(default_language=default_language, log_level=log_level)
    tt_extractor = TikTokExtractor(log_level=log_level)

    results: List[Dict[str, Any]] = []
    log.info("Starting processing of %d items (concurrency=%d)", len(items), concurrency)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                process_item,
                item,
                yt_extractor,
                tt_extractor,
                default_language,
                proxy_cfg,
            )
            for item in items
        ]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    write_json(args.output, results)

    if args.write_files:
        write_transcripts(results, artifacts_dir)

    log.info("Done. Processed %d items.", len(results))

if __name__ == "__main__":
    main()