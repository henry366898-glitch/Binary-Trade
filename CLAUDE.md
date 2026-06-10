# CLAUDE.md

> Project guidance for Claude Code. This file is read at the start of every session.
> It is committed to the repo so every team member's Claude Code shares the same rules.

## ⚠️ MANDATORY: Sync with git before ANY work

**Before making any change, decision, or recommendation in this repo — every single
session, every single time — you MUST first sync with git. Do not skip this, even for
small or "obvious" changes.** This project has multiple contributors, so your local view
is often stale. Acting on stale state causes conflicts and lost work.

Run this sequence at the start of the session, and again before starting any new task:

1. Check where you currently are:
   ```bash
   git status
   git branch --show-current
   ```

2. Fetch everything from the remote (this does NOT touch working files):
   ```bash
   git fetch --all --prune
   ```

3. Compare local vs remote for the current branch:
   ```bash
   git log --oneline -5
   git log --oneline -5 "origin/$(git branch --show-current)"
   ```

4. **Decide before pulling — do not pull blindly:**
   - Working tree is **clean** AND branch is **behind** remote → pull:
     ```bash
     git pull --ff-only
     ```
   - There are **uncommitted local changes** → **STOP.** Do not pull. List the dirty
     files and ask me how to proceed (stash, commit, or discard). Never overwrite my
     uncommitted work.
   - Local and remote have **diverged** → **STOP.** Report it and ask before merging
     or rebasing.

5. Before you start, confirm to me in one line the state you're working from:
   **current branch, latest commit hash + message, and whether you pulled anything.**

### Hard rules
- Always state which branch and commit you are operating on before proposing or making changes.
- Never assume an earlier session's state is still current — re-check at the start of each session.
- Never `git push --force`, never `git reset --hard`, never delete branches without my explicit confirmation.
- If you're unsure whether your view is current, fetch again rather than guess.
- If a teammate may also be working right now, mention it and double-check the remote before committing.

---

## ⚠️ MANDATORY: Verify and test before reporting ANY work as done

**After every change — every prompt, every time — you MUST verify the work actually
runs and behaves correctly before telling me it's finished. Never report a task as
complete based on the code "looking right." Run it. Prove it.** If you cannot verify
something, say so explicitly instead of claiming success.

### The protocol for every change

1. **Verify it works at all.** For backend changes, start the server and hit the
   affected endpoint(s). For frontend changes, start the dev server and load the
   affected screen. Watch the logs/console for errors.

2. **Test the full app, not just the line you touched.** A change is not done until
   you've confirmed it didn't break anything around it. Exercise the golden path AND
   check for regressions in adjacent features.

3. **Test with 4 cases — minimum — for the behavior you changed:**
   1. **Happy path** — normal, valid input that should succeed.
   2. **Edge case** — boundary values (empty, zero, max, very long, missing optional fields).
   3. **Invalid / error case** — bad input, unauthorized access, etc. Confirm it fails *gracefully* with the right error, not a crash.
   4. **Regression / integration case** — confirm a related existing feature still works end-to-end after your change.

### UI changes — additional mandatory steps

For anything visible in the browser, on top of the 4 cases above you MUST:

- **Take a screenshot** of the changed screen and actually look at it. Verify the
  feature renders and works — don't just assume.
- **Verify responsiveness.** Resize to mobile, tablet, and desktop widths and confirm
  the layout holds (no overflow, no clipped content, no broken stacking).
- **Verify it looks production-grade.** Check spacing, alignment, contrast, typography,
  loading/empty/error states, and dark mode if applicable. If it looks rough or
  "AI-generated," fix it before reporting done.
- **Share the proof.** Include the screenshot(s) and a short note on what you verified.

Use the `preview_*` tools for all of this (preview_start, preview_snapshot,
preview_screenshot, preview_resize, preview_console_logs, preview_click/fill). Never
ask me to check the browser manually — verify it yourself and show me the result.

### Hard rules
- No "should work" / "this will fix it" without having actually run it.
- If a test reveals a problem, fix it and re-run the full protocol — don't report partial success.
- If the environment makes verification impossible (e.g. MT5 not available, no DB),
  state exactly what you could and couldn't verify and why.

---

## Project overview

Educational binary-options trading simulator (virtual money only) with a lead-gen
funnel layer. Three components:

- **`backend/`** — FastAPI (Python). Async. MongoDB via **motor + beanie** (ODM).
  JWT auth (python-jose) + bcrypt (passlib). WebSocket price streaming. APScheduler
  drives the settlement loop. Routers: `auth`, `market`, `trades`, `leads`, `admin`.
- **`frontend/`** — React 18 + Vite + Zustand. TradingView `lightweight-charts`.
  Components: AuthScreen, Chart, TradeTicket, TradesList, LegalPages.
- **`mt5_bridge/`** — separate Python process that bridges a MetaTrader 5 terminal to
  the backend (real price history / live feed). Backend falls back to a mock/Binance
  feed when MT5 isn't available.

> Note: the top-level `README.md` is partly stale (it describes SQLite/SQLAlchemy; the
> code now uses MongoDB via motor/beanie). Trust the code over the README.

## Branching model

`main` = the integration branch (this is what PRs merge into). Multiple contributors
push here, so the git-sync section above is not optional.

## Coding conventions

- Backend: async throughout; Pydantic v2 schemas in `app/models/schemas.py`,
  beanie documents in `app/models/db.py`. Keep routers thin, logic in `services/`.
- Frontend: functional components; shared state in `src/lib/store.js` (Zustand);
  all network calls go through `src/lib/api.js`.
- Match the style of the file you're editing. Don't reformat unrelated code.

## Things to never touch without asking

- `backend/.env.local`, `mt5_bridge/.env*`, and any secrets/credentials.
- `nginx.conf`, `ecosystem.config.js` (PM2), `vercel.json` — deployment config.
- Anything under `venv/` or `node_modules/`.
