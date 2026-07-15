"""Built-in local web console for EasySourceFlow."""

from __future__ import annotations

import html
import json
import heapq
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EasySourceFlow</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #18181b;
      --muted: #686877;
      --faint: #9a9aaa;
      --line: #e8e8ef;
      --paper: #f7f7fa;
      --panel: #ffffff;
      --panel-soft: #fbfbfd;
      --pink: #ff62b7;
      --pink-soft: #fff0f8;
      --blue: #3aa7ff;
      --blue-soft: #eef8ff;
      --green: #22a06b;
      --red: #d84c5f;
      --gold: #b7791f;
      --charcoal: #15151a;
      --shadow: 0 22px 70px rgba(19, 19, 26, .09);
      --soft-shadow: 0 10px 30px rgba(19, 19, 26, .06);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 14px;
    }
    button, input, textarea, select {
      font: inherit;
    }
    a { color: var(--blue); text-decoration-thickness: 1px; text-underline-offset: 3px; }
    .app-shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 264px minmax(0, 1fr);
      gap: 18px;
      padding: 10px;
    }
    .sidebar {
      min-height: calc(100vh - 20px);
      position: sticky;
      top: 10px;
      align-self: start;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .sidebar {
      background: rgba(255, 255, 255, .72);
      border-right: 1px solid var(--line);
      padding: 10px 8px;
    }
    .workspace {
      min-width: 0;
      padding: 34px 0 44px;
    }
    .workspace > .workspace-page {
      max-width: 1120px;
      margin: 0 auto;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 8px 14px;
    }
    .brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      color: #fff;
      font-weight: 850;
      background: linear-gradient(135deg, var(--pink), var(--blue));
      box-shadow: 0 10px 22px rgba(255, 98, 183, .24);
    }
    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.1;
      letter-spacing: 0;
      font-weight: 820;
    }
    .brand small {
      display: block;
      margin-top: 3px;
      color: var(--faint);
      font-size: 11px;
    }
    .date {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      color: var(--muted);
      text-align: left;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .nav-label {
      margin: 12px 10px 4px;
      color: var(--faint);
      font-size: 12px;
      font-weight: 700;
    }
    .nav-list {
      display: grid;
      gap: 6px;
    }
    .stack { display: grid; gap: 12px; }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--soft-shadow);
      border-radius: 14px;
      padding: 16px;
    }
    .hero {
      min-height: 246px;
      display: grid;
      place-items: end center;
      text-align: center;
      padding: 28px 16px 22px;
    }
    .hero h2 {
      margin: 18px 0 12px;
      font-size: clamp(28px, 4vw, 48px);
      line-height: 1.12;
      letter-spacing: 0;
      font-weight: 860;
    }
    .gradient-word {
      background: linear-gradient(90deg, var(--pink), #8f79ff, var(--blue));
      -webkit-background-clip: text;
      color: transparent;
    }
    .hero-badges {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 9px;
    }
    .notice-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 6px 14px;
      border-radius: 999px;
      border: 1px solid #ffd1e9;
      background: #fff7fb;
      color: #e53894;
      font-weight: 720;
    }
    .primary-card {
      max-width: 1120px;
      margin: 0 auto 18px;
      border-color: var(--line);
      border-radius: 12px;
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 0;
      overflow: hidden;
    }
    .composer-tabs {
      display: flex;
      gap: 6px;
      padding: 12px 12px 0;
      background: var(--panel);
    }
    .source-support {
      padding: 11px 24px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .source-support strong { color: var(--ink); font-weight: 650; }
    .source-tab {
      min-height: 38px;
      border: 0;
      border-radius: 8px;
      background: #f6f6f8;
      color: var(--muted);
      box-shadow: none;
      padding: 8px 14px;
    }
    .source-tab.active {
      background: #fff;
      color: var(--ink);
      box-shadow: 0 5px 18px rgba(19, 19, 26, .10);
    }
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    h2 {
      margin: 0;
      font-size: 16px;
      line-height: 1.2;
      letter-spacing: 0;
      font-weight: 730;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel-soft);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      color: var(--muted);
      white-space: nowrap;
    }
    label {
      display: block;
      margin: 9px 0 6px;
      font-size: 12px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    textarea, input, select {
      width: 100%;
      border: 1px solid var(--line);
      background: var(--panel-soft);
      color: var(--ink);
      border-radius: 10px;
      padding: 10px 11px;
      outline: none;
    }
    textarea {
      min-height: 112px;
      resize: vertical;
      line-height: 1.45;
    }
    textarea:focus, input:focus, select:focus {
      border-color: var(--pink);
      box-shadow: 0 0 0 4px rgba(255, 98, 183, .13);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    button {
      border: 1px solid var(--charcoal);
      border-radius: 8px;
      background: var(--charcoal);
      color: #ffffff;
      padding: 9px 12px;
      cursor: pointer;
      min-height: 38px;
      font-weight: 650;
      transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
    }
    #submit-button {
      min-width: 260px;
      min-height: 48px;
      font-size: 17px;
      margin: 18px auto 0;
      display: block;
    }
    button:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 18px rgba(32, 40, 35, .12);
    }
    button.secondary {
      background: transparent;
      color: var(--ink);
      border-color: var(--line);
    }
    button.danger {
      background: var(--red);
      border-color: var(--red);
      color: #fffaf0;
    }
    button:disabled {
      opacity: .55;
      cursor: wait;
      transform: none;
      box-shadow: none;
    }
    .status-line {
      margin-top: 10px;
      min-height: 22px;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .segmented {
      display: none;
      gap: 6px;
      margin-bottom: 12px;
      padding: 5px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #f4f4f7;
    }
    .tab-button {
      min-height: 40px;
      border: 0;
      background: transparent;
      color: var(--muted);
      box-shadow: none;
      padding: 9px 10px;
      justify-content: flex-start;
      text-align: left;
      width: 100%;
    }
    .tab-button:hover { transform: none; box-shadow: none; }
    .tab-button.active {
      color: var(--ink);
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: 0 8px 22px rgba(19, 19, 26, .07);
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .workspace-page { display: none; }
    .workspace-page.active { display: block; }
    .embedded-panel {
      display: block;
      margin-top: 18px;
    }
    .composer-body {
      padding: 12px;
    }
    .composer-mode { display: none; }
    .composer-mode.active { display: block; }
    .composer-body textarea {
      min-height: 112px;
      border-color: #ff7bc4;
      background: #fff;
      font-size: 15px;
    }
    .composer-tools {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
      margin-top: 10px;
    }
    .quality-toggle {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .quality-toggle input {
      position: absolute;
      width: 1px;
      height: 1px;
      margin: 0;
      opacity: 0;
      pointer-events: none;
      clip: rect(0 0 0 0);
      clip-path: inset(50%);
    }
    .quality-toggle label {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      margin: 0;
      padding: 6px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel-soft);
      color: var(--muted);
      cursor: pointer;
      font-family: inherit;
      font-size: 13px;
      font-weight: 680;
    }
    .quality-toggle input:checked + label {
      border-color: var(--charcoal);
      background: var(--charcoal);
      color: #fff;
    }
    .quick-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
      color: var(--muted);
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      max-width: 100%;
      min-height: 28px;
      padding: 5px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f7f7f9;
      color: var(--ink);
      font-size: 12px;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .upload-zone {
      border: 1px dashed #b8c3bc;
      border-radius: 10px;
      padding: 12px;
      background: #fbfbfd;
    }
    .upload-zone input { background: #fff; }
    .inline-option {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      cursor: pointer;
    }
    .inline-option input { width: 16px; height: 16px; margin: 0; }
    .upload-progress {
      width: 100%;
      height: 8px;
      margin-top: 10px;
      accent-color: var(--pink);
    }
    .retry-editor {
      display: grid;
      gap: 8px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }
    .retry-editor .retry-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 120px auto;
      gap: 8px;
      align-items: center;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin: 7px 0 0;
    }
    .health-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .check {
      border: 1px solid var(--line);
      background: var(--panel-soft);
      border-radius: 10px;
      padding: 9px 10px;
      min-height: 60px;
    }
    .check strong {
      display: block;
      font-size: 14px;
      margin-bottom: 5px;
    }
    .check span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .ok { border-left: 5px solid var(--green); }
    .bad { border-left: 5px solid var(--red); }
    .filters {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 154px;
      gap: 8px;
      margin-bottom: 10px;
    }
    .compact-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .task-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(320px, .95fr);
      gap: 12px;
      align-items: start;
    }
    .control-row {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      margin-top: 10px;
    }
    .control-row label {
      margin: 0;
    }
    .list {
      display: grid;
      gap: 8px;
      max-height: calc(100vh - 380px);
      overflow: auto;
      padding-right: 3px;
    }
    .row {
      border: 1px solid var(--line);
      background: var(--panel-soft);
      border-radius: 12px;
      padding: 10px;
      display: grid;
      gap: 6px;
    }
    .row:hover {
      border-color: #b8c3bc;
      background: #ffffff;
    }
    .row-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }
    .title {
      font-weight: 750;
      overflow-wrap: anywhere;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      overflow-wrap: anywhere;
    }
    .status {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      padding: 3px 7px;
      border: 1px solid var(--line);
      border-radius: 999px;
      white-space: nowrap;
    }
    .mini-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .link-button {
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--blue);
      padding: 5px 8px;
      min-height: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      font-weight: 650;
    }
    .link-button.danger {
      border-color: rgba(216, 76, 95, .35);
      background: #fff5f6;
      color: var(--red);
    }
    .detail {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel-soft);
      padding: 12px;
      display: grid;
      gap: 8px;
      max-height: 46vh;
      overflow: auto;
    }
    .detail h3 {
      margin: 0;
      font-size: 16px;
      line-height: 1.2;
    }
    .steps {
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .succeeded { color: var(--green); }
    .failed { color: var(--red); }
    .canceled { color: var(--muted); }
    .running, .queued { color: var(--gold); }
    .empty {
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 12px;
      padding: 18px;
      background: rgba(255, 255, 255, .62);
    }
    .succeeded.status, .ok .status { border-color: rgba(31,122,90,.25); background: rgba(31,122,90,.08); color: var(--green); }
    .failed.status { border-color: rgba(185,75,66,.25); background: rgba(185,75,66,.08); color: var(--red); }
    .running.status, .queued.status { border-color: rgba(173,119,23,.25); background: rgba(173,119,23,.10); color: var(--gold); }
    .quick-summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      max-width: 900px;
      margin: 0 auto 12px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel);
      padding: 10px;
    }
    .metric strong {
      display: block;
      font-size: 20px;
      line-height: 1;
      margin-bottom: 5px;
    }
    .metric span {
      color: var(--muted);
      font-size: 12px;
    }
    .panel-wrap {
      max-width: 900px;
      margin: 0 auto;
    }
    .sidebar-actions {
      margin-top: auto;
      display: grid;
      gap: 8px;
      padding: 8px;
    }
    .mini-section {
      box-shadow: none;
      padding: 12px;
    }
    .secondary-card {
      border-color: var(--line);
      box-shadow: var(--soft-shadow);
    }
    @media (max-width: 1180px) {
      .app-shell {
        grid-template-columns: 220px minmax(0, 1fr);
      }
    }
    @media (max-width: 820px) {
      .app-shell {
        display: block;
        padding: 8px;
      }
      .sidebar {
        position: static;
        min-height: 0;
      }
      .sidebar {
        border-right: 0;
        border-bottom: 1px solid var(--line);
        margin-bottom: 10px;
      }
      .nav-list {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
      .tab-button {
        justify-content: center;
        text-align: center;
        padding: 8px 4px;
      }
      .sidebar-actions {
        grid-template-columns: 1fr;
        margin-top: 8px;
      }
      .sidebar .quick-summary {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        max-width: none;
        margin: 0;
      }
      .workspace {
        padding: 18px 0 30px;
      }
      .hero {
        min-height: 210px;
      }
      .hero h2 {
        font-size: 28px;
      }
      .composer-tools, .filters, .compact-grid, .quick-summary, .settings-grid, .task-layout, .control-row, .retry-editor .retry-row {
        grid-template-columns: 1fr;
      }
      #submit-button {
        width: 100%;
        min-width: 0;
      }
      .list { max-height: none; }
    }

    /* YouTube-inspired operational workspace */
    :root {
      --ink: #0f0f0f;
      --muted: #606060;
      --faint: #8a8a8a;
      --line: #e5e5e5;
      --paper: #ffffff;
      --panel: #ffffff;
      --panel-soft: #f8f8f8;
      --pink: #ff0000;
      --pink-soft: #fff0f0;
      --blue: #065fd4;
      --blue-soft: #def1ff;
      --green: #0f9d58;
      --red: #d93025;
      --gold: #b06000;
      --charcoal: #0f0f0f;
      --shadow: 0 1px 2px rgba(15, 15, 15, .08);
      --soft-shadow: none;
    }
    html { background: #fff; }
    body {
      background: #fff;
      font-family: Inter, "PingFang SC", "Hiragino Sans GB", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }
    button, input, textarea, select { letter-spacing: 0; }
    button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible, summary:focus-visible {
      outline: 3px solid rgba(6, 95, 212, .3);
      outline-offset: 2px;
    }
    a { color: var(--ink); text-decoration: none; }
    a:hover { color: var(--pink); }
    .sr-only {
      position: absolute !important;
      width: 1px !important;
      height: 1px !important;
      padding: 0 !important;
      margin: -1px !important;
      overflow: hidden !important;
      clip: rect(0, 0, 0, 0) !important;
      white-space: nowrap !important;
      border: 0 !important;
    }
    .app-shell {
      min-height: 100vh;
      grid-template-columns: 220px minmax(0, 1fr);
      gap: 0;
      padding: 0;
    }
    .sidebar {
      top: 0;
      min-height: 100vh;
      height: 100vh;
      padding: 18px 12px 14px;
      gap: 22px;
      background: #fff;
      border-right: 1px solid var(--line);
    }
    .brand { gap: 11px; padding: 4px 10px 12px; }
    .brand h1 { font-size: 17px; font-weight: 750; }
    .brand-mark {
      position: relative;
      width: 34px;
      height: 24px;
      border-radius: 7px;
      background: var(--pink);
      box-shadow: none;
    }
    .brand-mark span {
      width: 0;
      height: 0;
      border-top: 5px solid transparent;
      border-bottom: 5px solid transparent;
      border-left: 8px solid #fff;
      margin-left: 2px;
    }
    .nav-list { gap: 4px; }
    .tab-button {
      position: relative;
      display: flex;
      align-items: center;
      gap: 13px;
      min-height: 46px;
      padding: 10px 14px;
      border: 0;
      border-radius: 8px;
      color: #272727;
      font-size: 14px;
      font-weight: 540;
    }
    .tab-button:hover { background: #f2f2f2; }
    .tab-button.active {
      border: 0;
      background: #f2f2f2;
      box-shadow: none;
      color: var(--ink);
      font-weight: 680;
    }
    .tab-button.active::before {
      content: "";
      position: absolute;
      left: 0;
      top: 10px;
      bottom: 10px;
      width: 3px;
      border-radius: 2px;
      background: var(--pink);
    }
    .nav-icon {
      width: 20px;
      height: 20px;
      display: grid;
      place-items: center;
      font-size: 22px;
      line-height: 1;
      font-weight: 400;
    }
    .sidebar-actions {
      position: relative;
      margin-top: auto;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 36px;
      gap: 4px 8px;
      align-items: center;
      padding: 14px 10px 4px;
      border-top: 1px solid var(--line);
    }
    .service-state, .sidebar-model { grid-column: 1; font-size: 12px; color: var(--muted); }
    .service-state { display: flex; gap: 7px; align-items: center; color: var(--ink); }
    .service-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--gold); }
    .service-dot.ok { background: var(--green); }
    .service-dot.bad { background: var(--red); }
    .sidebar-model strong { margin-left: 5px; color: var(--ink); }
    .sidebar-time { grid-column: 1; font-size: 11px; color: var(--faint); }
    .icon-button {
      width: 36px;
      min-width: 36px;
      height: 36px;
      min-height: 36px;
      padding: 0;
      display: inline-grid;
      place-items: center;
      border-radius: 50%;
      font-size: 20px;
    }
    #refresh-button { grid-column: 2; grid-row: 1 / span 3; }
    .workspace { padding: 0 40px 64px; background: #fff; }
    .workspace > .workspace-page { max-width: 1180px; }
    .workspace-page { padding-top: 30px; }
    .page-header {
      min-height: 62px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 20px;
      margin-bottom: 30px;
      padding: 0;
    }
    .page-header h2 { font-size: 24px; line-height: 1.25; font-weight: 720; }
    .page-header p { margin: 7px 0 0; color: var(--muted); font-size: 13px; }
    .header-model { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }
    .header-model strong { color: var(--ink); font-size: 13px; }
    section {
      padding: 0;
      border: 0;
      border-radius: 0;
      box-shadow: none;
      background: transparent;
    }
    .primary-card {
      max-width: 900px;
      margin: 0 auto 48px;
      border: 1px solid #d9d9d9;
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: visible;
    }
    .composer-tabs {
      display: inline-flex;
      gap: 0;
      margin: 20px 20px 0;
      padding: 3px;
      border-radius: 7px;
      background: #f2f2f2;
    }
    .source-tab {
      min-width: 104px;
      min-height: 36px;
      padding: 7px 18px;
      border-radius: 5px;
      background: transparent;
      color: var(--muted);
    }
    .source-tab:hover { transform: none; box-shadow: none; background: #e9e9e9; }
    .source-tab.active { background: #fff; color: var(--ink); box-shadow: 0 1px 3px rgba(15,15,15,.12); }
    .composer-body { padding: 18px 20px 20px; }
    .quality-toggle { margin: 0 0 14px; gap: 0; }
    .quality-toggle > span:first-child { margin-right: 12px; color: var(--ink); font-weight: 650; }
    .quality-toggle label {
      min-width: 78px;
      min-height: 32px;
      justify-content: center;
      padding: 5px 14px;
      border-radius: 0;
      background: #fff;
      font-size: 13px;
    }
    .quality-toggle label[for="quality-fast"] { border-radius: 6px 0 0 6px; }
    .quality-toggle label[for="quality-pro"] { margin-left: -1px; border-radius: 0 6px 6px 0; }
    .quality-toggle input:checked + label { border-color: var(--pink); background: #fff; color: var(--pink); z-index: 1; }
    .quality-note { margin-left: 10px; color: var(--faint); font-size: 12px; }
    .composer-input-wrap { position: relative; }
    .composer-body textarea {
      min-height: 160px;
      padding: 15px 48px 15px 15px;
      border-color: #cfcfcf;
      border-radius: 7px;
      background: #fff;
      font-size: 15px;
    }
    textarea:focus, input:focus, select:focus { border-color: #606060; box-shadow: 0 0 0 2px rgba(6, 95, 212, .16); }
    .clear-input { position: absolute; top: 9px; right: 9px; color: var(--muted); border: 0; background: transparent; }
    .clear-input:hover { background: #f2f2f2; box-shadow: none; transform: none; }
    .advanced-settings { margin-top: 12px; }
    .advanced-settings summary { width: fit-content; cursor: pointer; color: var(--muted); font-size: 13px; }
    .advanced-content { display: grid; gap: 8px; margin-top: 12px; padding: 14px; background: #f8f8f8; border-radius: 7px; }
    .advanced-content label { margin: 0; }
    label { font-family: inherit; font-size: 13px; color: var(--ink); }
    textarea, input, select { border-radius: 6px; background: #fff; }
    .composer-submit-row { display: flex; justify-content: flex-end; align-items: center; gap: 18px; margin-top: 16px; }
    .composer-submit-row .status-line { flex: 1; margin: 0; }
    #submit-button, #file-submit-button {
      min-width: 150px;
      min-height: 44px;
      margin: 0;
      border-color: var(--pink);
      border-radius: 6px;
      background: var(--pink);
      font-size: 15px;
    }
    #download-panel { max-width: 1080px; }
    .download-card { max-width: 760px; margin: 0 0 36px; }
    .download-form { padding: 22px; }
    .download-url-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
    .download-url-row input { min-height: 46px; font-size: 15px; }
    .download-options { display: flex; flex-wrap: wrap; align-items: end; gap: 18px; margin-top: 18px; }
    .download-option { display: grid; gap: 7px; }
    .download-type-toggle { display: inline-flex; }
    .download-type-toggle input { position: absolute; width: 1px; height: 1px; margin: 0; opacity: 0; pointer-events: none; }
    .download-type-toggle label {
      min-width: 88px;
      min-height: 38px;
      display: grid;
      place-items: center;
      padding: 7px 16px;
      border: 1px solid #d3d3d3;
      background: #fff;
      cursor: pointer;
    }
    .download-type-toggle label:first-of-type { border-radius: 6px 0 0 6px; }
    .download-type-toggle label:last-of-type { margin-left: -1px; border-radius: 0 6px 6px 0; }
    .download-type-toggle input:checked + label { z-index: 1; color: var(--pink); border-color: var(--pink); }
    #download-format { min-width: 170px; min-height: 38px; }
    #download-submit-button { min-width: 126px; min-height: 46px; background: var(--pink); border-color: var(--pink); }
    .download-note { margin: 16px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
    .download-progress { width: 100%; height: 5px; margin-top: 10px; accent-color: var(--pink); }
    #config-save-button { background: var(--pink); border-color: var(--pink); }
    #config-save-button:hover { background: #cc0000; border-color: #cc0000; }
    button { border-radius: 6px; background: var(--ink); border-color: var(--ink); }
    button:hover { transform: none; box-shadow: none; background: #272727; }
    button.secondary { background: #fff; border-color: #d3d3d3; }
    button.secondary:hover { background: #f2f2f2; }
    button:disabled { cursor: not-allowed; }
    .upload-zone {
      min-height: 188px;
      display: grid;
      place-items: center;
      align-content: center;
      gap: 7px;
      padding: 24px;
      border-color: #bdbdbd;
      border-radius: 7px;
      background: #fafafa;
      text-align: center;
    }
    .upload-zone.dragging { border-color: var(--pink); background: var(--pink-soft); }
    .upload-icon { font-size: 28px; color: var(--muted); }
    .upload-zone input { width: auto; max-width: 100%; border: 0; padding: 5px; background: transparent; }
    .upload-progress { accent-color: var(--pink); }
    .section-title { margin: 0 0 14px; }
    .section-title h2, .section-title h3 { margin: 0; font-size: 17px; font-weight: 700; }
    #tasks-panel.embedded-panel { max-width: 1080px; margin: 0 auto; padding-top: 24px; border-top: 1px solid var(--line); }
    .view-switch { display: flex; gap: 4px; }
    .view-switch-button {
      min-height: 32px;
      padding: 5px 12px;
      border: 0;
      background: transparent;
      color: var(--muted);
    }
    .view-switch-button.active { background: #f2f2f2; color: var(--ink); }
    #batches-panel.embedded-panel { max-width: 1080px; margin: 0 auto; }
    #batches-panel.embedded-panel:not(.task-view-active), #tasks-panel.embedded-panel:not(.task-view-active) { display: none; }
    .task-layout { grid-template-columns: minmax(0, 1.2fr) minmax(300px, .8fr); gap: 28px; }
    .filters { gap: 10px; margin-bottom: 16px; }
    .list { max-height: none; overflow: visible; padding: 0; gap: 0; }
    .row {
      padding: 14px 10px;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      background: #fff;
    }
    .row:hover { border-color: var(--line); background: #fafafa; }
    .row-head { align-items: center; }
    .title { color: var(--ink); font-weight: 650; }
    .meta { font-family: inherit; color: var(--muted); line-height: 1.45; }
    .status { font-family: inherit; border: 0; border-radius: 4px; background: #f2f2f2; }
    .link-button {
      border: 0;
      background: transparent;
      color: var(--blue);
      font-family: inherit;
      padding: 4px 6px;
    }
    .link-button:hover { background: #eef6ff; }
    .link-button.danger { border: 0; background: transparent; }
    .row .title.link-button { color: var(--ink); padding-left: 0; text-align: left; }
    .path-detail { color: var(--muted); font-size: 12px; }
    .path-detail summary { width: fit-content; cursor: pointer; color: var(--ink); }
    .detail { max-height: none; padding: 18px; border-radius: 7px; background: #fafafa; }
    .empty { border-radius: 6px; background: #fafafa; }
    #outputs-panel, #favorites-panel, #search-panel { max-width: 1080px; }
    .result-count { color: var(--muted); font-size: 12px; }
    #fulltext-button { display: block; margin: -54px 166px 18px auto; min-height: 38px; background: var(--pink); border-color: var(--pink); }
    #fulltext-results .meta:last-child { max-width: 850px; font-size: 13px; color: #3f3f3f; }
    .search-more { display: block; margin: 20px auto 0; }
    .search-more[hidden] { display: none; }
    .maintenance-layout { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 36px; align-items: start; }
    .maintenance-nav { display: grid; position: sticky; top: 20px; }
    .maintenance-tab {
      min-height: 44px;
      padding: 10px 12px;
      border: 0;
      border-left: 3px solid transparent;
      border-radius: 0;
      background: transparent;
      color: var(--ink);
      text-align: left;
      font-weight: 520;
    }
    .maintenance-tab:hover { background: #f7f7f7; }
    .maintenance-tab.active { border-left-color: var(--pink); background: #f2f2f2; color: var(--pink); font-weight: 680; }
    .maintenance-view { display: none; }
    .maintenance-view.active { display: block; }
    .maintenance-view > section, .maintenance-view > .embedded-panel { display: block; margin: 0; }
    .settings-section { padding: 22px 0; border-bottom: 1px solid var(--line); }
    .settings-section:first-child { padding-top: 0; }
    .settings-heading, .settings-action-row { display: flex; justify-content: space-between; gap: 24px; align-items: center; }
    .settings-section h2, .settings-section h3, .settings-heading h3, .settings-action-row h3 { margin: 0; font-size: 17px; }
    .settings-section p, .settings-heading p, .settings-action-row p { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
    .prompt-editor { width: 100%; min-height: 220px; margin-top: 18px; resize: vertical; line-height: 1.7; }
    .editor-meta { display: flex; justify-content: space-between; gap: 16px; margin-top: 8px; color: var(--muted); font-size: 12px; }
    .fixed-rule-list { margin: 12px 0 0; padding-left: 20px; color: #3f3f3f; font-size: 13px; line-height: 1.8; }
    .agent-status-list { margin-top: 8px; }
    .agent-status-row { display: grid; grid-template-columns: 150px minmax(0, 1fr) auto; gap: 18px; align-items: center; padding: 16px 0; border-bottom: 1px solid var(--line); }
    .agent-status-row:last-child { border-bottom: 0; }
    .agent-status-row strong { font-size: 14px; }
    .agent-status-row .meta { min-width: 0; overflow-wrap: anywhere; }
    .code-block { position: relative; margin-top: 14px; padding: 16px 48px 16px 16px; border: 1px solid var(--line); border-radius: 6px; background: #fafafa; color: #202124; font: 12px/1.65 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    .copy-code { position: absolute; top: 8px; right: 8px; width: 32px; height: 32px; padding: 0; }
    #settings-panel, #model-choice-panel, #system-panel { padding: 0; }
    #settings-panel > .section-title, #model-choice-panel > .section-title, #system-panel > .section-title { margin-bottom: 18px; }
    .settings-grid { grid-template-columns: 1fr; gap: 0; }
    .settings-grid > .row { padding: 20px 0; }
    .control-row { grid-template-columns: 140px minmax(0, 1fr); max-width: 760px; }
    #model-choice-panel .settings-grid > .row:first-child { background: #fafafa; border: 1px solid var(--line); border-radius: 7px; padding: 18px; margin-bottom: 16px; }
    #model-choice-panel .settings-grid > .row:last-child { padding-top: 18px; }
    .model-provider-list { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 14px 0 18px; }
    .model-provider-button { min-height: 42px; background: #fff; color: var(--ink); border-color: var(--line); }
    .model-provider-button.active { color: var(--pink); border-color: var(--pink); background: var(--pink-soft); }
    .unsaved-notice { display: none; margin: 14px 0 0; color: var(--gold); font-size: 12px; }
    .unsaved-notice.visible { display: block; }
    .health-grid { gap: 0; }
    .check { min-height: auto; padding: 16px 10px; border: 0; border-bottom: 1px solid var(--line); border-radius: 0; background: #fff; }
    .ok, .bad { border-left: 0; }
    #runtime-status .row { padding-left: 0; padding-right: 0; }
    .toast-region {
      position: fixed;
      z-index: 1000;
      right: 24px;
      bottom: 24px;
      display: grid;
      gap: 8px;
      pointer-events: none;
    }
    .toast {
      min-width: 240px;
      max-width: 380px;
      padding: 12px 14px;
      border-radius: 6px;
      background: #0f0f0f;
      color: #fff;
      box-shadow: 0 8px 28px rgba(15,15,15,.22);
      animation: toast-in .18s ease-out;
    }
    .toast.error { background: #b3261e; }
    @keyframes toast-in { from { opacity: 0; transform: translateY(8px); } }
    @media (max-width: 900px) {
      .workspace { padding: 0 24px 56px; }
      .task-layout, .maintenance-layout { grid-template-columns: 1fr; }
      .maintenance-nav { position: static; grid-template-columns: repeat(6, minmax(0, 1fr)); overflow-x: auto; }
      .maintenance-tab { text-align: center; border-left: 0; border-bottom: 3px solid transparent; white-space: nowrap; }
      .maintenance-tab.active { border-left: 0; border-bottom-color: var(--pink); }
    }
    @media (max-width: 700px) {
      body { padding-bottom: 72px; }
      .app-shell { display: block; padding: 0; }
      .sidebar {
        position: fixed;
        z-index: 100;
        top: auto;
        bottom: 0;
        left: 0;
        right: 0;
        width: 100%;
        min-height: 64px;
        height: auto;
        padding: 5px 8px max(5px, env(safe-area-inset-bottom));
        border: 0;
        border-top: 1px solid var(--line);
        background: rgba(255,255,255,.98);
      }
      .brand, .sidebar-actions { display: none; }
      .nav-list { grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0; }
      .tab-button {
        min-height: 54px;
        padding: 5px 2px;
        display: grid;
        place-items: center;
        align-content: center;
        gap: 2px;
        border-radius: 6px;
        font-size: 10px;
      }
      .tab-button.active { background: transparent; color: var(--pink); }
      .tab-button.active::before { display: none; }
      .nav-icon { height: 22px; font-size: 21px; }
      .workspace { padding: 0 16px 32px; }
      .workspace-page { padding-top: 20px; }
      .page-header { min-height: 48px; margin-bottom: 18px; }
      .page-header h2 { font-size: 21px; }
      .page-header p { display: none; }
      .header-model { font-size: 11px; }
      .primary-card { margin-bottom: 30px; }
      .composer-tabs { width: calc(100% - 32px); margin: 16px 16px 0; }
      .source-tab { flex: 1; min-width: 0; }
      .composer-body { padding: 14px 16px 16px; }
      .quality-toggle { flex-wrap: nowrap; }
      .quality-note { display: none; }
      .composer-body textarea { min-height: 130px; }
      .composer-submit-row { align-items: stretch; flex-direction: column; gap: 8px; }
      #submit-button, #file-submit-button { width: 100%; }
      .download-card { margin-bottom: 28px; }
      .download-form { padding: 16px; }
      .download-url-row { grid-template-columns: 1fr; }
      .download-options { align-items: stretch; gap: 12px; }
      .download-option, #download-format, #download-submit-button { width: 100%; }
      .download-type-toggle { display: flex; }
      .download-type-toggle label { flex: 1; }
      .filters, .compact-grid, .settings-grid, .task-layout, .control-row, .retry-editor .retry-row { grid-template-columns: 1fr; }
      #fulltext-button { margin: 0 0 18px; width: 100%; }
      .maintenance-nav { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: max-content; }
      .maintenance-tab { padding: 8px 12px; }
      .agent-status-row { grid-template-columns: 1fr auto; gap: 6px 12px; }
      .agent-status-row .meta { grid-column: 1 / -1; }
      .settings-heading, .settings-action-row { align-items: flex-start; }
      .model-provider-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .row-head { align-items: flex-start; }
      .toast-region { left: 12px; right: 12px; bottom: 90px; }
      .toast { min-width: 0; max-width: none; width: 100%; }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><span></span></div>
        <h1>EasySourceFlow</h1>
      </div>
      <div class="nav-list" role="tablist" aria-label="工作区">
        <button class="tab-button active" type="button" role="tab" aria-selected="true" aria-controls="submit-panel" data-tab="submit-panel"><span class="nav-icon" aria-hidden="true">＋</span><span>新总结</span></button>
        <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="download-panel" data-tab="download-panel"><span class="nav-icon" aria-hidden="true">↓</span><span>音视频下载</span></button>
        <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="outputs-panel" data-tab="outputs-panel"><span class="nav-icon" aria-hidden="true">▤</span><span>结果库</span></button>
        <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="favorites-panel" data-tab="favorites-panel"><span class="nav-icon" aria-hidden="true">☆</span><span>收藏夹</span></button>
        <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="search-panel" data-tab="search-panel"><span class="nav-icon" aria-hidden="true">⌕</span><span>全局搜索</span></button>
        <button class="tab-button" type="button" role="tab" aria-selected="false" aria-controls="maintenance-panel" data-tab="maintenance-panel"><span class="nav-icon" aria-hidden="true">⚙</span><span>维护</span></button>
      </div>
      <div class="sidebar-actions">
        <div class="service-state"><span class="service-dot" id="service-dot"></span><span id="service-label">服务状态检查中</span></div>
        <div class="sidebar-model">当前模型 <strong id="sidebar-model">-</strong></div>
        <div class="sidebar-time" id="clock"></div>
        <button class="icon-button secondary" id="refresh-button" type="button" title="刷新数据" aria-label="刷新数据">↻</button>
      </div>
      <div class="sr-only" aria-hidden="true">
        <span id="job-count">0</span><span id="output-count">0</span><span id="favorite-count">0</span><span id="batch-count">0</span>
      </div>
    </aside>

    <main class="workspace">
      <div id="submit-panel" class="workspace-page active">
        <header class="page-header">
          <div><h2>新总结</h2><p>提交链接或本地文件，结果会保存在结果库。</p></div>
          <div class="header-model"><span>当前模型</span><strong id="header-model">-</strong></div>
        </header>

        <section class="primary-card">
          <div class="composer-tabs">
            <button class="source-tab active" type="button" data-mode="link-mode">链接</button>
            <button class="source-tab" type="button" data-mode="file-mode">文件</button>
          </div>
          <div class="source-support">
            <strong>支持来源：</strong>普通网页、微信公众号、Bilibili、YouTube；文件支持 PDF、DOCX、EPUB、TXT、Markdown、字幕和 HTML。
          </div>
          <div class="composer-body">
            <div class="quality-toggle" aria-label="总结质量">
              <span>质量</span>
              <input id="quality-fast" name="summary-quality" type="radio" value="fast" checked>
              <label for="quality-fast">Fast</label>
              <input id="quality-pro" name="summary-quality" type="radio" value="pro">
              <label for="quality-pro">Pro</label>
              <span class="quality-note">视频自动使用 Pro</span>
            </div>
            <form id="submit-form" class="composer-mode active" data-mode-panel="link-mode">
              <div class="composer-input-wrap">
                <textarea id="links" autocomplete="off" spellcheck="false" placeholder="粘贴一个或多个链接，每行一个"></textarea>
                <button class="icon-button clear-input" id="clear-links-button" type="button" title="清空链接" aria-label="清空链接">×</button>
              </div>
              <details class="advanced-settings">
                <summary>高级设置</summary>
                <div class="advanced-content">
                  <label for="instruction">处理要求</label>
                  <input id="instruction" value="用中文总结，保留关键结论和出处。" autocomplete="off">
                  <label class="inline-option" for="force-refresh">
                    <input id="force-refresh" type="checkbox">
                    <span>忽略缓存，重新抓取并总结</span>
                  </label>
                </div>
              </details>
              <div class="composer-submit-row">
                <div class="status-line" id="submit-status" role="status" aria-live="polite"></div>
                <button id="submit-button" type="submit">开始总结</button>
              </div>
            </form>

            <div id="file-composer" class="composer-mode" data-mode-panel="file-mode">
              <div class="upload-zone">
                <div class="upload-icon" aria-hidden="true">↑</div>
                <strong>选择或拖入文件</strong>
                <input id="file-input" type="file" accept=".txt,.md,.markdown,.srt,.vtt,.html,.htm,.docx,.epub,.pdf,text/plain,text/markdown,text/html,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/epub+zip">
                <p class="hint" id="file-hint">支持 txt、md、字幕、HTML、DOCX、EPUB、PDF。文件会提交到本机服务。</p>
                <progress id="file-progress" class="upload-progress" max="100" value="0" hidden></progress>
              </div>
              <div class="composer-submit-row">
                <div class="status-line" id="file-status" role="status" aria-live="polite"></div>
                <button id="file-submit-button" type="button">开始总结</button>
              </div>
            </div>
          </div>
        </section>
        <div id="submit-secondary-panels"></div>
      </div>

      <section id="download-panel" class="workspace-page">
        <header class="page-header"><div><h2>音视频下载</h2><p>下载 Bilibili 或 YouTube 的单个视频、视频音轨。</p></div></header>
        <section class="primary-card download-card">
          <form id="download-form" class="download-form">
            <div class="download-url-row">
              <input id="download-url" type="url" autocomplete="off" spellcheck="false" placeholder="粘贴 Bilibili 或 YouTube 链接" aria-label="音视频链接">
              <button id="download-submit-button" type="submit">开始下载</button>
            </div>
            <div class="download-options">
              <div class="download-option">
                <label>下载内容</label>
                <div class="download-type-toggle" role="radiogroup" aria-label="下载内容">
                  <input id="download-type-video" name="download-type" type="radio" value="video" checked>
                  <label for="download-type-video">视频</label>
                  <input id="download-type-audio" name="download-type" type="radio" value="audio">
                  <label for="download-type-audio">音频</label>
                </div>
              </div>
              <div class="download-option">
                <label id="download-format-label" for="download-format">清晰度</label>
                <select id="download-format"></select>
              </div>
            </div>
            <p class="download-note">仅下载你有权保存的内容；不会下载播放列表，也不会绕过付费或 DRM 限制。MP3、M4A 转换以及分离音视频合并需要 FFmpeg。</p>
            <div class="status-line" id="download-status" role="status" aria-live="polite"></div>
          </form>
        </section>
        <div class="section-title"><div><h3>最近下载</h3><div class="status-line" id="download-queue-status"></div></div></div>
        <div class="list" id="downloads"></div>
      </section>

      <section id="tasks-panel" class="workspace-page">
        <div class="section-title">
          <div><h2>最近任务</h2><div class="status-line" id="queue-status"></div></div>
          <div class="view-switch" role="tablist" aria-label="任务视图">
            <button class="view-switch-button active" type="button" data-task-view="tasks-panel">任务</button>
            <button class="view-switch-button" type="button" data-task-view="batches-panel">批量</button>
          </div>
        </div>
        <span class="sr-only" id="queue-pill">live</span>
        <div class="filters">
          <input id="job-search" placeholder="搜索任务标题、链接或编号">
          <select id="job-status-filter">
            <option value="">全部状态</option>
            <option value="queued">等待</option>
            <option value="running">运行</option>
            <option value="succeeded">成功</option>
            <option value="failed">失败</option>
            <option value="canceled">已取消</option>
          </select>
        </div>
        <div class="task-layout">
          <div class="list" id="jobs"></div>
          <div>
            <div class="section-title">
              <h2>选中任务</h2>
              <span class="pill" id="detail-pill">none</span>
            </div>
            <div id="job-detail" class="empty">选择一个任务查看详情</div>
          </div>
        </div>
      </section>

      <section id="outputs-panel" class="workspace-page">
        <header class="page-header"><div><h2>结果库</h2><p>浏览、筛选并打开已经生成的 Markdown 总结。</p></div></header>
        <div class="section-title">
          <h3>全部结果</h3>
          <span class="result-count"><span id="output-count-visible">0</span> 项</span>
        </div>
        <div class="filters">
          <input id="output-search" placeholder="搜索标题、路径或来源">
          <select id="output-source">
            <option value="">全部来源</option>
          </select>
        </div>
        <div class="list" id="outputs"></div>
      </section>

      <section id="favorites-panel" class="workspace-page">
        <header class="page-header"><div><h2>收藏夹</h2><p>收藏内容包含总结和对应资源包副本。</p></div></header>
        <div class="section-title">
          <h3>已收藏</h3>
        </div>
        <div class="filters">
          <input id="favorite-search" placeholder="搜索收藏标题、路径或来源">
          <select id="favorite-source">
            <option value="">全部来源</option>
          </select>
        </div>
        <div class="list" id="favorites"></div>
      </section>

      <section id="search-panel" class="workspace-page">
        <header class="page-header"><div><h2>全局搜索</h2><p>搜索结果库中的标题和 Markdown 正文。</p></div></header>
        <div class="section-title">
          <h3>搜索结果</h3>
          <span class="result-count"><span id="search-count">0</span> 项</span>
        </div>
        <div class="filters">
          <input id="fulltext-query" placeholder="搜索 Markdown 正文">
          <select id="fulltext-source">
            <option value="">全部来源</option>
          </select>
        </div>
        <button id="fulltext-button" type="button">搜索</button>
        <div class="list" id="fulltext-results"></div>
        <button class="secondary search-more" id="search-more-button" type="button" hidden>显示更多</button>
      </section>

      <section id="batches-panel" class="workspace-page">
        <div class="section-title">
          <h2>批量报告</h2>
          <span class="pill">batch</span>
        </div>
        <div class="list" id="batches"></div>
      </section>

      <section id="system-panel" class="workspace-page">
        <div class="section-title">
          <h2>系统状态</h2>
          <span class="pill" id="health-pill">checking</span>
        </div>
        <div class="health-grid" id="health"></div>
      </section>

      <section id="settings-panel" class="workspace-page">
        <div class="section-title">
          <h2>模型配置</h2>
          <span class="pill">provider</span>
        </div>
        <div class="settings-grid">
          <div class="row">
            <div class="row-head">
              <span class="title">B 站扫码</span>
              <span class="status" id="bilibili-status-pill">checking</span>
            </div>
            <div class="meta" id="bilibili-account-status">读取状态中</div>
            <div class="actions">
              <button class="secondary" id="bilibili-open-login-button" type="button">打开扫码页</button>
              <button class="secondary" id="bilibili-import-button" type="button">导入 Chrome 登录态</button>
            </div>
            <div class="status-line" id="bilibili-action-status"></div>
          </div>

          <div class="row">
            <div class="row-head">
              <span class="title">YouTube 登录态</span>
              <span class="status" id="youtube-status-pill">checking</span>
            </div>
            <div class="meta" id="youtube-account-status">读取状态中</div>
            <div class="actions">
              <button class="secondary" id="youtube-open-login-button" type="button">打开 YouTube</button>
              <button class="secondary" id="youtube-import-button" type="button">接入 Chrome 实时登录态</button>
            </div>
            <div class="status-line" id="youtube-action-status"></div>
          </div>

          <div class="row">
            <div class="row-head">
              <span class="title">模型服务商</span>
              <span class="status" id="model-service-pill">checking</span>
            </div>
            <div class="control-row">
              <label for="model-service">服务商</label>
              <select id="model-service"></select>
            </div>
            <div class="control-row">
              <label for="config-api-key">API Key</label>
              <input id="config-api-key" type="password" autocomplete="new-password" placeholder="输入后保存；留空不修改">
            </div>
            <div class="control-row">
              <label for="config-clear-key">清除 Key</label>
              <input id="config-clear-key" type="checkbox" aria-label="清除模型 API Key">
            </div>
            <p class="hint" id="model-service-help">选择服务商后会自动使用对应接口地址。</p>
            <p class="hint" id="model-key-status">API Key 状态读取中</p>
            <div class="actions">
              <button id="config-save-button" type="button">保存配置</button>
            </div>
            <div class="status-line" id="config-status"></div>
          </div>
        </div>
        <div class="section-title" style="margin-top: 16px;">
          <h2>运行状态</h2>
          <span class="pill">status</span>
        </div>
        <div class="list" id="runtime-status"></div>
        <div class="status-line" id="model-status"></div>
      </section>

      <section id="model-choice-panel" class="workspace-page">
        <div class="section-title">
          <h2>模型选择</h2>
          <span class="pill" id="current-model-pill">checking</span>
        </div>
        <div class="settings-grid">
          <div class="row">
            <div class="row-head">
              <span class="title">当前模型</span>
              <span class="status" id="current-provider-pill">-</span>
            </div>
            <div class="meta" id="current-model-summary">读取状态中</div>
            <div class="meta" id="current-model-endpoint"></div>
          </div>
          <div class="row">
            <div class="row-head">
              <span class="title">选择模型</span>
              <span class="status">保存后生效</span>
            </div>
            <div class="control-row">
              <label for="model-name">默认模型</label>
              <select id="model-name"></select>
            </div>
            <div class="control-row">
              <label for="strong-model-name">Pro 模型</label>
              <select id="strong-model-name"></select>
            </div>
            <div class="actions">
              <button id="model-save-button" type="button">保存选择</button>
              <button class="secondary" id="settings-model-test-button" type="button">测试当前模型</button>
            </div>
            <div class="status-line" id="settings-model-status"></div>
          </div>
        </div>
      </section>

      <section id="maintenance-panel" class="workspace-page">
        <header class="page-header"><div><h2>维护</h2><p>管理账号、模型、运行状态和本地数据。</p></div></header>
        <div class="maintenance-layout">
          <nav class="maintenance-nav" aria-label="维护功能">
            <button class="maintenance-tab active" type="button" data-maintenance-tab="account-maintenance">账号与授权</button>
            <button class="maintenance-tab" type="button" data-maintenance-tab="model-maintenance">模型</button>
            <button class="maintenance-tab" type="button" data-maintenance-tab="prompt-maintenance">总结提示词</button>
            <button class="maintenance-tab" type="button" data-maintenance-tab="agent-maintenance">Agent 接入</button>
            <button class="maintenance-tab" type="button" data-maintenance-tab="system-maintenance">系统状态</button>
            <button class="maintenance-tab" type="button" data-maintenance-tab="storage-maintenance">存储与备份</button>
          </nav>
          <div class="maintenance-content">
            <div id="account-maintenance" class="maintenance-view active"></div>
            <div id="model-maintenance" class="maintenance-view"></div>
            <div id="prompt-maintenance" class="maintenance-view">
              <div class="settings-section">
                <div class="settings-heading">
                  <div><h3>通用总结提示词</h3><p>同一份硬性规则和 Markdown 模板适用于所有云端模型。单次特殊要求仍在新总结的“高级设置”中填写。</p></div>
                  <span class="status" id="prompt-state-pill">读取中</span>
                </div>
                <textarea id="summary-prompt" class="prompt-editor" aria-label="通用总结提示词" spellcheck="false"></textarea>
                <div class="editor-meta"><span id="prompt-editor-state">尚未修改</span><span id="prompt-char-count">0 / 8000</span></div>
                <div class="actions">
                  <button id="prompt-save-button" type="button">保存提示词</button>
                  <button class="secondary" id="prompt-reset-button" type="button">恢复默认</button>
                </div>
                <div class="status-line" id="prompt-status" role="status" aria-live="polite"></div>
              </div>
              <div class="settings-section">
                <h3>程序自动附加的上下文</h3>
                <p>以下运行时信息无需写进提示词，并且会随每个来源自动变化。本地抽取式兜底不调用模型，因此不使用这份提示词。</p>
                <ul class="fixed-rule-list" id="prompt-automatic-context"></ul>
              </div>
            </div>
            <div id="agent-maintenance" class="maintenance-view">
              <div class="settings-section">
                <div class="settings-heading">
                  <div><h3>Agent 接入状态</h3><p id="agent-status-message">正在检查本机服务、MCP 和 Skill。</p></div>
                  <span class="status" id="agent-state-pill">检查中</span>
                </div>
                <div class="agent-status-list" id="agent-status-list"></div>
              </div>
              <div class="settings-section">
                <h3>1. 配置 MCP</h3>
                <p>把下面通用示例加入 Agent 的 MCP 配置，并在本机把 &lt;PROJECT_ROOT&gt; 替换为项目目录。模型密钥仍由 EasySourceFlow 管理，不要复制给 Agent，也不要把替换后的本机路径提交到 Git。</p>
                <pre class="code-block"><code id="agent-mcp-config">读取中</code><button class="icon-button secondary copy-code" id="copy-mcp-config" type="button" title="复制 MCP 配置" aria-label="复制 MCP 配置">⧉</button></pre>
              </div>
              <div class="settings-section">
                <h3>2. 安装官方 Skill</h3>
                <p>Skill 让 Agent 原样交付总结、持续查询同一任务，并支持回复“收藏”。</p>
                <pre class="code-block"><code id="agent-skill-command">读取中</code><button class="icon-button secondary copy-code" id="copy-skill-command" type="button" title="复制安装命令" aria-label="复制安装命令">⧉</button></pre>
              </div>
              <div class="settings-section">
                <h3>3. 验证连接</h3>
                <p>让 Agent 调用 EasySourceFlow 的健康检查或提交一个链接。本页会记录最近一次真实 MCP 调用，自动刷新后显示为“最近已连接”。</p>
              </div>
            </div>
            <div id="system-maintenance" class="maintenance-view"></div>
            <div id="storage-maintenance" class="maintenance-view">
              <div class="settings-section" id="maintenance-status-card">
                <div class="settings-heading"><div><h3>上次维护</h3><p id="maintenance-status-text">读取状态中</p></div><span class="status" id="maintenance-status-pill">检查中</span></div>
              </div>
              <div class="settings-section settings-action-row">
                <div><h3>清理预览</h3><p>检查临时文件、旧输出和任务记录，不会直接删除文件。</p></div>
                <button class="secondary" id="cleanup-preview-button" type="button">查看预览</button>
              </div>
              <div class="settings-section settings-action-row">
                <div><h3>本地备份</h3><p>备份数据库和输出目录到本机备份目录。</p></div>
                <button class="secondary" id="backup-button" type="button">立即备份</button>
              </div>
              <div class="status-line" id="ops-status" role="status" aria-live="polite"></div>
            </div>
          </div>
        </div>
        <div id="maintenance-secondary-panels" hidden></div>
      </section>
    </main>
  </div>
  <div class="toast-region" id="toast-region" aria-live="polite" aria-atomic="true"></div>

  <script>
    const state = { outputs: [], favorites: [], favoritePaths: new Set(), jobs: [], downloads: [], outputsByPath: new Map(), activeBatch: null, activeJob: null, queue: null, settingsDirty: false, promptDirty: false, prompt: null, agent: null, model: null, modelServices: [], initialized: false, refreshing: false, searchResults: [], searchQuery: '', searchVisibleCount: 20 };
    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));

    function tickClock() {
      $('clock').textContent = new Date().toLocaleString();
    }

    const panelRoutes = {
      'submit-panel': 'new',
      'download-panel': 'downloads',
      'outputs-panel': 'results',
      'favorites-panel': 'favorites',
      'search-panel': 'search',
      'maintenance-panel': 'maintenance'
    };

    function activateTab(panelId, updateRoute = true) {
      const target = $(panelId) ? panelId : 'submit-panel';
      document.querySelectorAll('.tab-button').forEach((button) => {
        const selected = button.dataset.tab === target;
        button.classList.toggle('active', selected);
        button.setAttribute('aria-selected', selected ? 'true' : 'false');
        button.tabIndex = selected ? 0 : -1;
      });
      document.querySelectorAll('.workspace-page').forEach((panel) => {
        panel.classList.toggle('active', panel.id === target);
      });
      if (updateRoute) {
        const route = panelRoutes[target] || 'new';
        const nextHash = `#${route}`;
        if (location.hash !== nextHash) history.pushState(null, '', nextHash);
      }
      window.scrollTo({ top: 0, behavior: 'instant' });
    }

    function mergePanels() {
      embedPanel('tasks-panel', 'submit-secondary-panels');
      embedPanel('batches-panel', 'submit-secondary-panels');
      $('tasks-panel').classList.add('task-view-active');
      organizeMaintenancePanels();
    }

    function embedPanel(panelId, containerId) {
      const panel = $(panelId);
      const container = $(containerId);
      if (!panel || !container) return;
      panel.classList.remove('workspace-page', 'active');
      panel.classList.add('embedded-panel');
      container.appendChild(panel);
    }

    function organizeMaintenancePanels() {
      const settingsPanel = $('settings-panel');
      const account = $('account-maintenance');
      const model = $('model-maintenance');
      const system = $('system-maintenance');
      const bilibiliRow = $('bilibili-import-button')?.closest('.row');
      const youtubeRow = $('youtube-import-button')?.closest('.row');
      const modelProviderRow = $('model-service')?.closest('.row');
      [bilibiliRow, youtubeRow].forEach((row) => {
        if (!row) return;
        row.classList.add('settings-section');
        account.appendChild(row);
      });
      const modelChoice = $('model-choice-panel');
      modelChoice.classList.remove('workspace-page');
      modelChoice.classList.add('embedded-panel');
      model.appendChild(modelChoice);
      if (modelProviderRow) {
        modelProviderRow.classList.add('settings-section');
        model.appendChild(modelProviderRow);
      }
      const serviceRow = $('model-service').closest('.control-row');
      if (serviceRow) serviceRow.classList.add('sr-only');
      const providerList = document.createElement('div');
      providerList.id = 'model-provider-list';
      providerList.className = 'model-provider-list';
      modelProviderRow?.insertBefore(providerList, modelProviderRow.querySelector('.control-row'));
      const unsaved = document.createElement('div');
      unsaved.id = 'model-unsaved-notice';
      unsaved.className = 'unsaved-notice';
      unsaved.textContent = '有尚未保存的更改。自动刷新不会覆盖这些内容。';
      modelProviderRow?.appendChild(unsaved);
      $('config-save-button').textContent = '保存并测试';
      $('model-save-button').hidden = true;

      const healthPanel = $('system-panel');
      healthPanel.classList.remove('workspace-page');
      healthPanel.classList.add('embedded-panel');
      system.appendChild(healthPanel);
      const runtime = $('runtime-status');
      const runtimeSection = document.createElement('div');
      runtimeSection.className = 'settings-section';
      runtimeSection.innerHTML = '<div class="section-title"><h3>运行配置</h3></div>';
      runtimeSection.appendChild(runtime);
      system.appendChild(runtimeSection);
      system.appendChild($('model-status'));
      settingsPanel.remove();
    }

    function activateMaintenanceTab(viewId, updateRoute = true) {
      const target = $(viewId) ? viewId : 'account-maintenance';
      document.querySelectorAll('.maintenance-tab').forEach((button) => {
        button.classList.toggle('active', button.dataset.maintenanceTab === target);
      });
      document.querySelectorAll('.maintenance-view').forEach((view) => {
        view.classList.toggle('active', view.id === target);
      });
      if (updateRoute) {
        const name = target.replace('-maintenance', '');
        history.pushState(null, '', `#maintenance/${name}`);
      }
    }

    function activateTaskView(panelId) {
      document.querySelectorAll('[data-task-view]').forEach((button) => {
        button.classList.toggle('active', button.dataset.taskView === panelId);
      });
      ['tasks-panel', 'batches-panel'].forEach((id) => $(id).classList.toggle('task-view-active', id === panelId));
    }

    function restoreRoute() {
      const route = location.hash.replace(/^#/, '') || 'new';
      if (route.startsWith('maintenance')) {
        activateTab('maintenance-panel', false);
        const view = route.split('/')[1] || 'account';
        activateMaintenanceTab(`${view}-maintenance`, false);
        return;
      }
      const panelId = Object.entries(panelRoutes).find(([, name]) => name === route)?.[0] || 'submit-panel';
      activateTab(panelId, false);
    }

    function toast(message, kind = 'info') {
      const item = document.createElement('div');
      item.className = `toast ${kind === 'error' ? 'error' : ''}`;
      item.textContent = message;
      $('toast-region').appendChild(item);
      setTimeout(() => item.remove(), 3600);
    }

    function activateComposerMode(mode) {
      document.querySelectorAll('.source-tab[data-mode]').forEach((button) => {
        button.classList.toggle('active', button.dataset.mode === mode);
      });
      document.querySelectorAll('.composer-mode').forEach((panel) => {
        panel.classList.toggle('active', panel.dataset.modePanel === mode);
      });
      if (mode === 'file-mode') {
        $('file-input').focus();
      } else {
        $('links').focus();
      }
    }

    async function getJson(url, options) {
      const response = await fetch(url, options);
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        throw new Error(`服务返回了无效结果 (${response.status})`);
      }
      if (!response.ok) {
        throw new Error(data?.error?.message || response.statusText);
      }
      return data;
    }

    async function submitLinks(event) {
      event.preventDefault();
      const urls = $('links').value.split(/\\n+/).map((line) => line.trim()).filter(Boolean);
      const instruction = $('instruction').value.trim();
      const summaryQuality = selectedSummaryQuality();
      const forceRefresh = $('force-refresh').checked;
      if (!urls.length) {
        $('submit-status').textContent = '没有链接';
        return;
      }
      $('submit-button').disabled = true;
      $('submit-status').textContent = '提交中';
      try {
        if (urls.length === 1) {
          const job = await getJson('/jobs', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ url: urls[0], instruction, summary_quality: summaryQuality, force_refresh: forceRefresh })
          });
          state.activeJob = job.job_id;
          $('submit-status').textContent = `任务 ${job.job_id}`;
          toast('任务已提交');
          activateTab('submit-panel');
        } else {
          const batch = await getJson('/batches', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ urls, instruction, summary_quality: summaryQuality, force_refresh: forceRefresh })
          });
          state.activeBatch = batch.batch_id;
          $('submit-status').textContent = `批量 ${batch.batch_id}`;
          toast(`已提交 ${urls.length} 个链接`);
          activateTab('submit-panel');
        }
        $('links').value = '';
        await refreshAll();
      } catch (error) {
        $('submit-status').textContent = error.message;
        toast(`提交失败：${error.message}`, 'error');
      } finally {
        $('submit-button').disabled = false;
      }
    }

    async function postJson(url, payload) {
      return getJson(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload || {})
      });
    }

    function selectedSummaryQuality() {
      return document.querySelector('input[name="summary-quality"]:checked')?.value || 'fast';
    }

    function selectedDownloadType() {
      return document.querySelector('input[name="download-type"]:checked')?.value || 'video';
    }

    function updateDownloadFormats() {
      const type = selectedDownloadType();
      const options = type === 'video'
        ? [['1080p', '1080p'], ['720p', '720p'], ['best', '最高可用画质']]
        : [['mp3', 'MP3'], ['m4a', 'M4A'], ['original', '原始音频']];
      $('download-format-label').textContent = type === 'video' ? '清晰度' : '音频格式';
      $('download-format').innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
    }

    async function submitDownload(event) {
      event.preventDefault();
      const url = $('download-url').value.trim();
      if (!url) {
        $('download-status').textContent = '请先粘贴链接';
        return;
      }
      $('download-submit-button').disabled = true;
      $('download-status').textContent = '正在创建下载任务';
      try {
        const job = await postJson('/downloads', {
          url,
          media_type: selectedDownloadType(),
          format: $('download-format').value
        });
        $('download-url').value = '';
        $('download-status').textContent = `任务已创建：${job.job_id}`;
        toast('下载任务已创建');
        await loadDownloads();
      } catch (error) {
        $('download-status').textContent = `提交失败：${error.message}`;
        toast(`提交失败：${error.message}`, 'error');
      } finally {
        $('download-submit-button').disabled = false;
      }
    }

    async function loadDownloads() {
      const [data, queue] = await Promise.all([getJson('/downloads?limit=30'), getJson('/downloads/queue')]);
      state.downloads = data.items || [];
      const counts = queue.counts || {};
      $('download-queue-status').textContent = `等待 ${counts.queued || 0} · 下载中 ${counts.running || 0} · 已完成 ${counts.succeeded || 0}`;
      renderDownloads();
    }

    function renderDownloads() {
      $('downloads').innerHTML = (state.downloads || []).map((job) => {
        const result = job.result || {};
        const payload = job.request_payload || {};
        const typeLabel = (result.media_type || payload.media_type) === 'audio' ? '音频' : '视频';
        const format = result.format || payload.format || '-';
        const progress = Math.round((job.progress || 0) * 100);
        const size = result.file_size ? ` · ${formatBytes(result.file_size)}` : '';
        const error = job.error_message ? `<div class="meta">${esc(job.error_message)}</div>` : '';
        const download = job.status === 'succeeded' && result.download_url
          ? `<a class="link-button" href="${esc(result.download_url)}" download>下载文件</a>` : '';
        const cancel = ['queued', 'running'].includes(job.status)
          ? `<button class="link-button" type="button" onclick="cancelDownload('${esc(job.job_id)}')">取消</button>` : '';
        const retry = ['failed', 'canceled'].includes(job.status)
          ? `<button class="link-button" type="button" onclick="retryDownload('${esc(job.job_id)}')">重试</button>` : '';
        return `
          <div class="row">
            <div class="row-head">
              <div class="title">${esc(job.title || job.url)}</div>
              <span class="status ${esc(job.status)}">${esc(statusLabel(job.status))}</span>
            </div>
            <div class="meta">${esc(downloadSourceLabel(job.url))} · ${typeLabel} · ${esc(format.toUpperCase())}${size} · ${esc(formatJobTime(job.updated_at || job.created_at))}</div>
            ${job.status === 'running' ? `<progress class="download-progress" max="100" value="${progress}" aria-label="下载进度 ${progress}%"></progress><div class="meta">${esc(downloadStageLabel(job.stage))} · ${progress}%</div>` : ''}
            ${error}
            ${(download || cancel || retry) ? `<div class="mini-actions">${download}${cancel}${retry}</div>` : ''}
          </div>
        `;
      }).join('') || '<div class="empty">暂无下载记录</div>';
    }

    function downloadSourceLabel(url) {
      const value = String(url || '');
      if (/bilibili[.]com|b23[.]tv/i.test(value)) return 'Bilibili';
      if (/youtube[.]com|youtu[.]be/i.test(value)) return 'YouTube';
      return '其他来源';
    }

    function downloadStageLabel(stage) {
      return ({ preparing_download: '正在准备', downloading: '正在下载', finalizing_download: '正在合并或转换' })[stage] || '正在处理';
    }

    function formatBytes(value) {
      const bytes = Number(value) || 0;
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
      return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
    }

    async function cancelDownload(jobId) {
      try {
        await postJson(`/downloads/${encodeURIComponent(jobId)}/cancel`, {});
        toast('下载任务已取消');
        await loadDownloads();
      } catch (error) {
        toast(`取消失败：${error.message}`, 'error');
      }
    }

    async function retryDownload(jobId) {
      try {
        await postJson(`/downloads/${encodeURIComponent(jobId)}/retry`, {});
        toast('下载任务已重新创建');
        await loadDownloads();
      } catch (error) {
        toast(`重试失败：${error.message}`, 'error');
      }
    }

    async function submitLocalFile() {
      const file = $('file-input').files[0];
      if (!file) {
        $('file-status').textContent = '没有选择文件';
        return;
      }
      if (file.size > 20 * 1024 * 1024) {
        $('file-status').textContent = '文件超过 20 MB，请先拆分或提取正文';
        return;
      }
      $('file-submit-button').disabled = true;
      $('file-status').textContent = '读取文件中';
      $('file-progress').hidden = false;
      $('file-progress').value = 0;
      try {
        const dataBase64 = await fileToBase64(file, (percent) => {
          $('file-progress').value = Math.round(percent * 0.35);
          $('file-status').textContent = `读取文件 ${Math.round(percent)}%`;
        });
        const job = await postJsonWithProgress('/documents', {
          title: file.name,
          mime_type: file.type,
          data_base64: dataBase64,
          instruction: $('instruction').value.trim(),
          summary_quality: selectedSummaryQuality(),
          force_refresh: $('force-refresh').checked
        }, (percent) => {
          const total = 35 + Math.round(percent * 0.65);
          $('file-progress').value = total;
          $('file-status').textContent = `上传文件 ${total}%`;
        });
        state.activeJob = job.job_id;
        $('file-progress').value = 100;
        $('file-status').textContent = `任务 ${job.job_id}`;
        toast('文件已提交');
        activateTab('submit-panel');
        await refreshAll();
      } catch (error) {
        $('file-status').textContent = error.message;
        toast(`文件提交失败：${error.message}`, 'error');
      } finally {
        $('file-submit-button').disabled = false;
      }
    }

    function fileToBase64(file, onProgress) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const text = String(reader.result || '');
          resolve(text.includes(',') ? text.split(',', 2)[1] : text);
        };
        reader.onprogress = (event) => {
          if (event.lengthComputable && onProgress) onProgress((event.loaded / event.total) * 100);
        };
        reader.onerror = () => reject(reader.error || new Error('读取文件失败'));
        reader.readAsDataURL(file);
      });
    }

    function postJsonWithProgress(url, payload, onProgress) {
      return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open('POST', url);
        request.setRequestHeader('content-type', 'application/json');
        request.upload.onprogress = (event) => {
          if (event.lengthComputable && onProgress) onProgress((event.loaded / event.total) * 100);
        };
        request.onerror = () => reject(new Error('上传失败，请检查本机服务'));
        request.onload = () => {
          let data = {};
          try { data = JSON.parse(request.responseText || '{}'); } catch (error) { reject(new Error('服务返回了无效结果')); return; }
          if (request.status < 200 || request.status >= 300) {
            reject(new Error(data?.error?.message || `上传失败 (${request.status})`));
            return;
          }
          resolve(data);
        };
        request.send(JSON.stringify(payload || {}));
      });
    }

    async function loadHealth() {
      const data = await getJson('/health');
      const runtime = data.runtime || {};
      const checks = runtime.checks || [];
      $('health-pill').textContent = `${runtime.ok ? '正常' : '需处理'} · v${data.version || '-'}`;
      $('service-dot').className = `service-dot ${runtime.ok ? 'ok' : 'bad'}`;
      $('service-label').textContent = runtime.ok ? '服务正常' : '服务需处理';
      $('health').innerHTML = checks.map((check) => `
        <div class="check ${check.ok ? 'ok' : 'bad'}">
          <strong>${esc(check.name)}</strong>
          <span>${esc(check.message)}</span>
          ${check.fix ? `<span>处理：${esc(check.fix)}</span>` : ''}
        </div>
      `).join('') || '<div class="empty">暂无检查项目</div>';
    }

    async function loadOutputs() {
      const data = await getJson('/outputs');
      const items = data.items || [];
      state.outputs = items;
      state.outputsByPath = new Map(items.map((item) => [item.output_markdown_path, item]));
      $('output-count').textContent = data.limited ? `${items.length}+` : String(items.length);
      $('output-count-visible').textContent = data.limited ? `${items.length}+` : String(items.length);
      renderOutputs();
      renderOutputSources(data.source_counts || {});
    }

    async function loadFavorites() {
      const data = await getJson('/favorites');
      const items = data.items || [];
      state.favorites = items;
      state.favoritePaths = new Set(items.map((item) => item.relative_path));
      $('favorite-count').textContent = data.limited ? `${items.length}+` : String(items.length);
      renderFavorites();
      renderFavoriteSources(data.source_counts || {});
    }

    function renderOutputSources(counts) {
      const select = $('output-source');
      const current = select.value;
      const options = ['<option value="">全部来源</option>'].concat(Object.entries(counts).map(([name, count]) => (
        `<option value="${esc(name)}">${esc(name)} (${count})</option>`
      )));
      select.innerHTML = options.join('');
      select.value = current;
      const searchSelect = $('fulltext-source');
      const searchCurrent = searchSelect.value;
      searchSelect.innerHTML = options.join('');
      searchSelect.value = searchCurrent;
    }

    function renderFavoriteSources(counts) {
      const select = $('favorite-source');
      const current = select.value;
      const options = ['<option value="">全部来源</option>'].concat(Object.entries(counts).map(([name, count]) => (
        `<option value="${esc(name)}">${esc(name)} (${count})</option>`
      )));
      select.innerHTML = options.join('');
      select.value = current;
    }

    function renderOutputs() {
      const q = $('output-search').value.trim().toLowerCase();
      const source = $('output-source').value;
      const items = state.outputs.filter((item) => {
        const haystack = `${item.title} ${item.relative_path} ${item.source_type}`.toLowerCase();
        return (!q || haystack.includes(q)) && (!source || item.source_type === source);
      });
      $('outputs').innerHTML = items.map((item) => `
        ${(() => {
          const isFavorite = item.is_favorite || state.favoritePaths?.has(item.relative_path);
          return `
        <div class="row result-row">
          <div class="row-head">
            <a class="title" href="${esc(item.view_url)}">${esc(item.title)}</a>
            <span class="status">${esc(item.source_type)}</span>
          </div>
          <div class="meta">${esc(item.date)} · 更新于 ${esc(item.updated_at)} · ${Math.ceil(item.size / 1024)} KB</div>
          <details class="path-detail"><summary>文件信息</summary><div class="meta">${esc(item.relative_path)}</div></details>
          <div class="mini-actions">
            <button class="link-button" type="button" data-favorite-path="${esc(item.relative_path)}" onclick="favoriteFromList(this)" ${isFavorite ? 'disabled' : ''}>${isFavorite ? '已收藏' : '收藏'}</button>
          </div>
        </div>
          `;
        })()}
      `).join('') || '<div class="empty">暂无输出</div>';
    }

    function renderFavorites() {
      const q = $('favorite-search').value.trim().toLowerCase();
      const source = $('favorite-source').value;
      const items = (state.favorites || []).filter((item) => {
        const haystack = `${item.title} ${item.relative_path} ${item.source_type}`.toLowerCase();
        return (!q || haystack.includes(q)) && (!source || item.source_type === source);
      });
      $('favorites').innerHTML = items.map((item) => `
        <div class="row">
          <div class="row-head">
            <a class="title" href="${esc(item.view_url)}">${esc(item.title)}</a>
            <span class="status">${esc(item.source_type)}</span>
          </div>
          <div class="meta">${esc(item.date)} · 更新于 ${esc(item.updated_at)} · ${Math.ceil(item.size / 1024)} KB</div>
          <div class="mini-actions">
            <button class="link-button danger" type="button" data-favorite-path="${esc(item.relative_path)}" onclick="deleteFavorite(this)">删除</button>
          </div>
        </div>
      `).join('') || '<div class="empty">暂无收藏</div>';
    }

    async function favoriteFromList(button) {
      const relativePath = button.dataset.favoritePath;
      button.disabled = true;
      $('submit-status').textContent = '正在收藏';
      try {
        const result = await postJson('/favorites', { relative_path: relativePath });
        button.textContent = '已收藏';
        $('submit-status').textContent = '已加入收藏夹';
        toast('已加入收藏夹');
        await Promise.allSettled([loadFavorites(), loadOutputs()]);
      } catch (error) {
        button.disabled = false;
        $('submit-status').textContent = `收藏失败：${error.message}`;
        toast(`收藏失败：${error.message}`, 'error');
      }
    }

    async function deleteFavorite(button) {
      const relativePath = button.dataset.favoritePath;
      if (!confirm('确认彻底删除这份收藏副本和它的资源包？原结果库文件不会删除。')) return;
      button.disabled = true;
      button.textContent = '删除中';
      $('submit-status').textContent = '正在删除收藏';
      try {
        await postJson('/favorites/delete', { relative_path: relativePath });
        $('submit-status').textContent = '收藏已删除';
        toast('收藏已彻底删除');
        await Promise.allSettled([loadFavorites(), loadOutputs()]);
      } catch (error) {
        button.disabled = false;
        button.textContent = '删除';
        $('submit-status').textContent = `删除失败：${error.message}`;
        toast(`删除失败：${error.message}`, 'error');
      }
    }

    function outputLink(path) {
      const item = state.outputsByPath.get(path);
      if (!item) return '';
      return `<a href="${esc(item.view_url)}" target="_blank" rel="noreferrer">打开结果</a>`;
    }

    async function loadJobs() {
      const [data, queue] = await Promise.all([getJson('/jobs?limit=50'), getJson('/queue')]);
      state.queue = queue;
      const counts = queue.counts || {};
      $('queue-status').textContent = `队列：等待 ${counts.queued || 0} · 运行 ${counts.running || 0} · 已取消 ${counts.canceled || 0}`;
      const items = data.items || [];
      state.jobs = items;
      $('job-count').textContent = String(items.length);
      $('queue-pill').textContent = queue.active_limited ? 'limited' : 'live';
      renderJobs();
      if (state.activeJob) {
        await showJob(state.activeJob, false);
      }
    }

    function renderJobs() {
      const q = $('job-search').value.trim().toLowerCase();
      const status = $('job-status-filter').value;
      const items = (state.jobs || []).filter((job) => {
        const haystack = `${job.job_id} ${job.title || ''} ${job.url || ''} ${job.stage || ''}`.toLowerCase();
        return (!q || haystack.includes(q)) && (!status || job.status === status);
      });
      const visibleItems = items.slice(0, 12);
      $('jobs').innerHTML = visibleItems.map((job) => {
        const result = job.result || {};
        const out = result.output_markdown_path ? outputLink(result.output_markdown_path) : '';
        const err = job.error_message ? `<div class="meta">${esc(job.error_code)} · ${esc(job.error_message)}</div>` : '';
        const transcript = transcriptMeta(result);
        const cancel = ['queued', 'running'].includes(job.status) ? `<button class="link-button" type="button" onclick="cancelJob('${esc(job.job_id)}')">取消</button>` : '';
        const quality = (job.summary_quality || result.summary_quality || 'fast').toLowerCase() === 'pro' ? 'Pro' : 'Fast';
        return `
          <div class="row">
            <div class="row-head">
              <button class="link-button title" type="button" onclick="showJob('${esc(job.job_id)}')">${esc(job.title || job.url)}</button>
              <span class="status ${esc(job.status)}">${esc(statusLabel(job.status))}</span>
            </div>
            <div class="meta">${esc(jobSourceLabel(job))} · ${quality} · ${esc(formatJobTime(job.updated_at || job.created_at))}${job.status === 'running' ? ` · ${Math.round((job.progress || 0) * 100)}%` : ''}</div>
            ${transcript ? `<div class="meta">${transcript}</div>` : ''}
            ${err}
            ${(out || cancel) ? `<div class="mini-actions">${out}${cancel}</div>` : ''}
            <details class="path-detail"><summary>任务信息</summary><div class="meta">${esc(job.job_id)} · ${esc(job.stage)} · ${esc(job.url)}</div></details>
          </div>
        `;
      }).join('') || '<div class="empty">暂无任务</div>';
    }

    function statusLabel(status) {
      return ({ queued: '等待', running: '进行中', succeeded: '已完成', failed: '失败', canceled: '已取消' })[status] || status || '-';
    }

    function jobSourceLabel(job) {
      if (job.request_kind === 'document') return '本地文件';
      const url = String(job.url || '');
      if (/bilibili[.]com|b23[.]tv/i.test(url)) return 'Bilibili';
      if (/youtube[.]com|youtu[.]be/i.test(url)) return 'YouTube';
      if (/mp[.]weixin[.]qq[.]com/i.test(url)) return '微信公众号';
      return '网页';
    }

    function formatJobTime(value) {
      if (!value) return '-';
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    async function showJob(jobId, remember = true) {
      if (remember) state.activeJob = jobId;
      const job = await getJson(`/jobs/${encodeURIComponent(jobId)}`);
      const result = job.result || {};
      $('detail-pill').textContent = job.status;
      $('job-detail').className = 'detail';
      const steps = (job.error_next_steps || []).map((step) => `<li>${esc(step)}</li>`).join('');
      const out = result.output_markdown_path ? outputLink(result.output_markdown_path) : '';
      const transcript = transcriptMeta(result);
      const cancel = ['queued', 'running'].includes(job.status) ? `<button class="link-button" type="button" onclick="cancelJob('${esc(job.job_id)}')">取消</button>` : '';
      const packageButton = result.resource_package_path ? `<button class="link-button" type="button" onclick="openResourcePackage('${esc(job.job_id)}')">打开资源包</button>` : '';
      const retryQuality = job.summary_quality || result.summary_quality || 'fast';
      $('job-detail').innerHTML = `
        <h3>${esc(job.title || job.url)}</h3>
        <div class="meta">${esc(job.status)} · ${esc(job.stage)} · ${Math.round((job.progress || 0) * 100)}%</div>
        <div class="meta">${esc(job.job_id)}</div>
        <div class="meta">${esc(job.url)}</div>
        ${transcript ? `<div class="meta">${transcript}</div>` : ''}
        ${job.error_message ? `<div class="meta">${esc(job.error_code)} · ${esc(job.error_message)}</div>` : ''}
        ${steps ? `<ol class="steps">${steps}</ol>` : ''}
        <div class="mini-actions">
          ${out}
          ${packageButton}
          ${cancel}
        </div>
        <div class="retry-editor">
          <strong>重新处理</strong>
          <div class="retry-row">
            <input id="retry-instruction" value="${esc(job.instruction || '')}" aria-label="重试处理要求">
            <select id="retry-quality" aria-label="重试总结质量">
              <option value="fast" ${retryQuality === 'fast' ? 'selected' : ''}>快速</option>
              <option value="pro" ${retryQuality === 'pro' ? 'selected' : ''}>深度</option>
            </select>
            <button class="secondary" type="button" onclick="retryJob('${esc(job.job_id)}')">重试</button>
          </div>
          <label class="inline-option" for="retry-force-refresh">
            <input id="retry-force-refresh" type="checkbox" checked>
            <span>忽略旧缓存</span>
          </label>
        </div>
      `;
    }

    function transcriptMeta(result) {
      const source = result?.source || {};
      const metadata = source.metadata || {};
      if (!['bilibili', 'youtube'].includes(source.source_type)) return '';
      const label = metadata.transcript_origin_label || '未知字幕来源';
      const status = metadata.subtitle_status || '';
      const sourceName = metadata.subtitle_source || '';
      const detail = [status, sourceName].filter(Boolean).join(' · ');
      return `字幕/转写：${esc(label)}${detail ? ` · ${esc(detail)}` : ''}`;
    }

    async function retryJob(jobId) {
      $('submit-status').textContent = '正在提交重试';
      try {
        const job = await postJson(`/jobs/${encodeURIComponent(jobId)}/retry`, {
          instruction: $('retry-instruction')?.value ?? '',
          summary_quality: $('retry-quality')?.value || 'fast',
          force_refresh: $('retry-force-refresh')?.checked ?? true
        });
        state.activeJob = job.job_id;
        activateTab('submit-panel');
        toast('重试任务已提交');
        await refreshAll();
      } catch (error) {
        $('submit-status').textContent = `重试失败：${error.message}`;
        toast(`重试失败：${error.message}`, 'error');
      }
    }

    async function openResourcePackage(jobId) {
      $('submit-status').textContent = '正在打开资源包';
      try {
        await postJson('/outputs/open-package', { job_id: jobId });
        $('submit-status').textContent = '资源包已在文件管理器中打开';
      } catch (error) {
        $('submit-status').textContent = error.message;
      }
    }

    async function cancelJob(jobId) {
      $('submit-status').textContent = '正在取消任务';
      try {
        const job = await postJson(`/jobs/${encodeURIComponent(jobId)}/cancel`, {});
        state.activeJob = job.job_id;
        activateTab('submit-panel');
        toast('任务已取消');
        await refreshAll();
      } catch (error) {
        $('submit-status').textContent = `取消失败：${error.message}`;
        toast(`取消失败：${error.message}`, 'error');
      }
    }

    async function loadBatches() {
      const data = await getJson('/batches?limit=20');
      const items = data.items || [];
      $('batch-count').textContent = String(items.length);
      $('batches').innerHTML = items.map((batch) => {
        const counts = batch.status_counts || {};
        const summary = batch.summary || {};
        const failed = (summary.failed || []).map((item) => `
          <div class="meta">失败：${esc(item.title || item.url)} · ${esc(item.error_code || '')} ${esc(item.error_message || '')}</div>
        `).join('');
        const succeeded = (summary.succeeded || []).map((item) => {
          const link = item.output_markdown_path ? outputLink(item.output_markdown_path) : '';
          return `<div class="meta">成功：${esc(item.title || item.url)} ${link}</div>`;
        }).join('');
        return `
          <div class="row">
            <div class="row-head">
              <span class="title">${esc(batch.batch_id)}</span>
              <span class="status ${esc(batch.status)}">${esc(batch.status)}</span>
            </div>
            <div class="meta">总数 ${batch.count} · 成功 ${counts.succeeded || 0} · 失败 ${counts.failed || 0} · 进行中 ${(counts.running || 0) + (counts.queued || 0)}</div>
            ${succeeded}
            ${failed}
          </div>
        `;
      }).join('') || '<div class="empty">暂无批量任务</div>';
    }

    async function previewCleanup() {
      $('ops-status').textContent = '清理预览中';
      $('cleanup-preview-button').disabled = true;
      try {
        const result = await postJson('/cleanup', { days: 14, dry_run: true, include_temp: true, include_outputs: true, include_jobs: false });
        $('ops-status').textContent = `可清理 ${result.removed.length} 项；默认没有删除任何文件。`;
      } catch (error) {
        $('ops-status').textContent = `清理预览失败：${error.message}`;
      } finally {
        $('cleanup-preview-button').disabled = false;
      }
    }

    async function runBackup() {
      $('ops-status').textContent = '备份中';
      $('backup-button').disabled = true;
      try {
        const result = await postJson('/backup', {});
        $('ops-status').textContent = `备份完成：${result.backup_dir}`;
        await loadMaintenanceStatus();
      } catch (error) {
        $('ops-status').textContent = `备份失败：${error.message}`;
      } finally {
        $('backup-button').disabled = false;
      }
    }

    async function loadMaintenanceStatus() {
      const status = await getJson('/maintenance/status');
      $('maintenance-status-pill').textContent = status.status || (status.ok ? 'ok' : 'failed');
      $('maintenance-status-pill').className = `status ${status.ok ? 'succeeded' : 'failed'}`;
      if (status.status === 'never_run') {
        $('maintenance-status-text').textContent = status.message;
        return;
      }
      const backupDir = status.backup?.backup_dir ? ` · ${status.backup.backup_dir}` : '';
      const error = status.error_message ? ` · ${status.error_type}: ${status.error_message}` : '';
      $('maintenance-status-text').textContent = `${status.created_at || '-'}${backupDir}${error}`;
    }

    async function loadPromptSettings() {
      const prompt = await getJson('/prompt');
      state.prompt = prompt;
      if (!state.promptDirty) {
        $('summary-prompt').value = prompt.prompt || '';
        $('prompt-editor-state').textContent = prompt.is_default ? '正在使用默认提示词' : '正在使用自定义提示词';
      }
      $('prompt-state-pill').textContent = prompt.is_default ? '所有模型 · 默认' : '所有模型 · 自定义';
      $('prompt-state-pill').className = 'status succeeded';
      $('prompt-automatic-context').innerHTML = (prompt.automatic_context || []).map((rule) => `<li>${esc(rule)}</li>`).join('');
      updatePromptEditor();
    }

    function updatePromptEditor() {
      const length = $('summary-prompt').value.length;
      const limit = state.prompt?.max_chars || 8000;
      $('prompt-char-count').textContent = `${length} / ${limit}`;
      $('prompt-save-button').disabled = !state.promptDirty || length < 10 || length > limit;
      if (state.promptDirty) $('prompt-editor-state').textContent = '有尚未保存的更改';
    }

    async function savePrompt(promptOverride = null) {
      const prompt = promptOverride ?? $('summary-prompt').value;
      $('prompt-save-button').disabled = true;
      $('prompt-reset-button').disabled = true;
      $('prompt-status').textContent = '保存中';
      try {
        const result = await postJson('/prompt', { prompt });
        state.prompt = result;
        state.promptDirty = false;
        $('summary-prompt').value = result.prompt || '';
        $('prompt-status').textContent = result.is_default ? '已恢复默认提示词。' : '自定义提示词已保存，新任务会立即使用。';
        $('prompt-editor-state').textContent = result.is_default ? '正在使用默认提示词' : '正在使用自定义提示词';
        $('prompt-state-pill').textContent = result.is_default ? '所有模型 · 默认' : '所有模型 · 自定义';
        toast(result.is_default ? '已恢复默认提示词' : '提示词已保存');
      } catch (error) {
        $('prompt-status').textContent = `保存失败：${error.message}`;
        toast(`提示词保存失败：${error.message}`, 'error');
      } finally {
        $('prompt-reset-button').disabled = false;
        updatePromptEditor();
      }
    }

    async function loadAgentStatus() {
      const agent = await getJson('/agent/status');
      state.agent = agent;
      const stateLabels = { connected: '最近已连接', ready: '接入就绪', mcp_ready: '待装 Skill', needs_setup: '需要配置' };
      $('agent-state-pill').textContent = stateLabels[agent.state] || agent.state || '未知';
      $('agent-state-pill').className = `status ${agent.state === 'connected' || agent.state === 'ready' ? 'succeeded' : agent.state === 'needs_setup' ? 'failed' : 'queued'}`;
      $('agent-status-message').textContent = agent.message || '';
      const seen = agent.activity?.last_seen_at ? new Date(agent.activity.last_seen_at).toLocaleString('zh-CN', { hour12: false }) : '尚无记录';
      const rows = [
        ['本机服务', agent.service_url || '-', true, '运行中'],
        ['MCP 适配器', agent.mcp?.available ? '已在本机找到 MCP 命令' : '未找到 MCP 命令', Boolean(agent.mcp?.available), agent.mcp?.available ? '可用' : '缺失'],
        ['官方 Skill', agent.skill?.installed ? '已在配置的 Agent 工作区安装' : agent.skill?.configured ? '工作区已配置，尚未安装 Skill' : '尚未配置 Agent 工作区', Boolean(agent.skill?.installed), agent.skill?.installed ? '已安装' : '未安装'],
        ['最近 MCP 调用', seen, Boolean(agent.activity?.recent), agent.activity?.recent ? '10 分钟内' : '未连接'],
      ];
      $('agent-status-list').innerHTML = rows.map(([label, detail, ok, status]) => `
        <div class="agent-status-row">
          <strong>${esc(label)}</strong>
          <div class="meta">${esc(detail)}</div>
          <span class="status ${ok ? 'succeeded' : 'queued'}">${esc(status)}</span>
        </div>
      `).join('');
      const mcpConfig = {
        mcpServers: {
          easysourceflow: {
            command: agent.mcp?.command || '/path/to/easysourceflow-mcp',
            env: { EASYSOURCEFLOW_BASE_URL: agent.service_url || 'http://127.0.0.1:8765' }
          }
        }
      };
      $('agent-mcp-config').textContent = JSON.stringify(mcpConfig, null, 2);
      $('agent-skill-command').textContent = agent.install_command || 'scripts/easysourceflow install-skill "$AGENT_WORKSPACE"';
    }

    async function copyText(text, successMessage) {
      try {
        await navigator.clipboard.writeText(text);
      } catch (_error) {
        const field = document.createElement('textarea');
        field.value = text;
        field.style.position = 'fixed';
        field.style.opacity = '0';
        document.body.appendChild(field);
        field.select();
        document.execCommand('copy');
        field.remove();
      }
      toast(successMessage);
    }

    async function loadRuntimeStatus() {
      const [cookies, youtubeCookies, model] = await Promise.all([getJson('/cookies/bilibili'), getJson('/cookies/youtube'), getJson('/model')]);
      const asr = model.asr || {};
      const parsers = model.document_parsers || {};
      renderSettingsPanel(cookies, youtubeCookies, model);
      $('runtime-status').innerHTML = `
        <div class="row">
          <div class="row-head">
            <span class="title">B站账号</span>
            <span class="status ${cookies.ok ? 'succeeded' : 'failed'}">${cookies.ok ? '可用' : '需处理'}</span>
          </div>
          <div class="meta">${esc(bilibiliCookieMessage(cookies))}</div>
          <details class="path-detail"><summary>文件信息</summary><div class="meta">${esc(cookies.path || '未配置')} · ${cookies.size || 0} B · ${esc(cookies.updated_at || '-')}</div></details>
        </div>
        <div class="row">
          <div class="row-head">
            <span class="title">YouTube 账号</span>
            <span class="status ${youtubeCookies.ok ? 'succeeded' : 'failed'}">${youtubeCookies.ok ? '已导入' : '需处理'}</span>
          </div>
          <div class="meta">${esc(youtubeCookieMessage(youtubeCookies))}</div>
          <details class="path-detail"><summary>文件信息</summary><div class="meta">${esc(youtubeCookies.path || '未配置')} · ${youtubeCookies.cookie_count || 0} 条 · ${esc(youtubeCookies.updated_at || '-')}</div></details>
        </div>
        <div class="row">
          <div class="row-head">
            <span class="title">当前模型</span>
            <span class="status">${esc(model.provider)}</span>
          </div>
          <div class="meta">Fast ${esc(model.model)} · Pro ${esc(model.strong_model)}</div>
          <div class="meta">API Key ${model.model_api_key_configured ? '已配置' : '未配置'} · ${esc(model.model_base_url || model.deepseek_base_url || '')}</div>
        </div>
        <div class="row">
          <div class="row-head">
            <span class="title">语音转写</span>
            <span class="status">${esc(asr.backend || '-')}</span>
          </div>
          <div class="meta">最长 ${esc(asr.max_transcription_seconds || '-')} 秒 · Whisper 模型${asr.whisper_model_exists ? '可用' : '缺失'}</div>
          <details class="path-detail"><summary>模型路径</summary><div class="meta">${esc(asr.whisper_model_path || '')}</div></details>
        </div>
        <div class="row">
          <div class="row-head">
            <span class="title">文档解析</span>
            <span class="status ${parsers.pdf ? 'succeeded' : 'queued'}">PDF ${parsers.pdf ? '可用' : '需安装 pypdf'}</span>
          </div>
          <div class="meta">TXT、HTML、DOCX、EPUB ${parsers.docx && parsers.epub ? '均可用' : '部分需处理'}</div>
        </div>
      `;
    }

    function bilibiliCookieMessage(cookies) {
      if (cookies.ok) return '登录态已经导入，可以访问需要账号权限的字幕。';
      if (cookies.exists) return '登录态文件无效或为空，请重新扫码导入。';
      return '尚未导入 B站登录态。';
    }

    function youtubeCookieMessage(cookies) {
      if (cookies.browser_cookie_source_configured) return '处理 YouTube 时会直接读取 Chrome 当前登录态，避免复用已轮换的 Cookie 文件。';
      if (cookies.ok && cookies.authenticated) return '已检测到 YouTube 登录 Cookie；处理视频时仍会由 YouTube 验证账号和访问权限。';
      if (cookies.ok) return '已导入 YouTube Cookie；如仍要求登录，请重新导入 Chrome 登录态。';
      if (cookies.exists) return '登录态文件中没有可用的 YouTube Cookie，请重新导入。';
      return '尚未导入 YouTube 登录态。';
    }

    function renderSettingsPanel(cookies, youtubeCookies, model) {
      state.model = model;
      state.modelServices = model.model_services || [];
      $('bilibili-status-pill').textContent = cookies.ok ? '可用' : '需处理';
      $('bilibili-status-pill').className = `status ${cookies.ok ? 'succeeded' : 'failed'}`;
      $('bilibili-account-status').innerHTML = `
        <div>${esc(bilibiliCookieMessage(cookies))}</div>
        <details class="path-detail"><summary>文件信息</summary><div class="meta">${esc(cookies.path || '')} · ${cookies.size || 0} B · ${esc(cookies.updated_at || '-')}</div></details>
      `;
      $('youtube-status-pill').textContent = youtubeCookies.ok ? (youtubeCookies.browser_cookie_source_configured ? '已接入' : '已导入') : '需处理';
      $('youtube-status-pill').className = `status ${youtubeCookies.ok ? 'succeeded' : 'failed'}`;
      $('youtube-account-status').innerHTML = `
        <div>${esc(youtubeCookieMessage(youtubeCookies))}</div>
        <div class="meta">认证来源：${youtubeCookies.browser_cookie_source_configured ? 'Chrome 实时登录态' : '本地 Cookie 文件'}</div>
        <details class="path-detail"><summary>文件信息</summary><div class="meta">${esc(youtubeCookies.path || '')} · ${youtubeCookies.cookie_count || 0} 条 · ${esc(youtubeCookies.updated_at || '-')}</div></details>
        <div class="meta">PO Token 高级参数：${youtubeCookies.extractor_args_configured ? '已配置' : '未配置'}</div>
      `;
      const service = currentModelService(model);
      $('model-service-pill').textContent = service.label || model.provider || '-';
      $('current-model-pill').textContent = model.model || '-';
      $('current-provider-pill').textContent = service.label || model.provider || '-';
      $('current-model-summary').textContent = `${model.model || '-'} · Pro ${model.strong_model || '-'}`;
      $('current-model-endpoint').textContent = model.provider === 'local' ? '本地抽取式兜底，不调用外部 API。' : `${service.label || model.provider} · ${model.model_base_url || model.deepseek_base_url || ''}`;
      $('sidebar-model').textContent = model.strong_model || model.model || '-';
      $('header-model').textContent = model.strong_model || model.model || '-';
      if (!state.settingsDirty) {
        renderModelServiceOptions(service.id || 'deepseek');
        renderModelChoiceOptions(service, model, false);
        $('config-api-key').value = '';
        $('config-clear-key').checked = false;
      }
      renderModelProviderButtons();
      renderCredentialStatus(selectedModelService());
      updateModelDraftState();
    }

    function currentModelService(model) {
      const services = model.model_services || state.modelServices || [];
      if (model.active_service_id) {
        const active = services.find((service) => service.id === model.active_service_id);
        if (active) return active;
      }
      if (model.provider === 'local') {
        return services.find((service) => service.id === 'local') || { id: 'local', label: '本地兜底', provider: 'local', base_url: '', models: ['local_extractive_fallback'] };
      }
      return services.find((service) => service.base_url === (model.model_base_url || model.deepseek_base_url))
        || services.find((service) => service.id === 'deepseek')
        || { id: 'deepseek', label: 'DeepSeek', provider: 'openai_compatible', base_url: model.model_base_url || model.deepseek_base_url || 'https://api.deepseek.com', models: model.available_models || [] };
    }

    function selectedModelService() {
      const selected = $('model-service').value;
      return (state.modelServices || []).find((service) => service.id === selected) || currentModelService(state.model || {});
    }

    function renderModelServiceOptions(selectedId) {
      const select = $('model-service');
      select.innerHTML = (state.modelServices || []).map((service) => (
        `<option value="${esc(service.id)}">${esc(service.label)}</option>`
      )).join('');
      select.value = selectedId || 'deepseek';
    }

    function renderModelChoiceOptions(service, model, preserve = true) {
      const previousModel = preserve ? $('model-name').value : '';
      const previousStrongModel = preserve ? $('strong-model-name').value : '';
      const names = [...(service.models || [])];
      const activeService = currentModelService(model || {});
      if (activeService.id === service.id) [model.model, model.strong_model].forEach((name) => {
        if (name && !names.includes(name)) names.push(name);
      });
      const options = names.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
      $('model-name').innerHTML = options;
      $('strong-model-name').innerHTML = options;
      const serviceDefault = names.includes(service.default_model) ? service.default_model : names[0];
      const serviceStrong = names.includes(service.strong_model) ? service.strong_model : names[1] || serviceDefault;
      const defaultModel = previousModel && names.includes(previousModel)
        ? previousModel
        : (activeService.id === service.id && names.includes(model.model) ? model.model : serviceDefault);
      const defaultStrong = previousStrongModel && names.includes(previousStrongModel)
        ? previousStrongModel
        : (activeService.id === service.id && names.includes(model.strong_model) ? model.strong_model : serviceStrong);
      $('model-name').value = defaultModel || '';
      $('strong-model-name').value = defaultStrong || defaultModel || '';
    }

    function renderModelProviderButtons() {
      const container = $('model-provider-list');
      if (!container) return;
      const selectedId = $('model-service').value;
      container.innerHTML = (state.modelServices || []).map((service) => `
        <button class="model-provider-button ${service.id === selectedId ? 'active' : ''}" type="button" data-service-id="${esc(service.id)}">${esc(service.label)}</button>
      `).join('');
      container.querySelectorAll('[data-service-id]').forEach((button) => {
        button.addEventListener('click', () => selectModelService(button.dataset.serviceId));
      });
    }

    function selectModelService(serviceId) {
      if (!$('model-service').querySelector(`option[value="${CSS.escape(serviceId)}"]`)) return;
      $('model-service').value = serviceId;
      const service = selectedModelService();
      renderModelChoiceOptions(service, state.model || {}, false);
      markModelDirty();
      renderModelProviderButtons();
      renderCredentialStatus(service);
    }

    function renderCredentialStatus(service) {
      const configured = service.provider === 'local' || Boolean(state.model?.credential_status?.[service.id]);
      $('model-service-pill').textContent = service.label;
      $('model-service-help').textContent = service.provider === 'local'
        ? '本地兜底不调用外部模型。'
        : `官方兼容接口：${service.base_url}`;
      $('model-key-status').textContent = service.provider === 'local'
        ? '本地模型不需要 API Key。'
        : configured ? `${service.label} 的 API Key 已配置，留空不会修改。` : `${service.label} 尚未配置 API Key。`;
      $('config-api-key').disabled = service.provider === 'local';
      $('config-clear-key').disabled = service.provider === 'local' || !configured;
    }

    function markModelDirty() {
      state.settingsDirty = true;
      updateModelDraftState();
    }

    function updateModelDraftState() {
      $('model-unsaved-notice')?.classList.toggle('visible', state.settingsDirty);
      $('settings-model-test-button').disabled = state.settingsDirty;
    }

    async function testModel() {
      if (state.settingsDirty) {
        setModelStatus('请先保存当前配置，再测试生效模型。');
        return false;
      }
      setModelStatus('测试中');
      $('settings-model-test-button').disabled = true;
      try {
        const result = await postJson('/model/test', {});
        setModelStatus(result.ok ? '模型连通正常' : `模型测试失败：${result.check?.message || 'unknown'}`);
        toast(result.ok ? '模型测试通过' : '模型测试失败', result.ok ? 'info' : 'error');
        return Boolean(result.ok);
      } catch (error) {
        setModelStatus(`模型测试失败：${error.message}`);
        toast(`模型测试失败：${error.message}`, 'error');
        return false;
      } finally {
        $('settings-model-test-button').disabled = state.settingsDirty;
      }
    }

    function setModelStatus(message) {
      $('model-status').textContent = message;
      $('settings-model-status').textContent = message;
    }

    async function saveModelConfig(testAfterSave = true) {
      $('config-status').textContent = '保存中';
      $('config-save-button').disabled = true;
      const service = selectedModelService();
      try {
        const result = await postJson('/model', {
          service_id: service.id,
          provider: service.provider,
          model: $('model-name').value,
          strong_model: $('strong-model-name').value,
          model_base_url: service.base_url,
          model_api_key: $('config-api-key').value.trim(),
          clear_model_api_key: $('config-clear-key').checked
        });
        state.settingsDirty = false;
        state.model = result.model;
        $('config-api-key').value = '';
        $('config-clear-key').checked = false;
        $('config-status').textContent = `已保存：${service.label}`;
        toast(`已启用 ${service.label} · ${result.model.model}`);
        updateModelDraftState();
        await Promise.allSettled([loadRuntimeStatus(), loadHealth()]);
        if (testAfterSave) await testModel();
        return true;
      } catch (error) {
        $('config-status').textContent = `保存失败：${error.message}`;
        toast(`保存失败：${error.message}`, 'error');
        return false;
      } finally {
        $('config-save-button').disabled = false;
      }
    }

    async function saveModelChoice() {
      return saveModelConfig(false);
    }

    async function openBilibiliLogin() {
      $('bilibili-action-status').textContent = '正在打开扫码页';
      $('bilibili-open-login-button').disabled = true;
      try {
        const result = await postJson('/bilibili/login/open', {});
        $('bilibili-action-status').textContent = result.ok ? '已打开 B 站扫码页；扫码登录后再点“导入 Chrome 登录态”。' : `请手动打开：${result.url}`;
      } catch (error) {
        $('bilibili-action-status').textContent = `打开失败：${error.message}`;
      } finally {
        $('bilibili-open-login-button').disabled = false;
      }
    }

    async function importBilibiliCookies() {
      $('bilibili-action-status').textContent = '正在从 Chrome 导入登录态';
      $('bilibili-import-button').disabled = true;
      try {
        const result = await postJson('/cookies/bilibili/import', {});
        $('bilibili-action-status').textContent = result.ok ? `导入成功：${result.cookies.updated_at || '已更新'}` : '导入未完成';
        await Promise.allSettled([loadRuntimeStatus(), loadHealth()]);
      } catch (error) {
        $('bilibili-action-status').textContent = `导入失败：${error.message}`;
      } finally {
        $('bilibili-import-button').disabled = false;
      }
    }

    async function openYoutubeLogin() {
      $('youtube-action-status').textContent = '正在打开 YouTube';
      $('youtube-open-login-button').disabled = true;
      try {
        const result = await postJson('/youtube/login/open', {});
        $('youtube-action-status').textContent = result.ok ? '已打开 YouTube；确认登录后再点“接入 Chrome 实时登录态”。' : `请手动打开：${result.url}`;
      } catch (error) {
        $('youtube-action-status').textContent = `打开失败：${error.message}`;
      } finally {
        $('youtube-open-login-button').disabled = false;
      }
    }

    async function importYoutubeCookies() {
      $('youtube-action-status').textContent = '正在接入 Chrome 当前 YouTube 登录态';
      $('youtube-import-button').disabled = true;
      try {
        const result = await postJson('/cookies/youtube/import', {});
        $('youtube-action-status').textContent = result.ok ? '接入成功：后续任务将读取 Chrome 当前登录态' : '接入未完成';
        await Promise.allSettled([loadRuntimeStatus(), loadHealth()]);
      } catch (error) {
        $('youtube-action-status').textContent = `导入失败：${error.message}`;
      } finally {
        $('youtube-import-button').disabled = false;
      }
    }

    async function fulltextSearch() {
      const query = $('fulltext-query').value.trim();
      if (!query) {
        $('fulltext-results').innerHTML = '<div class="empty">输入关键词后搜索</div>';
        $('search-count').textContent = '0';
        $('search-more-button').hidden = true;
        return;
      }
      const source = $('fulltext-source').value;
      $('fulltext-button').disabled = true;
      $('fulltext-results').innerHTML = '<div class="empty">正在搜索…</div>';
      try {
        const data = await getJson(`/search?q=${encodeURIComponent(query)}&source=${encodeURIComponent(source)}&limit=50`);
        state.searchResults = data.items || [];
        state.searchQuery = query;
        state.searchVisibleCount = 20;
        $('search-count').textContent = String(data.count || 0);
        renderSearchResults();
      } catch (error) {
        $('fulltext-results').innerHTML = `<div class="empty">搜索失败：${esc(error.message)}</div>`;
        $('search-more-button').hidden = true;
        toast(`搜索失败：${error.message}`, 'error');
      } finally {
        $('fulltext-button').disabled = false;
      }
    }

    function renderSearchResults() {
      const query = state.searchQuery;
      const visible = state.searchResults.slice(0, state.searchVisibleCount);
      $('fulltext-results').innerHTML = visible.map((item) => `
          <div class="row">
            <div class="row-head">
              <a class="title" href="${esc(item.view_url)}">${highlightText(item.title, query)}</a>
              <span class="status">${esc(item.source_type)}</span>
            </div>
            <div class="meta">${esc(item.date)} · ${Math.ceil(item.size / 1024)} KB</div>
            <div class="meta">${highlightText(cleanMarkdownSnippet(item.snippet), query)}</div>
          </div>
      `).join('') || '<div class="empty">没有匹配结果</div>';
      $('search-more-button').hidden = state.searchVisibleCount >= state.searchResults.length;
    }

    function cleanMarkdownSnippet(text) {
      return String(text || '')
        .replace(/!\\[([^\\]]*)\\]\\([^)]*\\)/g, '$1')
        .replace(/\\[([^\\]]+)\\]\\([^)]*\\)/g, '$1')
        .replace(/#{1,6}\\s*/g, '')
        .replace(/[*_`>|~-]+/g, ' ')
        .replace(/\\s+/g, ' ')
        .trim();
    }

    function highlightText(text, query) {
      const source = String(text || '');
      const needle = String(query || '').trim();
      if (!needle) return esc(source);
      const pattern = new RegExp(needle.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'ig');
      let cursor = 0;
      let output = '';
      for (const match of source.matchAll(pattern)) {
        output += esc(source.slice(cursor, match.index));
        output += `<mark>${esc(match[0])}</mark>`;
        cursor = match.index + match[0].length;
      }
      return output + esc(source.slice(cursor));
    }

    async function refreshAll(manual = false) {
      if (state.refreshing) return;
      state.refreshing = true;
      const activePanel = document.querySelector('.workspace-page.active')?.id || 'submit-panel';
      const tasks = [loadJobs()];
      if (!state.initialized || activePanel === 'outputs-panel') tasks.push(loadOutputs());
      if (!state.initialized || activePanel === 'favorites-panel') tasks.push(loadFavorites());
      if (!state.initialized || activePanel === 'submit-panel') tasks.push(loadBatches());
      if (!state.initialized || activePanel === 'download-panel') tasks.push(loadDownloads());
      if (!state.initialized || activePanel === 'maintenance-panel') {
        tasks.push(loadHealth(), loadRuntimeStatus(), loadMaintenanceStatus(), loadPromptSettings(), loadAgentStatus());
      }
      const results = await Promise.allSettled(tasks);
      const failed = results.filter((result) => result.status === 'rejected');
      if (failed.length) {
        $('service-dot').className = 'service-dot bad';
        $('service-label').textContent = '部分数据刷新失败';
        if (manual) toast('部分数据刷新失败，请检查服务状态', 'error');
      } else if (manual) {
        toast('数据已刷新');
      }
      state.initialized = true;
      state.refreshing = false;
    }

    mergePanels();
    $('submit-form').addEventListener('submit', submitLinks);
    $('download-form').addEventListener('submit', submitDownload);
    document.querySelectorAll('input[name="download-type"]').forEach((input) => input.addEventListener('change', updateDownloadFormats));
    $('refresh-button').addEventListener('click', () => refreshAll(true));
    $('clear-links-button').addEventListener('click', () => {
      $('links').value = '';
      $('submit-status').textContent = '';
      $('links').focus();
    });
    $('cleanup-preview-button').addEventListener('click', previewCleanup);
    $('backup-button').addEventListener('click', runBackup);
    $('file-submit-button').addEventListener('click', submitLocalFile);
    $('file-input').addEventListener('change', () => {
      const file = $('file-input').files[0];
      $('file-hint').textContent = file ? `${file.name} · ${Math.ceil(file.size / 1024)} KB` : '支持 txt、md、字幕、HTML、DOCX、EPUB、PDF。文件内容在浏览器读取后提交给本机服务。';
    });
    $('settings-model-test-button').addEventListener('click', testModel);
    $('config-save-button').addEventListener('click', saveModelConfig);
    $('model-save-button').addEventListener('click', saveModelChoice);
    $('bilibili-open-login-button').addEventListener('click', openBilibiliLogin);
    $('bilibili-import-button').addEventListener('click', importBilibiliCookies);
    $('youtube-open-login-button').addEventListener('click', openYoutubeLogin);
    $('youtube-import-button').addEventListener('click', importYoutubeCookies);
    $('model-service').addEventListener('change', () => selectModelService($('model-service').value));
    $('summary-prompt').addEventListener('input', () => {
      state.promptDirty = true;
      updatePromptEditor();
    });
    $('prompt-save-button').addEventListener('click', () => savePrompt());
    $('prompt-reset-button').addEventListener('click', () => savePrompt(state.prompt?.default_prompt || ''));
    $('copy-mcp-config').addEventListener('click', () => copyText($('agent-mcp-config').textContent, 'MCP 配置已复制'));
    $('copy-skill-command').addEventListener('click', () => copyText($('agent-skill-command').textContent, 'Skill 安装命令已复制'));
    ['model-name', 'strong-model-name', 'config-api-key', 'config-clear-key'].forEach((id) => {
      $(id).addEventListener('input', () => {
        markModelDirty();
      });
      $(id).addEventListener('change', () => {
        markModelDirty();
      });
    });
    $('fulltext-button').addEventListener('click', fulltextSearch);
    $('search-more-button').addEventListener('click', () => {
      state.searchVisibleCount += 20;
      renderSearchResults();
    });
    $('fulltext-query').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') fulltextSearch();
    });
    $('output-search').addEventListener('input', renderOutputs);
    $('output-source').addEventListener('change', renderOutputs);
    $('favorite-search').addEventListener('input', renderFavorites);
    $('favorite-source').addEventListener('change', renderFavorites);
    $('job-search').addEventListener('input', renderJobs);
    $('job-status-filter').addEventListener('change', renderJobs);
    document.querySelectorAll('.tab-button').forEach((button) => {
      button.addEventListener('click', () => activateTab(button.dataset.tab));
      button.addEventListener('keydown', (event) => {
        if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const tabs = Array.from(document.querySelectorAll('.tab-button'));
        const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
        tabs[(tabs.indexOf(button) + direction + tabs.length) % tabs.length].focus();
      });
    });
    document.querySelectorAll('.maintenance-tab').forEach((button) => {
      button.addEventListener('click', () => activateMaintenanceTab(button.dataset.maintenanceTab));
    });
    document.querySelectorAll('[data-task-view]').forEach((button) => {
      button.addEventListener('click', () => activateTaskView(button.dataset.taskView));
    });
    document.querySelectorAll('.source-tab[data-mode]').forEach((button) => {
      button.addEventListener('click', () => activateComposerMode(button.dataset.mode));
    });
    const uploadZone = document.querySelector('.upload-zone');
    ['dragenter', 'dragover'].forEach((name) => uploadZone.addEventListener(name, (event) => {
      event.preventDefault();
      uploadZone.classList.add('dragging');
    }));
    ['dragleave', 'drop'].forEach((name) => uploadZone.addEventListener(name, (event) => {
      event.preventDefault();
      uploadZone.classList.remove('dragging');
    }));
    uploadZone.addEventListener('drop', (event) => {
      if (!event.dataTransfer?.files?.length) return;
      $('file-input').files = event.dataTransfer.files;
      $('file-input').dispatchEvent(new Event('change'));
    });
    window.addEventListener('hashchange', restoreRoute);
    window.showJob = showJob;
    window.retryJob = retryJob;
    window.openResourcePackage = openResourcePackage;
    window.cancelJob = cancelJob;
    window.cancelDownload = cancelDownload;
    window.retryDownload = retryDownload;
    window.favoriteFromList = favoriteFromList;
    window.deleteFavorite = deleteFavorite;
    window.activateTab = activateTab;
    window.activateComposerMode = activateComposerMode;
    tickClock();
    updateDownloadFormats();
    setInterval(tickClock, 1000);
    restoreRoute();
    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>
"""


def render_index() -> str:
    return INDEX_HTML


def search_outputs(output_dir: Path, query: str, source_type: str = "", limit: int = 50) -> dict:
    root = output_dir.expanduser().resolve()
    q = query.strip().lower()
    if not q:
        return {"items": [], "count": 0, "query": query}
    items = []
    for item in list_outputs(root, limit=max(limit * 20, 500))["items"]:
        if source_type and item["source_type"] != source_type:
            continue
        path = Path(item["output_markdown_path"])
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        haystack = f"{item['title']}\n{item['relative_path']}\n{text}".lower()
        index = haystack.find(q)
        if index < 0:
            continue
        snippet = _snippet(text, query)
        hit = dict(item)
        hit["snippet"] = snippet
        items.append(hit)
        if len(items) >= limit:
            break
    return {"items": items, "count": len(items), "query": query}


def list_outputs(output_dir: Path, limit: int = 1000) -> dict:
    root = output_dir.expanduser().resolve()
    items = []
    source_counts: dict[str, int] = {}
    date_counts: dict[str, int] = {}
    skipped = 0
    total_candidates = 0
    if root.exists():
        max_items = max(1, min(limit, 5000))
        candidates = []
        for path in root.rglob("*.md"):
            try:
                rel_parts = path.resolve().relative_to(root).parts
            except ValueError:
                skipped += 1
                continue
            if rel_parts and rel_parts[0] == "favorites":
                skipped += 1
                continue
            if path.name == "latest.md":
                skipped += 1
                continue
            if path.name == "summary.md":
                skipped += 1
                continue
            if path.name == "timeline.md":
                skipped += 1
                continue
            if not path.is_file():
                skipped += 1
                continue
            try:
                stat = path.stat()
            except OSError:
                skipped += 1
                continue
            total_candidates += 1
            item = (stat.st_mtime, path, stat)
            if len(candidates) < max_items:
                heapq.heappush(candidates, item)
            elif stat.st_mtime > candidates[0][0]:
                heapq.heapreplace(candidates, item)
        for _, path, stat in sorted(candidates, key=lambda item: item[0], reverse=True):
            rel = path.resolve().relative_to(root).as_posix()
            parts = rel.split("/")
            date = parts[0] if parts else ""
            source_type = parts[1] if len(parts) > 2 else "output"
            favorite_path = _favorites_dir(root) / rel
            source_counts[source_type] = source_counts.get(source_type, 0) + 1
            if date:
                date_counts[date] = date_counts.get(date, 0) + 1
            items.append(
                {
                    "title": _title_from_path(path),
                    "date": date,
                    "relative_path": rel,
                    "output_markdown_path": str(path.resolve()),
                    "source_type": source_type,
                    "size": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "view_url": "/outputs/" + quote(rel),
                    "is_favorite": favorite_path.exists(),
                }
            )
    return {
        "items": items,
        "count": len(items),
        "total_candidates": total_candidates,
        "limited": total_candidates > len(items),
        "skipped": skipped,
        "output_dir": str(root),
        "source_counts": source_counts,
        "date_counts": date_counts,
    }


def list_favorites(output_dir: Path, limit: int = 1000) -> dict:
    favorites_root = _favorites_dir(output_dir)
    data = list_outputs(favorites_root, limit=limit)
    for item in data["items"]:
        item["view_url"] = "/outputs/favorites/" + quote(item["relative_path"])
    data["output_dir"] = str(favorites_root)
    return data


def favorite_output(output_dir: Path, raw_relative_path: str) -> dict:
    root = output_dir.expanduser().resolve()
    source_path = _resolve_output_file(root, raw_relative_path)
    favorites_root = _favorites_dir(root)
    favorites_root.mkdir(parents=True, exist_ok=True)
    try:
        existing_rel = source_path.relative_to(favorites_root)
        return _favorite_result(source_path, existing_rel.as_posix(), already=True)
    except ValueError:
        source_rel = source_path.relative_to(root)
    target_path = favorites_root / source_rel
    if target_path.exists():
        return _favorite_result(target_path, target_path.relative_to(favorites_root).as_posix(), already=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)

    source_package = source_path.with_suffix("")
    target_package = target_path.with_suffix("")
    if source_package.is_dir():
        if target_package.exists():
            target_package = _dedupe_path(target_package)
        shutil.copytree(source_package, target_package)

    return _favorite_result(target_path, target_path.relative_to(favorites_root).as_posix(), already=False)


def delete_favorite(output_dir: Path, raw_relative_path: str) -> dict:
    favorites_root = _favorites_dir(output_dir)
    favorite_path = _resolve_output_file(favorites_root, raw_relative_path)
    package_path = favorite_path.with_suffix("")
    deleted = [str(favorite_path)]
    favorite_path.unlink()
    if package_path.is_dir():
        shutil.rmtree(package_path)
        deleted.append(str(package_path))
    _prune_empty_dirs(favorite_path.parent, favorites_root)
    return {
        "ok": True,
        "deleted": deleted,
        "favorite_relative_path": unquote(raw_relative_path).lstrip("/"),
    }


def _favorite_result(path: Path, relative_path: str, already: bool) -> dict:
    package_path = path.with_suffix("")
    return {
        "ok": True,
        "already_favorited": already,
        "favorite_markdown_path": str(path),
        "favorite_relative_path": relative_path,
        "favorite_view_url": "/outputs/favorites/" + quote(relative_path),
        "copied_package_path": str(package_path) if package_path.exists() else "",
    }


def _favorites_dir(output_dir: Path) -> Path:
    return output_dir.expanduser().resolve() / "favorites"


def _resolve_output_file(root: Path, raw_relative_path: str) -> Path:
    relative_path = unquote(raw_relative_path).lstrip("/")
    if not relative_path or relative_path.startswith("../") or "/../" in relative_path:
        raise FileNotFoundError("Output not found")
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FileNotFoundError("Output not found") from exc
    if not path.is_file() or path.suffix.lower() != ".md":
        raise FileNotFoundError("Output not found")
    return path


def _prune_empty_dirs(start: Path, stop: Path) -> None:
    current = start.resolve()
    stop = stop.resolve()
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(2, 1000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not find available favorite path.")


def _snippet(text: str, query: str) -> str:
    lowered = text.lower()
    index = lowered.find(query.lower())
    if index < 0:
        return text[:220].replace("\n", " ")
    start = max(0, index - 90)
    end = min(len(text), index + len(query) + 130)
    snippet = text[start:end].replace("\n", " ")
    if start:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


def render_output(output_dir: Path, raw_relative_path: str) -> tuple[int, str]:
    root = output_dir.expanduser().resolve()
    try:
        path = _resolve_output_file(root, raw_relative_path)
    except FileNotFoundError:
        return 404, _message_page("Output not found")
    relative_path = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    favorites_root = _favorites_dir(root)
    try:
        path.relative_to(favorites_root)
        is_favorited = True
    except ValueError:
        is_favorited = (favorites_root / relative_path).exists()
    return 200, _markdown_page(title=_title_from_path(path), relative_path=relative_path, text=text, is_favorited=is_favorited)


def _title_from_path(path: Path) -> str:
    stem = path.stem
    if len(stem) > 7 and stem[:6].isdigit() and stem[6] == "-":
        stem = stem[7:]
    return stem.replace("-", " ") or path.name


def _message_page(message: str) -> str:
    return f"<!doctype html><meta charset='utf-8'><title>EasySourceFlow</title><p>{html.escape(message)}</p>"


def _markdown_page(title: str, relative_path: str, text: str, is_favorited: bool = False) -> str:
    escaped_title = html.escape(title)
    escaped_path = html.escape(relative_path)
    rendered_html = _render_markdown(text)
    toc_html = _markdown_toc(text)
    data = json.dumps(text, ensure_ascii=False)
    relative_data = json.dumps(relative_path, ensure_ascii=False)
    favorite_button_text = "已收藏" if is_favorited else "收藏"
    favorite_button_disabled = " disabled" if is_favorited else ""
    download_url = "data:text/markdown;charset=utf-8," + quote(text)
    download_name = html.escape(_download_filename(title))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    body {{
      margin: 0;
      background: #f4f6f2;
      color: #18201d;
      font-family: "Songti SC", "Noto Serif CJK SC", Georgia, serif;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 26px 0 56px;
    }}
    header {{
      border-bottom: 1px solid #cfd8cf;
      margin-bottom: 20px;
      padding-bottom: 16px;
    }}
    header > h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 4vw, 46px);
      line-height: 1.08;
      letter-spacing: 0;
    }}
    .meta {{
      color: #66716c;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .reader-layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 240px;
      gap: 18px;
      align-items: start;
    }}
    .toc {{
      position: sticky;
      top: 18px;
      max-height: calc(100vh - 36px);
      overflow: auto;
      background: #ffffff;
      border: 1px solid #d9dfd9;
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 12px 34px rgba(34, 43, 38, .08);
    }}
    .toc strong {{
      display: block;
      margin-bottom: 8px;
      font-size: 13px;
      color: #45514a;
    }}
    .toc a {{
      display: block;
      padding: 5px 0;
      color: #245f9d;
      font-size: 13px;
      line-height: 1.35;
      text-decoration: none;
    }}
    .toc .level-3 {{ padding-left: 12px; }}
    .toc .level-4 {{ padding-left: 22px; }}
    article {{
      background: #ffffff;
      border: 1px solid #d9dfd9;
      border-radius: 8px;
      padding: clamp(18px, 4vw, 34px);
      box-shadow: 0 16px 46px rgba(34, 43, 38, .10);
    }}
    article :first-child {{ margin-top: 0; }}
    article :last-child {{ margin-bottom: 0; }}
    article h1, h2, h3, h4 {{
      margin: 1.5em 0 .55em;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    article h1 {{ font-size: 28px; }}
    h2 {{
      border-bottom: 1px solid #e3e7e2;
      padding-bottom: 8px;
      font-size: 24px;
    }}
    h3 {{ font-size: 20px; }}
    h4 {{ font-size: 17px; }}
    p, li, blockquote {{
      font-size: 16px;
      line-height: 1.78;
    }}
    p {{ margin: .85em 0; }}
    ul, ol {{
      padding-left: 1.4em;
      margin: .7em 0 1em;
    }}
    li {{ margin: .25em 0; }}
    blockquote {{
      margin: 1em 0;
      padding: 2px 0 2px 16px;
      border-left: 4px solid #1f7a5a;
      color: #45514a;
      background: #f7faf6;
    }}
    pre, code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    pre {{
      margin: 1em 0;
      padding: 14px;
      border-radius: 8px;
      background: #18201d;
      color: #f5f7f3;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.65;
    }}
    code {{
      border-radius: 5px;
      background: #eef3ed;
      padding: 2px 5px;
      font-size: .92em;
    }}
    pre code {{
      background: transparent;
      padding: 0;
      font-size: 14px;
    }}
    a {{
      color: #245f9d;
      text-decoration-thickness: 1px;
      text-underline-offset: 3px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
      align-items: center;
    }}
    a, button {{
      color: #245f9d;
    }}
    button {{
      border: 1px solid #c8d0c8;
      border-radius: 7px;
      background: transparent;
      padding: 8px 12px;
      cursor: pointer;
      font: inherit;
    }}
    .download {{
      border: 1px solid #c8d0c8;
      border-radius: 7px;
      padding: 8px 12px;
      text-decoration: none;
    }}
    @media (max-width: 860px) {{
      .reader-layout {{ grid-template-columns: 1fr; }}
      .toc {{ position: static; max-height: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escaped_title}</h1>
      <div class="meta">{escaped_path}</div>
      <div class="actions">
        <a href="/">返回控制台</a>
        <a class="download" href="{html.escape(download_url)}" download="{download_name}">下载 Markdown</a>
        <button id="favorite-button" type="button" onclick="favoriteCurrent()"{favorite_button_disabled}>{favorite_button_text}</button>
        <button type="button" onclick="navigator.clipboard.writeText(markdownText)">复制 Markdown</button>
        <span class="meta" id="favorite-status"></span>
      </div>
    </header>
    <div class="reader-layout">
      <article>{rendered_html}</article>
      {toc_html}
    </div>
  </main>
  <script>
    const markdownText = {data};
    const relativePath = {relative_data};
    async function favoriteCurrent() {{
      const button = document.getElementById('favorite-button');
      const status = document.getElementById('favorite-status');
      button.disabled = true;
      status.textContent = '正在收藏';
      try {{
        const response = await fetch('/favorites', {{
          method: 'POST',
          headers: {{ 'content-type': 'application/json' }},
          body: JSON.stringify({{ relative_path: relativePath }})
        }});
        const data = await response.json();
        if (!response.ok) throw new Error(data?.error?.message || response.statusText);
        button.textContent = '已收藏';
        button.disabled = true;
        status.innerHTML = '已加入收藏夹 · <a href="' + data.favorite_view_url + '" target="_blank" rel="noreferrer">打开收藏副本</a>';
      }} catch (error) {{
        status.textContent = '收藏失败：' + error.message;
      }} finally {{
        if (!button.textContent.includes('已收藏')) button.disabled = false;
      }}
    }}
  </script>
</body>
</html>"""


_LINK_RE = re.compile(
    r"\[([^\]\n]+)\]\((https?://[^\s)]+|/[^\s)]+|(?:\.\/)?(?!\.\.)(?![A-Za-z][A-Za-z0-9+.-]*:)[^\s)]+)\)"
)


def _markdown_toc(text: str) -> str:
    used_anchors: set[str] = set()
    items = []
    for line in text.splitlines():
        heading = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
        if not heading:
            continue
        level = len(heading.group(1))
        title = heading.group(2).strip()
        anchor = _anchor_id(title, used_anchors)
        items.append(f'<a class="level-{level}" href="#{html.escape(anchor)}">{_render_inline(title)}</a>')
        if len(items) >= 24:
            break
    if not items:
        return ""
    return '<nav class="toc"><strong>目录</strong>' + "".join(items) + "</nav>"


def _anchor_id(title: str, used: set[str]) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.lower()).strip("-")
    base = base or "section"
    anchor = base
    index = 2
    while anchor in used:
        anchor = f"{base}-{index}"
        index += 1
    used.add(anchor)
    return anchor


def _download_filename(title: str) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", title).strip(".-") or "easysourceflow-output"
    return stem + ".md"


def _render_markdown(text: str) -> str:
    lines = text.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []
    list_tag = ""
    in_code = False
    code_lines: list[str] = []
    used_anchors: set[str] = set()

    def flush_paragraph() -> None:
        if paragraph:
            parts.append(f"<p>{_render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_tag
        if list_tag:
            parts.append(f"</{list_tag}>")
            list_tag = ""

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                flush_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(raw_line)
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            anchor = _anchor_id(heading.group(2), used_anchors)
            parts.append(f'<h{level} id="{html.escape(anchor)}">{_render_inline(heading.group(2))}</h{level}>')
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            flush_list()
            parts.append("<hr>")
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            flush_list()
            quote_text = stripped.lstrip("> ").strip()
            parts.append(f"<blockquote>{_render_inline(quote_text)}</blockquote>")
            continue

        item = re.match(r"^([-*+]|\d+[.)])\s+(.+)$", stripped)
        if item:
            flush_paragraph()
            target_tag = "ol" if item.group(1)[0].isdigit() else "ul"
            if list_tag != target_tag:
                flush_list()
                list_tag = target_tag
                parts.append(f"<{list_tag}>")
            parts.append(f"<li>{_render_inline(item.group(2))}</li>")
            continue

        flush_list()
        paragraph.append(stripped)

    if in_code:
        parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    flush_list()
    return "\n".join(parts) or "<p></p>"


def _render_inline(text: str) -> str:
    rendered: list[str] = []
    segments = re.split(r"(`[^`]+`)", text)
    for segment in segments:
        if not segment:
            continue
        if segment.startswith("`") and segment.endswith("`") and len(segment) > 1:
            rendered.append(f"<code>{html.escape(segment[1:-1])}</code>")
        else:
            rendered.append(_render_inline_text(segment))
    return "".join(rendered)


def _render_inline_text(text: str) -> str:
    links: list[str] = []

    def replace_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        links.append(f'<a href="{url}" target="_blank" rel="noreferrer noopener">{label}</a>')
        return f"\u0000{len(links) - 1}\u0000"

    escaped = html.escape(_LINK_RE.sub(replace_link, text))
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", escaped)
    for index, link in enumerate(links):
        escaped = escaped.replace(f"\u0000{index}\u0000", link)
    return escaped
