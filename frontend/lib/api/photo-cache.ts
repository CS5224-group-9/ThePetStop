// Downloaded pet photos as object URLs, keyed by pet and `photo_version`.
// Presigned `photo_url`s change on every response, so the version (not the
// URL) decides whether a photo must be fetched again. Cleared on sign-out so
// the next user of the tab never sees another owner's photos.
import { transferPrivateFile } from "./client.ts";

type Deps = {
  fetchBlob: (url: string) => Promise<Blob>;
  createUrl: (blob: Blob) => string;
  revokeUrl: (url: string) => void;
};
type Entry = {
  version: string;
  promise: Promise<string | null>;
  url: string | null;
};

export function createPhotoCache(deps: Deps): {
  load(
    petId: string,
    version: string,
    sourceUrl: string | null,
  ): Promise<string | null>;
  peek(petId: string, version: string): string | null;
  forget(petId: string): void;
  clear(): void;
} {
  const entries = new Map<string, Entry>();
  const release = (entry: Entry | undefined) => {
    if (entry?.url) deps.revokeUrl(entry.url);
  };
  async function fetchInto(
    petId: string,
    entry: Entry,
    sourceUrl: string,
  ): Promise<string | null> {
    try {
      const blob = await deps.fetchBlob(sourceUrl);
      if (!blob.type.startsWith("image/")) throw new Error("Not an image.");
      const url = deps.createUrl(blob);
      if (entries.get(petId) !== entry) {
        // Cleared, forgotten or replaced by a newer version meanwhile.
        deps.revokeUrl(url);
        return null;
      }
      entry.url = url;
      return url;
    } catch {
      if (entries.get(petId) === entry) entries.delete(petId);
      return null;
    }
  }
  return {
    load(petId, version, sourceUrl) {
      const current = entries.get(petId);
      if (current?.version === version) return current.promise;
      if (!sourceUrl) return Promise.resolve(null);
      release(current);
      const entry: Entry = {
        version,
        url: null,
        promise: Promise.resolve(null),
      };
      // Register before fetching, so a failure can always tell it is current.
      entries.set(petId, entry);
      entry.promise = fetchInto(petId, entry, sourceUrl);
      return entry.promise;
    },
    peek(petId, version) {
      const entry = entries.get(petId);
      return entry?.version === version ? entry.url : null;
    },
    forget(petId) {
      release(entries.get(petId));
      entries.delete(petId);
    },
    clear() {
      for (const entry of entries.values()) release(entry);
      entries.clear();
    },
  };
}

export const photoCache = createPhotoCache({
  fetchBlob: async (url) => (await transferPrivateFile(url)).blob(),
  createUrl: (blob) => URL.createObjectURL(blob),
  revokeUrl: (url) => URL.revokeObjectURL(url),
});
