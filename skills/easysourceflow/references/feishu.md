# Feishu connector and delivery

Use these rules only when the source or delivery channel is Feishu.

## Read private cloud documents

1. Resolve a Feishu Wiki node when necessary and read the complete document body with the authenticated Feishu connector.
2. Call `easysourceflow_submit_document` with the complete `content`, document `title`, and the user's original HTTPS link as `source_url`.
3. Retain the job ID and poll EasySourceFlow. Never summarize or deliver the connector output directly.
4. If the connector cannot return the complete body, report that failure instead of using a partial preview.

## Deliver the result

1. Pass Feishu `message.card` as a JSON object, not a JSON-encoded string.
2. Put the exact `result.summary_markdown` in the card's Markdown content field.
3. If the tool reports `card: must be object`, correct the argument type and retry.
4. If card delivery still fails, send the complete Markdown unchanged as plain messages, splitting only at natural Markdown boundaries.
5. Never show card JSON as message text or replace the result with a shorter summary.
