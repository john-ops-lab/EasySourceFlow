# Bilibili Regression Samples

This file tracks real Bilibili videos used to validate subtitle selection, ASR fallback, and summary timeline quality.

## Review Rules

- Prefer platform subtitles when Chinese subtitles are available.
- Use ASR only when subtitles are missing or unusable.
- If English subtitles or English speech are used, the final summary and key timeline should be Chinese.
- The summary timeline is not raw subtitle text. Each item should be a summarized core point and the timestamp where that point starts.
- The rendered result page should show the main Markdown only; full transcript timeline stays in the linked `timeline.md`.

## Manual Sample Set

| ID | URL | Expected Path | Checks |
| --- | --- | --- | --- |
| `nihaixia-subtitle` | `https://www.bilibili.com/video/BV1mY411U7as` | Chinese subtitle preferred | No unnecessary ASR; key timeline uses summarized points; full timeline link exists. |
| `english-to-chinese` | `https://www.bilibili.com/video/BV19CoBYjEFg` | English subtitle or English speech | Chinese summary; Chinese key timeline; full timeline link exists. |
| `no-subtitle-asr` | `https://www.bilibili.com/video/BV1uRHQeCEyf/` | ASR fallback | Status explains transcription; timestamps are monotonic; poor ASR quality is visible in metadata/status. |

The machine-readable manifest is `docs/bilibili_regression_samples.json`. Run the real-platform suite explicitly; it is intentionally excluded from ordinary CI:

```bash
scripts/easysourceflow bilibili-regression
```

Use `scripts/easysourceflow asr-eval <reference.txt> <transcript.txt> [duration]` to calculate character error rate, timestamp monotonicity, and duration coverage without storing reference transcripts in Git.

## When Adding Samples

Add the video URL, expected extraction path, and a short reason. Do not store cookies, downloaded media, or private transcripts in this repository.
