export type SearchLocation = {
  latitude: number;
  longitude: number;
  label: string;
  source: "search" | "device";
  accuracyMetres?: number;
};

// Match the bounds of the Singapore facility map, not a jurisdiction boundary.
export const singaporeBounds: [[number, number], [number, number]] = [
  [103.55, 1.15],
  [104.15, 1.5],
];

export function currentLocation(
  geolocation: Pick<Geolocation, "getCurrentPosition"> | undefined,
  secureContext: boolean,
): Promise<SearchLocation> {
  if (!secureContext)
    return Promise.reject(new Error("Location requires HTTPS or localhost."));
  if (!geolocation)
    return Promise.reject(
      new Error("Your browser does not support location access."),
    );
  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      ({ coords }) => {
        const { latitude, longitude, accuracy } = coords;
        const [sw, ne] = singaporeBounds;
        if (
          !Number.isFinite(latitude) ||
          !Number.isFinite(longitude) ||
          longitude < sw[0] ||
          longitude > ne[0] ||
          latitude < sw[1] ||
          latitude > ne[1]
        ) {
          reject(
            new Error(
              "Your location is outside this map’s Singapore coverage. You can still browse the facility list.",
            ),
          );
          return;
        }
        resolve({
          latitude,
          longitude,
          label: "Your current location",
          source: "device",
          accuracyMetres:
            Number.isFinite(accuracy) && accuracy >= 0 ? accuracy : undefined,
        });
      },
      ({ code }) =>
        reject(
          new Error(
            code === 1
              ? "Location permission was denied. Allow location access in your browser settings to try again."
              : code === 3
                ? "Finding your location timed out. Please try again."
                : "Your location is unavailable. Please try again.",
          ),
        ),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });
}
