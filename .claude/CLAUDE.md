Always answer in 简体中文

## Coding Standards

Key rules:
- **Database Migration:** Only use `auto_migrate.py` `REQUIRED_FIELDS`. Never use Alembic manually.
- **Exception Handling:** Never use `except Exception:`. NoneBot2's `finish()/send()` relies on raising exceptions for control flow.
- **Transaction Management:** Always use `safe_session()`.
- **Command Sync:** When adding/modifying commands, always update `player/help.py` AND `data/knowledge/*.yaml`.

## Project Documentation

System knowledge base lives in `llmdoc/`. Entry point: `/llmdoc/index.md`.
Consult architecture, guides, and reference directories as needed.

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

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
