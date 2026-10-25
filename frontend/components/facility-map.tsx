"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, Marker } from "maplibre-gl";
import { singaporeBounds, type SearchLocation } from "@/lib/location";
import type { Facility } from "@/lib/api/types";
function LiveFacilityMap({
  facilities,
  selected,
  onSelect,
  location,
}: {
  facilities: Facility[];
  selected: string;
  onSelect: (id: string) => void;
  location: SearchLocation | null;
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
      .then(({ Map, NavigationControl }) => {
        if (!current || !container.current) return;
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
    if (!ready || !map.current || !location) return;
    let current = true;
    let marker: Marker | undefined;
    const instance = map.current;
    import("maplibre-gl").then(({ Marker }) => {
      if (!current) return;
      const element = document.createElement("div");
      element.className = "current-location-marker";
      element.setAttribute("role", "img");
      element.setAttribute("aria-label", location.label);
      element.title = location.label;
      marker = new Marker({ element })
        .setLngLat([location.longitude, location.latitude])
        .addTo(instance);
      instance.flyTo({
        center: [location.longitude, location.latitude],
        zoom: 15,
        animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      });
    });
    return () => {
      current = false;
      marker?.remove();
    };
  }, [location, ready]);
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
}) {
  return <LiveFacilityMap {...props} />;
}
