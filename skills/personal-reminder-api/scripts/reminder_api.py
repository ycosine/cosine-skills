#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def request(method, path, payload=None):
    base = os.environ.get("PERSONAL_REMINDER_API_URL", "").rstrip("/")
    token = os.environ.get("PERSONAL_REMINDER_API_TOKEN", "")
    if not base or not token:
        raise RuntimeError("Set PERSONAL_REMINDER_API_URL and PERSONAL_REMINDER_API_TOKEN")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"API returned HTTP {error.code}: {detail}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach reminder API: {error.reason}") from None


def parser():
    root = argparse.ArgumentParser(description="Personal Reminder API client")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("list-schedules")

    schedule = commands.add_parser("set-schedule")
    schedule.add_argument("id")
    schedule.add_argument("--times", help='fixed local fire times, e.g. "10:30" or "11:50,18:00"')
    schedule.add_argument("--interval", type=int)
    schedule.add_argument("--start")
    schedule.add_argument("--end")
    schedule.add_argument("--weekdays")
    schedule.add_argument("--windows", help='e.g. "10:00-12:00,14:00-18:00"')
    state = schedule.add_mutually_exclusive_group()
    state.add_argument("--enable", action="store_true")
    state.add_argument("--disable", action="store_true")
    schedule.add_argument("--title")
    schedule.add_argument("--body")
    activity_mode = schedule.add_mutually_exclusive_group()
    activity_mode.add_argument("--activity-based", action="store_true")
    activity_mode.add_argument("--wall-clock", action="store_true")

    timer = commands.add_parser("create-timer")
    when = timer.add_mutually_exclusive_group(required=True)
    when.add_argument("--minutes", type=float)
    when.add_argument("--due-at")
    timer.add_argument("--title")
    timer.add_argument("--body")

    create = commands.add_parser("create-schedule")
    create.add_argument("id")
    create.add_argument("--title", required=True)
    create.add_argument("--body")
    create.add_argument("--times", help='fixed local fire times, e.g. "10:30" or "11:50,18:00"')
    create.add_argument("--interval", type=int)
    create.add_argument("--windows")
    create.add_argument("--weekdays")
    create.add_argument("--activity-based", action="store_true")
    delete = commands.add_parser("delete-schedule")
    delete.add_argument("id")

    list_timers = commands.add_parser("list-timers")
    list_timers.add_argument("--limit", type=int, default=50)
    cancel = commands.add_parser("cancel-timer")
    cancel.add_argument("id")
    test = commands.add_parser("test")
    test.add_argument("--title")
    test.add_argument("--body")
    events = commands.add_parser("events")
    events.add_argument("--limit", type=int, default=50)
    commands.add_parser("activity")
    health = commands.add_parser("health")
    health.add_argument("--metric", default="step_count")
    health.add_argument("--hours", type=int, default=24)
    health.add_argument("--limit", type=int, default=200)
    workouts = commands.add_parser("workouts")
    workouts.add_argument("--limit", type=int, default=10)
    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("--source", default="manual")
    return root


def main():
    args = parser().parse_args()
    if args.command == "status":
        result = request("GET", "/api/v1/status")
    elif args.command == "list-schedules":
        result = request("GET", "/api/v1/schedules")
    elif args.command == "set-schedule":
        payload = {}
        if args.interval is not None:
            payload["interval_minutes"] = args.interval
        if args.start is not None:
            payload["window_start"] = args.start
        if args.end is not None:
            payload["window_end"] = args.end
        if args.weekdays is not None:
            payload["weekdays"] = [int(day) for day in args.weekdays.split(",") if day]
        if args.windows is not None:
            payload["windows"] = [w.strip() for w in args.windows.split(",") if w.strip()]
        if args.times is not None:
            payload["times"] = [t.strip() for t in args.times.split(",") if t.strip()]
        if args.enable:
            payload["enabled"] = True
        if args.disable:
            payload["enabled"] = False
        if args.title is not None:
            payload["title"] = args.title
        if args.body is not None:
            payload["body"] = args.body
        if args.activity_based:
            payload["activity_based"] = True
        if args.wall_clock:
            payload["activity_based"] = False
        if not payload:
            raise RuntimeError("Provide at least one schedule change")
        result = request("PUT", "/api/v1/schedules/" + urllib.parse.quote(args.id), payload)
    elif args.command == "create-schedule":
        payload = {"id": args.id, "title": args.title}
        if args.body is not None:
            payload["body"] = args.body
        if args.times is not None:
            payload["times"] = [t.strip() for t in args.times.split(",") if t.strip()]
        if args.interval is not None:
            payload["interval_minutes"] = args.interval
        if args.windows is not None:
            payload["windows"] = [w.strip() for w in args.windows.split(",") if w.strip()]
        if args.weekdays is not None:
            payload["weekdays"] = [int(day) for day in args.weekdays.split(",") if day]
        if args.activity_based:
            payload["activity_based"] = True
        result = request("POST", "/api/v1/schedules", payload)
    elif args.command == "delete-schedule":
        result = request("DELETE", "/api/v1/schedules/" + urllib.parse.quote(args.id))
    elif args.command == "create-timer":
        payload = {"after_minutes": args.minutes} if args.minutes is not None else {"due_at": args.due_at}
        if args.title is not None:
            payload["title"] = args.title
        if args.body is not None:
            payload["body"] = args.body
        result = request("POST", "/api/v1/timers", payload)
    elif args.command == "list-timers":
        result = request("GET", "/api/v1/timers?limit=" + str(args.limit))
    elif args.command == "cancel-timer":
        result = request("DELETE", "/api/v1/timers/" + urllib.parse.quote(args.id))
    elif args.command == "test":
        payload = {}
        if args.title is not None:
            payload["title"] = args.title
        if args.body is not None:
            payload["body"] = args.body
        result = request("POST", "/api/v1/test", payload)
    elif args.command == "events":
        result = request("GET", "/api/v1/events?limit=" + str(args.limit))
    elif args.command == "activity":
        result = request("GET", "/api/v1/activity")
    elif args.command == "health":
        result = request("GET", f"/api/v1/health?metric={urllib.parse.quote(args.metric)}&hours={args.hours}&limit={args.limit}")
    elif args.command == "workouts":
        result = request("GET", f"/api/v1/workouts?limit={args.limit}")
    elif args.command == "heartbeat":
        result = request("POST", "/api/v1/activity", {"source": args.source})
    else:
        raise RuntimeError("Unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
