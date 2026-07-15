# YouTube Regression Samples

This sample set validates YouTube login-state import, subtitle selection, Chinese summaries, and the core-point timeline.

## Expected Behavior

- Prefer creator-provided subtitles, with Chinese tracks first when available.
- If no manual subtitle is usable, prefer the video's original automatic caption before translated tracks.
- Use local ASR only when no usable platform caption exists.
- Generate the final Markdown in Chinese even when the selected caption or speech is English.
- Keep the core-point timeline count equal to the core-point count.

The machine-readable manifest is `docs/youtube_regression_samples.json`. Sign in to YouTube in Chrome and import the login state from **维护 → 账号与授权** before running:

```bash
scripts/easysourceflow youtube-regression --force-refresh
```

The real-platform suite is intentionally excluded from ordinary CI because YouTube access, captions, account state, and rate limits can change. Never commit cookies, PO Tokens, downloaded media, transcripts, or generated summaries.
