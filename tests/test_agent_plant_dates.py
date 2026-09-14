"""Relative dates in agent queries follow the plant calendar, not the server clock."""

from __future__ import annotations

from datetime import date, datetime

from app.agent.queries import common
from app.agent.tools import execute_tool
from app.extensions import db
from app.models import Role, Task, TaskStatus, User


def test_day_bounds_convert_the_plant_day_to_utc(app):
    """A Berlin day in summer runs from 22:00 UTC the evening before to 22:00 UTC."""
    with app.app_context():
        start, end = common.day_bounds(date(2026, 9, 14))
        winter_start, _ = common.day_bounds(date(2026, 1, 14))

    assert start == datetime(2026, 9, 13, 22, 0)
    assert end == datetime(2026, 9, 14, 22, 0)
    assert winter_start == datetime(2026, 1, 13, 23, 0)


def test_plant_timezone_is_configurable(app):
    """PLANT_TIMEZONE moves the day bounds."""
    app.config["PLANT_TIMEZONE"] = "UTC"
    try:
        with app.app_context():
            start, end = common.day_bounds(date(2026, 9, 14))
    finally:
        app.config.pop("PLANT_TIMEZONE")

    assert (start, end) == (datetime(2026, 9, 14), datetime(2026, 9, 15))


def test_tasks_done_today_include_work_after_midnight_plant_time(
    app, make_user, make_task, monkeypatch
):
    """A task finished at 00:30 Berlin (22:30 UTC the day before) counts as done today."""
    admin = make_user(username="plant_day_admin", role=Role.MASTER_ADMIN, department_name=None)
    after_midnight = make_task("Nach Mitternacht", admin["username"], status=TaskStatus.DONE)
    before_midnight = make_task("Vor Mitternacht", admin["username"], status=TaskStatus.DONE)
    monkeypatch.setattr(common, "plant_today", lambda: date(2026, 9, 14))

    with app.app_context():
        db.session.get(Task, after_midnight).completed_at = datetime(2026, 9, 13, 22, 30)
        db.session.get(Task, before_midnight).completed_at = datetime(2026, 9, 13, 21, 30)
        db.session.commit()
        user = db.session.get(User, admin["id"])
        today = execute_tool("list_tasks", {"status": "done", "time_range": "today"}, user)
        yesterday = execute_tool("list_tasks", {"status": "done", "time_range": "yesterday"}, user)

    assert [item["title"] for item in today.content["items"]] == ["Nach Mitternacht"]
    assert [item["title"] for item in yesterday.content["items"]] == ["Vor Mitternacht"]
