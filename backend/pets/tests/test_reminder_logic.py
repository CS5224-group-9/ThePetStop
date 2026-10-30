from datetime import UTC, date, datetime, timedelta

from django.test import SimpleTestCase

from pets import reminders
from pets.models import Reminder

TODAY = date(2026, 10, 30)


def reminder(day: date, done=False) -> Reminder:
    """An unsaved reminder due at 09:00 Singapore time on this day."""
    return Reminder(title="Booster", due_at=reminders.due_at_for_date(day), done=done)


class ReminderLogicTests(SimpleTestCase):
    def test_today_is_the_singapore_calendar_date(self):
        now = datetime(2026, 10, 30, 16, 30, tzinfo=UTC)
        self.assertEqual(reminders.today_sgt(now), date(2026, 10, 31))
        now = datetime(2026, 10, 30, 15, 59, tzinfo=UTC)
        self.assertEqual(reminders.today_sgt(now), date(2026, 10, 30))

    def test_due_date_is_the_singapore_calendar_date(self):
        due_at = datetime(2026, 10, 31, 16, 30, tzinfo=UTC)
        self.assertEqual(reminders.due_date(due_at), date(2026, 11, 1))

    def test_is_overdue(self):
        self.assertTrue(
            reminders.is_overdue(reminder(TODAY - timedelta(days=1)), TODAY)
        )
        self.assertFalse(
            reminders.is_overdue(reminder(TODAY - timedelta(days=1), done=True), TODAY)
        )
        self.assertFalse(reminders.is_overdue(reminder(TODAY), TODAY))

    def test_is_due_soon(self):
        self.assertTrue(reminders.is_due_soon(reminder(TODAY), TODAY))
        self.assertTrue(
            reminders.is_due_soon(reminder(TODAY + timedelta(days=7)), TODAY)
        )
        self.assertFalse(
            reminders.is_due_soon(reminder(TODAY + timedelta(days=8)), TODAY)
        )
        self.assertFalse(
            reminders.is_due_soon(reminder(TODAY - timedelta(days=1)), TODAY)
        )
        self.assertFalse(reminders.is_due_soon(reminder(TODAY, done=True), TODAY))

    def test_overdue_and_due_soon_are_exclusive(self):
        for offset in range(-3, 10):
            for done in [False, True]:
                item = reminder(TODAY + timedelta(days=offset), done=done)
                with self.subTest(offset=offset, done=done):
                    self.assertFalse(
                        reminders.is_overdue(item, TODAY)
                        and reminders.is_due_soon(item, TODAY)
                    )

    def test_due_at_for_date_is_nine_am_in_singapore(self):
        due_at = reminders.due_at_for_date(date(2026, 11, 5))
        self.assertEqual(due_at.isoformat(), "2026-11-05T09:00:00+08:00")
        self.assertEqual(due_at, datetime(2026, 11, 5, 1, 0, tzinfo=UTC))
        self.assertEqual(due_at.tzinfo, reminders.SGT)
