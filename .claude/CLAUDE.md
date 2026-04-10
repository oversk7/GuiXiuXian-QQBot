Always answer in 简体中文

## Project Documentation

This project has a comprehensive `llmdoc` documentation system. When working on unfamiliar modules, consult:
- `/llmdoc/index.md` — Main index (start here)
- `/llmdoc/overview/` — Project context ("What is this?")
- `/llmdoc/architecture/` — System design ("How does it work?")
- `/llmdoc/guides/` — Step-by-step instructions ("How do I do X?")
- `/llmdoc/reference/` — API specs, config, conventions
- `/llmdoc/design/` — Feature specs and implementation plans
- `/llmdoc/agent/` — Investigation reports

## Code Search

Prefer `mcp__ace-tool__search_context` (ACE) for semantic code search — finding functions, understanding logic flow, locating definitions. Use Grep for exact string constants, Glob for file pattern matching, and Read when the file path is already known.

## Programming Principles

After thorough research, use `AskUserQuestion` to present users with choices rather than jumping to conclusions.

## Project Rules

- **Database Migration:** ALWAYS use `plugins/xiuxian_game/models/auto_migrate.py` for schema changes. NEVER use Alembic manually. Add field definitions to `REQUIRED_FIELDS` and restart the bot.
- **Help Information Sync:** When adding/modifying commands, ALWAYS update `plugins/xiuxian_game/player/help.py` with command syntax, description, and usage examples.
- **AI Knowledge Base Sync:** After updating `help.py`, ALWAYS update the corresponding YAML in `plugins/xiuxian_game/data/knowledge/`. Each YAML maps 1:1 to a help handler. Copy the new `msg` text into the `body` field.
- **NoneBot2 Exception Handling:**
  - NEVER use `except Exception:` in command handlers — NoneBot2's `finish()`, `send()`, `reject()` throw `FinishedException`/`PausedException`/`RejectedException` for control flow
  - Only catch specific exceptions (`requests.RequestException`, `json.JSONDecodeError`, `ValueError`, etc.)
  - Place validation logic OUTSIDE try-except blocks when possible
  - Example:
    ```python
    # GOOD: Specific exception handling
    @handler.handle()
    async def handle_cmd(event: MessageEvent):
        if not args:
            await handler.finish("Error")  # FinishedException propagates safely

        try:
            response = requests.get(url)
            data = response.json()
        except requests.RequestException:
            await handler.finish("Network error")
        except json.JSONDecodeError:
            await handler.finish("Parse error")

        await handler.finish("Success")

    # BAD: Catching all exceptions breaks NoneBot2 control flow
    @handler.handle()
    async def handle_cmd(event: MessageEvent):
        try:
            await handler.finish("Error")  # FinishedException caught below!
        except Exception:  # Swallows control flow exceptions
            await handler.finish("Unknown error")  # Never works properly
    ```

## Deployment

- **Server:** root@***REMOVED***, password: ***REMOVED***
- **Project path:** /home/admin/GuiXiuXian2
- **Screen:** The `qqbot` screen session runs under the `admin` user.
- **Workflow:** When the user says "部署" (deploy), execute ALL of the following steps automatically:
  1. `git push`
  2. `ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && git pull'"`
  3. Kill the old bot process and restart in admin's screen:
     ```bash
     ssh root@***REMOVED*** bash -c '
       su - admin -c "screen -X -S qqbot quit" 2>/dev/null
       sleep 1
       pkill -u admin -f "bot\.py" 2>/dev/null
       sleep 1
       su - admin -c "screen -dmS qqbot bash -c \"cd /home/admin/GuiXiuXian2 && nb run; exec bash\""
     '
     ```
  4. Verify the process started successfully (`ps aux | grep bot.py`)