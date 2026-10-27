import type { Facility } from "./api/types.ts";

export function filterFacilities(
  facilities: Facility[],
  filters: { query: string; type: string },
): Facility[] {
  const query = filters.query.trim().toLowerCase();
  return facilities.filter(
    (facility) =>
      (!filters.type || facility.type === filters.type) &&
      `${facility.name} ${facility.area} ${facility.address}`
        .toLowerCase()
        .includes(query),
  );
}

const earthRadiusKm = 6371;
const radians = (degrees: number) => (degrees * Math.PI) / 180;
const degrees = (radians: number) => (radians * 180) / Math.PI;
type Coordinates = { latitude: number; longitude: number };

export function distanceKm(from: Coordinates, to: Coordinates): number | null {
  if (
    ![from.latitude, from.longitude, to.latitude, to.longitude].every(
      Number.isFinite,
    ) ||
    Math.abs(from.latitude) > 90 ||
    Math.abs(to.latitude) > 90 ||
    Math.abs(from.longitude) > 180 ||
    Math.abs(to.longitude) > 180
  )
    return null;
  const lat1 = radians(from.latitude),
    lat2 = radians(to.latitude);
  const a =
    Math.sin((lat2 - lat1) / 2) ** 2 +
    Math.cos(lat1) *
      Math.cos(lat2) *
      Math.sin(radians(to.longitude - from.longitude) / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))));
}

export function nearbyFacilities(
  facilities: Facility[],
  filters: { type: string },
  centre: Coordinates | null,
  radiusKm: number | null,
): (Facility & { distance_km: number | null })[] {
  const results = filterFacilities(facilities, { ...filters, query: "" })
    .map((facility) => ({
      ...facility,
      distance_km:
        centre && facility.latitude !== null && facility.longitude !== null
          ? distanceKm(centre, {
              latitude: facility.latitude,
              longitude: facility.longitude,
            })
          : null,
    }))
    .filter(
      (facility) =>
        !centre ||
        radiusKm === null ||
        (facility.distance_km !== null && facility.distance_km <= radiusKm),
    );
  if (centre)
    results.sort(
      (a, b) =>
        (a.distance_km ?? Number.MAX_VALUE) -
          (b.distance_km ?? Number.MAX_VALUE) || a.name.localeCompare(b.name),
    );
  return results;
}

export function radiusArea(centre: Coordinates, radiusKm: number) {
  const lat = radians(centre.latitude),
    lng = radians(centre.longitude),
    angle = radiusKm / earthRadiusKm;
  const ring: number[][] = [];
  for (let step = 0; step < 72; step++) {
    const bearing = (2 * Math.PI * step) / 72;
    const latitude = Math.asin(
      Math.sin(lat) * Math.cos(angle) +
        Math.cos(lat) * Math.sin(angle) * Math.cos(bearing),
    );
    const longitude =
      lng +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angle) * Math.cos(lat),
        Math.cos(angle) - Math.sin(lat) * Math.sin(latitude),
      );
    ring.push([degrees(longitude), degrees(latitude)]);
  }
  ring.push([...ring[0]]);
  return {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "Polygon" as const, coordinates: [ring] },
  };
}
