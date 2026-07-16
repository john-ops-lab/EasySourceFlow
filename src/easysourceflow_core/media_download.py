"""Controlled Bilibili and YouTube media downloads for the local Web UI."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .config import Settings, effective_bilibili_cookies_file
from .errors import EasySourceFlowError, dependency_missing, invalid_url, need_cookies
from .extractors.video import _add_youtube_auth_args, _find_ytdlp, _youtube_failure_status
from .url_utils import detect_source_type, normalize_url


logger = logging.getLogger(__name__)

VIDEO_QUALITIES = {
    "best": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b",
}
AUDIO_FORMATS = {"mp3", "m4a", "original"}
_PROGRESS_RE = re.compile(r"PROGRESS:\s*([0-9]+(?:\.[0-9]+)?)%")


def media_download_root(settings: Settings) -> Path:
    return settings.data_dir.expanduser().resolve() / "media-downloads"


def download_media(
    url: str,
    media_type: str,
    format_name: str,
    settings: Settings,
    destination_dir: Path,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    canonical_url = normalize_url(url, settings.allow_local_urls, settings.trusted_fake_ip_cidrs)
    source_type = detect_source_type(canonical_url)
    if source_type not in {"bilibili", "youtube"}:
        raise invalid_url("音视频下载只支持 Bilibili 和 YouTube 链接。")

    normalized_type = str(media_type or "").strip().lower()
    normalized_format = str(format_name or "").strip().lower()
    if normalized_type == "video":
        if normalized_format not in VIDEO_QUALITIES:
            raise _invalid_download_option("视频清晰度无效。")
    elif normalized_type == "audio":
        if normalized_format not in AUDIO_FORMATS:
            raise _invalid_download_option("音频格式无效。")
    else:
        raise _invalid_download_option("下载类型必须是视频或音频。")

    destination = destination_dir.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    ytdlp = _find_ytdlp(settings)
    command = _download_command(
        ytdlp,
        canonical_url,
        source_type,
        normalized_type,
        normalized_format,
        settings,
        destination,
    )
    if progress_callback:
        progress_callback("preparing_download", 0.05)

    logger.info(
        "media download started source=%s type=%s format=%s destination=%s",
        source_type,
        normalized_type,
        normalized_format,
        destination,
    )
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    title = ""
    final_path_text = ""
    output_tail: list[str] = []
    try:
        if process.stdout is None:
            raise RuntimeError("yt-dlp stdout pipe was not created")
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line:
                output_tail.append(line)
                output_tail = output_tail[-30:]
            if cancel_check and cancel_check():
                _terminate_process(process)
                _remove_download_directory(destination)
                return {"canceled": True}
            if line.startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("FILE:"):
                final_path_text = line[5:].strip()
            else:
                match = _PROGRESS_RE.search(line)
                if match and progress_callback:
                    percent = min(100.0, max(0.0, float(match.group(1))))
                    progress_callback("downloading", 0.08 + percent / 100 * 0.82)
        return_code = process.wait()
    except Exception:
        _terminate_process(process)
        raise

    if cancel_check and cancel_check():
        _remove_download_directory(destination)
        return {"canceled": True}
    if return_code != 0:
        _remove_download_directory(destination)
        raise _download_failure(source_type, "\n".join(output_tail))

    if progress_callback:
        progress_callback("finalizing_download", 0.95)
    final_path = _resolve_downloaded_file(destination, final_path_text)
    stat = final_path.stat()
    logger.info("media download succeeded source=%s file=%s size=%s", source_type, final_path.name, stat.st_size)
    return {
        "operation": "media_download",
        "source_url": url,
        "canonical_url": canonical_url,
        "source_type": source_type,
        "media_type": normalized_type,
        "format": normalized_format,
        "title": title or final_path.stem,
        "file_path": str(final_path),
        "file_name": final_path.name,
        "file_size": stat.st_size,
    }


def _download_command(
    ytdlp: str,
    url: str,
    source_type: str,
    media_type: str,
    format_name: str,
    settings: Settings,
    destination: Path,
) -> list[str]:
    command = [
        ytdlp,
        "--no-playlist",
        "--newline",
        "--progress",
        "--no-overwrites",
        "--trim-filenames",
        "160",
        "--paths",
        str(destination),
        "--output",
        "%(title)s [%(id)s].%(ext)s",
        "--print",
        "before_dl:TITLE:%(title)s",
        "--print",
        "after_move:FILE:%(filepath)s",
        "--progress-template",
        "download:PROGRESS:%(progress._percent_str)s",
    ]
    if settings.ffmpeg_path:
        ffmpeg = shutil.which(settings.ffmpeg_path) or settings.ffmpeg_path
        command.extend(["--ffmpeg-location", str(Path(ffmpeg).parent) if Path(ffmpeg).is_file() else ffmpeg])
    if media_type == "video":
        command.extend(["--format", VIDEO_QUALITIES[format_name], "--merge-output-format", "mp4/mkv"])
    else:
        command.extend(["--format", "ba/b"])
        if format_name != "original":
            command.extend(["--extract-audio", "--audio-format", format_name, "--audio-quality", "0"])

    if source_type == "bilibili":
        cookies_file = effective_bilibili_cookies_file(settings)
        if cookies_file:
            path = Path(cookies_file).expanduser()
            if not path.exists():
                raise need_cookies(f"Configured Bilibili cookies file does not exist: {path}")
            command.extend(["--cookies", str(path)])
    if source_type == "youtube":
        deno = shutil.which("deno")
        node = shutil.which("node")
        if deno:
            command.extend(["--js-runtimes", f"deno:{deno}"])
        elif node:
            command.extend(["--js-runtimes", f"node:{node}"])
    _add_youtube_auth_args(command, source_type, settings)
    command.append(url)
    return command


def _resolve_downloaded_file(destination: Path, printed_path: str) -> Path:
    root = destination.resolve()
    candidates = []
    if printed_path:
        candidates.append(Path(printed_path).expanduser())
    candidates.extend(
        path for path in destination.iterdir()
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl", ".temp"}
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    raise EasySourceFlowError(
        "download_file_missing",
        "下载命令已结束，但没有找到可用的音视频文件。",
        ["检查磁盘空间和 FFmpeg 配置后重试。"],
    )


def _download_failure(source_type: str, output: str) -> EasySourceFlowError:
    if source_type == "youtube":
        status = _youtube_failure_status(output)
        if status == "youtube_auth_required":
            return need_cookies("YouTube 拒绝了下载请求，请重新导入浏览器登录态后重试。")
        if status == "youtube_po_token_required":
            return EasySourceFlowError(
                status,
                "YouTube 要求当前下载客户端提供 PO Token。",
                ["更新 yt-dlp 并重新导入 YouTube 登录态。", "仍失败时配置受支持的 PO Token provider。"],
            )
        if status == "youtube_rate_limited":
            return EasySourceFlowError(
                status,
                "YouTube 暂时限制了当前网络的下载请求。",
                ["等待一段时间后重试。", "避免短时间重复下载同一个视频。"],
            )
        lowered = output.lower()
        if "challenge solving failed" in lowered or "only images are available" in lowered:
            return EasySourceFlowError(
                "youtube_challenge_solver_required",
                "YouTube 的 JavaScript 验证没有完成。",
                ["安装 Deno 2.3+ 或 Node 22+。", "使用 yt-dlp[default] 安装匹配版本的 EJS 脚本后重试。"],
            )
    lowered = output.lower()
    if source_type == "bilibili" and any(token in lowered for token in ("login", "cookie", "账号", "登录")):
        return need_cookies("Bilibili 要求登录或当前登录态已失效，请重新导入浏览器登录态。")
    if "ffmpeg" in lowered and any(token in lowered for token in ("not found", "not installed", "unable to obtain")):
        return dependency_missing("合并视频或转换音频需要 FFmpeg。")
    return EasySourceFlowError(
        "media_download_failed",
        "平台未能完成音视频下载。",
        ["确认链接可在浏览器中播放。", "在维护页面重新导入对应平台登录态后重试。"],
    )


def _invalid_download_option(message: str) -> EasySourceFlowError:
    return EasySourceFlowError("invalid_download_option", message, ["请使用网页中提供的下载选项。"])


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _remove_download_directory(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("could not remove incomplete media download directory=%s", path, exc_info=True)
