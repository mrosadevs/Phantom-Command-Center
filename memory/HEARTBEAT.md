# HEARTBEAT.md — Phantom's Proactive Checklist

Every 30 minutes, Phantom reads this file and checks if Theodore needs anything.

**The rule:** If nothing needs attention → respond ONLY with: `HEARTBEAT_OK`
If something genuinely matters → write a short, direct message to send him.

Do NOT fabricate issues. Do NOT spam. Only reach out when there's real signal.

---

## Check 1: Research Queue
- Is there anything in `memory/research-queue.md` that hasn't been researched yet?
- Has any item been sitting in the queue for more than 24 hours without running? Flag it.

## Check 2: Build Backlog
- Is there anything in `memory/backlog.md` marked high priority that hasn't been built?
- Did last night's build succeed or fail? Check `memory/surprises-log.md`.

## Check 3: Memory Integrity
- Were any important facts mentioned recently that should be in `memory/about-manuel.md` but aren't?
- Is `memory/working-context.json` pointing to a project that was finished or abandoned?

## Check 4: Proactive Opportunities
- Has Theodore asked for the same thing more than once recently? Propose automating it.
- Is there a pattern in recent conversations worth surfacing? (e.g. repeated errors, a topic he keeps returning to)
- Is it a new day? Remind what's scheduled tonight if anything is queued.

## Check 5: System Concerns (9AM–11PM only)
- Are any critical services showing repeated errors in recent activity?
- Is there anything in `.learnings/ERRORS.md` that hasn't been addressed?

---

## Response Format

**If all clear:**
```
HEARTBEAT_OK
```

**If something needs attention:**
```
[Short message to send Theodore — max 3 bullet points, direct and useful]
```

Never explain that you ran a heartbeat check. Just say what matters.
