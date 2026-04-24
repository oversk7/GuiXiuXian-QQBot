Always answer in 简体中文

## Coding Standards

Coding conventions are managed by Trellis Spec. Run `/trellis:before-dev` before development to auto-inject relevant specs. Manual reference: `.trellis/spec/backend/`.

Key rules (see spec for details):
- **Database Migration:** Only use `auto_migrate.py` `REQUIRED_FIELDS`. Never use Alembic manually.
- **Exception Handling:** Never use `except Exception:`. NoneBot2's `finish()/send()` relies on raising exceptions for control flow.
- **Transaction Management:** Always use `safe_session()`.
- **Command Sync:** When adding/modifying commands, always update `player/help.py` AND `data/knowledge/*.yaml`.

## Project Documentation

System knowledge base lives in `llmdoc/`. Entry point: `/llmdoc/index.md`.
Consult architecture, guides, and reference directories as needed.

## Code Search

Prefer `mcp__ace-tool__search_context` (ACE) for semantic code search.
Use Grep for exact strings, Glob for file patterns, Read for known paths.

## Programming Principles

After thorough research, use `AskUserQuestion` to present choices rather than jumping to conclusions.

## Deployment

- **Server:** root@***REMOVED***, password: ***REMOVED***
- **Project path:** /home/admin/GuiXiuXian2
- **Screen:** `qqbot` screen session (admin user)
- **Workflow:** When user says "部署" (deploy), execute ALL steps automatically:
  1. `git push`
  2. `ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && git pull'"`
  3. Kill old process and restart:
     ```bash
     ssh root@***REMOVED*** bash -c '
       su - admin -c "screen -X -S qqbot quit" 2>/dev/null
       sleep 1
       pkill -u admin -f "bot\.py" 2>/dev/null
       sleep 1
       su - admin -c "screen -dmS qqbot bash -c \"cd /home/admin/GuiXiuXian2 && nb run; exec bash\""
     '
     ```
  4. Verify: `ps aux | grep bot.py`
