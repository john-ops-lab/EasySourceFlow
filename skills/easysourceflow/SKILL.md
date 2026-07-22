---
name: easysourceflow
description: Use EasySourceFlow whenever the user provides a supported webpage, video, cloud-document link, or file for summarization. A bare supported link or attachment means "summarize this with EasySourceFlow" unless the user explicitly requests a different operation. Also use it for notes, transcription, previous results, subtitle source, local ASR, search, or favorites.
compatibility: Requires a running EasySourceFlow service and its MCP tools.
license: MIT
metadata:
  version: "0.2.0"
---

# EasySourceFlow

Use EasySourceFlow as the single content-processing pipeline. Do not reproduce its extraction, subtitle, transcription, summarization, file-writing, or favorite logic with unrelated tools.

## Choose the workflow

- Treat a message containing only a supported URL, authenticated cloud-document link, or a PDF, DOCX, EPUB, TXT, Markdown, or HTML attachment as an implicit EasySourceFlow summary request. An explicit user instruction takes precedence.
- For another authenticated cloud-document link that EasySourceFlow cannot fetch directly, use its dedicated connector to read the complete body, then pass the title, content, and original HTTPS `source_url` to `easysourceflow_submit_document` in the same way.
- If a cloud-document connector cannot return the complete body, report the connector access or completeness failure. Do not ask EasySourceFlow to fetch a private link, and do not use the Agent's own model as a fallback summary.
- For every other single URL, including public webpages, WeChat articles, Bilibili, and YouTube, call `easysourceflow_submit_link` and retain its `job_id`.
- Call `easysourceflow_get_job` with that `job_id` and `wait_seconds=45`. If it remains queued or running, call the same tool again until it reaches a terminal state.
- Treat `easysourceflow_summarize_link` as a compatibility tool for short non-video webpages only. Do not choose it for new Agent workflows.
- For multiple links, call `easysourceflow_submit_batch`, then poll `easysourceflow_get_batch`.
- For an uploaded PDF, call `easysourceflow_submit_document_file` with the attachment path and original filename. Message-injected PDF text may be a truncated preview and must not be treated as the complete document.
- For pasted text, connector-read cloud content, or a non-PDF attachment whose complete body is already present, call `easysourceflow_submit_document` after excluding transport metadata, local paths, wrapper tags, and untrusted-content markers. Use the original filename or connector title as `title`; connector-read cloud content must also include its original `source_url`.
- If the file submission tool is unavailable, report that the EasySourceFlow integration must be updated. Do not use a PDF model, document reader, inline preview, or the Agent's own model as a fallback summary.
- A repeated link or attachment is still an EasySourceFlow request. Submit it normally with `force_refresh=false` so the service can reuse a valid cached result; never replace the tool call with a duplicate-content response.
- Poll document jobs with `easysourceflow_get_job` exactly like URL jobs.
- For old results, use `easysourceflow_search_outputs` or `easysourceflow_list_recent_jobs`.
- Tool names may have an extra client-specific server prefix. Match the `easysourceflow_` suffixes above.

Use `summary_quality="pro"` for videos. The service also enforces Pro automatically for recognized video links. For non-video sources, honor an explicit user choice; otherwise use `fast`.

Use `force_refresh=true` only when the user explicitly asks to re-fetch, re-transcribe, regenerate, or ignore an old result. Normal submissions should leave it false so valid cached results can be reused. A retry defaults to force refresh.

## Deliver the result

Treat `result.summary_markdown` as the finished deliverable.

1. Return the Markdown unchanged. Do not summarize, rewrite, shorten, translate, transcribe, reorder, or selectively quote it unless the user explicitly asks for a new transformation.
2. Do not replace the result with your own interpretation of the source.
3. Preserve headings, links, core-point timeline entries, subtitle-source labels, and the output path.
4. If the chat platform supports Markdown cards, place the exact `result.summary_markdown` value in its Markdown content field. Do not rebuild it from selected sections.
5. If rich delivery fails, send the complete Markdown unchanged as plain messages; split only at natural Markdown boundaries when the channel requires it.
6. Do not expose the internal HTML instruction comment that may precede the finished Markdown.

## Track the latest result

Retain the latest successful `job_id`, `output_markdown_path`, and `relative_path` in the current conversation context. These identifiers are needed for follow-up actions.

If the user replies exactly `收藏` after receiving an EasySourceFlow result:

1. Call `easysourceflow_favorite_result` with the latest known identifier, preferring `job_id` or `output_markdown_path`.
2. If no identifier is available, call it without arguments so the service resolves the newest output.
3. On success, reply only that the summary was saved. Do not resend the full summary.

## Report progress and failures

- A queued or running job is not a failure. Keep the same `job_id`; do not switch to `web_fetch`, a browser, or another summarizer.
- Only `status=succeeded` with a non-empty `result.summary_markdown` means the summary is complete.
- While polling, report concise stage changes only when useful; do not invent progress.
- On success, rely on the service's subtitle-source label. Never describe local ASR as original platform subtitles.
- On failure, relay the service's `error_message` and `error_next_steps` in plain language.
- If the daemon is unavailable, suggest starting EasySourceFlow or running its health check. Do not silently fall back to a lower-quality independent summary.

## Safety boundaries

- Do not ask EasySourceFlow to read arbitrary local paths. Submit document content through the document tool.
- Never include API keys, cookies, `.env` contents, or private source text in diagnostics.
- Keep cleanup in dry-run mode unless the user explicitly approves deletion.

Read [references/tools.md](references/tools.md) only when exact tool selection or parameter behavior is needed. When the active connector or delivery channel is Feishu, also read [references/feishu.md](references/feishu.md).
