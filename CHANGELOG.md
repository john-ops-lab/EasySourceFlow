# Changelog

All notable changes to EasySourceFlow will be documented in this file.

This project follows semantic versioning while it remains pre-1.0: minor versions may include breaking changes, and patch versions should be backward compatible.

## [Unreleased]

### Added

- Official EasySourceFlow Agent Skill with workflows for direct Markdown delivery, Pro video summaries, and favorites.
- MCP tool annotations, structured results, and strict argument validation.
- Agent integration guide and reusable Skill installer command.

### Fixed

- Malformed JSON-RPC input now returns a protocol error instead of terminating the MCP process.
- Removed private development identifiers from LaunchAgent defaults and security scan examples.

### Security

- Added a redacted Gitleaks scan for the current tree and complete visible Git history in CI.

## [0.1.0] - 2026-07-02

### Added

- Local HTTP daemon and Web console for link, document, and video summarization.
- stdio MCP adapter for local agents.
- Web, WeChat, Bilibili, document upload, subtitle, and local ASR flows.
- Markdown output packages, favorites, search, cleanup, backup, and launchd helpers.
- OpenAI-compatible model configuration.

### Notes

- Default runtime is local-only at `127.0.0.1:8765`.
- macOS is the primary supported platform; Linux is expected to work for daemon/MCP flows but is not fully validated.
