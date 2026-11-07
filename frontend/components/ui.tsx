"use client";
import { useEffect, useState, type ReactNode } from "react";
import Image from "next/image";
import { localUI } from "@/lib/data-source";
import { photoCache } from "@/lib/api/photo-cache";
import type { Reminder } from "@/lib/api/types";
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    medical: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <path d="M10 7h4v3h3v4h-3v3h-4v-3H7v-4h3Z" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="3" />
        <path d="M5 21v-2a7 7 0 0 1 14 0v2Z" />
      </>
    ),
    filter: (
      <>
        <path d="M4 6h16M7 12h10m-7 6h4" />
        <circle cx="9" cy="6" r="2" fill="currentColor" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4m10-4v4M3 10h18m-13 4h2m4 0h2m-8 3h2" />
      </>
    ),

    paw: (
      <>
        <ellipse cx="12" cy="15" rx="5" ry="4" />
        <ellipse cx="5" cy="9" rx="2" ry="3" />
        <ellipse cx="10" cy="5" rx="2" ry="3" />
        <ellipse cx="16" cy="6" rx="2" ry="3" />
        <ellipse cx="20" cy="11" rx="2" ry="3" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    map: (
      <>
        <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z" />
        <path d="M9 3v15m6-12v15" />
      </>
    ),
    bag: (
      <>
        <path d="M4 7h16l1 14H3Z" />
        <path d="M8 8V6a4 4 0 0 1 8 0v2" />
      </>
    ),
    heart: (
      <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />
    ),
    bell: (
      <>
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
        <path d="M10 21h4" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    check: <path d="m5 12 4 4L19 6" />,
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    shield: (
      <>
        <path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Z" />
        <path d="m8 11 3 3 5-5" />
      </>
    ),
    file: (
      <>
        <path d="M14 2H5v20h14V7Z" />
        <path d="M14 2v6h5M8 12h8m-8 4h6" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 6v6l4 2" />
      </>
    ),
    pin: (
      <>
        <path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" />
        <circle cx="12" cy="10" r="2.5" />
      </>
    ),
    box: (
      <>
        <path d="m12 2 10 5v10l-10 5-10-5V7Zm0 10v10M2 7l10 5 10-5M7 4.5l10 5v4" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.heart}
    </svg>
  );
}
export function Badge({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon name="box" size={36} />
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
/**
 * A pet's private photo, or a paw placeholder. API photos are downloaded once
 * per `photoVersion` into the shared photo cache: a fresh presigned
 * `photoUrl` with the same version neither refetches nor flickers.
 */
export function PetAvatar({
  species,
  large = false,
  petId = "",
  photoUrl = null,
  photoVersion = null,
}: {
  species: string;
  large?: boolean;
  petId?: string;
  photoUrl?: string | null;
  photoVersion?: string | null;
}) {
  // Local mode keeps photos as in-memory blob URLs; render them directly.
  const direct = localUI && photoUrl?.startsWith("blob:") ? photoUrl : null;
  const key = photoVersion ? `${petId}:${photoVersion}` : "";
  const [loaded, setLoaded] = useState<{ key: string; url: string | null }>({
    key: "",
    url: null,
  });
  const [broken, setBroken] = useState<string | null>(null);
  useEffect(() => {
    if (direct || !photoVersion) return;
    let live = true;
    const current = `${petId}:${photoVersion}`;
    void photoCache.load(petId, photoVersion, photoUrl).then((url) => {
      if (live) setLoaded({ key: current, url });
    });
    return () => {
      live = false;
    };
  }, [petId, photoVersion, photoUrl, direct]);
  const src =
    direct ??
    (key
      ? loaded.key === key
        ? loaded.url
        : photoCache.peek(petId, photoVersion as string)
      : null);
  return (
    <div
      className={`pet-avatar ${large ? "large" : ""}`}
      role="img"
      aria-label={`${species} profile`}
    >
      {src && src !== broken ? (
        <Image
          src={src}
          alt={`${species} profile photo`}
          width={180}
          height={180}
          onError={() => {
            setBroken(src);
            if (!direct) photoCache.forget(petId);
          }}
        />
      ) : (
        <Icon name="paw" size={large ? 40 : 22} />
      )}
    </div>
  );
}
/** Completed, Overdue, Due soon or Upcoming, from the reminder's flags. */
export function ReminderBadge({
  reminder,
  upcomingTone,
}: {
  reminder: Reminder;
  upcomingTone: "green" | "neutral";
}) {
  if (reminder.done) return <Badge tone="green">Completed</Badge>;
  if (reminder.is_overdue) return <Badge tone="rose">Overdue</Badge>;
  if (reminder.is_due_soon) return <Badge tone="amber">Due soon</Badge>;
  return <Badge tone={upcomingTone}>Upcoming</Badge>;
}
