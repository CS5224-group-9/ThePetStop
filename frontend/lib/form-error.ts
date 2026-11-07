import { ApiError } from "./api/client.ts";

const FIELD_LABELS: Record<string, string> = {
  microchip_no: "Microchip number",
  date_of_birth: "Date of birth",
  weight_kg: "Weight",
  diet_notes: "Dietary preferences",
  allergies: "Allergies",
  next_due: "Next due date",
  record_type: "Record type",
  health_record: "Care record",
  due_at: "Due date",
};

function fieldLabel(field: string): string {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  const words = field.replaceAll("_", " ");
  return words ? words[0].toUpperCase() + words.slice(1) : words;
}

// DRF details are a list of messages per field, or (inside list fields) an
// object keyed by item index; take the first message at any depth.
function firstMessage(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return firstMessage(value[0]);
  if (value && typeof value === "object")
    return firstMessage(Object.values(value)[0]);
  return "";
}

/** A user-facing message for a failed form submission. */
export function formError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.code === "invalid") {
    const [first] = Object.entries(cause.details ?? {});
    if (first) {
      const [field, value] = first;
      let message = firstMessage(value);
      if (message.startsWith("Invalid pk"))
        message = "This item is no longer available. Refresh and try again.";
      if (message)
        return field === "non_field_errors"
          ? message
          : `${cause.message} ${fieldLabel(field)}: ${message}`;
    }
  }
  return cause instanceof Error ? cause.message : fallback;
}
