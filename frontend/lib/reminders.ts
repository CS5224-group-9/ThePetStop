import { todaySG } from "./format.ts";
import type { HealthRecord, Reminder } from "./api/types.ts";

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Adds calendar days to a YYYY-MM-DD date. */
export function addDays(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days))
    .toISOString()
    .slice(0, 10);
}

/**
 * The backend rule (Asia/Singapore calendar dates): an open reminder is
 * overdue before today and due soon from today to today + 7 days inclusive.
 */
export function reminderStatus(
  due_date: string,
  done: boolean,
  today = todaySG(),
): { is_overdue: boolean; is_due_soon: boolean } {
  if (done || !DATE.test(due_date))
    return { is_overdue: false, is_due_soon: false };
  return {
    is_overdue: due_date < today,
    is_due_soon: due_date >= today && due_date <= addDays(today, 7),
  };
}

/**
 * Whether a care record's next due date is already covered by a reminder of
 * the same pet: one linked to the record (done or not), or one with the same
 * title and due date.
 */
export function recordHasReminder(
  petId: string,
  record: HealthRecord,
  reminders: Reminder[],
): boolean {
  return reminders.some(
    (r) =>
      r.pet_id === petId &&
      (r.health_record_id === record.id ||
        (r.title === record.title && r.due_date === record.next_due)),
  );
}
