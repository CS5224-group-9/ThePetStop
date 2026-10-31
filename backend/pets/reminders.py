"""Reminder dates in Singapore time. Computed per request; nothing is stored.

The pure functions accept unsaved Reminder instances. Nothing here creates
reminders: `due_at_for_date` is for seed data and matches the frontend, which
sends a date picked in a date input as 09:00 Asia/Singapore.
"""

import datetime
import zoneinfo
from datetime import date, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from .models import Reminder

SGT = zoneinfo.ZoneInfo("Asia/Singapore")
DUE_SOON_DAYS = 7
DEFAULT_DUE_TIME = datetime.time(9, 0)


def today_sgt(now: datetime.datetime | None = None) -> date:
    """Today's calendar date in Singapore."""
    return (now or timezone.now()).astimezone(SGT).date()


def due_date(due_at: datetime.datetime) -> date:
    """The Singapore calendar date a reminder is due on."""
    return due_at.astimezone(SGT).date()


def is_overdue(reminder: Reminder, today: date) -> bool:
    """Open and due before today."""
    return not reminder.done and due_date(reminder.due_at) < today


def is_due_soon(reminder: Reminder, today: date) -> bool:
    """Open and due today or within the next DUE_SOON_DAYS days (inclusive)."""
    if reminder.done:
        return False
    return today <= due_date(reminder.due_at) <= today + timedelta(days=DUE_SOON_DAYS)


def due_at_for_date(day: date) -> datetime.datetime:
    """09:00 Singapore time on this date."""
    return datetime.datetime.combine(day, DEFAULT_DUE_TIME, tzinfo=SGT)


def owner_reminders(user) -> QuerySet[Reminder]:
    """All of this user's reminders, including done ones, soonest first."""
    return Reminder.objects.filter(pet__owner=user).order_by(
        "due_at", "created_at", "id"
    )
