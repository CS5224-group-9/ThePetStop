// Client-side checks that mirror the API limits, so problems are reported
// before any request is made.
export const PHOTO_TYPES: readonly string[] = ["image/jpeg", "image/png"];
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
export const DOCUMENT_TYPES: readonly string[] = [
  "application/pdf",
  "image/jpeg",
  "image/png",
];
export const DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
const MAX_ALLERGIES = 20;
const MAX_ALLERGY_LENGTH = 50;

type FileLike = { type: string; size: number };
const fits = (
  file: FileLike,
  types: readonly string[],
  maxBytes: number,
): boolean =>
  types.includes(file.type) && file.size >= 1 && file.size <= maxBytes;

export function photoProblem(file: FileLike): string | null {
  return fits(file, PHOTO_TYPES, PHOTO_MAX_BYTES)
    ? null
    : "Choose a JPEG or PNG photo up to 5 MB.";
}

export function documentProblem(file: FileLike): string | null {
  return fits(file, DOCUMENT_TYPES, DOCUMENT_MAX_BYTES)
    ? null
    : "Choose a PDF, JPEG or PNG file up to 10 MB.";
}

/** Splits comma-separated allergies, trimming and dropping blanks and case-insensitive duplicates. */
export function parseAllergies(text: string): {
  allergies: string[];
  problem: string | null;
} {
  const seen = new Set<string>();
  const allergies: string[] = [];
  for (const raw of text.split(",")) {
    const item = raw.trim();
    const folded = item.toLowerCase();
    if (!item || seen.has(folded)) continue;
    seen.add(folded);
    allergies.push(item);
  }
  const problem =
    allergies.length > MAX_ALLERGIES
      ? "List up to 20 allergies, separated by commas."
      : allergies.some((item) => item.length > MAX_ALLERGY_LENGTH)
        ? "Each allergy can be up to 50 characters. Separate allergies with commas."
        : null;
  return { allergies, problem };
}
