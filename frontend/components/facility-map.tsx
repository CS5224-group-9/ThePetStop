"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, Marker } from "maplibre-gl";
import { radiusArea } from "@/lib/facility-search";
import { singaporeBounds, type SearchLocation } from "@/lib/location";
import type { Facility } from "@/lib/api/types";
function LiveFacilityMap({
  facilities,
  selected,
  onSelect,
  location,
  radiusKm,
}: {
  facilities: Facility[];
  selected: string;
  onSelect: (id: string) => void;
  location: SearchLocation | null;
  radiusKm: number | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const selectedId = useRef(selected);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    let resize: ResizeObserver | null = null;
    import("maplibre-gl")
      .then(({ Map, NavigationControl, getVersion, setWorkerUrl }) => {
        if (!current || !container.current) return;
        // Next.js bundles the main module, so its relative worker URL isn't
        // reliable. predev/prebuild publish the matching version locally.
        setWorkerUrl(`/maplibre/${getVersion()}/maplibre-gl-worker.mjs`);
        const instance = new Map({
          container: container.current,
          center: [103.83, 1.35],
          zoom: 11,
          minZoom: 11,
          maxZoom: 19,
          maxBounds: singaporeBounds,
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
                // OneMap's published TileJSON coverage. Avoid tile requests
                // beyond the provider's extent when panning near the edges.
                bounds: [103.502, 1.16, 104.11475, 1.56073],
                attribution:
                  '<img src="https://www.onemap.gov.sg/web-assets/images/logo/om_logo.png" alt="" width="20" height="20" /> <a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener noreferrer">OneMap</a> &copy; contributors | <a href="https://www.sla.gov.sg/" target="_blank" rel="noopener noreferrer">Singapore Land Authority</a>',
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
        instance.on("error", (event) => {
          if (process.env.NODE_ENV === "development")
            console.warn("[Facility map]", event.error);
          if (current)
            setError(
              "Some map content could not load. You can still use the facility list and directions links.",
            );
        });
        instance.on("sourcedata", (event) => {
          // Clear a transient warning when a OneMap tile loads successfully.
          // Source metadata/idle events alone don't prove that a tile loaded.
          if (
            current &&
            event.sourceId === "onemap" &&
            event.sourceDataType === "content" &&
            event.coord
          )
            setError("");
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
    if (!ready || !map.current) return;
    if (!location) {
      map.current.fitBounds(singaporeBounds, { padding: 40, animate: false });
      return;
    }
    let current = true;
    let marker: Marker | undefined;
    const instance = map.current;
    import("maplibre-gl").then(({ Marker }) => {
      if (!current) return;
      const element = document.createElement("div");
      element.className =
        location.source === "device"
          ? "current-location-marker"
          : "searched-location-marker";
      if (location.source === "search") {
        // Constant SVG; location labels are assigned separately as text attributes.
        element.innerHTML =
          '<svg viewBox="0 0 32 40" aria-hidden="true"><path d="M16 1C8 1 2 7 2 15c0 10 14 24 14 24s14-14 14-24C30 7 24 1 16 1Z" fill="currentColor" stroke="white" stroke-width="2"/><circle cx="16" cy="15" r="5" fill="white"/></svg>';
      }
      element.setAttribute("role", "img");
      element.setAttribute("aria-label", location.label);
      element.title = location.label;
      marker = new Marker({
        element,
        anchor: location.source === "search" ? "bottom" : "center",
      })
        .setLngLat([location.longitude, location.latitude])
        .addTo(instance);
      const animate = !window.matchMedia("(prefers-reduced-motion: reduce)")
        .matches;
      if (radiusKm === null) {
        instance.fitBounds(singaporeBounds, { padding: 40, animate });
      } else {
        const ring = radiusArea(location, radiusKm).geometry.coordinates[0];
        const xs = ring.map((point) => point[0]),
          ys = ring.map((point) => point[1]);
        instance.fitBounds(
          [
            [Math.min(...xs), Math.min(...ys)],
            [Math.max(...xs), Math.max(...ys)],
          ],
          { padding: 40, maxZoom: 15, animate },
        );
      }
    });
    return () => {
      current = false;
      marker?.remove();
    };
  }, [location, radiusKm, ready]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const instance = map.current;
    const id = "facility-search-radius";
    if (!location || radiusKm === null) {
      if (instance.getLayer(`${id}-line`)) instance.removeLayer(`${id}-line`);
      if (instance.getLayer(`${id}-fill`)) instance.removeLayer(`${id}-fill`);
      if (instance.getSource(id)) instance.removeSource(id);
      return;
    }
    const data = radiusArea(location, radiusKm);
    const source = instance.getSource<import("maplibre-gl").GeoJSONSource>(id);
    if (source) source.setData(data);
    else {
      instance.addSource(id, { type: "geojson", data });
      instance.addLayer({
        id: `${id}-fill`,
        type: "fill",
        source: id,
        paint: { "fill-color": "#006b5f", "fill-opacity": 0.08 },
      });
      instance.addLayer({
        id: `${id}-line`,
        type: "line",
        source: id,
        paint: {
          "line-color": "#006b5f",
          "line-width": 2,
          "line-dasharray": [3, 2],
        },
      });
    }
  }, [location, radiusKm, ready]);
  useEffect(() => {
    selectedId.current = selected;
    markers.current.forEach((marker) => {
      const element = marker.getElement();
      const active = element.dataset.facilityId === selected;
      element.classList.toggle("active", active);
      element.setAttribute("aria-pressed", String(active));
    });
    const facility = facilities.find((f) => f.id === selected);
    if (
      !ready ||
      !map.current ||
      !facility ||
      facility.latitude === null ||
      facility.longitude === null
    )
      return;
    map.current.flyTo({
      center: [facility.longitude, facility.latitude],
      zoom: Math.max(map.current.getZoom(), 14),
      animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
  }, [selected, facilities, ready]);
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
        element.dataset.facilityId = facility.id;
        const active = facility.id === selectedId.current;
        element.className = `facility-live-marker ${active ? "active" : ""} ${facility.type === "Pet shop" ? "shop" : "vet"}`;
        const svg = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "svg",
        );
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "1.8");
        svg.setAttribute("stroke-linecap", "round");
        svg.setAttribute("stroke-linejoin", "round");
        svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "path",
        );
        path.setAttribute(
          "d",
          facility.type === "Pet shop"
            ? "M4 7h16l1 14H3Z M8 8V6a4 4 0 0 1 8 0v2"
            : "M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6Z",
        );
        svg.appendChild(path);
        element.appendChild(svg);
        element.setAttribute("aria-label", `Show ${facility.name}`);
        element.setAttribute("aria-pressed", String(active));
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
  }, [facilities, onSelect, ready]);
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
  location: SearchLocation | null;
  radiusKm: number | null;
}) {
  return <LiveFacilityMap {...props} />;
}
