# 飞书适配

本页只描述飞书连接器和消息卡片差异。EasySourceFlow 的任务调用仍遵循通用 Agent 契约。

## 云文档

飞书 Wiki/Docs 等需要登录的链接不能交给公开网页抓取器。Agent 应：

1. 使用已授权的飞书连接器解析 Wiki 节点并读取完整标题和正文。
2. 调用 `easysourceflow_submit_document`，传入完整 `content`、`title` 和用户发送的原始 HTTPS `source_url`。
3. 轮询同一个任务，等待 EasySourceFlow 生成结果。
4. 不得直接总结或发送连接器正文。

连接器只负责读取，飞书凭据不会交给 EasySourceFlow。

## Markdown 卡片

通过飞书 `message` 工具发送结果时：

- `card` 必须是 JSON 对象，不能是序列化后的 JSON 字符串。
- 将完整 `result.summary_markdown` 放入卡片 Markdown 内容字段，不重新拼装或缩写。
- 如果出现 `card: must be object`，修正参数类型后重试。
- 卡片仍然失败时，按自然 Markdown 边界拆分并发送完整原文，不得改成二次总结。
- 不要把卡片 JSON 当作普通消息发给用户。
