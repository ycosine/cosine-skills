---
name: personal-reminder-api
description: Create and cancel one-off personal timers, inspect delivery events, test Bark delivery, and view or update sedentary and water schedules through a deployed Personal Reminder API. Use when the user asks to be reminded later, start a cooking timer, manage recurring health reminders, test their Bark notifications, or inspect recent reminder activity.
---

# Personal Reminder API

Use the bundled client for deterministic authenticated requests. Require these environment variables:

- `PERSONAL_REMINDER_API_URL`, such as `https://reminder.example.com`
- `PERSONAL_REMINDER_API_TOKEN`

Never print, persist, or repeat the token. If either variable is missing, ask the user to configure it before making a live request.

## Workflow

1. Translate the request into one API operation.
2. For relative timers, preserve the requested duration; do not replace it with a guessed absolute time.
3. Run `python scripts/reminder_api.py <command>` from this skill directory.
4. Confirm the returned timer ID, resolved due time, or updated schedule values.
5. When a request fails, report the API error without exposing request headers.

Create explicitly requested timers and schedule updates without an extra confirmation. Before cancelling a timer, make sure the target ID came from the user or a fresh `list-timers` response and state which timer will be cancelled.

## Commands

```bash
python scripts/reminder_api.py status
python scripts/reminder_api.py create-timer --minutes 25 --title "记得关火" --body "汤已经煮好了"
python scripts/reminder_api.py list-timers --limit 20
python scripts/reminder_api.py cancel-timer TIMER_ID
python scripts/reminder_api.py list-schedules
python scripts/reminder_api.py set-schedule sedentary --interval 45 --start 09:00 --end 18:30 --weekdays 1,2,3,4,5 --enable
python scripts/reminder_api.py test --title "测试" --body "Bark 已连接"
python scripts/reminder_api.py events --limit 20
python scripts/reminder_api.py activity
python scripts/reminder_api.py set-schedule sedentary --activity-based
```

Use `0` for Sunday through `6` for Saturday.

## Activity-based schedules

Schedules with `activityBased: true` (the sedentary reminder by default) track real sitting time instead of wall-clock intervals. The user's Mac sends a heartbeat every minute while in use (`scripts/mac-heartbeat.sh` via launchd). A heartbeat gap over 5 minutes counts as a standing break: the next heartbeat restarts the interval. While no fresh heartbeat exists (away from the computer), these schedules stay silent. Use `activity` to inspect the current streak (`active`, `streak_minutes`) — for example when the user asks "坐了多久了". If an activity-based reminder never fires, check that heartbeats are arriving before touching the schedule. Read [references/api.md](references/api.md) only when constructing an uncommon request or diagnosing validation behavior.
