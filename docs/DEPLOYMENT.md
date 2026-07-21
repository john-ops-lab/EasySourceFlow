# 部署说明

## 1. 部署目标

目标环境是用户本机。服务默认只监听 localhost，Agent 通过 MCP 调用。当前阶段不开放公网端口，不依赖 Obsidian。

## 2. 组件

```text
easysourceflowd
  -> listens on http://127.0.0.1:8765

Codex / OpenClaw / other MCP clients
  -> starts easysourceflow_mcp stdio adapter
  -> adapter calls easysourceflowd
```

## 3. 依赖

必须：

- Python 3.10 或更新版本。
- SQLite。
- 模型 API key。
- `yt-dlp`。
- `ffmpeg`。

YouTube 还需要：

- Deno 2.3+（推荐）或 Node.js 22+。
- 与当前 `yt-dlp` 匹配的 EJS 包；项目通过 `yt-dlp[default]` 自动安装。

视频转写需要：

- `whisper-cli`。
- Whisper 模型文件，例如 `ggml-base.bin`。

微信公众号浏览器兜底需要：

- Playwright Python 包。
- 本机 Google Chrome。

可选：

- `mlx-whisper`。
- `faster-whisper`。

暂缓：

- Obsidian。
- Obsidian Local REST API 插件。

## 4. 目录

项目代码目录示例：

```text
~/src/EasySourceFlow
```

默认数据目录：

```text
~/.local/share/easysourceflow
```

默认输出目录：

```text
~/.local/share/easysourceflow/output
```

Web 音视频下载目录：

```text
~/.local/share/easysourceflow/media-downloads
```

B 站 cookies 和 Whisper 模型可以放在用户数据目录：

```text
~/.local/share/easysourceflow/
├── models/
└── secrets/
```

## 5. 配置

复制配置模板：

```bash
cp .env.example .env
```

`.env` 不要提交、打印或写入交接文档。

关键配置：

```env
EASYSOURCEFLOW_HOST=127.0.0.1
EASYSOURCEFLOW_PORT=8765
EASYSOURCEFLOW_DATA_DIR=~/.local/share/easysourceflow
EASYSOURCEFLOW_OUTPUT_DIR=~/.local/share/easysourceflow/output
EASYSOURCEFLOW_BILIBILI_COOKIES_FILE=~/.local/share/easysourceflow/secrets/bilibili-cookies.txt
EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE=~/.local/share/easysourceflow/secrets/youtube-cookies.txt
EASYSOURCEFLOW_FFMPEG_PATH=ffmpeg
EASYSOURCEFLOW_WHISPER_CLI_PATH=whisper-cli
EASYSOURCEFLOW_WHISPER_MODEL_PATH=~/.local/share/easysourceflow/models/ggml-base.bin
EASYSOURCEFLOW_TRANSCRIPTION_BACKEND=whisper_cpp
EASYSOURCEFLOW_MODEL_PROVIDER=openai_compatible
EASYSOURCEFLOW_MODEL=deepseek-chat
EASYSOURCEFLOW_STRONG_MODEL=deepseek-reasoner
EASYSOURCEFLOW_MODEL_BASE_URL=https://api.deepseek.com
EASYSOURCEFLOW_MODEL_API_KEY=...
```

当前没有任何 Obsidian 环境变量配置项。

## 6. 启动服务

手动启动：

```bash
scripts/easysourceflow start
```

查看状态：

```bash
scripts/easysourceflow status
```

停止服务：

```bash
scripts/easysourceflow stop
```

服务启动后默认监听：

```text
http://127.0.0.1:8765/
```

## 7. macOS launchd 自启动

安装并立即启动当前用户的 LaunchAgent：

```bash
scripts/easysourceflow install-launchd
```

查看状态：

```bash
scripts/easysourceflow launchd-status
```

卸载：

```bash
scripts/easysourceflow uninstall-launchd
```

生成的 plist：

```text
~/Library/LaunchAgents/app.easysourceflow.daemon.plist
```

`launchd` 模式使用独立运行目录：

```text
~/.local/share/easysourceflow/launchd
```

该目录会保存同步后的源码、专用虚拟环境、数据库和输出目录。脚本会在 plist 中写入 `PYTHONPATH`、配置文件路径、输出路径、`yt-dlp`、`ffmpeg` 和 `whisper-cli` 的实际路径，避免依赖登录 shell 的环境。

从 v0.2.x 升级时，`sync-runtime` 会检测旧 Python 3.9 虚拟环境并使用当前 Python 3.10+ 重建。重建后运行 `scripts/easysourceflow install-launchd`，让 plist 同步新的解释器和 site-packages 路径。

`sync-runtime` 会刷新项目源码和 `.env` 中的配置，同时保留 launchd `runtime.env` 中由本地 Web 控制台写入的模型、API Key、Fake-IP 信任和平台登录配置。这样更新运行副本不会把 Web 中已经验证并保存的当前模型覆盖回项目根目录的旧值。

## 8. MCP 配置

Codex / OpenClaw 需要配置 stdio MCP server，命令指向：

```bash
python3 -m easysourceflow_mcp.server
```

概念示例：

```toml
[mcp_servers.easysourceflow]
command = "python3"
args = ["-m", "easysourceflow_mcp.server"]
env = { PYTHONPATH = "/path/to/EasySourceFlow/src", EASYSOURCEFLOW_BASE_URL = "http://127.0.0.1:8765" }
```

OpenClaw 当前 CLI 可用以下命令注册：

```bash
openclaw mcp set easysourceflow '{"command":"python3","args":["-m","easysourceflow_mcp.server"],"env":{"PYTHONPATH":"/path/to/EasySourceFlow/src","EASYSOURCEFLOW_BASE_URL":"http://127.0.0.1:8765"}}'
openclaw gateway restart
```

验证：

```bash
openclaw mcp list
openclaw agent --agent varys --message '请调用 EasySourceFlow 的 MCP 健康检查工具，只返回它是否 ok。不要总结别的内容。' --json
```

具体配置文件路径以当前 Agent 客户端为准。

## 9. B 站 cookies

推荐使用导出的 cookies 文件，不默认读取浏览器 cookies。cookies 文件等同登录凭证。

推荐路径：

```text
~/.local/share/easysourceflow/secrets/bilibili-cookies.txt
```

建议权限：

```bash
chmod 700 ~/.local/share/easysourceflow/secrets
chmod 600 ~/.local/share/easysourceflow/secrets/bilibili-cookies.txt
```

不要在聊天、日志或文档里打印 cookies 内容。

## 10. 转写依赖

当前主路径：

```env
EASYSOURCEFLOW_TRANSCRIPTION_BACKEND=whisper_cpp
EASYSOURCEFLOW_WHISPER_CLI_PATH=whisper-cli
EASYSOURCEFLOW_WHISPER_MODEL_PATH=~/.local/share/easysourceflow/models/ggml-base.bin
```

`ffmpeg` 用于抽取音频，`whisper-cli` 用于本地转写。

## 11. 验证

```bash
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
scripts/easysourceflow health
scripts/easysourceflow cleanup-preview 14
scripts/easysourceflow backup
```

健康检查应确认：

- 输出目录可写。
- 模型名称、API 地址和凭证已配置。
- `yt-dlp` 可用。
- `ffmpeg` 可用。
- Whisper CLI 和模型可用。
- B 站 cookies 文件存在。
- Playwright 和 Chrome 可用。

健康检查不会调用外部模型。需要验证模型真实连通性时，在 Web“维护 → 模型”中手动点击“测试模型”；每次测试会产生一次模型请求。

Web 控制台应能打开：

```text
http://127.0.0.1:8765/
```

控制台应显示：

- 任务详情。
- 批量报告。
- 输出文件搜索和来源筛选。
- 健康检查失败时的修复提示。
- 清理预览和备份入口。

## 12. 升级和回滚

升级前：

- 备份 `var/easysourceflow.sqlite3`。
- 备份 `.env`。
- 确认当前测试通过。

升级后：

- 运行健康检查。
- 运行 `scripts/easysourceflow backup`。
- 用普通网页做一次总结。
- 用 B 站样例做一次任务提交或查询。

回滚：

- 恢复上一版代码目录。
- 恢复数据库备份。
- 不删除输出目录，避免误删历史总结。
