@echo off
REM Codex MIMO proxy - auto-starts on login
REM Translates Responses API to Chat Completions for MIMO
npx @codeproxy/cli --base-url https://token-plan-cn.xiaomimimo.com/v1 --model mimo-v2.5 --model mimo-v2.5-pro --apikey YOUR_API_KEY
