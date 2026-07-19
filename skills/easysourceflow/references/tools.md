# Tool Reference

## Content processing

- `easysourceflow_submit_link`: default processing entry point for every URL. Inputs: `url`, optional `instruction`, optional `summary_quality` (`fast` or `pro`), and optional `force_refresh`. Retain the returned job ID.
- `easysourceflow_get_job`: query by `job_id`; pass `wait_seconds=45` and repeat while queued or running. A succeeded job contains the final Markdown and output paths.
- `easysourceflow_summarize_link`: compatibility-only synchronous processing for short non-video webpages. It rejects Bilibili and YouTube links.
- `easysourceflow_submit_document_file`: submit an uploaded PDF or other supported attachment by its platform-provided path. The MCP adapter only accepts files below configured upload roots and sends the original bytes to EasySourceFlow.
- `easysourceflow_submit_document`: submit pasted text or a complete non-PDF document body, with optional `title`, `instruction`, `summary_quality`, and `force_refresh`; retain its job ID and poll `easysourceflow_get_job`. Never pass local paths or message-envelope metadata as content.
- `easysourceflow_submit_batch`: submit `urls` plus optional shared instruction, quality, and `force_refresh`. Follow with `easysourceflow_get_batch`.

## Result management

- `easysourceflow_favorite_result`: favorite by `job_id`, `output_markdown_path`, or `relative_path`. With no arguments, it uses the newest output.
- `easysourceflow_search_outputs`: search previous Markdown using `q`, optional `source`, and `limit`.
- `easysourceflow_list_recent_jobs`: list recent jobs with optional `status` and `limit`.
- `easysourceflow_retry_job`: retry a failed or completed job, optionally replacing its instruction or quality. It force-refreshes by default; set `force_refresh=false` only when cache reuse is intended.
- `easysourceflow_cancel_job`: cancel queued or running work.

## Diagnostics and maintenance

- `easysourceflow_health_check`: inspect runtime dependencies and configuration.
- `easysourceflow_bilibili_cookie_status`: check cookie-file availability without exposing cookies.
- `easysourceflow_model_status`: inspect active model configuration without exposing API keys.
- `easysourceflow_cleanup`: preview with `dry_run=true`; only use `false` after explicit deletion approval.
- `easysourceflow_backup`: back up the database and output directory.

All tools return a human-readable text part. Successful calls also return the underlying service payload as structured content when the MCP client supports it.
