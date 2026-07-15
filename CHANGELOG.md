# 更新日志

EasySourceFlow 使用[语义化版本](https://semver.org/lang/zh-CN/)。正式发布的版本会同时出现在本文件、Git 标签和 GitHub Release 中。在 `1.0.0` 之前，次版本可能包含不兼容调整，补丁版本保持向后兼容。

## 未发布

- 暂无。

## [0.1.1] - 2026-07-15

### 改进

- 将仓库路径和发布配置的安全回归检查改为通用规则。

## [0.1.0] - 2026-07-15

首个公开版本。

### 新增

- 面向 Agent 的 MCP、HTTP 和 Web 三种入口。
- 网页、微信公众号、Bilibili、YouTube 实验能力和本地文档处理。
- 平台字幕优先、本地 ASR 回退及字幕来源标记。
- OpenAI-compatible 模型配置、Fast/Pro 模型选择和通用总结提示词。
- 可恢复任务队列、SQLite 缓存、全文搜索、资源包和收藏夹。
- macOS LaunchAgent、自检、备份、清理预览、日志轮转和维护任务。
- 匿名化发布检查、Gitleaks 和多 Python 版本 CI。

### 说明

- 当前主要支持 macOS 本地部署。
- YouTube 字幕和部分受限页面仍可能依赖 Cookie 或浏览器配置。
