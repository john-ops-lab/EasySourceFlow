# 更新日志

EasySourceFlow 使用[语义化版本](https://semver.org/lang/zh-CN/)。正式发布的版本会同时出现在本文件、Git 标签和 GitHub Release 中。在 `1.0.0` 之前，次版本可能包含不兼容调整，补丁版本保持向后兼容。

## 未发布

### 新增

- Web“网络与安全”页面可显式启用 fake-ip trusted 模式并管理可信 CIDR；默认仅预制 `198.18.0.0/15`，保存后立即生效。

### 安全

- 公网 URL 校验兼容受信任的本机 fake-ip 代理，同时继续拒绝直接保留 IP、loopback、link-local、multicast 和未配置的非公网网段。
- 普通网页的 HTTP 重定向目标会重新执行 SSRF 校验。

## [0.5.0] - 2026-07-16

### 新增

- B站扫码或 YouTube 登录后自动检测并接入 Chrome 登录态，失败或五分钟超时时才显示手动重试。
- 已接入的 B站和 YouTube 账号可在 Web 中退出 EasySourceFlow，且不会退出 Chrome 中的账号。

### 改进

- 模型连通性测试兼容推理模型：扩大短测试输出预算，识别 Chat Completions 与 Responses API 的推理输出，并避免不兼容的通用参数造成误报。
- 模型总结输出统一提取最终答案：MiniMax 启用官方推理分离，忽略各兼容接口的独立推理字段，并阻止 `<think>`、提示词回显和 Responses reasoning 项进入 Markdown。
- 登录检测要求平台认证 Cookie，未登录的匿名 Cookie 不再被误判为可用，也不会覆盖已有 Cookie 文件。

### 修复

- 修复 B站扫码后因首页不受 `yt-dlp` 支持而误报导入失败；macOS 登录按钮现在明确使用 Google Chrome 打开。
- Web 管理的 B站和 YouTube 登录状态在服务代码同步或重启后继续生效，不再被根目录旧配置覆盖。

## [0.4.0] - 2026-07-15

### 新增

- Web 模型配置增加 MiniMax、Google Gemini、硅基流动、Ollama、LM Studio、xAI Grok、火山方舟/豆包、百度千帆和腾讯混元/TokenHub。
- Fast/Pro 模型字段支持常用预设和手动模型 ID，适配本地已安装模型及服务商滚动更新。
- 增加豆包 Responses API 响应解析，并支持回环地址上的 Ollama、LM Studio 在无 API Key 时调用。

### 改进

- Gemini 使用适合当前模型的温度默认值；腾讯混元预设改用迁移后的 TokenHub 地址。
- 补充新增服务商、本地模型数据边界和配置行为的文档与回归测试。

## [0.3.0] - 2026-07-15

### 新增

- 增加仅限本机 Web 的 Bilibili/YouTube 音视频下载页，支持视频 1080p/720p/最高画质和 MP3/M4A/原始音频。
- 下载任务持久化到 SQLite，支持进度、取消、重试、重启恢复和附件下载。

### 改进

- 下载任务与总结任务、MCP 工具和 Agent 通知隔离。
- 修复 YouTube 普通浏览器 Cookie 轮换后 Varys 仍使用失效文件的问题；Web 接入后改为读取 Chrome 当前登录态。
- 下载文件限制在数据目录的 `media-downloads/<job_id>/`，禁止播放列表、任意命令参数、覆盖和路径越界。
- 最低运行版本提升到 Python 3.10，并使用 `yt-dlp[default] 2026.7.4+`、Deno/Node 和 EJS 适配当前 YouTube JavaScript 验证。
- 修复移动端隐藏单选框撑宽页面，以及不支持来源被错误标记为 YouTube 的问题。

## [0.2.0] - 2026-07-15

### 新增

- 在 Web“维护 → 账号与授权”中查看 YouTube 登录状态、打开登录页并从本机 Chrome 导入登录态。
- YouTube 优先使用人工字幕；没有人工字幕时优先原语言自动字幕，最后才使用本地 ASR。
- 增加 YouTube 登录、PO Token、限流和字幕失败的独立状态，以及可选真实平台回归命令。

### 改进

- 浏览器 Cookie 导入先写临时文件，再按目标平台域名过滤并以 `0600` 权限原子替换，避免保存无关站点 Cookie。
- 修复新增 YouTube 卡片后被错误归入“模型”维护页的问题。
- 更新需求、架构、运行、配置、安全、测试和路线图文档，使其与当前实现一致。

## [0.1.1] - 2026-07-15

### 改进

- 将仓库路径和发布配置的安全回归检查改为通用规则。

## [0.1.0] - 2026-07-15

首个公开版本。

### 新增

- 面向 Agent 的 MCP、HTTP 和 Web 三种入口。
- 网页、微信公众号、Bilibili、YouTube 初始能力和本地文档处理。
- 平台字幕优先、本地 ASR 回退及字幕来源标记。
- OpenAI-compatible 模型配置、Fast/Pro 模型选择和通用总结提示词。
- 可恢复任务队列、SQLite 缓存、全文搜索、资源包和收藏夹。
- macOS LaunchAgent、自检、备份、清理预览、日志轮转和维护任务。
- 匿名化发布检查、Gitleaks 和多 Python 版本 CI。

### 说明

- 当前主要支持 macOS 本地部署。
- YouTube 字幕和部分受限页面仍可能依赖 Cookie 或浏览器配置。
