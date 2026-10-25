import { api, ApiError, type createApiClient } from "./client.ts";
import { singaporeBounds, type SearchLocation } from "../location.ts";

export type LocationResult = SearchLocation & {
  source: "search";
  postal_code: string | null;
};

// Address search always uses the real API, including in local facility-data mode.
export function createLocationService(
  client: ReturnType<typeof createApiClient>,
) {
  return async (
    query: string,
    signal?: AbortSignal,
  ): Promise<LocationResult[]> => {
    const value: unknown = await client.request(
      `locations/search/?${new URLSearchParams({ q: query.trim() })}`,
      { signal },
    );
    const invalid = () =>
      new ApiError(
        502,
        "invalid_response",
        "Location search returned an unexpected response. Please try again.",
      );
    if (
      !value ||
      typeof value !== "object" ||
      !("results" in value) ||
      !Array.isArray(value.results) ||
      value.results.length > 10
    )
      throw invalid();
    return value.results.map((row: unknown) => {
      if (!row || typeof row !== "object") throw invalid();
      const r = row as Record<string, unknown>;
      const [sw, ne] = singaporeBounds;
      if (
        typeof r.label !== "string" ||
        !r.label.trim() ||
        typeof r.latitude !== "number" ||
        !Number.isFinite(r.latitude) ||
        r.latitude < sw[1] ||
        r.latitude > ne[1] ||
        typeof r.longitude !== "number" ||
        !Number.isFinite(r.longitude) ||
        r.longitude < sw[0] ||
        r.longitude > ne[0] ||
        !(
          r.postal_code === null ||
          (typeof r.postal_code === "string" && /^\d{6}$/.test(r.postal_code))
        )
      )
        throw invalid();
      return {
        label: r.label,
        latitude: r.latitude,
        longitude: r.longitude,
        postal_code: r.postal_code,
        source: "search",
      };
    });
  };
}
export const searchLocations = createLocationService(api);
