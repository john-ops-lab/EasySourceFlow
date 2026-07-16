"""Video metadata extraction through yt-dlp."""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
import hashlib
import tempfile
import time
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from easysourceflow_core.config import Settings, effective_bilibili_cookies_file, effective_youtube_cookies_file
from easysourceflow_core.asr_quality import describe_transcript_quality
from easysourceflow_core.errors import dependency_missing, extraction_error, extraction_failed, need_cookies
from easysourceflow_core.models import SourceDocument
from easysourceflow_core.url_utils import detect_source_type, normalize_url


ProgressCallback = Callable[[str, float], None]
logger = logging.getLogger(__name__)

_BILIBILI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_BILIBILI_DM_WBI_PARAMS = {
    "dm_img_list": "[]",
    "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
    "dm_cover_img_str": "QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgUlRYIDQwNjAgTGFwdG9wIEdQVSAoMHgwMDAwMjhFMCkgRGlyZWN0M0QxMSB2c181XzAgcHNfNV8wLCBEM0QxMSlHb29nbGUgSW5jLiAoTlZJRElBKQ",
    "dm_img_inter": '{"ds":[],"wh":[5231,6067,75],"of":[475,950,475]}',
}
_TRANSCRIPT_TIME_PATTERN = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?"
_TRANSCRIPT_RANGE_RE = re.compile(
    rf"^\[(?P<start>{_TRANSCRIPT_TIME_PATTERN})\s*(?:-|-->)\s*(?P<end>{_TRANSCRIPT_TIME_PATTERN})\]"
)


def extract_video_document(
    url: str,
    settings: Settings,
    progress_callback: Optional[ProgressCallback] = None,
) -> SourceDocument:
    canonical_url = normalize_url(url, settings.allow_local_urls, settings.trusted_fake_ip_cidrs)
    ytdlp = _find_ytdlp(settings)
    source_type = detect_source_type(canonical_url)
    _progress(progress_callback, "metadata", 0.20)
    data = _dump_metadata(ytdlp, canonical_url, source_type, settings)

    title = str(data.get("title") or canonical_url)
    uploader = data.get("uploader") or data.get("channel")
    content_text = _metadata_to_text(data, canonical_url)
    base_content_text = content_text
    extraction_method = "yt_dlp_metadata"
    transcript: Optional[str] = None
    subtitle_status = "not_attempted"
    subtitle_vtt = ""
    subtitle_source = ""
    subtitle_language = ""
    subtitle_rejections = ""
    subtitle_provenance: Dict[str, Any] = {}

    _progress(progress_callback, "subtitle", 0.35)
    subtitle_result = _extract_ytdlp_subtitle(ytdlp, canonical_url, source_type, settings, data)
    platform_transcript = subtitle_result.get("transcript") or None
    platform_subtitle_vtt = subtitle_result.get("subtitle_vtt", "")
    subtitle_status = subtitle_result.get("status", "unavailable")
    if platform_transcript:
        platform_validation = _validate_transcript_timing(
            platform_transcript,
            _metadata_duration_seconds(data),
            require_timestamps=True,
        )
        if platform_validation["valid"] and not _is_low_value_subtitle(platform_transcript):
            transcript = platform_transcript
            subtitle_vtt = platform_subtitle_vtt
            subtitle_source = subtitle_result.get("source", "yt_dlp_subtitle")
            subtitle_language = subtitle_result.get("language", "")
            content_text = _content_with_transcript(base_content_text, transcript)
            extraction_method = "yt_dlp_metadata_platform_subtitle"
        else:
            subtitle_rejections = f"yt_dlp:{platform_validation['reason']}"
            subtitle_status = f"{subtitle_status}_invalid"

    if source_type == "bilibili":
        bilibili_subtitle = _extract_bilibili_subtitle(canonical_url, settings, data)
        if bilibili_subtitle.get("transcript"):
            bilibili_transcript = bilibili_subtitle["transcript"]
            if _platform_transcript_is_usable(bilibili_transcript, data):
                transcript = bilibili_transcript
                subtitle_vtt = bilibili_subtitle.get("subtitle_vtt", "")
                subtitle_status = "bilibili_subtitle"
                subtitle_source = bilibili_subtitle.get("source", "")
                subtitle_language = bilibili_subtitle.get("language", "")
                subtitle_rejections = bilibili_subtitle.get("rejections", "")
                subtitle_provenance = bilibili_subtitle.get("provenance", {})
                content_text = _content_with_transcript(base_content_text, transcript)
                extraction_method = "yt_dlp_metadata_bilibili_subtitle"
            else:
                logger.warning(
                    "bilibili subtitle rejected by timing validation title=%s status=%s",
                    title,
                    bilibili_subtitle.get("status"),
                )
                if not transcript:
                    subtitle_status = "bilibili_subtitle_mismatch"
                    subtitle_source = bilibili_subtitle.get("source", "")
                    subtitle_language = bilibili_subtitle.get("language", "")
                    subtitle_rejections = bilibili_subtitle.get("rejections", "")
        elif not transcript and bilibili_subtitle.get("status") not in {"", "subtitle_unavailable"}:
            subtitle_status = bilibili_subtitle.get("status", "subtitle_unavailable")
            subtitle_source = bilibili_subtitle.get("source", "")
            subtitle_language = bilibili_subtitle.get("language", "")
            subtitle_rejections = bilibili_subtitle.get("rejections", "")

    if not transcript:
        _progress(progress_callback, "audio_download", 0.45)
        transcription = _transcribe_video_audio(
            ytdlp,
            canonical_url,
            source_type,
            settings,
            data,
            progress_callback,
        )
        transcript = transcription.get("transcript") or None
        if transcript:
            asr_validation = _validate_transcript_timing(
                transcript,
                _metadata_duration_seconds(data),
                require_timestamps=False,
            )
            if asr_validation["valid"]:
                subtitle_vtt = transcription.get("subtitle_vtt", "")
                content_text = _content_with_transcript(base_content_text, transcript)
                extraction_method = "yt_dlp_metadata_whisper_transcription"
                subtitle_status = transcription.get("status", "transcribed")
                subtitle_source = transcription.get("source", "audio_transcription")
                subtitle_language = transcription.get("language", "")
            else:
                subtitle_rejections = _append_rejection(
                    subtitle_rejections,
                    f"local_asr:{asr_validation['reason']}",
                )
                transcript = None
                subtitle_status = "transcription_invalid"
        else:
            subtitle_status = _combine_status(subtitle_status, transcription.get("status", "transcription_unavailable"))

    if not transcript:
        raise extraction_error(
            "transcript_unavailable",
            "No trustworthy subtitle or local transcription was available for this video.",
            [
                "Confirm the video is playable and the platform login state is available.",
                "Install and configure a local ASR backend, then retry with force refresh.",
                "Do not summarize video metadata as if it were the spoken content.",
            ],
        )

    transcript_with_timestamps = transcript or ""
    plain_transcript = _plain_transcript(transcript_with_timestamps)
    transcript_origin = _transcript_origin(extraction_method, subtitle_status, bool(transcript))
    transcript_quality = describe_transcript_quality(
        transcript_with_timestamps,
        _optional_float(data.get("duration")),
        transcript_origin["origin"],
    )
    transcript_validation = _validate_transcript_timing(
        transcript_with_timestamps,
        _optional_float(data.get("duration")) or 0.0,
        require_timestamps=transcript_origin["origin"] == "platform_subtitle",
    )
    if subtitle_provenance.get("duration_ratio") is not None:
        transcript_quality["duration_coverage"] = subtitle_provenance["duration_ratio"]
        transcript_quality["last_timestamp_seconds"] = subtitle_provenance["subtitle_end_seconds"]
        transcript_validation["duration_ratio"] = subtitle_provenance["duration_ratio"]
        transcript_validation["last_timestamp_seconds"] = subtitle_provenance["subtitle_end_seconds"]
    return SourceDocument(
        source_url=url,
        canonical_url=canonical_url,
        source_type=source_type,
        title=title,
        author=str(uploader) if uploader else None,
        published_at=str(data.get("upload_date") or "") or None,
        language=str(data.get("language") or "") or None,
        content_text=content_text,
        content_markdown=content_text,
        metadata={
            "duration": str(data.get("duration") or ""),
            "extractor": str(data.get("extractor") or ""),
            "webpage_url": str(data.get("webpage_url") or canonical_url),
            "transcript_has_timestamps": str(bool(transcript and "[" in transcript[:40])),
            "subtitle_status": subtitle_status,
            "subtitle_source": subtitle_source,
            "subtitle_language": subtitle_language,
            "subtitle_rejections": subtitle_rejections,
            "subtitle_provenance": subtitle_provenance,
            "transcript_origin": transcript_origin["origin"],
            "transcript_origin_label": transcript_origin["label"],
            "transcript_quality": transcript_quality,
            "transcript_validation": transcript_validation,
            "subtitle_vtt": subtitle_vtt,
            "transcript_text": plain_transcript,
            "transcript_with_timestamps": transcript_with_timestamps,
            "raw_metadata": _compact_raw_metadata(data),
        },
        extraction_method=extraction_method,
    )


def _transcript_origin(extraction_method: str, subtitle_status: str, has_transcript: bool) -> Dict[str, str]:
    if not has_transcript:
        return {"origin": "none", "label": "未获取可用字幕或转写"}
    if extraction_method == "yt_dlp_metadata_whisper_transcription" or subtitle_status.startswith("transcribed"):
        return {"origin": "local_asr", "label": "本地 ASR 转写"}
    if extraction_method in {"yt_dlp_metadata_platform_subtitle", "yt_dlp_metadata_bilibili_subtitle"}:
        return {"origin": "platform_subtitle", "label": "原始字幕"}
    return {"origin": "unknown", "label": "未知字幕来源"}


def _optional_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_ytdlp(settings: Settings) -> str:
    candidates = []
    if settings.ytdlp_path:
        candidates.append(settings.ytdlp_path)
    which = shutil.which("yt-dlp")
    if which:
        candidates.append(which)

    project_root = Path(__file__).resolve().parents[3]
    candidates.append(str(project_root / ".venv" / "bin" / "yt-dlp"))

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise dependency_missing("yt-dlp is required for Bilibili and YouTube links.")


def _dump_metadata(ytdlp: str, url: str, source_type: str, settings: Settings) -> Dict[str, Any]:
    command = [
        ytdlp,
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--no-playlist",
    ]
    bilibili_cookies_file = effective_bilibili_cookies_file(settings)
    if source_type == "bilibili":
        command.extend(
            [
                "--user-agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "--add-header",
                "Referer:https://www.bilibili.com/",
            ]
        )
        if bilibili_cookies_file:
            cookies_file = Path(bilibili_cookies_file).expanduser()
            if not cookies_file.exists():
                raise need_cookies(f"Configured Bilibili cookies file does not exist: {cookies_file}")
            command.extend(["--cookies", str(cookies_file)])
    _add_youtube_auth_args(command, source_type, settings)
    command.append(url)

    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(30, int(settings.request_timeout_seconds) + 30),
        )
    except subprocess.TimeoutExpired as exc:
        raise extraction_failed("yt-dlp timed out while reading video metadata.") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
        message = detail[0] if detail else "yt-dlp could not read video metadata."
        if source_type == "bilibili" and ("HTTP Error 412" in message or "Precondition Failed" in message):
            raise need_cookies("Bilibili rejected the metadata request with HTTP 412.")
        if source_type == "youtube":
            status = _youtube_failure_status(message)
            if status == "youtube_auth_required":
                raise extraction_error(
                    status,
                    message,
                    [
                        "Sign in to YouTube in Chrome and import the login state from Web maintenance.",
                        "Retry after confirming the video is accessible in the same account.",
                    ],
                )
            if status == "youtube_po_token_required":
                raise extraction_error(
                    status,
                    message,
                    [
                        "Update yt-dlp and retry with the imported YouTube login state.",
                        "If yt-dlp still requires a PO Token, configure a supported PO Token provider or EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS.",
                    ],
                )
            if status == "youtube_rate_limited":
                raise extraction_error(
                    status,
                    message,
                    ["Wait before retrying and avoid submitting the same video repeatedly."],
                )
        if "login" in message.lower() or "cookies" in message.lower():
            raise need_cookies(message)
        raise extraction_failed(message)

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise extraction_failed("yt-dlp returned invalid metadata JSON.") from exc


def _metadata_to_text(data: Dict[str, Any], canonical_url: str) -> str:
    lines: List[str] = []
    lines.append(f"Title: {data.get('title') or canonical_url}")
    if data.get("uploader") or data.get("channel"):
        lines.append(f"Author: {data.get('uploader') or data.get('channel')}")
    if data.get("duration_string"):
        lines.append(f"Duration: {data.get('duration_string')}")
    elif data.get("duration"):
        lines.append(f"Duration seconds: {data.get('duration')}")
    if data.get("description"):
        lines.append(f"Description: {data.get('description')}")
    if data.get("tags"):
        tags = ", ".join(str(tag) for tag in data.get("tags")[:20])
        lines.append(f"Tags: {tags}")

    subtitles = data.get("subtitles") or {}
    automatic_captions = data.get("automatic_captions") or {}
    if subtitles:
        lines.append(f"Available subtitles: {', '.join(sorted(subtitles.keys()))}")
    if automatic_captions:
        lines.append(f"Available automatic captions: {', '.join(sorted(automatic_captions.keys())[:10])}")
    if not subtitles and not automatic_captions:
        lines.append("Transcript: No public subtitles were found by yt-dlp in this M2-lite extractor.")

    return "\n\n".join(line for line in lines if line)


def _content_with_transcript(content_text: str, transcript: str) -> str:
    cleaned = content_text.replace(
        "\n\nTranscript: No public subtitles were found by yt-dlp in this M2-lite extractor.",
        "",
    )
    return f"{cleaned}\n\nTranscript:\n\n{transcript}"


def _transcribe_video_audio(
    ytdlp: str,
    url: str,
    source_type: str,
    settings: Settings,
    metadata: Dict[str, Any],
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    duration = metadata.get("duration")
    if duration and float(duration) > settings.max_transcription_seconds:
        return {"transcript": "", "status": "transcription_skipped_too_long"}
    ffmpeg = shutil.which(settings.ffmpeg_path) or settings.ffmpeg_path
    if not ffmpeg:
        return {"transcript": "", "status": "dependency_missing_ffmpeg"}

    downloads_dir = settings.data_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="transcribe-", dir=str(downloads_dir)) as tmpdir:
        tmp = Path(tmpdir)
        audio_prefix = tmp / "audio"
        command = [
            ytdlp,
            "--no-warnings",
            "--no-playlist",
            "-f",
            "ba/best",
            "-x",
            "--audio-format",
            "wav",
            "--ffmpeg-location",
            str(Path(ffmpeg).parent) if Path(ffmpeg).exists() else ffmpeg,
            "-o",
            str(audio_prefix) + ".%(ext)s",
        ]
        bilibili_cookies_file = effective_bilibili_cookies_file(settings)
        if source_type == "bilibili" and bilibili_cookies_file:
            command.extend(["--cookies", str(Path(bilibili_cookies_file).expanduser())])
        _add_youtube_auth_args(command, source_type, settings)
        command.append(url)

        download = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(120, int(float(duration or 60) * 3)),
        )
        if download.returncode != 0:
            status = _youtube_failure_status(f"{download.stdout}\n{download.stderr}") if source_type == "youtube" else ""
            return {"transcript": "", "status": status or "audio_download_failed"}
        wav_files = list(tmp.glob("audio*.wav"))
        if not wav_files:
            return {"transcript": "", "status": "audio_download_failed"}

        _progress(progress_callback, "transcribing", 0.55)
        language_hint = "zh" if source_type == "bilibili" else "auto"
        return _transcribe_audio_file(wav_files[0], tmp, settings, duration, language_hint)


def _extract_ytdlp_subtitle(
    ytdlp: str,
    url: str,
    source_type: str,
    settings: Settings,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    if source_type == "youtube":
        return _extract_youtube_subtitle(ytdlp, url, settings, metadata or {})
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="subtitle-", dir=str(settings.data_dir)) as tmpdir:
        manual = _download_subtitle_once(
            ytdlp=ytdlp,
            url=url,
            source_type=source_type,
            settings=settings,
            tmpdir=tmpdir,
            auto=False,
        )
        status = manual
        candidates = sorted(Path(tmpdir).glob("subtitle*"), key=_subtitle_priority)
        transcript = _first_subtitle_transcript(candidates)
        if transcript:
            return {"transcript": transcript, "status": "manual_subtitle", "subtitle_vtt": _read_first_subtitle(candidates)}

        auto = _download_subtitle_once(
            ytdlp=ytdlp,
            url=url,
            source_type=source_type,
            settings=settings,
            tmpdir=tmpdir,
            auto=True,
            languages="zh,en",
        )
        if "po_token_missing" in {manual, auto}:
            status = "po_token_missing"
        else:
            status = auto
        candidates = sorted(Path(tmpdir).glob("subtitle*"), key=_subtitle_priority)
        transcript = _first_subtitle_transcript(candidates)
        if transcript:
            return {"transcript": transcript, "status": "auto_subtitle", "subtitle_vtt": _read_first_subtitle(candidates)}
        fallback = _download_subtitle_once(
            ytdlp=ytdlp,
            url=url,
            source_type=source_type,
            settings=settings,
            tmpdir=tmpdir,
            auto=True,
            languages="all,-live_chat",
        )
        if "po_token_missing" in {status, fallback}:
            status = "po_token_missing"
        else:
            status = fallback
        candidates = sorted(Path(tmpdir).glob("subtitle*"), key=_subtitle_priority)
        transcript = _first_subtitle_transcript(candidates)
        if transcript:
            return {"transcript": transcript, "status": "auto_subtitle_fallback_language", "subtitle_vtt": _read_first_subtitle(candidates)}
    return {"transcript": "", "status": status or "subtitle_unavailable", "subtitle_vtt": ""}


def _extract_youtube_subtitle(
    ytdlp: str,
    url: str,
    settings: Settings,
    metadata: Dict[str, Any],
) -> Dict[str, str]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    statuses: List[str] = []
    attempts = [
        (False, _youtube_subtitle_languages(metadata, auto=False), "youtube_manual", "youtube_manual_subtitle"),
        (True, _youtube_subtitle_languages(metadata, auto=True), "youtube_auto", "youtube_auto_subtitle"),
    ]
    with tempfile.TemporaryDirectory(prefix="youtube-subtitle-", dir=str(settings.data_dir)) as tmpdir:
        for auto, languages, output_name, source in attempts:
            if not languages:
                continue
            status = _download_subtitle_once(
                ytdlp=ytdlp,
                url=url,
                source_type="youtube",
                settings=settings,
                tmpdir=tmpdir,
                auto=auto,
                languages=",".join(languages),
                output_name=output_name,
            )
            statuses.append(status)
            result = _youtube_subtitle_result(Path(tmpdir), output_name, languages, source)
            if result:
                return result
    return {
        "transcript": "",
        "status": _most_actionable_youtube_status(statuses),
        "subtitle_vtt": "",
        "source": "yt_dlp",
        "language": "",
    }


def _youtube_subtitle_languages(metadata: Dict[str, Any], auto: bool) -> List[str]:
    available = metadata.get("automatic_captions" if auto else "subtitles") or {}
    keys = [str(key) for key in available.keys() if key and key != "live_chat"]
    if not keys:
        if _metadata_advertises_subtitles(metadata):
            return []
        return ["en-orig", "en", "zh-Hans", "zh-Hant", "zh"] if auto else ["zh-Hans", "zh-Hant", "zh", "en"]

    video_language = str(metadata.get("language") or "").strip()
    chinese = [key for key in keys if key.lower().startswith(("zh", "cmn", "yue"))]
    original = [key for key in keys if key.lower().endswith("-orig")]
    same_language = [
        key for key in keys
        if video_language and (key.lower() == video_language.lower() or key.lower().startswith(video_language.lower() + "-"))
    ]
    english = [key for key in keys if key.lower() in {"en", "en-orig"}]
    if auto:
        groups = [original, same_language, english, chinese, keys]
        limit = 8
    else:
        groups = [chinese, same_language, english, original, keys]
        limit = 16
    ranked: List[str] = []
    for group in groups:
        for key in group:
            if key not in ranked:
                ranked.append(key)
            if len(ranked) >= limit:
                return ranked
    return ranked


def _youtube_subtitle_result(
    directory: Path,
    output_name: str,
    languages: List[str],
    source: str,
) -> Optional[Dict[str, str]]:
    candidates = [path for path in directory.glob(f"{output_name}.*") if path.suffix.lower() in {".vtt", ".srt"}]
    ranked = sorted(candidates, key=lambda path: _youtube_subtitle_path_priority(path, output_name, languages))
    for candidate in ranked:
        raw = candidate.read_text(encoding="utf-8", errors="replace")
        transcript = _parse_srt(raw) if candidate.suffix.lower() == ".srt" else _parse_vtt(raw)
        if not transcript or _is_low_value_subtitle(transcript):
            continue
        language = _youtube_subtitle_language(candidate, output_name)
        return {
            "transcript": transcript,
            "status": source,
            "subtitle_vtt": _srt_to_vtt(raw) if candidate.suffix.lower() == ".srt" else raw.strip(),
            "source": source,
            "language": language,
        }
    return None


def _youtube_subtitle_path_priority(path: Path, output_name: str, languages: List[str]) -> tuple[int, str]:
    language = _youtube_subtitle_language(path, output_name)
    try:
        index = languages.index(language)
    except ValueError:
        index = len(languages)
    return index, path.name


def _youtube_subtitle_language(path: Path, output_name: str) -> str:
    prefix = output_name + "."
    name = path.name
    if name.startswith(prefix):
        return name[len(prefix) : -len(path.suffix)]
    return ""


def _most_actionable_youtube_status(statuses: List[str]) -> str:
    for status in [
        "youtube_auth_required",
        "youtube_po_token_required",
        "youtube_rate_limited",
        "subtitle_download_failed",
        "no_requested_language_subtitles",
    ]:
        if status in statuses:
            return status
    return next((status for status in statuses if status), "subtitle_unavailable")


def _extract_bilibili_subtitle(
    url: str,
    settings: Settings,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bvid = _extract_bvid(url)
    if not bvid:
        return {"transcript": "", "subtitle_vtt": "", "status": "subtitle_unavailable"}
    opener = _build_bilibili_opener(settings)
    wbi_keys = _bilibili_wbi_keys(opener)
    view_sources = []
    if wbi_keys:
        view_sources.append(
            _bilibili_wbi_url("https://api.bilibili.com/x/web-interface/wbi/view", {"bvid": bvid}, wbi_keys)
        )
    view_sources.append(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")

    view: Dict[str, Any] = {}
    for view_url in view_sources:
        view = _bilibili_json(opener, view_url)
        if not view.get("__fetch_error") and view.get("data"):
            break
    if view.get("__fetch_error") or not view.get("data"):
        return {"transcript": "", "subtitle_vtt": "", "status": "bilibili_view_api_failed"}
    view_data = view.get("data") or {}
    aid = view_data.get("aid")
    resolved_bvid = str(view_data.get("bvid") or bvid)
    if resolved_bvid.lower() != bvid.lower():
        return {
            "transcript": "",
            "subtitle_vtt": "",
            "status": "bilibili_video_identity_mismatch",
        }
    pages = view_data.get("pages") or []
    page_index = _bilibili_page_index(url)
    if page_index < 0 or page_index >= len(pages):
        return {"transcript": "", "subtitle_vtt": "", "status": "bilibili_page_not_found"}
    page = pages[page_index]
    cid = page.get("cid")
    if not cid:
        return {"transcript": "", "subtitle_vtt": "", "status": "subtitle_unavailable"}
    video_duration = _optional_float(page.get("duration")) or _metadata_duration_seconds(metadata or {})

    if not wbi_keys:
        return {
            "transcript": "",
            "subtitle_vtt": "",
            "status": "bilibili_wbi_unavailable",
            "source": "bilibili_wbi_player_v2",
        }

    seen_urls = set()
    saw_invalid = False
    saw_low_value = False
    saw_player_error = False
    subtitle_api_failed = False
    rejections: List[str] = []
    player_sources = [
        (
            "bilibili_wbi_player_v2",
            _bilibili_wbi_url(
                "https://api.bilibili.com/x/player/wbi/v2",
                {"bvid": bvid, "cid": cid, **_BILIBILI_DM_WBI_PARAMS},
                wbi_keys,
            ),
        )
    ]

    for source, player_url in player_sources:
        for attempt in range(3):
            player = _bilibili_json(opener, player_url)
            if player.get("__fetch_error"):
                saw_player_error = True
                if attempt < 2:
                    time.sleep(0.35)
                continue

            subtitle_items = (((player.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
            if not subtitle_items:
                break
            for item in sorted(subtitle_items, key=_bilibili_subtitle_item_priority):
                subtitle_url = item.get("subtitle_url")
                if not subtitle_url:
                    continue
                if subtitle_url.startswith("//"):
                    subtitle_url = "https:" + subtitle_url
                if subtitle_url in seen_urls:
                    continue
                seen_urls.add(subtitle_url)

                language = str(item.get("lan_doc") or item.get("lan") or "")
                subtitle_payload = _bilibili_json(opener, subtitle_url)
                if subtitle_payload.get("__fetch_error"):
                    subtitle_api_failed = True
                    rejections.append(f"{source}:{language or 'unknown'}:api_failed")
                    continue
                payload_validation = _validate_bilibili_payload_timing(subtitle_payload, video_duration)
                if not payload_validation["valid"]:
                    saw_invalid = True
                    rejections.append(
                        f"{source}:{language or 'unknown'}:{payload_validation['reason']}"
                    )
                    continue
                candidate = _bilibili_subtitle_payload_to_result(subtitle_payload)
                candidate["source"] = source
                candidate["language"] = language
                candidate["rejections"] = ";".join(rejections)
                transcript = candidate.get("transcript", "")
                if not transcript or _is_low_value_subtitle(transcript):
                    saw_low_value = True
                    rejections.append(f"{source}:{language or 'unknown'}:low_value")
                    continue
                validation = _validate_transcript_timing(
                    transcript,
                    video_duration,
                    require_timestamps=True,
                )
                if not validation["valid"]:
                    saw_invalid = True
                    rejections.append(f"{source}:{language or 'unknown'}:{validation['reason']}")
                    continue
                candidate["rejections"] = ";".join(rejections)
                candidate["provenance"] = {
                    "bvid": bvid,
                    "aid": aid,
                    "cid": cid,
                    "page": page_index + 1,
                    "video_duration_seconds": round(video_duration, 3) if video_duration else None,
                    "subtitle_id": str(item.get("id") or item.get("id_str") or ""),
                    "language": language,
                    "ai_type": item.get("ai_type"),
                    "subtitle_end_seconds": payload_validation["last_timestamp_seconds"],
                    "duration_ratio": payload_validation["duration_ratio"],
                    "content_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
                    "subtitle_url_sha256": hashlib.sha256(
                        urllib.parse.urlsplit(subtitle_url)._replace(query="", fragment="").geturl().encode("utf-8")
                    ).hexdigest(),
                }
                return candidate

            if attempt < 2:
                time.sleep(0.35)

    source_text = ",".join(source for source, _ in player_sources)
    rejection_text = ";".join(rejections)
    if saw_invalid:
        status = "bilibili_subtitle_invalid"
    elif saw_low_value:
        status = "bilibili_subtitle_low_value"
    elif subtitle_api_failed:
        status = "bilibili_subtitle_api_failed"
    elif saw_player_error:
        status = "bilibili_player_api_failed"
    else:
        status = "subtitle_unavailable"
    return {"transcript": "", "subtitle_vtt": "", "status": status, "source": source_text, "rejections": rejection_text}


def _bilibili_wbi_keys(opener: urllib.request.OpenerDirector) -> Optional[tuple[str, str]]:
    nav = _bilibili_json(opener, "https://api.bilibili.com/x/web-interface/nav")
    if nav.get("__fetch_error"):
        return None
    wbi_img = ((nav.get("data") or {}).get("wbi_img") or {})
    img_key = Path(urllib.parse.urlparse(str(wbi_img.get("img_url") or "")).path).stem
    sub_key = Path(urllib.parse.urlparse(str(wbi_img.get("sub_url") or "")).path).stem
    if len(img_key + sub_key) < max(_BILIBILI_MIXIN_KEY_ENC_TAB) + 1:
        return None
    return img_key, sub_key


def _bilibili_wbi_url(endpoint: str, params: Dict[str, Any], keys: tuple[str, str]) -> str:
    return endpoint + "?" + _bilibili_wbi_query(params, keys)


def _bilibili_wbi_query(params: Dict[str, Any], keys: tuple[str, str]) -> str:
    img_key, sub_key = keys
    raw_key = img_key + sub_key
    mixin_key = "".join(raw_key[index] for index in _BILIBILI_MIXIN_KEY_ENC_TAB)[:32]
    signed_params = {key: str(value) for key, value in params.items()}
    signed_params["wts"] = str(round(time.time()))
    filtered_params = {}
    for key, value in sorted(signed_params.items()):
        filtered_params[key] = re.sub(r"[!'()*]", "", value)
    query = urllib.parse.urlencode(filtered_params)
    filtered_params["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return urllib.parse.urlencode(filtered_params)


def _bilibili_page_index(url: str) -> int:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    try:
        page_number = int((query.get("p") or ["1"])[0])
        return page_number - 1 if page_number >= 1 else -1
    except (TypeError, ValueError):
        return -1


def _bilibili_subtitle_item_priority(item: Dict[str, Any]) -> tuple[int, str]:
    language = str(item.get("lan") or item.get("lan_doc") or "").lower()
    chinese = language.startswith(("zh", "cmn", "yue")) or "中文" in language
    try:
        automatic = int(item.get("ai_type") or 0) != 0
    except (TypeError, ValueError):
        automatic = bool(item.get("ai_type"))
    if chinese and not automatic:
        rank = 0
    elif chinese:
        rank = 1
    elif not automatic:
        rank = 2
    else:
        rank = 3
    return rank, language


def _bilibili_subtitle_payload_to_result(subtitle_payload: Dict[str, Any]) -> Dict[str, str]:
    body = subtitle_payload.get("body") or []
    lines = []
    vtt_segments = []
    for entry in body:
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        start = _format_seconds(entry.get("from"))
        end = _format_seconds(entry.get("to"), round_up=True)
        prefix = f"[{start}-{end}] " if start and end else ""
        lines.append(prefix + content)
        if start and end:
            vtt_segments.append((entry.get("from"), entry.get("to"), content))
    transcript = "\n".join(line for line in lines if line)
    return {
        "transcript": transcript,
        "subtitle_vtt": _segments_to_vtt(vtt_segments),
        "status": "bilibili_subtitle",
    }


def _validate_bilibili_payload_timing(subtitle_payload: Dict[str, Any], duration_seconds: float) -> Dict[str, Any]:
    timestamp_count = 0
    previous_start = -1.0
    last_end = 0.0
    for entry in subtitle_payload.get("body") or []:
        if not str(entry.get("content") or "").strip():
            continue
        try:
            start = float(entry.get("from"))
            end = float(entry.get("to"))
        except (TypeError, ValueError):
            return _bilibili_payload_timing_report(
                "invalid_timestamp_range", timestamp_count, last_end, duration_seconds
            )
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            return _bilibili_payload_timing_report(
                "invalid_timestamp_range", timestamp_count, last_end, duration_seconds
            )
        if start < previous_start:
            return _bilibili_payload_timing_report(
                "timestamps_not_monotonic", timestamp_count, last_end, duration_seconds
            )
        timestamp_count += 1
        previous_start = start
        last_end = max(last_end, end)

    if timestamp_count == 0:
        reason = "timestamps_missing"
    else:
        duration = max(0.0, float(duration_seconds or 0.0))
        tolerance = max(5.0, duration * 0.03) if duration else 0.0
        if duration and last_end > duration + tolerance:
            reason = "duration_exceeded"
        elif duration >= 300 and last_end < min(180.0, duration * 0.15):
            reason = "insufficient_coverage"
        else:
            reason = "ok"
    return _bilibili_payload_timing_report(reason, timestamp_count, last_end, duration_seconds)


def _bilibili_payload_timing_report(
    reason: str,
    timestamp_count: int,
    last_end: float,
    duration_seconds: float,
) -> Dict[str, Any]:
    duration = max(0.0, float(duration_seconds or 0.0))
    ratio = last_end / duration if duration and timestamp_count else None
    return {
        "valid": reason == "ok",
        "reason": reason,
        "timestamp_count": timestamp_count,
        "last_timestamp_seconds": round(last_end, 3) if timestamp_count else None,
        "duration_ratio": round(ratio, 4) if ratio is not None else None,
    }


def _extract_bvid(url: str) -> Optional[str]:
    match = re.search(r"/video/(BV[A-Za-z0-9]+)", url)
    return match.group(1) if match else None


def _build_bilibili_opener(settings: Settings) -> urllib.request.OpenerDirector:
    handlers = []
    bilibili_cookies_file = effective_bilibili_cookies_file(settings)
    if bilibili_cookies_file:
        cookies_file = Path(bilibili_cookies_file).expanduser()
        if cookies_file.exists():
            jar = http.cookiejar.MozillaCookieJar(str(cookies_file))
            jar.load(ignore_discard=True, ignore_expires=True)
            handlers.append(urllib.request.HTTPCookieProcessor(jar))
    return urllib.request.build_opener(*handlers)


def _bilibili_json(opener: urllib.request.OpenerDirector, url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        },
    )
    try:
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("bilibili api request failed url=%s error=%s", url, type(exc).__name__)
        return {"__fetch_error": type(exc).__name__}


def _download_subtitle_once(
    ytdlp: str,
    url: str,
    source_type: str,
    settings: Settings,
    tmpdir: str,
    auto: bool,
    languages: Optional[str] = None,
    output_name: str = "subtitle",
) -> str:
    output = Path(tmpdir) / output_name
    command = [
        ytdlp,
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--write-auto-subs" if auto else "--write-subs",
        "--sub-lang",
        languages or ("zh,en,zh-Hans,zh-Hant" if not auto else "zh,en"),
        "--sub-format",
        "vtt/srt/best",
        "-o",
        str(output),
    ]
    bilibili_cookies_file = effective_bilibili_cookies_file(settings)
    if source_type == "bilibili" and bilibili_cookies_file:
        command.extend(["--cookies", str(Path(bilibili_cookies_file).expanduser())])
    _add_youtube_auth_args(command, source_type, settings)
    command.append(url)
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(60, int(settings.request_timeout_seconds) + 60),
    )
    combined = f"{completed.stdout}\n{completed.stderr}"
    if source_type == "youtube":
        failure = _youtube_failure_status(combined)
        if failure:
            return failure
    if completed.returncode != 0:
        return "subtitle_download_failed" if source_type == "youtube" else "download_failed"
    if "There are no subtitles for the requested languages" in combined:
        return "no_requested_language_subtitles"
    return "downloaded"


def _first_subtitle_transcript(candidates: List[Path]) -> str:
    for candidate in candidates:
        if not candidate.is_file():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if candidate.suffix.lower() == ".srt":
            transcript = _parse_srt(text)
        else:
            transcript = _parse_vtt(text)
        if transcript:
            return transcript
    return ""


def _read_first_subtitle(candidates: List[Path]) -> str:
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in {".vtt", ".srt"}:
            text = candidate.read_text(encoding="utf-8", errors="replace").strip()
            if candidate.suffix.lower() == ".srt":
                return _srt_to_vtt(text)
            return text
    return ""


def _add_youtube_auth_args(command: List[str], source_type: str, settings: Settings) -> None:
    if source_type != "youtube":
        return
    browser_cookie_source = settings.youtube_browser_cookie_source.strip()
    youtube_cookies_file = effective_youtube_cookies_file(settings)
    if browser_cookie_source:
        command.extend(["--cookies-from-browser", browser_cookie_source])
    elif youtube_cookies_file:
        cookies_file = Path(youtube_cookies_file).expanduser()
        if not cookies_file.exists():
            raise need_cookies(f"Configured YouTube cookies file does not exist: {cookies_file}")
        command.extend(["--cookies", str(cookies_file)])
    if settings.youtube_extractor_args:
        command.extend(["--extractor-args", settings.youtube_extractor_args])


def _youtube_failure_status(output: str) -> str:
    lowered = output.lower()
    if "po token" in lowered or "proof of origin" in lowered:
        return "youtube_po_token_required"
    if "http error 429" in lowered or "too many requests" in lowered or "rate limit" in lowered:
        return "youtube_rate_limited"
    if "sign in to confirm" in lowered or "login required" in lowered or "use --cookies" in lowered:
        return "youtube_auth_required"
    return ""


def _transcribe_audio_file(
    audio_path: Path,
    tmp: Path,
    settings: Settings,
    duration: object,
    language_hint: str = "auto",
) -> Dict[str, str]:
    backend = settings.transcription_backend.strip().lower()
    candidates = []
    if backend:
        candidates.append(backend)
    for fallback in ["mlx_whisper", "faster_whisper", "whisper_cpp"]:
        if fallback not in candidates:
            candidates.append(fallback)

    for candidate in candidates:
        if candidate == "mlx_whisper":
            result = _transcribe_with_external_command(
                executable=settings.mlx_whisper_path,
                args=[str(audio_path), "--output-dir", str(tmp), "--format", "srt"],
                tmp=tmp,
                duration=duration,
                status="transcribed_mlx_whisper",
            )
        elif candidate == "faster_whisper":
            result = _transcribe_with_external_command(
                executable=settings.faster_whisper_path,
                args=[str(audio_path), "--output_dir", str(tmp), "--output_format", "srt"],
                tmp=tmp,
                duration=duration,
                status="transcribed_faster_whisper",
            )
        else:
            result = _transcribe_with_whisper_cpp(audio_path, tmp, settings, duration, language_hint)
        if result.get("transcript"):
            return result
    return {"transcript": "", "subtitle_vtt": "", "status": "transcription_failed"}


def _transcribe_with_whisper_cpp(
    audio_path: Path,
    tmp: Path,
    settings: Settings,
    duration: object,
    language_hint: str = "auto",
) -> Dict[str, str]:
    whisper_model = Path(settings.whisper_model_path).expanduser()
    if not whisper_model.exists():
        return {"transcript": "", "subtitle_vtt": "", "status": "dependency_missing_whisper_model"}
    whisper_cli = shutil.which(settings.whisper_cli_path) or settings.whisper_cli_path
    if not whisper_cli or not Path(whisper_cli).exists():
        return {"transcript": "", "subtitle_vtt": "", "status": "dependency_missing_whisper_cli"}
    output_prefix = tmp / "transcript"
    transcribe = subprocess.run(
        [
            whisper_cli,
            "-m",
            str(whisper_model),
            "-f",
            str(audio_path),
            "-l",
            language_hint or "auto",
            "-of",
            str(output_prefix),
            "-otxt",
            "-osrt",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(180, int(float(duration or 60) * 4)),
    )
    if transcribe.returncode != 0:
        return {"transcript": "", "subtitle_vtt": "", "status": "transcription_failed"}
    return _transcription_files_to_result(tmp, "transcribed_whisper_cpp")


def _transcribe_with_external_command(
    executable: str,
    args: List[str],
    tmp: Path,
    duration: object,
    status: str,
) -> Dict[str, str]:
    path = shutil.which(executable) or executable
    if not path or not Path(path).exists():
        return {"transcript": "", "subtitle_vtt": "", "status": f"dependency_missing_{status}"}
    completed = subprocess.run(
        [path, *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(180, int(float(duration or 60) * 4)),
    )
    if completed.returncode != 0:
        return {"transcript": "", "subtitle_vtt": "", "status": "transcription_failed"}
    return _transcription_files_to_result(tmp, status)


def _transcription_files_to_result(tmp: Path, status: str) -> Dict[str, str]:
    srt_files = sorted(tmp.glob("*.srt"))
    txt_files = sorted(tmp.glob("*.txt"))
    if srt_files:
        srt = srt_files[0].read_text(encoding="utf-8", errors="replace")
        transcript = _parse_srt(srt)
        if transcript:
            return {"transcript": transcript, "subtitle_vtt": _srt_to_vtt(srt), "status": status}
    if txt_files:
        transcript = txt_files[0].read_text(encoding="utf-8", errors="replace").strip()
        if transcript:
            return {"transcript": transcript, "subtitle_vtt": "", "status": status}
    return {"transcript": "", "subtitle_vtt": "", "status": "transcription_failed"}


def _transcript_matches_video(transcript: str, metadata: Dict[str, Any]) -> bool:
    return _platform_transcript_is_usable(transcript, metadata)


def _platform_transcript_is_usable(transcript: str, metadata: Dict[str, Any]) -> bool:
    if _is_low_value_subtitle(transcript):
        return False
    return bool(
        _validate_transcript_timing(
            transcript,
            _metadata_duration_seconds(metadata),
            require_timestamps=True,
        )["valid"]
    )


def _validate_transcript_timing(
    transcript: str,
    duration_seconds: float,
    *,
    require_timestamps: bool,
) -> Dict[str, Any]:
    timestamp_count = 0
    previous_start = -1.0
    last_end = 0.0
    monotonic = True
    structurally_valid = True
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _TRANSCRIPT_RANGE_RE.match(line)
        if not match:
            continue
        start = _timestamp_to_seconds(match.group("start"))
        end = _timestamp_to_seconds(match.group("end"))
        timestamp_count += 1
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            structurally_valid = False
            continue
        if start < previous_start:
            monotonic = False
        previous_start = start
        last_end = max(last_end, end)

    duration = max(0.0, float(duration_seconds or 0.0))
    tolerance = max(5.0, duration * 0.03) if duration else 0.0
    duration_ratio = last_end / duration if duration and timestamp_count else None
    reason = "ok"
    if require_timestamps and timestamp_count == 0:
        reason = "timestamps_missing"
    elif not structurally_valid:
        reason = "invalid_timestamp_range"
    elif not monotonic:
        reason = "timestamps_not_monotonic"
    elif duration and last_end > duration + tolerance:
        reason = "duration_exceeded"
    elif duration >= 300 and last_end and last_end < min(180.0, duration * 0.15):
        reason = "insufficient_coverage"

    return {
        "valid": reason == "ok",
        "reason": reason,
        "timestamp_count": timestamp_count,
        "timestamps_monotonic": monotonic,
        "last_timestamp_seconds": round(last_end, 3) if timestamp_count else None,
        "duration_seconds": round(duration, 3) if duration else None,
        "duration_ratio": round(duration_ratio, 4) if duration_ratio is not None else None,
        "duration_tolerance_seconds": round(tolerance, 3) if duration else None,
    }


def _metadata_duration_seconds(metadata: Dict[str, Any]) -> float:
    try:
        return float(metadata.get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0


def _transcript_coverage_seconds(transcript: str) -> float:
    report = _validate_transcript_timing(transcript, 0.0, require_timestamps=False)
    return float(report["last_timestamp_seconds"] or 0.0)


def _timestamp_to_seconds(value: str) -> float:
    parts = [float(part) for part in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0


def _append_rejection(current: str, rejection: str) -> str:
    return ";".join(part for part in [current, rejection] if part)


def _is_low_value_subtitle(transcript: str) -> bool:
    lines = [re.sub(r"^\[[^\]]+\]\s*", "", line).strip() for line in transcript.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return True
    music_like = 0
    for line in lines:
        cleaned = re.sub(r"[\s♪♫~～,，。.!！?？-]+", "", line).lower()
        if cleaned in {"音乐", "music", "bgm"}:
            music_like += 1
    meaningful_chars = sum(len(line) for line in lines) - music_like * 2
    return music_like / len(lines) >= 0.75 or meaningful_chars < 30


def _parse_vtt(text: str) -> str:
    lines: List[str] = []
    current_time = ""
    buffer: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:"):
            if current_time and buffer:
                lines.append(f"[{current_time}] {_clean_subtitle_text(' '.join(buffer))}")
            current_time = ""
            buffer = []
            continue
        if "-->" in line:
            if current_time and buffer:
                lines.append(f"[{current_time}] {_clean_subtitle_text(' '.join(buffer))}")
            current_time = _normalize_time_range(line)
            buffer = []
            continue
        if current_time and not line.isdigit():
            buffer.append(line)
    if current_time and buffer:
        lines.append(f"[{current_time}] {_clean_subtitle_text(' '.join(buffer))}")
    return "\n".join(_dedupe_subtitle_lines(lines))


def _parse_srt(text: str) -> str:
    lines: List[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        parts = [line.strip() for line in block.splitlines() if line.strip()]
        if len(parts) < 2:
            continue
        time_line = next((part for part in parts if "-->" in part), "")
        if not time_line:
            continue
        text_parts = [part for part in parts if "-->" not in part and not part.isdigit()]
        subtitle = _clean_subtitle_text(" ".join(text_parts))
        if subtitle:
            lines.append(f"[{_normalize_time_range(time_line)}] {subtitle}")
    return "\n".join(_dedupe_subtitle_lines(lines))


def _normalize_time_range(value: str) -> str:
    start, end = value.split("-->", 1)
    return f"{_compact_timestamp(start)}-{_compact_timestamp(end)}"


def _compact_timestamp(value: str) -> str:
    cleaned = value.strip().split()[0].replace(",", ".")
    if "." in cleaned:
        cleaned = cleaned.split(".", 1)[0]
    if cleaned.startswith("00:"):
        cleaned = cleaned[3:]
    return cleaned


def _format_seconds(value: object, *, round_up: bool = False) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return ""
    total = math.ceil(seconds) if round_up else int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _clean_subtitle_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _dedupe_subtitle_lines(lines: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for line in lines:
        key = re.sub(r"^\[[^\]]+\]\s*", "", line)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(line)
    return cleaned


def _subtitle_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if ".zh" in name or ".cmn" in name:
        return (0, name)
    if ".en" in name:
        return (1, name)
    return (2, name)


def _srt_to_vtt(text: str) -> str:
    body = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    body = body.replace(",", ".")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return "WEBVTT\n\n" + body + "\n" if body else ""


def _segments_to_vtt(segments: List[tuple[object, object, str]]) -> str:
    if not segments:
        return ""
    lines = ["WEBVTT", ""]
    for start, end, text in segments:
        start_text = _vtt_timestamp(start)
        end_text = _vtt_timestamp(end)
        if start_text and end_text:
            lines.append(f"{start_text} --> {end_text}")
            lines.append(text)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _vtt_timestamp(value: object) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return ""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _plain_transcript(transcript: str) -> str:
    lines = []
    for line in transcript.splitlines():
        cleaned = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _compact_raw_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "id",
        "title",
        "uploader",
        "channel",
        "duration",
        "duration_string",
        "upload_date",
        "webpage_url",
        "extractor",
        "description",
        "tags",
        "subtitles",
        "automatic_captions",
        "language",
    }
    return {key: data.get(key) for key in allowed if key in data}


def _metadata_advertises_subtitles(data: Dict[str, Any]) -> bool:
    return bool(data.get("subtitles") or data.get("automatic_captions"))


def _combine_status(first: str, second: str) -> str:
    if first in {"manual_subtitle", "auto_subtitle", "bilibili_subtitle"}:
        return first
    if first.startswith("youtube_") and first not in {"youtube_manual_subtitle", "youtube_auto_subtitle"}:
        return f"{first};{second}" if second else first
    if second:
        return second
    return first or "subtitle_unavailable"


def _progress(callback: Optional[ProgressCallback], stage: str, progress: float) -> None:
    if callback:
        callback(stage, progress)
