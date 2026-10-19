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
  if (!localUI) return <LiveFacilityMap {...props} />;
  return (
    <div
      className="local-facility-map"
      aria-label="Singapore sample facility map"
    >
      <svg
        viewBox="0 0 800 470"
        role="img"
        aria-label="Schematic of Singapore, approximate locations"
        preserveAspectRatio="xMidYMid slice"
      >
        <rect width="800" height="470" fill="#dbe9eb" />
        <path
          d="M65 290L107 229L160 223L190 156L274 116L347 99L409 136L481 128L551 159L624 167L719 230L746 284L674 314L611 311L545 350L462 337L402 358L337 322L249 334L182 312L121 327Z"
          fill="#e9eee4"
          stroke="#c6d4c7"
          strokeWidth="3"
        />
        <path
          d="M110 279L263 242L409 202L574 220L702 262 M190 290L337 262L485 282L627 274 M291 149L332 264L403 329 M487 151L485 282"
          fill="none"
          stroke="#fff"
          strokeWidth="12"
        />
        <path
          d="M110 279L263 242L409 202L574 220L702 262 M190 290L337 262L485 282L627 274 M291 149L332 264L403 329 M487 151L485 282"
          fill="none"
          stroke="#d6d3be"
          strokeWidth="2"
        />
        <path d="M351 127L374 173L355 217L325 204L319 166Z" fill="#c5d9bd" />
        <g fill="#526b65" fontSize="16" fontFamily="system-ui">
          <text x="120" y="203">
            Jurong
          </text>
          <text x="350" y="110">
            Central catchment
          </text>
          <text x="594" y="195">
            Tampines
          </text>
          <text x="446" y="335">
            City centre
          </text>
        </g>
      </svg>
      <span className="local-map-caption">SINGAPORE · SCHEMATIC MAP</span>
      {props.facilities.map((f) => (
        <button
          key={f.id}
          type="button"
          className={`local-map-pin facility-live-marker ${f.id === props.selected ? "active" : ""}`}
          style={{
            left: `${15 + (((f.longitude ?? 103.8) - 103.7) / 0.3) * 70}%`,
            top: `${75 - (((f.latitude ?? 1.33) - 1.28) / 0.13) * 65}%`,
          }}
          aria-label={`Show ${f.name}`}
          aria-pressed={f.id === props.selected}
          title={f.name}
          onClick={() => props.onSelect(f.id)}
        >
          {f.type === "Pet shop" ? "●" : "+"}
        </button>
      ))}
      <span className="local-map-note">
        Sample locations · Not for navigation
      </span>
    </div>
  );
}
