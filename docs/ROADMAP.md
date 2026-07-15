# 路线图

## 已完成

- 文档和基础设计。
- 项目改名为 EasySourceFlow。
- 本地 HTTP 服务 `easysourceflowd`。
- stdio MCP 适配器 `easysourceflow_mcp`。
- 普通网页总结。
- 微信公众号公开文章提取和浏览器兜底。
- B 站视频元数据、字幕、cookies 文件支持。
- 无字幕视频转写兜底。
- OpenAI-compatible 模型 API 总结。
- 本地 Markdown 输出。
- 本机 Web 控制台。
- 视频资源包输出。
- SQLite 任务记录和缓存。
- 批量链接处理。
- 清理工具。
- 健康检查。
- 旧项目名和旧路径清理。
- 一键启动/停止脚本和 launchd 开机自启动。
- OpenClaw MCP 接入。
- Web 任务详情、批量报告和输出索引筛选。
- 失败原因下一步建议。
- 依赖缺失修复提示。
- 日志状态命令。
- SQLite 和输出目录备份命令。
- 分类清理策略。
- 任务重试。
- 输出 Markdown 全文搜索。
- B 站 cookies 状态展示。
- 微信公众号浏览器池复用。
- 公开网页 JSON-LD 和 Jina Reader fallback。
- 视频时间轴摘要和 `timeline.md`。
- 本地文本/Markdown 文件输入。
- 模型配置、模型选择和模型连通测试。
- 维护任务失败状态展示。
- B 站样例库文档。
- 本地 HTML/DOCX/EPUB/PDF 文件上传解析。
- 任务取消和队列状态展示。
- 本地烟测回归命令。
- 日志轮转和每日维护 LaunchAgent。
- Web ASR 配置状态展示。
- MCP 备份和取消任务工具。
- SQLite 版本化迁移和中断任务自动恢复。
- 模型、提示词版本感知的缓存键、过期策略和强制刷新。
- SQLite FTS 增量输出检索及兼容回退。
- 真实 B 站回归运行器和 ASR 质量指标。
- 可配置的任务与维护通知。
- Web 上传进度、可编辑重试和资源包打开功能。

## 当前优先级

### P1: 日常使用体验

- 本地菜单栏入口。
- Web 控制台浏览器回归持续扩展。
- README 快速上手持续校准。

### P2: 稳定性

- 定期运行真实 B 站样例并维护失效样例。
- 持续积累有参考文本的 ASR 质量基准。
- 真实平台失败样例库。
- FunASR 或国内 ASR 后端。
- B 站多 P 视频支持。

### P3: 运行管理

- 任务恢复后的输出幂等性继续增强。

## 暂缓

### Obsidian

后续再做：

- Obsidian vault 配置。
- 保存工具。
- 路径校验。
- 模板规则。
- Local REST API 可选模式。

### YouTube

后续再做：

- YouTube cookies。
- PO Token 处理。
- 字幕优先级策略。
- YouTube 专门回归测试。

### 知识库能力

后续再评估：

- NotebookLM。
- RAG。
- 本地向量索引。
- 统一知识库整理。

## 不做

- 公网服务。
- 多用户权限系统。
- 绕过 DRM、付费墙或平台权限限制。
- 视频下载器替代品。
