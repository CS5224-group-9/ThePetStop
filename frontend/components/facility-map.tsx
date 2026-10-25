"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, Marker } from "maplibre-gl";
import { localUI } from "@/lib/data-source";
import type { Facility } from "@/lib/api/types";
function LiveFacilityMap({
  facilities,
  selected,
  onSelect,
}: {
  facilities: Facility[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    let resize: ResizeObserver | null = null;
    import("maplibre-gl")
      .then(({ Map, NavigationControl }) => {
        if (!current || !container.current) return;
        const instance = new Map({
          container: container.current,
          center: [103.83, 1.35],
          zoom: 11,
          minZoom: 11,
          maxZoom: 19,
          maxBounds: [
            [103.55, 1.15],
            [104.15, 1.5],
          ],
          style: {
            version: 8,
            sources: {
              onemap: {
                type: "raster",
                tiles: [
                  "https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png",
                ],
                tileSize: 256,
                minzoom: 11,
                maxzoom: 19,
                attribution:
                  '<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener noreferrer">OneMap</a> &copy; contributors | <a href="https://www.sla.gov.sg/" target="_blank" rel="noopener noreferrer">Singapore Land Authority</a>',
              },
            },
            layers: [{ id: "onemap", type: "raster", source: "onemap" }],
          },
        });
        map.current = instance;
        instance.addControl(
          new NavigationControl({ showCompass: false }),
          "top-right",
        );
        instance.on("load", () => {
          if (current) setReady(true);
        });
        instance.on("error", () => {
          if (current)
            setError(
              "Map tiles are unavailable. You can still use the facility list and directions links.",
            );
        });
        resize = new ResizeObserver(() => instance.resize());
        resize.observe(container.current);
      })
      .catch(() => {
        if (current)
          setError(
            "The map could not be loaded. Use the facility list to continue.",
          );
      });
    return () => {
      current = false;
      resize?.disconnect();
      markers.current.forEach((m) => m.remove());
      markers.current = [];
      map.current?.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    let current = true;
    if (!ready || !map.current) return;
    const instance = map.current;
    markers.current.forEach((marker) => marker.remove());
    markers.current = [];
    import("maplibre-gl").then(({ Marker }) => {
      if (!current) return;
      for (const facility of facilities) {
        if (facility.latitude === null || facility.longitude === null) continue;
        const element = document.createElement("button");
        element.type = "button";
        element.className = `facility-live-marker ${facility.id === selected ? "active" : ""} ${facility.emergency ? "emergency" : ""}`;
        element.textContent = facility.type === "Pet shop" ? "●" : "+";
        element.setAttribute("aria-label", `Show ${facility.name}`);
        element.setAttribute("aria-pressed", String(facility.id === selected));
        element.addEventListener("click", () => onSelect(facility.id));
        markers.current.push(
          new Marker({ element })
            .setLngLat([facility.longitude, facility.latitude])
            .addTo(instance),
        );
      }
    });
    return () => {
      current = false;
    };
  }, [facilities, selected, onSelect, ready]);
  return (
    <>
      <div
        ref={container}
        className="live-map"
        aria-label="Singapore facility map"
      />
      {!ready && !error && (
        <p className="map-status" role="status">
          Loading Singapore map…
        </p>
      )}
      {error && (
        <p className="map-status" role="status">
          {error}
        </p>
      )}
    </>
  );
}

export function FacilityMap(props: {
  facilities: Facility[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  return <LiveFacilityMap {...props} />;
}
