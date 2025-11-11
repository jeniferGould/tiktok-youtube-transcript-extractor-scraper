thonfrom __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup  # type: ignore[import-untyped]

from .helpers import (
    build_proxies,
    get_logger,
    http_get,
    strip_vtt_to_plain_text,
)

class TikTokExtractor:
    def __init__(self, log_level: str = "INFO") -> None:
        self.log = get_logger(self.__class__.__name__, log_level)

    def _extract_state_json(self, html: str) -> Optional[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="SIGI_STATE")
        if not script or not script.string:
            return None
        try:
            return json.loads(script.string)
        except json.JSONDecodeError as exc:
            self.log.warning("Failed to decode SIGI_STATE JSON: %s", exc)
            return None

    def _extract_item(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        item_module = state.get("ItemModule") or {}
        if not isinstance(item_module, dict):
            return None
        for _, item in item_module.items():
            if isinstance(item, dict):
                return item
        return None

    def _extract_transcript_from_video(
        self,
        video: Dict[str, Any],
        proxies: Optional[Dict[str, Optional[str]]],
    ) -> Optional[str]:
        subs = (
            video.get("subtitleInfos")
            or video.get("subtitleInfo")
            or video.get("subtitles")
            or []
        )
        if not isinstance(subs, list):
            subs = []
        for entry in subs:
            url = (
                entry.get("Url")
                or entry.get("url")
                or entry.get("subtitleUrl")
            )
            if not url:
                continue
            try:
                resp = http_get(url, proxies=proxies, timeout=20, max_retries=3, logger=self.log)
                text = resp.text.strip()
                if text:
                    if not text.lstrip().upper().startswith("WEBVTT"):
                        # Assume it's JSON with captions
                        try:
                            segments = json.loads(text)
                            if isinstance(segments, list):
                                from .helpers import segments_to_webvtt  # local import to avoid cycles

                                return segments_to_webvtt(segments)
                        except json.JSONDecodeError:
                            pass
                    return text
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Failed to download TikTok subtitle from %s: %s", url, exc)
        return None

    def extract(
        self,
        url: str,
        proxies: Optional[Dict[str, Optional[str]]] = None,
    ) -> Dict[str, Any]:
        self.log.info("Processing TikTok URL: %s", url)
        proxy_dict = build_proxies(proxies)
        resp = http_get(url, proxies=proxy_dict, timeout=20, max_retries=3, logger=self.log)
        html = resp.text

        state = self._extract_state_json(html)
        if not state:
            self.log.warning("Could not read TikTok state JSON for %s", url)
            return {
                "platform": "tiktok",
                "url": url,
                "transcript": None,
                "transcript_only_text": None,
                "videoId": None,
                "title": None,
                "lengthSeconds": None,
                "keywords": [],
                "author": None,
                "viewCount": None,
                "likeCount": None,
                "publishDate": None,
                "thumbnail": [],
            }

        item = self._extract_item(state)
        if not item:
            self.log.warning("Could not locate ItemModule entry for %s", url)
            return {
                "platform": "tiktok",
                "url": url,
                "transcript": None,
                "transcript_only_text": None,
                "videoId": None,
                "title": None,
                "lengthSeconds": None,
                "keywords": [],
                "author": None,
                "viewCount": None,
                "likeCount": None,
                "publishDate": None,
                "thumbnail": [],
            }

        video = item.get("video") or {}
        stats = item.get("stats") or {}
        author_name = item.get("author") or None
        user_module = state.get("UserModule") or {}
        users = user_module.get("users") or {}
        if author_name and author_name in users:
            author_name = users[author_name].get("nickname") or users[author_name].get("uniqueId") or author_name

        transcript_vtt = self._extract_transcript_from_video(video, proxy_dict)
        if not transcript_vtt:
            # Fall back to generating a trivial WebVTT with the description as a single cue
            desc = (item.get("desc") or "").strip()
            if desc:
                transcript_vtt = "WEBVTT\n\n00:00:00.000 --> 00:59:59.000\n" + desc + "\n"

        plain_text = strip_vtt_to_plain_text(transcript_vtt) if transcript_vtt else None

        keywords: List[str] = []
        text_extra = item.get("textExtra") or []
        if isinstance(text_extra, list):
            for entry in text_extra:
                tag = entry.get("hashtagName") or entry.get("hashtagNameRaw")
                if tag:
                    keywords.append(str(tag))

        length_seconds: Optional[str] = None
        duration = video.get("duration") or video.get("durationTime")
        if duration is not None:
            try:
                length_seconds = str(int(duration))
            except (TypeError, ValueError):
                pass

        publish_date: Optional[str] = None
        create_time = item.get("createTime")
        if create_time is not None:
            try:
                ts = int(create_time)
                publish_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (TypeError, ValueError):
                pass

        thumbnail: List[str] = []
        thumb_fields = [
            "cover",
            "originCover",
            "dynamicCover",
            "shareCover",
        ]
        for field in thumb_fields:
            value = video.get(field)
            if isinstance(value, list):
                thumbnail.extend(str(v) for v in value)
            elif isinstance(value, str):
                thumbnail.append(value)

        result: Dict[str, Any] = {
            "platform": "tiktok",
            "url": url,
            "transcript": transcript_vtt or None,
            "transcript_only_text": plain_text or None,
            "videoId": item.get("id"),
            "title": item.get("desc"),
            "lengthSeconds": length_seconds,
            "keywords": keywords,
            "author": author_name,
            "viewCount": str(stats.get("playCount")) if stats.get("playCount") is not None else None,
            "likeCount": str(stats.get("diggCount")) if stats.get("diggCount") is not None else None,
            "publishDate": publish_date,
            "thumbnail": thumbnail,
        }
        return result