<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

Use the `/trellis:start` command when starting a new session to:
- Initialize your developer identity
- Understand current project context
- Read relevant guidelines

Use `@/.trellis/` to learn:
- Development workflow (`workflow.md`)
- Project structure guidelines (`spec/`)
- Developer workspace (`workspace/`)

If you're using Codex, project-scoped helpers may also live in:
- `.agents/skills/` for reusable Trellis skills
- `.codex/agents/` for optional custom subagents

Keep this managed block so 'trellis update' can refresh the instructions.

<!-- TRELLIS:END -->


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

## 5. Deployment

**Deploy automatically when the user says "部署" / "deploy".**

- Server: `root@***REMOVED***`
- Project path: `/home/admin/GuiXiuXian2`
- Runtime: `qqbot` screen session under the `admin` user
- Do not use `deploy.sh` for bot deployment; it is for the game guide web page.
- Do not write server passwords or long-lived credentials into repository files.

Deployment workflow:

1. Push the current branch:
   ```bash
   git push
   ```

2. Pull on the server:
   ```bash
   ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && git pull'"
   ```

3. Restart the bot:
   ```bash
   ssh root@***REMOVED*** bash -c '
     su - admin -c "screen -X -S qqbot quit" 2>/dev/null
     sleep 1
     pkill -u admin -f "bot\.py" 2>/dev/null
     sleep 1
     su - admin -c "screen -dmS qqbot bash -c \"cd /home/admin/GuiXiuXian2 && nb run; exec bash\""
   '
   ```

   If the local shell mangles nested quotes, run the restart as simpler separate SSH commands instead:
   ```bash
   ssh root@***REMOVED*** "su - admin -c 'screen -S qqbot -X quit || true'"
   ssh root@***REMOVED*** "su - admin -c 'pkill -f bot.py || true'"
   ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && screen -dmS qqbot nb run'"
   ```

4. Verify:
   ```bash
   ssh root@***REMOVED*** "ps aux | grep bot.py"
   ssh root@***REMOVED*** "su - admin -c 'screen -ls'"
   ```
