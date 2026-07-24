#!/usr/bin/env python3
"""Build the private Adam Erhart YouTube caption study library.

The script intentionally downloads no video or audio. It retrieves public
metadata and caption tracks only, writes cleaned Markdown transcripts, and
generates the repository indexes and processing reports.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi


CREATOR = "Adam Erhart"
PROCESSED_AT = date.today().isoformat()
EXPECTED_EXPLICIT_OCCURRENCES = 54
EXPECTED_UNIQUE_EXPLICIT_IDS = 46
MODERN_MARKETING_PLAYLIST_ID = "PLxb4RhBMfU_Hhurhw3HLXxoQXa_LhXAHv"
MODERN_MARKETING_EXPECTED_SIZE = 22
CANONICAL_VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"
CANONICAL_PLAYLIST_URL = "https://www.youtube.com/playlist?list={playlist_id}"
ROOT_BEGIN = "<!-- BEGIN ADAM ERHART TRANSCRIPT LIBRARY -->"
ROOT_END = "<!-- END ADAM ERHART TRANSCRIPT LIBRARY -->"
MANAGED_BEGIN = "<!-- BEGIN AUTO-GENERATED ADAM ERHART CONTENT -->"
MANAGED_END = "<!-- END AUTO-GENERATED ADAM ERHART CONTENT -->"
TRANSCRIPT_BEGIN = "<!-- BEGIN AUTO-GENERATED ADAM ERHART TRANSCRIPT -->"
TRANSCRIPT_END = "<!-- END AUTO-GENERATED ADAM ERHART TRANSCRIPT -->"


PLAYLIST_SPECS: list[dict[str, Any]] = [
    {
        "priority": 1,
        "playlist_id": "PLxb4RhBMfU_G0v-DhqFq1zfdwBX7zzbW8",
        "mode": "Selected supplied videos",
        "supplied_video_ids": [
            "h95cQkEWBx0",
            "MAMUTGwYOcY",
            "NcgxgPCjFZc",
            "LeIePgFDAQI",
            "R1BOgBTzE1M",
            "NvgJ2mPWHX8",
            "Z_KspIX1oXU",
        ],
    },
    {
        "priority": 2,
        "playlist_id": "PLxb4RhBMfU_H1yhuXU79byfYtuYJMCgF9",
        "mode": "Selected supplied videos",
        "supplied_video_ids": [
            "jcDuq5Prt6A",
            "8jJxQo7nGog",
            "zArRjQ07CfU",
            "d2xiKX3TAhQ",
            "BZXLCn-8FjE",
            "PV0WQHWKfA0",
            "R1BOgBTzE1M",
        ],
    },
    {
        "priority": 3,
        "playlist_id": "PLxb4RhBMfU_FDfzNl1x0d-rrOA5cNEN2P",
        "mode": "Selected supplied videos",
        "supplied_video_ids": [
            "h95cQkEWBx0",
            "8Sj2tbh-ozE",
            "2g2fSvvcN2Q",
            "pbNlQs2eBDY",
            "b8oP6oeJ5WM",
            "n8M00vmp6v0",
            "7cCjX5MY28A",
            "_R-f_AlRLT8",
        ],
    },
    {
        "priority": 4,
        "playlist_id": "PLxb4RhBMfU_F-fhAGL00-CpG9BcEW1thc",
        "mode": "Selected supplied videos",
        "supplied_video_ids": ["ykCSh0PKqpo", "Awf_SgjrTQI"],
    },
    {
        "priority": 5,
        "playlist_id": "PLxb4RhBMfU_HQTzrP-9v22MyqZu-Z3kUj",
        "mode": "Selected supplied videos",
        "supplied_video_ids": [
            "rG88y8Lgv0w",
            "OyM2T2t4OoE",
            "0uaJDIc-n0M",
            "_mZBOToAEIk",
            "JcIqG143dyY",
            "_rVKxx-mUDQ",
            "OD22G8JRjQM",
            "JRENE4FcpiI",
            "l84ETfVheOM",
            "dJvq8UeE8sg",
            "7XjFMt6ER5w",
            "MYijSfg0eNM",
            "SKyKvGxpBYg",
            "3LZLNgQCXfs",
            "0d4-gmDv6Xc",
            "Olx26i7j6U4",
            "0zFpuU5Tupo",
            "cr3zHh3eNGM",
        ],
    },
    {
        "priority": 6,
        "playlist_id": "PLxb4RhBMfU_GoiBMtU9WPwVPnIGYCpCZz",
        "mode": "Selected supplied videos",
        "supplied_video_ids": [
            "ZYw52nVZl_0",
            "R1BOgBTzE1M",
            "Z_KspIX1oXU",
            "kJ6V76Zd05Q",
            "PKrc12Fr1qs",
        ],
    },
    {
        "priority": 7,
        "playlist_id": MODERN_MARKETING_PLAYLIST_ID,
        "known_title": "Modern Marketing Minute",
        "mode": "Entire playlist",
        "seed_video_id": "lkYHmbKCnk4",
        "expected_size": MODERN_MARKETING_EXPECTED_SIZE,
        "supplied_video_ids": ["lkYHmbKCnk4"],
    },
    {
        "priority": 8,
        "playlist_id": "PLxb4RhBMfU_HfQW9UtshQxeOA9-iV6bYo",
        "mode": "Selected supplied videos",
        "supplied_video_ids": [
            "_rVKxx-mUDQ",
            "kJ6V76Zd05Q",
            "-chPfQn0c7U",
            "rG88y8Lgv0w",
            "DmRDV0W2v1k",
            "OD22G8JRjQM",
        ],
    },
]


WORD_RE = re.compile(r"\b[\w]+(?:[’'-][\w]+)*\b", re.UNICODE)
TIMESTAMP_RE = re.compile(
    r"(?<!\d)(?:\[|\()?\d{1,2}:\d{2}(?::\d{2})?(?:\]|\))?(?!\d)"
)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
MANUAL_REVIEW_RE = re.compile(
    r"(?im)^(?:manually_reviewed|manual_reviewed):\s*(?:true|yes)\s*$"
)


@dataclass
class CaptionResult:
    caption_type: str
    language: str
    status: str
    segments: list[dict[str, Any]]
    source: str
    error_type: str = ""
    error_message: str = ""


def log(message: str) -> None:
    print(message, flush=True)


def canonical_video_url(video_id: str) -> str:
    return CANONICAL_VIDEO_URL.format(video_id=video_id)


def canonical_playlist_url(playlist_id: str) -> str:
    return CANONICAL_PLAYLIST_URL.format(playlist_id=playlist_id)


def compact_error(error: BaseException | str, limit: int = 500) -> str:
    text = SPACE_RE.sub(" ", str(error)).strip()
    return text[:limit]


def yaml_string(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def normalized_words(text: str) -> list[str]:
    return [word.casefold().replace("’", "'") for word in WORD_RE.findall(text)]


def slugify(value: str, maximum: int = 80) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.casefold().replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    slug = re.sub(r"-{2,}", "-", slug).strip("-._ ")
    slug = slug[:maximum].rstrip("-._ ")
    return slug or "untitled"


def format_duration(value: Any) -> str:
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError):
        return "unknown"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_published(metadata: dict[str, Any]) -> str:
    raw = metadata.get("upload_date") or metadata.get("release_date")
    if raw and re.fullmatch(r"\d{8}", str(raw)):
        raw = str(raw)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    timestamp = metadata.get("timestamp") or metadata.get("release_timestamp")
    if timestamp:
        try:
            return date.fromtimestamp(float(timestamp)).isoformat()
        except (OSError, TypeError, ValueError):
            pass
    return "unknown"


def existing_path_for_video(root: Path, video_id: str) -> Path | None:
    matches = list(root.glob(f"**/*--{video_id}.md"))
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple transcript pages already exist for {video_id}: "
            + ", ".join(str(path) for path in matches)
        )
    return matches[0] if matches else None


def replace_managed_block(
    path: Path, content: str, begin: str, end: str, *, preserve_outside: bool = True
) -> None:
    block = f"{begin}\n{content.rstrip()}\n{end}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8", newline="\n")
        return

    existing = path.read_text(encoding="utf-8")
    if begin in existing and end in existing:
        prefix, remainder = existing.split(begin, 1)
        _, suffix = remainder.split(end, 1)
        updated = f"{prefix}{block}{suffix.lstrip(chr(10))}" if preserve_outside else block
    elif preserve_outside:
        separator = "" if existing.endswith("\n\n") else "\n"
        updated = f"{existing.rstrip()}{separator}\n{block}"
    else:
        updated = block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8", newline="\n")


def write_transcript_page(path: Path, content: str, force: bool) -> bool:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if MANUAL_REVIEW_RE.search(existing) and not force:
            log(f"  protected manually reviewed transcript: {path.name}")
            return False
        if (
            'generated_by: "scripts/build_adam_erhart_transcripts.py"'
            not in existing
            and not force
        ):
            log(f"  protected non-generated transcript: {path.name}")
            return False
        suffix = (
            existing.split(TRANSCRIPT_END, 1)[1]
            if TRANSCRIPT_END in existing
            else ""
        )
    else:
        suffix = ""
    block = f"{content.rstrip()}\n{TRANSCRIPT_END}\n"
    updated = f"{block}{suffix.lstrip(chr(10))}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def migrate_transcript_front_matter(path: Path) -> None:
    """Move the legacy generated marker out of the front-matter position."""
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    legacy_prefix = f"{TRANSCRIPT_BEGIN}\n"
    if existing.startswith(legacy_prefix):
        path.write_text(
            existing[len(legacy_prefix) :], encoding="utf-8", newline="\n"
        )


def reflow_existing_transcript(path: Path) -> None:
    """Apply presentation-only paragraph limits to an existing generated page."""
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    start_marker = "## Full transcript\n\n"
    end_marker = "\n\n## Transcript processing note"
    if start_marker not in existing or end_marker not in existing:
        return
    prefix, remainder = existing.split(start_marker, 1)
    transcript, suffix = remainder.split(end_marker, 1)
    transcript = re.sub(
        r"\bAdam\s+Earhart\b",
        "Adam Erhart",
        transcript,
        flags=re.IGNORECASE,
    )
    reflowed = split_long_paragraphs(transcript.strip())
    updated = f"{prefix}{start_marker}{reflowed}{end_marker}{suffix}"
    if updated != existing:
        path.write_text(updated, encoding="utf-8", newline="\n")


def ydl_base_options() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "windowsfilenames": True,
    }


def fetch_playlist_metadata(spec: dict[str, Any]) -> dict[str, Any]:
    playlist_id = spec["playlist_id"]
    options = ydl_base_options()
    options.update(
        {
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
        }
    )
    if spec["mode"] != "Entire playlist":
        options["playlistend"] = 1
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(canonical_playlist_url(playlist_id), download=False)
    if not result:
        raise RuntimeError("yt-dlp returned no playlist metadata")
    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(result.get("entries") or [], start=1):
        if not entry or not entry.get("id"):
            continue
        entries.append(
            {
                "position": entry.get("playlist_index") or index,
                "video_id": entry["id"],
                "title": entry.get("title") or f"Video {entry['id']}",
            }
        )
    return {
        "title": result.get("title")
        or spec.get("known_title")
        or f"playlist-{playlist_id}",
        "entries": entries,
    }


def fetch_video_metadata(video_id: str) -> tuple[dict[str, Any], str, str]:
    try:
        with yt_dlp.YoutubeDL(ydl_base_options()) as ydl:
            result = ydl.extract_info(canonical_video_url(video_id), download=False)
        if not result:
            raise RuntimeError("yt-dlp returned no video metadata")
        return result, "success", ""
    except Exception as error:  # yt-dlp raises several extractor-specific classes
        message = compact_error(error)
        lowered = message.casefold()
        if any(
            marker in lowered
            for marker in (
                "private video",
                "video unavailable",
                "has been removed",
                "members-only",
                "not available",
            )
        ):
            return {}, "unavailable", message
        return {}, "failure", message


def english_language_codes(tracks: Iterable[Any], generated: bool) -> list[Any]:
    candidates = [
        track
        for track in tracks
        if bool(track.is_generated) is generated
        and str(track.language_code).casefold().startswith("en")
    ]
    return sorted(
        candidates,
        key=lambda track: (
            str(track.language_code).casefold() != "en",
            str(track.language_code).casefold(),
        ),
    )


def fetch_captions_with_api(
    api: YouTubeTranscriptApi, video_id: str
) -> CaptionResult:
    transcript_list = api.list(video_id)
    tracks = list(transcript_list)
    selected = None
    caption_type = ""
    for generated, label in ((False, "manual"), (True, "auto-generated")):
        candidates = english_language_codes(tracks, generated)
        if candidates:
            selected = candidates[0]
            caption_type = label
            break
    if selected is None:
        available = ", ".join(
            f"{track.language_code} ({'auto' if track.is_generated else 'manual'})"
            for track in tracks
        )
        return CaptionResult(
            caption_type="unavailable",
            language="unknown",
            status="unavailable",
            segments=[],
            source="youtube-transcript-api",
            error_type="NoEnglishTranscript",
            error_message=(
                f"No public English caption track was listed. Available: {available}"
                if available
                else "No public caption tracks were listed."
            ),
        )
    fetched = selected.fetch(preserve_formatting=False)
    segments = [
        {
            "text": snippet.text,
            "start": float(snippet.start),
            "duration": float(snippet.duration),
        }
        for snippet in fetched
    ]
    if not segments:
        return CaptionResult(
            caption_type="unavailable",
            language=selected.language_code,
            status="unavailable",
            segments=[],
            source="youtube-transcript-api",
            error_type="EmptyTranscript",
            error_message="The selected public caption track was empty.",
        )
    return CaptionResult(
        caption_type=caption_type,
        language=selected.language_code,
        status="success",
        segments=segments,
        source="youtube-transcript-api",
    )


def choose_english_track(tracks: dict[str, Any]) -> str | None:
    candidates = [code for code in tracks if code.casefold().startswith("en")]
    if not candidates:
        return None
    return sorted(
        candidates, key=lambda code: (code.casefold() != "en", code.casefold())
    )[0]


def parse_vtt(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n{2,}", raw)
    segments: list[dict[str, Any]] = []
    timing_re = re.compile(
        r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
        r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})"
    )

    def timestamp_seconds(value: str) -> float:
        value = value.replace(",", ".")
        parts = [float(part) for part in value.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return parts[0] * 60 + parts[1]

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line), None
        )
        if timing_index is None:
            continue
        match = timing_re.search(lines[timing_index])
        if not match:
            continue
        text_lines = lines[timing_index + 1 :]
        if not text_lines:
            continue
        start = timestamp_seconds(match.group("start"))
        end = timestamp_seconds(match.group("end"))
        text = " ".join(text_lines)
        segments.append(
            {"text": text, "start": start, "duration": max(0.0, end - start)}
        )
    return segments


def fetch_captions_with_ytdlp(
    video_id: str,
    metadata: dict[str, Any],
    temp_root: Path,
    keep_temporary: bool,
) -> CaptionResult:
    subtitles = metadata.get("subtitles") or {}
    automatic = metadata.get("automatic_captions") or {}
    language = choose_english_track(subtitles)
    caption_type = "manual"
    if language is None:
        language = choose_english_track(automatic)
        caption_type = "auto-generated"
    if language is None:
        return CaptionResult(
            caption_type="unavailable",
            language="unknown",
            status="unavailable",
            segments=[],
            source="yt-dlp",
            error_type="NoEnglishTranscript",
            error_message="yt-dlp found no public English subtitle track.",
        )

    temp_root.mkdir(parents=True, exist_ok=True)
    for stale in temp_root.glob(f"{video_id}.*"):
        if stale.is_file():
            stale.unlink()
    output_template = str(temp_root / f"{video_id}.%(ext)s")
    options = ydl_base_options()
    options.update(
        {
            "writesubtitles": caption_type == "manual",
            "writeautomaticsub": caption_type == "auto-generated",
            "subtitleslangs": [language],
            "subtitlesformat": "vtt",
            "outtmpl": output_template,
        }
    )
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(canonical_video_url(video_id), download=True)
    files = sorted(temp_root.glob(f"{video_id}*.vtt"))
    if not files:
        return CaptionResult(
            caption_type=caption_type,
            language=language,
            status="failed",
            segments=[],
            source="yt-dlp",
            error_type="SubtitleDownloadFailure",
            error_message="yt-dlp selected a caption track but wrote no VTT file.",
        )
    selected_file = files[0]
    segments = parse_vtt(selected_file)
    if segments and not keep_temporary:
        for path in files:
            path.unlink(missing_ok=True)
    if not segments:
        return CaptionResult(
            caption_type=caption_type,
            language=language,
            status="failed",
            segments=[],
            source="yt-dlp",
            error_type="EmptySubtitleFile",
            error_message=f"No caption cues could be parsed from {selected_file.name}.",
        )
    return CaptionResult(
        caption_type=caption_type,
        language=language,
        status="success",
        segments=segments,
        source="yt-dlp",
    )


def fetch_captions_with_relay(
    api: YouTubeTranscriptApi, video_id: str
) -> CaptionResult:
    """Retrieve the same public track through a cookie-free URL relay.

    This is a last resort for IP-level HTTP 429 responses. The relay receives
    only YouTube's short-lived, signed public caption URL. No repository data,
    browser state, cookies, or credentials are sent.
    """
    tracks = list(api.list(video_id))
    selected = None
    caption_type = ""
    for generated, label in ((False, "manual"), (True, "auto-generated")):
        candidates = english_language_codes(tracks, generated)
        if candidates:
            selected = candidates[0]
            caption_type = label
            break
    if selected is None:
        return CaptionResult(
            caption_type="unavailable",
            language="unknown",
            status="unavailable",
            segments=[],
            source="youtube-transcript-api + read-only URL relay",
            error_type="NoEnglishTranscript",
            error_message="No public English caption track was available to relay.",
        )
    signed_url = getattr(selected, "_url", "")
    if not signed_url:
        raise RuntimeError("The selected caption track did not expose its fetch URL.")
    separator = "&" if "?" in signed_url else "?"
    relay_url = f"https://r.jina.ai/{signed_url}{separator}fmt=json3"
    request = urllib.request.Request(
        relay_url,
        headers={
            "User-Agent": "marketing-study-caption-builder/1.0",
            "X-Return-Format": "text",
            "X-No-Cache": "true",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read(8 * 1024 * 1024).decode("utf-8", errors="replace")
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("The caption relay did not return JSON3 data.")
    payload = json.loads(body[start : end + 1])
    segments: list[dict[str, Any]] = []
    for event in payload.get("events") or []:
        text = "".join(
            str(segment.get("utf8") or "")
            for segment in event.get("segs") or []
        )
        text = SPACE_RE.sub(" ", html.unescape(text)).strip()
        if not text:
            continue
        segments.append(
            {
                "text": text,
                "start": float(event.get("tStartMs") or 0) / 1000.0,
                "duration": float(event.get("dDurationMs") or 0) / 1000.0,
            }
        )
    if not segments:
        raise RuntimeError("The relayed JSON3 caption track contained no text.")
    return CaptionResult(
        caption_type=caption_type,
        language=selected.language_code,
        status="success",
        segments=segments,
        source="youtube-transcript-api + read-only URL relay",
    )


def retrieve_captions(
    api: YouTubeTranscriptApi,
    video_id: str,
    metadata: dict[str, Any],
    temp_root: Path,
    keep_temporary: bool,
) -> CaptionResult:
    api_error: BaseException | None = None
    api_result: CaptionResult | None = None
    try:
        api_result = fetch_captions_with_api(api, video_id)
        if api_result.status == "success":
            return api_result
    except Exception as error:
        api_error = error

    try:
        fallback = fetch_captions_with_ytdlp(
            video_id, metadata, temp_root, keep_temporary
        )
        if fallback.status == "success":
            return fallback
        if fallback.status == "unavailable":
            if api_result is not None and api_result.status == "unavailable":
                return api_result
            if api_error is not None:
                name = type(api_error).__name__
                unavailable_names = {
                    "NoTranscriptFound",
                    "TranscriptsDisabled",
                    "VideoUnavailable",
                    "VideoUnplayable",
                    "AgeRestricted",
                }
                if name in unavailable_names:
                    return CaptionResult(
                        caption_type="unavailable",
                        language="unknown",
                        status="unavailable",
                        segments=[],
                        source="youtube-transcript-api + yt-dlp",
                        error_type=name,
                        error_message=compact_error(api_error),
                    )
            return fallback
        try:
            relay = fetch_captions_with_relay(api, video_id)
            if relay.status == "success":
                return relay
        except Exception as relay_error:
            fallback.error_message = (
                f"{fallback.error_message}; relay: {compact_error(relay_error)}"
            ).strip("; ")
        return fallback
    except Exception as fallback_error:
        if api_result is not None and api_result.status == "unavailable":
            return api_result
        relay_error: BaseException | None = None
        try:
            relay = fetch_captions_with_relay(api, video_id)
            if relay.status == "success":
                return relay
        except Exception as error:
            relay_error = error
        if api_error is not None:
            name = type(api_error).__name__
            unavailable_names = {
                "NoTranscriptFound",
                "TranscriptsDisabled",
                "VideoUnavailable",
                "VideoUnplayable",
                "AgeRestricted",
            }
            if name in unavailable_names:
                return CaptionResult(
                    caption_type="unavailable",
                    language="unknown",
                    status="unavailable",
                    segments=[],
                    source="youtube-transcript-api + yt-dlp",
                    error_type=name,
                    error_message=compact_error(api_error),
                )
        combined = (
            f"youtube-transcript-api: {compact_error(api_error)}; "
            f"yt-dlp: {compact_error(fallback_error)}; "
            f"relay: {compact_error(relay_error)}"
        )
        return CaptionResult(
            caption_type="unavailable",
            language="unknown",
            status="failed",
            segments=[],
            source="youtube-transcript-api + yt-dlp",
            error_type="TranscriptRetrievalFailure",
            error_message=combined,
        )


def normalize_caption_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = TAG_RE.sub("", value)
    value = value.replace("\n", " ")
    value = TIMESTAMP_RE.sub("", value)
    value = SPACE_RE.sub(" ", value).strip()
    value = re.sub(
        r"\bAdam\s+Earhart\b", "Adam Erhart", value, flags=re.IGNORECASE
    )
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value


def overlap_length(previous: Sequence[str], current: Sequence[str]) -> int:
    maximum = min(len(previous), len(current), 40)
    previous_normalized = [
        re.sub(r"^\W+|\W+$", "", token.casefold()) for token in previous
    ]
    current_normalized = [
        re.sub(r"^\W+|\W+$", "", token.casefold()) for token in current
    ]
    for size in range(maximum, 0, -1):
        if previous_normalized[-size:] == current_normalized[:size]:
            return size
    return 0


def merge_caption_segments(
    segments: list[dict[str, Any]],
) -> tuple[list[str], int, int]:
    merged_tokens: list[str] = []
    pieces: list[str] = []
    duplicate_fragments_removed = 0
    previous_end = -1.0
    previous_start = -1.0
    previous_cue = ""
    last_nonspeech: tuple[str, float] | None = None

    for segment in segments:
        text = normalize_caption_text(str(segment.get("text") or ""))
        if not text:
            continue
        start = float(segment.get("start") or 0.0)
        duration = float(segment.get("duration") or 0.0)
        nonspeech = bool(re.fullmatch(r"\[[^\]]+\]", text))
        if nonspeech:
            if (
                last_nonspeech
                and last_nonspeech[0].casefold() == text.casefold()
                and start - last_nonspeech[1] < 30
            ):
                duplicate_fragments_removed += 1
                continue
            last_nonspeech = (text, start)

        tokens = text.split()
        temporal_overlap = start < previous_end - 0.05
        close_cue = previous_start >= 0 and start - previous_start < 1.25
        overlap = overlap_length(merged_tokens, tokens) if merged_tokens else 0
        exact_previous = text.casefold() == previous_cue.casefold()
        remove = 0
        if exact_previous and (temporal_overlap or close_cue):
            remove = len(tokens)
        elif overlap >= 3 or (overlap >= 2 and temporal_overlap):
            remove = overlap
        if remove:
            tokens = tokens[remove:]
            duplicate_fragments_removed += 1
        if tokens:
            piece = " ".join(tokens)
            pieces.append(piece)
            merged_tokens.extend(tokens)
        previous_start = start
        previous_end = max(previous_end, start + duration)
        previous_cue = text

    merged_text = " ".join(pieces)
    return pieces, duplicate_fragments_removed, word_count(merged_text)


def capitalize_conservatively(text: str) -> str:
    def first_letter(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    text = re.sub(r"(^|[.!?]\s+)([a-z])", first_letter, text)
    return text


def split_long_paragraphs(text: str, limit: int = 150) -> str:
    """Split unusually long caption run-ons without changing their words."""
    result: list[str] = []

    def finish_paragraph(value: str) -> str:
        value = capitalize_conservatively(value.strip())
        if re.search(r"[.!?…][\"'”’)]?$", value):
            return value
        value = re.sub(r"[,;:—–-]+([\"'”’)]?)$", r".\1", value)
        if not re.search(r"[.!?…][\"'”’)]?$", value):
            value += "."
        return value

    for paragraph in text.split("\n\n"):
        words = paragraph.split()
        while word_count(" ".join(words)) > limit and len(words) > 1:
            lower = min(85, len(words) - 1)
            upper = min(135, len(words) - 1)
            target = min(110, upper)
            punctuation_candidates = [
                index
                for index in range(lower, upper + 1)
                if re.search(r"[,;:—–-][\"'”’)]?$", words[index - 1])
            ]
            cut = (
                min(punctuation_candidates, key=lambda index: abs(index - target))
                if punctuation_candidates
                else target
            )
            result.append(finish_paragraph(" ".join(words[:cut])))
            words = words[cut:]
        if words:
            result.append(finish_paragraph(" ".join(words)))
    return "\n\n".join(result)


def paragraph_transcript(pieces: list[str]) -> str:
    if not pieces:
        return ""
    combined = SPACE_RE.sub(" ", " ".join(pieces)).strip()
    combined = re.sub(
        r"\bAdam\s+Earhart\b", "Adam Erhart", combined, flags=re.IGNORECASE
    )
    combined = re.sub(r"\s+([,.;:!?])", r"\1", combined)
    combined = re.sub(r"([,.;:!?])(?=[A-Za-z])", r"\1 ", combined)
    combined = capitalize_conservatively(combined)
    total_words = word_count(combined)
    terminal_count = len(re.findall(r"[.!?](?:[\"'”’)]|$|\s)", combined))
    paragraphs: list[str] = []

    if terminal_count and total_words / terminal_count <= 65:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", combined)
            if sentence.strip()
        ]
        current: list[str] = []
        current_words = 0
        for sentence in sentences:
            sentence_words = word_count(sentence)
            if current and (
                len(current) >= 5
                or current_words + sentence_words > 145
                or (len(current) >= 2 and current_words >= 85)
            ):
                paragraphs.append(" ".join(current))
                current = []
                current_words = 0
            current.append(sentence)
            current_words += sentence_words
        if current:
            paragraphs.append(" ".join(current))
    else:
        sentences: list[str] = []
        current_pieces: list[str] = []
        current_words = 0
        continuation_words = {
            "a",
            "an",
            "and",
            "as",
            "at",
            "because",
            "but",
            "by",
            "for",
            "from",
            "how",
            "if",
            "in",
            "of",
            "one",
            "on",
            "or",
            "second",
            "so",
            "than",
            "that",
            "the",
            "then",
            "third",
            "three",
            "to",
            "two",
            "when",
            "where",
            "whether",
            "which",
            "while",
            "who",
            "with",
        }
        next_continuation_words = {
            "a",
            "an",
            "and",
            "as",
            "at",
            "because",
            "but",
            "completely",
            "for",
            "from",
            "in",
            "just",
            "of",
            "on",
            "or",
            "really",
            "than",
            "that",
            "the",
            "then",
            "to",
            "which",
            "who",
            "with",
            "would",
        }
        strong_sentence_starters = {
            "finally",
            "however",
            "how",
            "meanwhile",
            "next",
            "now",
            "therefore",
            "well",
            "what",
            "when",
            "whether",
            "why",
        }
        for piece_index, piece in enumerate(pieces):
            cleaned_piece = SPACE_RE.sub(" ", piece).strip()
            if not cleaned_piece:
                continue
            piece_words = word_count(cleaned_piece)
            current_pieces.append(cleaned_piece)
            current_words += piece_words
            final_words = normalized_words(cleaned_piece)
            final_word = final_words[-1] if final_words else ""
            next_words = (
                normalized_words(pieces[piece_index + 1])
                if piece_index + 1 < len(pieces)
                else []
            )
            next_word = next_words[0] if next_words else ""
            strong_next = (
                next_word in strong_sentence_starters
                or next_words[:2] == ["all", "right"]
                or next_words[:3] == ["on", "the", "other"]
            )
            has_terminal = bool(
                re.search(r"[.!?…][\"'”’)]?$", cleaned_piece)
            )
            if (
                has_terminal
                or (
                    current_words >= 20
                    and strong_next
                )
                or (
                    current_words >= 125
                    and len(current_pieces) >= 3
                    and final_word not in continuation_words
                    and next_word not in next_continuation_words
                )
            ):
                sentence = capitalize_conservatively(
                    " ".join(current_pieces)
                )
                if not has_terminal:
                    sentence += "."
                sentences.append(sentence)
                current_pieces = []
                current_words = 0
        if current_pieces:
            sentence = capitalize_conservatively(" ".join(current_pieces))
            if not re.search(r"[.!?…][\"'”’)]?$", sentence):
                sentence += "."
            sentences.append(sentence)

        current_sentences: list[str] = []
        current_words = 0
        for sentence in sentences:
            sentence_words = word_count(sentence)
            if current_sentences and (
                len(current_sentences) >= 5
                or current_words + sentence_words > 135
                or (len(current_sentences) >= 3 and current_words >= 85)
            ):
                paragraphs.append(" ".join(current_sentences))
                current_sentences = []
                current_words = 0
            current_sentences.append(sentence)
            current_words += sentence_words
        if current_sentences:
            paragraphs.append(" ".join(current_sentences))

    transcript = "\n\n".join(
        SPACE_RE.sub(" ", paragraph).strip() for paragraph in paragraphs
    )
    return split_long_paragraphs(transcript)


def verify_boundary(raw_merged: str, cleaned: str, beginning: bool) -> bool:
    raw_words = normalized_words(raw_merged)
    cleaned_words = normalized_words(cleaned)
    if not raw_words or not cleaned_words:
        return False
    size = min(10, len(raw_words), len(cleaned_words))
    if beginning:
        return raw_words[:size] == cleaned_words[:size]
    return raw_words[-size:] == cleaned_words[-size:]


def clean_transcript(
    segments: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    raw_word_total = sum(
        word_count(normalize_caption_text(str(segment.get("text") or "")))
        for segment in segments
    )
    pieces, duplicates_removed, merged_word_total = merge_caption_segments(segments)
    raw_merged = " ".join(pieces)
    cleaned = paragraph_transcript(pieces)
    cleaned_words = word_count(cleaned)
    difference = cleaned_words - raw_word_total
    percentage = (difference / raw_word_total * 100.0) if raw_word_total else 0.0
    warnings: list[str] = []
    if abs(percentage) > 10:
        warnings.append(
            f"Cleaned/raw word-count difference is {percentage:.2f}%; "
            f"{duplicates_removed} rolling-caption fragments were removed."
        )
    if merged_word_total != cleaned_words:
        warnings.append(
            "Paragraph formatting changed the merged word count unexpectedly."
        )
    beginning_verified = verify_boundary(raw_merged, cleaned, True)
    ending_verified = verify_boundary(raw_merged, cleaned, False)
    if not beginning_verified:
        warnings.append("Beginning boundary comparison failed.")
    if not ending_verified:
        warnings.append("Ending boundary comparison failed.")
    if TIMESTAMP_RE.search(cleaned):
        warnings.append("A timestamp-like token remains in the transcript.")
    if cleaned_words > 150 and len(re.findall(r"[.!?]", cleaned)) == 0:
        warnings.append("Transcript contains little or no sentence punctuation.")
    stats = {
        "raw_segment_count": len(segments),
        "raw_word_count": raw_word_total,
        "cleaned_word_count": cleaned_words,
        "word_count_difference": difference,
        "percentage_difference": round(percentage, 2),
        "duplicate_fragments_removed": duplicates_removed,
        "unclear_markers_added": cleaned.count("[unclear]"),
        "quality_warnings": warnings,
        "beginning_verified": beginning_verified,
        "ending_verified": ending_verified,
    }
    return cleaned, stats


def build_occurrences(
    playlists: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    occurrences: list[dict[str, Any]] = []
    primary_by_id: dict[str, dict[str, Any]] = {}
    for playlist in playlists:
        for entry in playlist["entries"]:
            occurrence = {
                "playlist_priority": playlist["priority"],
                "playlist_id": playlist["playlist_id"],
                "playlist_title": playlist["title"],
                "playlist_processing_mode": playlist["mode"],
                "playlist_position": entry["position"],
                "video_id": entry["video_id"],
                "entry_title": entry.get("title") or f"Video {entry['video_id']}",
                "canonical_video_url": canonical_video_url(entry["video_id"]),
            }
            primary = primary_by_id.get(entry["video_id"])
            if primary is None:
                primary = occurrence.copy()
                primary_by_id[entry["video_id"]] = primary
                occurrence["is_duplicate"] = False
            else:
                occurrence["is_duplicate"] = True
            occurrence["primary_playlist_id"] = primary["playlist_id"]
            occurrence["primary_playlist_title"] = primary["playlist_title"]
            occurrence["primary_playlist_position"] = primary["playlist_position"]
            occurrences.append(occurrence)
    return occurrences, primary_by_id


def read_previous_status(data_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    quality_path = data_dir / "transcript-quality.json"
    status_path = data_dir / "processing-status.csv"
    quality: dict[str, Any] = {}
    status: dict[str, Any] = {}
    if quality_path.exists():
        try:
            for item in json.loads(quality_path.read_text(encoding="utf-8")):
                quality[item["video_id"]] = item
        except (KeyError, TypeError, ValueError):
            pass
    if status_path.exists():
        try:
            with status_path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row.get("video_id") and not row.get("is_duplicate") == "true":
                        status[row["video_id"]] = row
        except (OSError, csv.Error):
            pass
    return quality, status


def create_playlist_records(
    selected_playlist_id: str | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for original in PLAYLIST_SPECS:
        if selected_playlist_id and original["playlist_id"] != selected_playlist_id:
            continue
        spec = dict(original)
        log(
            f"[playlist {spec['priority']}/8] Retrieving metadata for "
            f"{spec['playlist_id']}"
        )
        try:
            metadata = fetch_playlist_metadata(spec)
            title = metadata["title"]
            metadata_status = "success"
            metadata_error = ""
        except Exception as error:
            title = spec.get("known_title") or f"playlist-{spec['playlist_id']}"
            metadata = {"entries": []}
            metadata_status = "failure"
            metadata_error = compact_error(error)
            log(f"  playlist metadata failure: {metadata_error}")

        if spec["mode"] == "Entire playlist":
            entries = metadata["entries"]
            if not entries:
                raise RuntimeError(
                    "The complete Modern Marketing Minute playlist could not be "
                    "expanded; refusing to substitute only the seed video."
                )
            log(
                f"  retrieved {len(entries)} entries; expected "
                f"{spec['expected_size']}"
            )
        else:
            entries = [
                {
                    "position": position,
                    "video_id": video_id,
                    "title": f"Video {video_id}",
                }
                for position, video_id in enumerate(
                    spec["supplied_video_ids"], start=1
                )
            ]
        records.append(
            {
                **spec,
                "title": title,
                "metadata_status": metadata_status,
                "metadata_error": metadata_error,
                "entries": entries,
                "folder": f"{spec['priority']:02d}-{slugify(title, 68)}",
            }
        )
    return records


def transcript_path_for(
    transcripts_root: Path,
    primary: dict[str, Any],
    playlist_by_id: dict[str, dict[str, Any]],
    title: str,
) -> Path:
    existing = existing_path_for_video(transcripts_root, primary["video_id"])
    if existing:
        return existing
    playlist = playlist_by_id[primary["playlist_id"]]
    filename = (
        f"{int(primary['playlist_position']):02d}-"
        f"{slugify(title, 82)}--{primary['video_id']}.md"
    )
    return transcripts_root / playlist["folder"] / filename


def build_video_page(
    item: dict[str, Any],
    previous_path: Path | None,
    next_path: Path | None,
    playlist_index_path: Path,
) -> str:
    metadata = item["metadata"]
    primary = item["primary"]
    playlist_title = primary["playlist_title"]
    playlist_id = primary["playlist_id"]
    caption = item["caption"]
    stats = item["stats"]
    title = item["title"]
    published = item["published"]
    duration = item["duration"]
    status = item["transcript_status"]
    caption_type = caption.caption_type
    caption_language = caption.language
    caption_source_text = {
        "manual": "Manual English captions",
        "auto-generated": "Auto-generated English captions",
        "unavailable": "Unavailable",
    }.get(caption_type, "Unavailable")
    status_label = {
        "complete": "Complete",
        "unavailable": "Unavailable",
        "failed": "Failed",
    }.get(status, status.title())
    front_matter = [
        "---",
        f"title: {yaml_string(title)}",
        f"creator: {yaml_string(CREATOR)}",
        f"video_id: {yaml_string(primary['video_id'])}",
        f"youtube_url: {yaml_string(canonical_video_url(primary['video_id']))}",
        f"playlist_title: {yaml_string(playlist_title)}",
        f"playlist_id: {yaml_string(playlist_id)}",
        f"playlist_position: {int(primary['playlist_position'])}",
        f"published: {yaml_string(published)}",
        f"duration: {yaml_string(duration)}",
        f"caption_type: {yaml_string(caption_type)}",
        f"caption_language: {yaml_string(caption_language)}",
        f"transcript_status: {yaml_string(status)}",
        f"raw_segment_count: {stats['raw_segment_count']}",
        f"raw_word_count: {stats['raw_word_count']}",
        f"cleaned_word_count: {stats['cleaned_word_count']}",
        f"processed_at: {yaml_string(PROCESSED_AT)}",
        'generated_by: "scripts/build_adam_erhart_transcripts.py"',
        "manually_reviewed: false",
        "---",
    ]
    lines = [
        *front_matter,
        "",
        f"# {title}",
        "",
        "## Video information",
        "",
        f"- **Creator:** {CREATOR}",
        f"- **Video:** [Watch on YouTube]({canonical_video_url(primary['video_id'])})",
        f"- **Playlist:** [{playlist_title}]({canonical_playlist_url(playlist_id)})",
        f"- **Playlist position:** {primary['playlist_position']}",
        f"- **Published:** {published}",
        f"- **Duration:** {duration}",
        f"- **Caption source:** {caption_source_text}",
        f"- **Transcript status:** {status_label}",
        "",
        "## Full transcript",
        "",
    ]
    if status == "complete":
        lines.extend([item["cleaned_transcript"], ""])
    else:
        lines.extend(
            [
                "A transcript could not be retrieved because publicly available "
                "captions were unavailable or inaccessible.",
                "",
            ]
        )
    unclear_note = (
        f"{stats['unclear_markers_added']} `[unclear]` marker(s) remain."
        if stats["unclear_markers_added"]
        else "No `[unclear]` markers were added."
    )
    quality_note = (
        "Automatic captions may contain recognition or punctuation errors."
        if caption_type == "auto-generated"
        else "Caption wording was preserved; minor source-caption errors may remain."
    )
    lines.extend(
        [
            "## Transcript processing note",
            "",
            f"- **Caption source:** {caption.source}",
            f"- **Caption language:** {caption_language}",
            f"- **Caption type:** {caption_type}",
            f"- **Unclear words:** {unclear_note}",
            f"- **Quality note:** {quality_note}",
            f"- **Raw caption segments:** {stats['raw_segment_count']}",
            f"- **Raw caption words:** {stats['raw_word_count']}",
            f"- **Cleaned transcript words:** {stats['cleaned_word_count']}",
            "",
            "## Navigation",
            "",
        ]
    )
    if previous_path:
        lines.append(f"- [Previous video]({previous_path.name})")
    else:
        lines.append("- Previous video: none")
    lines.append(f"- [Playlist index]({playlist_index_path.name})")
    if next_path:
        lines.append(f"- [Next video]({next_path.name})")
    else:
        lines.append("- Next video: none")
    return "\n".join(lines).rstrip() + "\n"


def relative_link(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, from_path.parent)).as_posix()


def status_label_for(item: dict[str, Any]) -> str:
    if item.get("is_duplicate"):
        return "Duplicate — stored elsewhere"
    caption: CaptionResult = item["video"]["caption"]
    if item["video"]["transcript_status"] == "complete":
        if caption.caption_type == "manual":
            return "Complete — manual captions"
        return "Complete — auto-generated captions"
    if item["video"]["metadata_status"] == "unavailable":
        return "Video unavailable"
    if item["video"]["metadata_status"] == "failure":
        return "Metadata failure"
    if item["video"]["transcript_status"] == "unavailable":
        return "Captions unavailable"
    return "Transcript retrieval failure"


def make_duplicates(
    occurrences: list[dict[str, Any]],
    videos: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    duplicates_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    primary_by_id: dict[str, dict[str, Any]] = {}
    for occurrence in occurrences:
        if occurrence["is_duplicate"]:
            duplicates_by_id[occurrence["video_id"]].append(occurrence)
        else:
            primary_by_id[occurrence["video_id"]] = occurrence
    result: list[dict[str, Any]] = []
    for video_id, duplicate_occurrences in duplicates_by_id.items():
        primary = primary_by_id[video_id]
        video = videos[video_id]
        result.append(
            {
                "video_id": video_id,
                "exact_video_title": video["title"],
                "canonical_youtube_url": canonical_video_url(video_id),
                "primary_playlist_id": primary["playlist_id"],
                "primary_playlist_title": primary["playlist_title"],
                "primary_playlist_position": primary["playlist_position"],
                "primary_transcript_path": video["relative_path"],
                "duplicate_playlist_ids": [
                    occurrence["playlist_id"]
                    for occurrence in duplicate_occurrences
                ],
                "duplicate_playlist_titles": [
                    occurrence["playlist_title"]
                    for occurrence in duplicate_occurrences
                ],
                "duplicate_playlist_positions": [
                    occurrence["playlist_position"]
                    for occurrence in duplicate_occurrences
                ],
            }
        )
    return result


def build_processing_rows(
    occurrences: list[dict[str, Any]], videos: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for occurrence in occurrences:
        video = videos[occurrence["video_id"]]
        caption: CaptionResult = video["caption"]
        stats = video["stats"]
        rows.append(
            {
                "playlist_priority": occurrence["playlist_priority"],
                "playlist_id": occurrence["playlist_id"],
                "playlist_title": occurrence["playlist_title"],
                "playlist_processing_mode": occurrence[
                    "playlist_processing_mode"
                ],
                "playlist_position": occurrence["playlist_position"],
                "video_id": occurrence["video_id"],
                "video_title": video["title"],
                "canonical_video_url": occurrence["canonical_video_url"],
                "is_duplicate": str(occurrence["is_duplicate"]).lower(),
                "primary_playlist_id": occurrence["primary_playlist_id"],
                "primary_playlist_title": occurrence["primary_playlist_title"],
                "primary_transcript_path": video["relative_path"],
                "metadata_status": video["metadata_status"],
                "caption_type": caption.caption_type,
                "caption_language": caption.language,
                "caption_status": caption.status,
                "raw_segment_count": stats["raw_segment_count"],
                "raw_word_count": stats["raw_word_count"],
                "cleaned_word_count": stats["cleaned_word_count"],
                "transcript_status": video["transcript_status"],
                "error_type": caption.error_type
                or (
                    "MetadataFailure"
                    if video["metadata_status"] != "success"
                    else ""
                ),
                "error_message": caption.error_message
                or video["metadata_error"],
                "processed_at": PROCESSED_AT,
            }
        )
    return rows


PROCESSING_COLUMNS = [
    "playlist_priority",
    "playlist_id",
    "playlist_title",
    "playlist_processing_mode",
    "playlist_position",
    "video_id",
    "video_title",
    "canonical_video_url",
    "is_duplicate",
    "primary_playlist_id",
    "primary_playlist_title",
    "primary_transcript_path",
    "metadata_status",
    "caption_type",
    "caption_language",
    "caption_status",
    "raw_segment_count",
    "raw_word_count",
    "cleaned_word_count",
    "transcript_status",
    "error_type",
    "error_message",
    "processed_at",
]


def write_processing_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROCESSING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_playlist_readme(
    playlist: dict[str, Any],
    playlist_occurrences: list[dict[str, Any]],
    videos: dict[str, dict[str, Any]],
    readme_path: Path,
) -> str:
    unique_stored = sum(not item["is_duplicate"] for item in playlist_occurrences)
    duplicate_count = sum(item["is_duplicate"] for item in playlist_occurrences)
    unavailable_count = sum(
        not item["is_duplicate"]
        and videos[item["video_id"]]["transcript_status"] != "complete"
        for item in playlist_occurrences
    )
    lines = [
        f"# {playlist['title']}",
        "",
        f"- **Creator:** {CREATOR}",
        f"- **YouTube playlist:** [Open playlist]({canonical_playlist_url(playlist['playlist_id'])})",
        f"- **Playlist ID:** {playlist['playlist_id']}",
        f"- **Processing mode:** {playlist['mode']}",
        f"- **Source entries:** {len(playlist_occurrences)}",
        f"- **Unique transcripts stored here:** {unique_stored}",
        f"- **Duplicate references:** {duplicate_count}",
        f"- **Unavailable transcripts:** {unavailable_count}",
        "",
        "## Videos",
        "",
        "| # | Video | YouTube | Transcript | Status | Notes |",
        "|---:|---|---|---|---|---|",
    ]
    for occurrence in playlist_occurrences:
        video = videos[occurrence["video_id"]]
        target_path = video["path"]
        transcript_link = relative_link(readme_path, target_path)
        item = {**occurrence, "video": video}
        status = status_label_for(item)
        note = ""
        if occurrence["is_duplicate"]:
            note = (
                f'Duplicate — stored under “{occurrence["primary_playlist_title"]}”'
            )
        elif video["stats"]["quality_warnings"]:
            note = "Quality warning recorded"
        title = video["title"].replace("|", r"\|")
        note = note.replace("|", r"\|")
        lines.append(
            f"| {occurrence['playlist_position']} | {title} | "
            f"[YouTube]({occurrence['canonical_video_url']}) | "
            f"[Transcript]({transcript_link}) | {status} | {note} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def summary_counts(
    occurrences: list[dict[str, Any]], videos: dict[str, dict[str, Any]]
) -> dict[str, int]:
    return {
        "source_occurrences": len(occurrences),
        "unique_videos": len(videos),
        "duplicate_references": sum(item["is_duplicate"] for item in occurrences),
        "completed": sum(
            video["transcript_status"] == "complete" for video in videos.values()
        ),
        "manual_completed": sum(
            video["transcript_status"] == "complete"
            and video["caption"].caption_type == "manual"
            for video in videos.values()
        ),
        "auto_completed": sum(
            video["transcript_status"] == "complete"
            and video["caption"].caption_type == "auto-generated"
            for video in videos.values()
        ),
        "unavailable": sum(
            video["transcript_status"] == "unavailable"
            for video in videos.values()
        ),
        "metadata_failures": sum(
            video["metadata_status"] != "success" for video in videos.values()
        ),
        "transcript_failures": sum(
            video["transcript_status"] == "failed" for video in videos.values()
        ),
        "quality_warnings": sum(
            bool(video["stats"]["quality_warnings"]) for video in videos.values()
        ),
    }


def build_central_readme(
    playlists: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    videos: dict[str, dict[str, Any]],
    central_path: Path,
    data_dir: Path,
) -> str:
    counts = summary_counts(occurrences, videos)
    lines = [
        "# Adam Erhart Marketing Transcript Library",
        "",
        "This private personal-study library contains complete, readable transcripts "
        "made from publicly available YouTube caption tracks. It is organised for "
        "searching, comparing, and studying Adam Erhart's marketing lessons.",
        "",
        f"- **Creator:** {CREATOR}",
        "- **Use:** Private study",
        f"- **Playlist categories:** {len(playlists)}",
        f"- **Total source entries:** {counts['source_occurrences']}",
        f"- **Total unique videos:** {counts['unique_videos']}",
        f"- **Completed transcripts:** {counts['completed']}",
        f"- **Unavailable transcripts:** {counts['unavailable'] + counts['transcript_failures']}",
        f"- **Duplicate references:** {counts['duplicate_references']}",
        "",
        "Each unique video has one canonical transcript page under the first supplied "
        "playlist in which it appears. Later playlist appearances link back to that "
        "page instead of copying the transcript.",
        "",
        "## Playlist navigation",
        "",
    ]
    for playlist in playlists:
        path = central_path.parent / playlist["folder"] / "README.md"
        link = relative_link(central_path, path)
        lines.append(
            f"{playlist['priority']}. [{playlist['title']}]({link})"
        )
    lines.extend(
        [
            "",
            "## Processing data",
            "",
            f"- [Processing status]({relative_link(central_path, data_dir / 'processing-status.csv')})",
            f"- [Duplicate references]({relative_link(central_path, data_dir / 'duplicates.json')})",
            f"- [Transcript quality]({relative_link(central_path, data_dir / 'transcript-quality.json')})",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_root_section(
    playlists: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    videos: dict[str, dict[str, Any]],
    root_readme: Path,
    central_path: Path,
) -> str:
    counts = summary_counts(occurrences, videos)
    lines = [
        "# Adam Erhart Marketing Transcript Library",
        "",
        "This private personal-study library contains full, cleaned transcripts of "
        "Adam Erhart marketing videos when public YouTube captions were available. "
        "The caption wording and complete spoken sequence are preserved; the cleanup "
        "removes subtitle artifacts and adds conservative reading structure.",
        "",
        f"- **Creator:** {CREATOR}",
        f"- **Playlist categories:** {len(playlists)}",
        f"- **Total source occurrences:** {counts['source_occurrences']}",
        f"- **Total unique videos:** {counts['unique_videos']}",
        f"- **Successful transcripts:** {counts['completed']}",
        f"- **Unavailable captions:** {counts['unavailable'] + counts['transcript_failures']}",
        f"- **Duplicate references:** {counts['duplicate_references']}",
        f"- **Last processed:** {PROCESSED_AT}",
        "",
        "Videos are grouped by playlist. A video appearing more than once is stored "
        "only under its earliest supplied playlist; later playlist indexes link to "
        "the canonical transcript page.",
        "",
        f"[Open the central transcript index]({relative_link(root_readme, central_path)})",
        "",
        "## Playlist navigation",
        "",
        "| # | Playlist | YouTube | Unique transcripts | Duplicate references | Unavailable | Repository folder |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for playlist in playlists:
        selected = [
            occurrence
            for occurrence in occurrences
            if occurrence["playlist_id"] == playlist["playlist_id"]
        ]
        unique_count = sum(not item["is_duplicate"] for item in selected)
        duplicate_count = sum(item["is_duplicate"] for item in selected)
        unavailable_count = sum(
            not item["is_duplicate"]
            and videos[item["video_id"]]["transcript_status"] != "complete"
            for item in selected
        )
        readme = central_path.parent / playlist["folder"] / "README.md"
        lines.append(
            f"| {playlist['priority']} | {playlist['title']} | "
            f"[YouTube]({canonical_playlist_url(playlist['playlist_id'])}) | "
            f"{unique_count} | {duplicate_count} | {unavailable_count} | "
            f"[Folder]({relative_link(root_readme, readme)}) |"
        )
    return "\n".join(lines).rstrip() + "\n"


def build_manifest(
    playlists: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    videos: dict[str, dict[str, Any]],
    duplicates: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = summary_counts(occurrences, videos)
    playlist_items: list[dict[str, Any]] = []
    for playlist in playlists:
        entries: list[dict[str, Any]] = []
        for occurrence in occurrences:
            if occurrence["playlist_id"] != playlist["playlist_id"]:
                continue
            entries.append(
                {
                    "position": occurrence["playlist_position"],
                    "video_id": occurrence["video_id"],
                    "title": videos[occurrence["video_id"]]["title"],
                    "canonical_video_url": occurrence["canonical_video_url"],
                    "is_duplicate": occurrence["is_duplicate"],
                    "primary_playlist_id": occurrence["primary_playlist_id"],
                    "primary_transcript_path": videos[
                        occurrence["video_id"]
                    ]["relative_path"],
                }
            )
        playlist_items.append(
            {
                "priority": playlist["priority"],
                "playlist_id": playlist["playlist_id"],
                "retrieved_title": playlist["title"],
                "canonical_playlist_url": canonical_playlist_url(
                    playlist["playlist_id"]
                ),
                "processing_mode": playlist["mode"],
                "supplied_video_ids": playlist["supplied_video_ids"],
                "supplied_order": list(
                    range(1, len(playlist["supplied_video_ids"]) + 1)
                ),
                "seed_video_id": playlist.get("seed_video_id"),
                "expected_entire_playlist_size": playlist.get("expected_size"),
                "retrieved_entry_count": len(entries),
                "playlist_metadata_status": playlist["metadata_status"],
                "playlist_metadata_error": playlist["metadata_error"],
                "repository_folder": (
                    f"transcripts/adam-erhart/{playlist['folder']}"
                ),
                "entries": entries,
            }
        )
    modern = next(
        (
            playlist
            for playlist in playlists
            if playlist["playlist_id"] == MODERN_MARKETING_PLAYLIST_ID
        ),
        None,
    )
    return {
        "creator": CREATOR,
        "processed_at": PROCESSED_AT,
        "explicit_source_occurrences": EXPECTED_EXPLICIT_OCCURRENCES,
        "unique_explicit_video_ids": EXPECTED_UNIQUE_EXPLICIT_IDS,
        "malformed_url_correction": {
            "intended_video_id": "NcgxgPCjFZc",
            "status": "corrected in source manifest",
        },
        "modern_marketing_minute": {
            "playlist_id": MODERN_MARKETING_PLAYLIST_ID,
            "expected_size": MODERN_MARKETING_EXPECTED_SIZE,
            "retrieved_size": len(modern["entries"]) if modern else None,
        },
        "totals_after_expansion": counts,
        "playlists": playlist_items,
        "duplicate_occurrences": duplicates,
    }


def quality_records(videos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for video_id, video in videos.items():
        stats = video["stats"]
        records.append(
            {
                "video_id": video_id,
                "title": video["title"],
                "transcript_path": video["relative_path"],
                "caption_type": video["caption"].caption_type,
                "caption_language": video["caption"].language,
                "raw_segment_count": stats["raw_segment_count"],
                "raw_word_count": stats["raw_word_count"],
                "cleaned_word_count": stats["cleaned_word_count"],
                "word_count_difference": stats["word_count_difference"],
                "percentage_difference": stats["percentage_difference"],
                "duplicate_fragments_removed": stats[
                    "duplicate_fragments_removed"
                ],
                "unclear_markers_added": stats["unclear_markers_added"],
                "quality_warnings": stats["quality_warnings"],
                "beginning_verified": stats["beginning_verified"],
                "ending_verified": stats["ending_verified"],
                "status": video["transcript_status"],
            }
        )
    return records


def validate_library(
    repo_root: Path,
    playlists: list[dict[str, Any]],
    occurrences: list[dict[str, Any]],
    videos: dict[str, dict[str, Any]],
) -> list[str]:
    fatal: list[str] = []
    explicit_ids = [
        video_id
        for spec in PLAYLIST_SPECS
        for video_id in spec["supplied_video_ids"]
    ]
    if len(explicit_ids) != EXPECTED_EXPLICIT_OCCURRENCES:
        fatal.append(
            f"Explicit source occurrence count is {len(explicit_ids)}, expected "
            f"{EXPECTED_EXPLICIT_OCCURRENCES}."
        )
    if len(set(explicit_ids)) != EXPECTED_UNIQUE_EXPLICIT_IDS:
        fatal.append(
            f"Unique explicit video count is {len(set(explicit_ids))}, expected "
            f"{EXPECTED_UNIQUE_EXPLICIT_IDS}."
        )
    modern = next(
        (
            playlist
            for playlist in playlists
            if playlist["playlist_id"] == MODERN_MARKETING_PLAYLIST_ID
        ),
        None,
    )
    if modern and len(modern["entries"]) != MODERN_MARKETING_EXPECTED_SIZE:
        log(
            f"QUALITY WARNING: Modern Marketing Minute has "
            f"{len(modern['entries'])} live entries; expected "
            f"{MODERN_MARKETING_EXPECTED_SIZE}."
        )
    if len({occurrence["video_id"] for occurrence in occurrences}) != len(videos):
        fatal.append("Unique occurrence count does not match processed video count.")
    seen_paths: dict[str, str] = {}
    for video_id, video in videos.items():
        path = video["relative_path"].casefold()
        if path in seen_paths:
            fatal.append(
                f"Videos {video_id} and {seen_paths[path]} share a transcript path."
            )
        seen_paths[path] = video_id
        if not video["path"].exists():
            fatal.append(f"Transcript page is missing: {video['relative_path']}")
        if video["transcript_status"] == "complete":
            if video.get("preserve_existing"):
                continue
            stats = video["stats"]
            if not stats["beginning_verified"] or not stats["ending_verified"]:
                fatal.append(f"Caption boundary verification failed for {video_id}.")
            if not video["cleaned_transcript"].strip():
                fatal.append(f"Completed transcript is empty for {video_id}.")
            if TIMESTAMP_RE.search(video["cleaned_transcript"]):
                fatal.append(f"Timestamp-like text remains in {video_id}.")
    forbidden_extensions = {
        ".vtt",
        ".srt",
        ".srv1",
        ".srv2",
        ".srv3",
        ".ttml",
        ".json3",
        ".mp4",
        ".mkv",
        ".webm",
        ".mp3",
        ".m4a",
        ".wav",
    }
    for path in repo_root.rglob("*"):
        if ".git" in path.parts or ".temp" in path.parts or not path.is_file():
            continue
        if path.suffix.casefold() in forbidden_extensions:
            fatal.append(f"Forbidden raw/media artifact exists: {path}")
    return fatal


def run_git_delivery(repo_root: Path) -> None:
    git = os.environ.get("GIT_EXECUTABLE") or shutil.which("git")
    if not git:
        raise RuntimeError(
            "Git executable not found. Set GIT_EXECUTABLE or rerun with --no-push."
        )
    intended = [
        ".gitignore",
        "README.md",
        "requirements.txt",
        "scripts/build_adam_erhart_transcripts.py",
        "data",
        "transcripts",
    ]
    subprocess.run([git, "add", "--", *intended], cwd=repo_root, check=True)
    diff = subprocess.run(
        [git, "diff", "--cached", "--quiet"], cwd=repo_root, check=False
    )
    if diff.returncode == 0:
        log("No staged changes; skipping commit and push.")
        return
    subprocess.run(
        [
            git,
            "commit",
            "-m",
            "Add private Adam Erhart transcript study library",
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run([git, "push"], cwd=repo_root, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Retrieve metadata and generate unavailable placeholders without captions.",
    )
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="Retry videos previously recorded as unavailable or failed.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting pages marked manually reviewed.",
    )
    parser.add_argument("--playlist", help="Process one playlist ID.")
    parser.add_argument("--video", help="Process one video ID.")
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Generate and validate files without committing or pushing.",
    )
    parser.add_argument(
        "--keep-temporary-captions",
        action="store_true",
        help="Keep subtitle-only fallback files in the gitignored .temp directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    transcripts_root = repo_root / "transcripts" / "adam-erhart"
    data_dir = repo_root / "data"
    temp_root = repo_root / ".temp" / "adam-erhart-captions"

    explicit_ids = [
        video_id
        for spec in PLAYLIST_SPECS
        for video_id in spec["supplied_video_ids"]
    ]
    if (
        len(explicit_ids) != EXPECTED_EXPLICIT_OCCURRENCES
        or len(set(explicit_ids)) != EXPECTED_UNIQUE_EXPLICIT_IDS
    ):
        raise RuntimeError(
            "The embedded source manifest does not match the required 54 explicit "
            "occurrences and 46 unique explicit video IDs."
        )

    playlists = create_playlist_records(args.playlist)
    occurrences, primary_by_id = build_occurrences(playlists)
    if args.video:
        if args.video not in primary_by_id:
            raise RuntimeError(
                f"Video {args.video} is not present in the selected source manifest."
            )
        occurrences = [
            occurrence
            for occurrence in occurrences
            if occurrence["video_id"] == args.video
        ]
        primary_by_id = {args.video: primary_by_id[args.video]}

    previous_quality, previous_status = read_previous_status(data_dir)
    retry_ids: set[str] | None = None
    if args.retry_failures:
        retry_ids = {
            video_id
            for video_id, row in previous_status.items()
            if row.get("transcript_status") != "complete"
            or row.get("metadata_status") != "success"
        }
        if not retry_ids:
            log("No previous failures were recorded; processing all selected videos.")
            retry_ids = None

    playlist_by_id = {
        playlist["playlist_id"]: playlist for playlist in playlists
    }
    title_hints: dict[str, str] = {}
    for occurrence in occurrences:
        if not occurrence["entry_title"].startswith("Video "):
            title_hints.setdefault(
                occurrence["video_id"], occurrence["entry_title"]
            )

    api = YouTubeTranscriptApi()
    videos: dict[str, dict[str, Any]] = {}
    total = len(primary_by_id)
    for index, (video_id, primary) in enumerate(primary_by_id.items(), start=1):
        log(f"[video {index}/{total}] {video_id}")
        metadata, metadata_status, metadata_error = fetch_video_metadata(video_id)
        title = (
            metadata.get("title")
            or title_hints.get(video_id)
            or f"Video {video_id}"
        )
        published = format_published(metadata)
        duration = format_duration(metadata.get("duration"))

        if args.metadata_only:
            caption = CaptionResult(
                caption_type="unavailable",
                language="unknown",
                status="unavailable",
                segments=[],
                source="metadata-only mode",
                error_type="MetadataOnly",
                error_message="Caption retrieval was skipped by --metadata-only.",
            )
        elif retry_ids is not None and video_id not in retry_ids:
            old = previous_status.get(video_id, {})
            caption = CaptionResult(
                caption_type=old.get("caption_type", "unavailable"),
                language=old.get("caption_language", "unknown"),
                status=old.get("caption_status", "unavailable"),
                segments=[],
                source="preserved previous result",
                error_type=old.get("error_type", ""),
                error_message=old.get("error_message", ""),
            )
        else:
            caption = retrieve_captions(
                api,
                video_id,
                metadata,
                temp_root,
                args.keep_temporary_captions,
            )

        preserve_existing = retry_ids is not None and video_id not in retry_ids
        if preserve_existing:
            stats = {
                "raw_segment_count": int(
                    previous_quality.get(video_id, {}).get(
                        "raw_segment_count", 0
                    )
                ),
                "raw_word_count": int(
                    previous_quality.get(video_id, {}).get("raw_word_count", 0)
                ),
                "cleaned_word_count": int(
                    previous_quality.get(video_id, {}).get(
                        "cleaned_word_count", 0
                    )
                ),
                "word_count_difference": int(
                    previous_quality.get(video_id, {}).get(
                        "word_count_difference", 0
                    )
                ),
                "percentage_difference": float(
                    previous_quality.get(video_id, {}).get(
                        "percentage_difference", 0
                    )
                ),
                "duplicate_fragments_removed": int(
                    previous_quality.get(video_id, {}).get(
                        "duplicate_fragments_removed", 0
                    )
                ),
                "unclear_markers_added": int(
                    previous_quality.get(video_id, {}).get(
                        "unclear_markers_added", 0
                    )
                ),
                "quality_warnings": previous_quality.get(video_id, {}).get(
                    "quality_warnings", []
                ),
                "beginning_verified": bool(
                    previous_quality.get(video_id, {}).get(
                        "beginning_verified", False
                    )
                ),
                "ending_verified": bool(
                    previous_quality.get(video_id, {}).get(
                        "ending_verified", False
                    )
                ),
            }
            transcript_status = previous_quality.get(video_id, {}).get(
                "status", "unavailable"
            )
            cleaned = ""
        elif caption.status == "success":
            cleaned, stats = clean_transcript(caption.segments)
            transcript_status = "complete" if cleaned else "failed"
            if not cleaned:
                caption.status = "failed"
                caption.error_type = "EmptyCleanedTranscript"
                caption.error_message = "Caption cleaning produced no transcript text."
        else:
            stats = {
                "raw_segment_count": 0,
                "raw_word_count": 0,
                "cleaned_word_count": 0,
                "word_count_difference": 0,
                "percentage_difference": 0.0,
                "duplicate_fragments_removed": 0,
                "unclear_markers_added": 0,
                "quality_warnings": [],
                "beginning_verified": False,
                "ending_verified": False,
            }
            transcript_status = (
                "unavailable" if caption.status == "unavailable" else "failed"
            )
            cleaned = ""

        path = transcript_path_for(
            transcripts_root, primary, playlist_by_id, title
        )
        videos[video_id] = {
            "video_id": video_id,
            "title": title,
            "metadata": metadata,
            "metadata_status": metadata_status,
            "metadata_error": metadata_error,
            "published": published,
            "duration": duration,
            "caption": caption,
            "cleaned_transcript": cleaned,
            "transcript_status": transcript_status,
            "stats": stats,
            "primary": primary,
            "path": path,
            "relative_path": path.relative_to(repo_root).as_posix(),
            "preserve_existing": preserve_existing,
        }
        log(
            f"  {transcript_status}: {caption.caption_type} "
            f"{stats['cleaned_word_count']} words"
        )

    primary_by_playlist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for video in videos.values():
        primary_by_playlist[video["primary"]["playlist_id"]].append(video)
    for items in primary_by_playlist.values():
        items.sort(key=lambda item: int(item["primary"]["playlist_position"]))
        for index, video in enumerate(items):
            if video.get("preserve_existing") and video["path"].exists():
                migrate_transcript_front_matter(video["path"])
                reflow_existing_transcript(video["path"])
                continue
            previous_path = items[index - 1]["path"] if index > 0 else None
            next_path = items[index + 1]["path"] if index + 1 < len(items) else None
            playlist_readme = video["path"].parent / "README.md"
            content = build_video_page(
                video, previous_path, next_path, playlist_readme
            )
            write_transcript_page(video["path"], content, args.force)

    duplicates = make_duplicates(occurrences, videos)
    processing_rows = build_processing_rows(occurrences, videos)
    write_processing_csv(data_dir / "processing-status.csv", processing_rows)
    (data_dir / "duplicates.json").parent.mkdir(parents=True, exist_ok=True)
    (data_dir / "duplicates.json").write_text(
        json.dumps(duplicates, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "transcript-quality.json").write_text(
        json.dumps(quality_records(videos), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "source-manifest.json").write_text(
        json.dumps(
            build_manifest(playlists, occurrences, videos, duplicates),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    for playlist in playlists:
        readme_path = transcripts_root / playlist["folder"] / "README.md"
        selected = [
            occurrence
            for occurrence in occurrences
            if occurrence["playlist_id"] == playlist["playlist_id"]
        ]
        content = build_playlist_readme(
            playlist, selected, videos, readme_path
        )
        replace_managed_block(
            readme_path, content, MANAGED_BEGIN, MANAGED_END
        )

    central_path = transcripts_root / "README.md"
    central_content = build_central_readme(
        playlists, occurrences, videos, central_path, data_dir
    )
    replace_managed_block(
        central_path, central_content, MANAGED_BEGIN, MANAGED_END
    )
    root_readme = repo_root / "README.md"
    root_content = build_root_section(
        playlists, occurrences, videos, root_readme, central_path
    )
    replace_managed_block(
        root_readme, root_content, ROOT_BEGIN, ROOT_END
    )

    fatal = validate_library(
        repo_root, playlists, occurrences, videos
    )
    if fatal:
        log("QUALITY CONTROL FAILED:")
        for item in fatal:
            log(f"  - {item}")
        return 2

    counts = summary_counts(occurrences, videos)
    log("QUALITY CONTROL PASSED")
    log(json.dumps(counts, indent=2))
    if not args.keep_temporary_captions and temp_root.exists():
        try:
            temp_root.rmdir()
            temp_root.parent.rmdir()
        except OSError:
            pass
    if not args.no_push:
        run_git_delivery(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
