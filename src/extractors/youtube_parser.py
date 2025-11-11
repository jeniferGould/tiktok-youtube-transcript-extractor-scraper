thonfrom __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pytube import YouTube
from youtube_transcript_api import (  # type: ignore[import-untyped]
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from .helpers import (
    build_proxies,
    get_logger,
    parse_youtube_video_id,
    segments_to_webvtt,
)

class YouTubeExtractor:
    def __init__(self, default_language: str = "en", log_level: str = "INFO") -> None:
        self.default_language = default_language
        self.log = get_logger(self.__class__.__name__, log_level)

    def _fetch_transcript_segments(
        self,
        video_id: str,
        language: Optional[str] = None,
        proxies: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[Dict[str, Any]]:
        lang = language or self.default_language
        proxy_dict = build_proxies(proxies)
        kwargs: Dict[str, Any] = {}
        if proxy_dict:
            kwargs["proxies"] = proxy_dict
        try:
            self.log.debug(
                "Fetching transcript for YouTube video %s (languages=%s)",
                video_id,
                [lang, "en"],
            )
            segments = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=[lang, "en"],
                **kwargs,
            )
            return segments
        except (TranscriptsDisabled, NoTranscriptFound) as exc:
            self.log.warning("No transcript available for %s: %s", video_id, exc)
            return []
        except Exception as exc:  # noqa: BLE001
            self.log.error("Failed to fetch transcript for %s: %s", video_id, exc)
            return []

    def _fetch_metadata(
        self,
        url: str,
        proxies: Optional[Dict[str, Optional[str]]] = None,
    ) -> Dict[str, Any]:
        if proxies:
            # Pytube uses environment variables for proxies; we leave it to the environment
            self.log.debug("Proxies provided for metadata fetch, relying on environment variables")
        yt = YouTube(url)
        publish_date_iso: Optional[str] = None
        if getattr(yt, "publish_date", None):
            publish_date_iso = yt.publish_date.isoformat()
        thumbs: List[str] = []
        if getattr(yt, "thumbnail_url", None):
            thumbs.append(yt.thumbnail_url)
        metadata: Dict[str, Any] = {
            "videoId": yt.video_id,
            "title": yt.title,
            "lengthSeconds": str(getattr(yt, "length", 0)),
            "keywords": getattr(yt, "keywords", []) or [],
            "author": yt.author,
            "viewCount": str(getattr(yt, "views", 0)),
            "likeCount": None,  # Not reliably accessible without additional scraping
            "publishDate": publish_date_iso,
            "thumbnail": thumbs,
        }
        return metadata

    def extract(
        self,
        url: str,
        language: Optional[str] = None,
        proxies: Optional[Dict[str, Optional[str]]] = None,
    ) -> Dict[str, Any]:
        self.log.info("Processing YouTube URL: %s", url)
        video_id = parse_youtube_video_id(url)
        if not video_id:
            raise ValueError(f"Could not parse YouTube video ID from URL: {url}")

        segments = self._fetch_transcript_segments(
            video_id=video_id,
            language=language,
            proxies=proxies,
        )
        transcript_vtt = segments_to_webvtt(segments) if segments else ""

        plain_text = " ".join(seg.get("text", "").replace("\n", " ").strip() for seg in segments)
        plain_text = " ".join(part for part in plain_text.split() if part)

        metadata = self._fetch_metadata(url, proxies=proxies)
        result: Dict[str, Any] = {
            "platform": "youtube",
            "url": url,
            "transcript": transcript_vtt or None,
            "transcript_only_text": plain_text or None,
            "videoId": metadata.get("videoId"),
            "title": metadata.get("title"),
            "lengthSeconds": metadata.get("lengthSeconds"),
            "keywords": metadata.get("keywords"),
            "author": metadata.get("author"),
            "viewCount": metadata.get("viewCount"),
            "likeCount": metadata.get("likeCount"),
            "publishDate": metadata.get("publishDate"),
            "thumbnail": metadata.get("thumbnail"),
        }
        # Normalize types (e.g., ensure strings)
        if result["publishDate"] and isinstance(result["publishDate"], datetime):
            result["publishDate"] = result["publishDate"].isoformat()
        return result