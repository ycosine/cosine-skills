# API reference

All endpoints except `/healthz` require `Authorization: Bearer <token>` and use JSON.

| Operation | Method and path | Notes |
|---|---|---|
| Status | `GET /api/v1/status` | Reports timezone and whether Bark is configured. |
| List schedules | `GET /api/v1/schedules` | Includes `sedentary` and `water`. |
| Update schedule | `PUT /api/v1/schedules/{id}` | Accepts `enabled`, `interval_minutes`, `window_start`, `window_end`, `weekdays`, `title`, and `body`. |
| Test schedule | `POST /api/v1/schedules/{id}/test` | Sends immediately without changing its next run. |
| Create timer | `POST /api/v1/timers` | Provide exactly one of `after_minutes` or ISO 8601 `due_at`; maximum seven days. |
| List timers | `GET /api/v1/timers?limit=50` | Returns newest first. |
| Cancel timer | `DELETE /api/v1/timers/{id}` | Only pending timers can be cancelled. |
| Test Bark | `POST /api/v1/test` | Accepts optional `title` and `body`. |
| Events | `GET /api/v1/events?limit=50` | Returns delivery and configuration history. |

Recurring schedules run only inside their configured local-time window and weekdays. Timers ignore the recurring work window. Cooking timers use Bark's time-sensitive level and alarm sound.
