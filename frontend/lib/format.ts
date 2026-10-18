export const money = (cents: number) =>
  new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" }).format(
    cents / 100,
  );
export const displayDate = (date: string) => {
  if (!date) return "Not recorded";
  const value = new Date(date.includes("T") ? date : `${date}T12:00:00+08:00`);
  return Number.isNaN(value.getTime())
    ? "Not recorded"
    : value.toLocaleDateString("en-SG", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "Asia/Singapore",
      });
};
export const todaySG = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Singapore",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export const safeExternalUrl = (value?: string | null) => {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
};
export function nextPath(value: unknown, fallback = "/pets/") {
  return typeof value === "string" &&
    value.startsWith("/") &&
    !value.startsWith("//") &&
    !Array.from(value).some(
      (c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 92,
    ) &&
    !value.startsWith("/auth/") &&
    !value.startsWith("/login")
    ? value
    : fallback;
}
