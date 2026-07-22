Always answer in 简体中文

## Coding Standards

Key rules:
- **Database Migration:** Only use `auto_migrate.py` `REQUIRED_FIELDS`. Never use Alembic manually.
- **Exception Handling:** Never use `except Exception:`. NoneBot2's `finish()/send()` relies on raising exceptions for control flow.
- **Transaction Management:** Always use `safe_session()`.
- **Command Sync:** Help content single source = `data/knowledge/*.yaml` (bodies auto-render as in-game help pages via `player/help_topics.py`; add `help_command`/`help_aliases` for new topics). When adding/modifying commands, update the topic's yaml only. `player/help.py` holds only the main menu and module navigation pages.

## Project Documentation

System knowledge base lives in `llmdoc/`. Entry point: `/llmdoc/index.md`.
Consult architecture, guides, and reference directories as needed.

## Programming Principles

After thorough research, use `AskUserQuestion` to present choices rather than jumping to conclusions.

## Deployment

- **Server:** root@***REMOVED***, password: ***REMOVED***
- **Project path:** /home/admin/GuiXiuXian2
- **Service:** systemd unit `guixiuxian-bot` (User=admin, `/etc/systemd/system/guixiuxian-bot.service`, Restart=always, 开机自启). 自 2026-06-10 起取代旧的 `qqbot` screen 会话。
- **Workflow:** When user says "部署" (deploy), execute ALL steps automatically:
  1. `git push`
  2. `ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && git pull'"`
  3. `ssh root@***REMOVED*** "systemctl restart guixiuxian-bot"`
  4. Verify: `ssh root@***REMOVED*** "systemctl status guixiuxian-bot --no-pager | head -5"`
- **Logs:** `journalctl -u guixiuxian-bot` 或 `/home/admin/GuiXiuXian2/logs/bot.log`