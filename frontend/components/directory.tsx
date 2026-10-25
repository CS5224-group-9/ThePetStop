"use client";
import "./facility-explorer.css";
import { localUI } from "@/lib/data-source";
import { useEffect, useMemo, useRef, useState } from "react";
import { currentLocation, type SearchLocation } from "@/lib/location";
import { useApp } from "./app-provider";
import { Badge, Empty, Icon } from "./ui";
import { ResourceState } from "./resource-state";
import { FacilityMap } from "./facility-map";
import { displayDate, safeExternalUrl } from "@/lib/format";
export function Directory() {
  const { state } = useApp();
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [emergency, setEmergency] = useState(false);
  const [selected, setSelected] = useState("");
  const [view, setView] = useState("split");
  const [location, setLocation] = useState<SearchLocation | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [showLocationPrompt, setShowLocationPrompt] = useState(true);
  const locationRequest = useRef(0);
  const pendingLocation = useRef(false);
  useEffect(
    () => () => {
      locationRequest.current += 1;
    },
    [],
  );
  async function locate() {
    if (pendingLocation.current) return;
    setShowLocationPrompt(false);
    pendingLocation.current = true;
    const request = ++locationRequest.current;
    setLocating(true);
    setLocationError("");
    try {
      const result = await currentLocation(
        navigator.geolocation,
        window.isSecureContext,
      );
      if (request !== locationRequest.current) return;
      setLocation(result);
      setView((value) => (value === "list" ? "split" : value));
    } catch (error) {
      if (request === locationRequest.current)
        setLocationError(
          error instanceof Error
            ? error.message
            : "Your location is unavailable. Please try again.",
        );
    } finally {
      pendingLocation.current = false;
      if (request === locationRequest.current) setLocating(false);
    }
  }
  const filtered = useMemo(
    () =>
      state.facilities.filter(
        (f) =>
          (!type || f.type === type) &&
          (!emergency || f.emergency) &&
          `${f.name} ${f.area} ${f.address}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [state.facilities, type, emergency, query],
  );
  const facility = filtered.find((f) => f.id === selected);
  const source = safeExternalUrl(facility?.source_url);
  const website = safeExternalUrl(facility?.website);
  function resetFilters() {
    setQuery("");
    setType("");
    setEmergency(false);
  }
  const hasFilters = Boolean(query || type || emergency);
  return (
    <div className="facility-explorer">
      <header className="explorer-heading">
        <div>
          <h1>Find pet care in Singapore</h1>
          <p>Explore veterinary centres and pet shops, all in one place.</p>
        </div>
      </header>
      {showLocationPrompt && (
        <section
          className="explorer-location-prompt"
          aria-labelledby="location-prompt-title"
        >
          <Icon name="pin" size={24} />
          <div>
            <h2 id="location-prompt-title">
              Start from your current location?
            </h2>
            <p>
              Centre the map on you. Your browser will ask for permission if
              needed, and your location stays in this page’s memory.
            </p>
          </div>
          <div className="explorer-prompt-actions">
            <button type="button" className="button" onClick={locate}>
              Use my location
            </button>
            <button
              type="button"
              className="explorer-locate"
              onClick={() => {
                setShowLocationPrompt(false);
                document.getElementById("explorer-locate")?.focus();
              }}
            >
              Not now
            </button>
          </div>
        </section>
      )}
      <ResourceState domain="facilities">
        <div className="explorer-workspace">
          <div className="explorer-controls">
            <div className="explorer-searchbar">
              <label className="explorer-search">
                <Icon name="search" size={20} />
                <input
                  type="search"
                  aria-label="Search facilities by name, neighbourhood or postal code"
                  placeholder="Search facilities, neighbourhood or postal code"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="explorer-locate"
                id="explorer-locate"
                onClick={locate}
                disabled={locating}
                aria-describedby="location-status"
              >
                <Icon name="pin" size={18} />
                {locating ? "Finding location…" : "Use my current location"}
              </button>
            </div>
            <div className="explorer-filterbar">
              <div
                className="explorer-scopes"
                role="group"
                aria-label="Facility type"
              >
                {[
                  ["", "All facilities", "map"],
                  ["Veterinary centre", "Vets", "medical"],
                  ["Pet shop", "Pet shops", "bag"],
                ].map(([value, label, icon]) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={type === value}
                    onClick={() => setType(value)}
                  >
                    <Icon name={icon} size={16} />
                    {label}
                  </button>
                ))}
              </div>
              <label className="explorer-emergency">
                <input
                  type="checkbox"
                  checked={emergency}
                  onChange={(e) => setEmergency(e.target.checked)}
                />
                24-hour emergency
              </label>
              <div
                className="explorer-views"
                role="group"
                aria-label="Directory layout"
              >
                {[
                  ["split", "Split"],
                  ["map", "Map"],
                  ["list", "List"],
                ].map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    id={`explorer-view-${value}`}
                    aria-pressed={view === value}
                    onClick={() => setView(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="explorer-panes" data-view={view}>
            <section className="explorer-results" aria-label="Facility results">
              <div className="explorer-results-heading">
                <h2 aria-live="polite">
                  {filtered.length}{" "}
                  {filtered.length === 1 ? "facility" : "facilities"}
                </h2>
                {hasFilters ? (
                  <button type="button" onClick={resetFilters}>
                    Clear filters
                  </button>
                ) : (
                  <span>Singapore</span>
                )}
              </div>
              <div className="explorer-rows">
                {filtered.length ? (
                  filtered.map((f) => (
                    <button
                      type="button"
                      className="explorer-row"
                      key={f.id}
                      id={`facility-result-${encodeURIComponent(f.id)}`}
                      aria-pressed={facility?.id === f.id}
                      aria-controls={
                        facility ? "facility-detail-panel" : undefined
                      }
                      onClick={() => setSelected(f.id)}
                    >
                      <span
                        className={`explorer-type-icon ${f.type === "Pet shop" ? "shop" : "vet"}`}
                      >
                        <Icon
                          name={f.type === "Pet shop" ? "bag" : "medical"}
                          size={20}
                        />
                      </span>
                      <span className="explorer-row-content">
                        <span className="explorer-row-heading">
                          <span className="explorer-row-type">{f.type}</span>
                          {f.emergency && (
                            <span className="explorer-hours-badge">
                              <Icon name="clock" size={13} />
                              24-hour
                            </span>
                          )}
                        </span>
                        <strong>{f.name}</strong>
                        <span className="explorer-row-address">
                          {f.address}
                        </span>
                        <span className="explorer-row-verification">
                          <Icon name="shield" size={13} />
                          {f.verification_status === "verified" &&
                          f.last_checked_at
                            ? "Registry checked"
                            : "Not verified"}
                        </span>
                        <span className="explorer-row-source">
                          {f.source || "Source not supplied"} ·{" "}
                          {f.last_checked_at
                            ? `Checked ${displayDate(f.last_checked_at)}`
                            : "Check date not supplied"}
                        </span>
                        <span className="explorer-row-action">
                          {facility?.id === f.id
                            ? "Selected · details below"
                            : "View facility"}
                          <Icon
                            name={facility?.id === f.id ? "check" : "arrow"}
                            size={14}
                          />
                        </span>
                      </span>
                    </button>
                  ))
                ) : (
                  <Empty title="No facilities found">
                    Try another name or{" "}
                    <button
                      type="button"
                      className="text-button"
                      onClick={resetFilters}
                    >
                      clear filters
                    </button>
                    .
                  </Empty>
                )}
              </div>
            </section>
            <section
              className="explorer-map"
              aria-label="Singapore facility map"
            >
              <FacilityMap
                facilities={filtered}
                selected={facility?.id || ""}
                onSelect={setSelected}
                location={location}
              />
            </section>
          </div>
          <div className="explorer-map-footer">
            <div className="explorer-legend" aria-label="Map legend">
              <span>
                <Icon name="medical" size={16} /> Vet
              </span>
              <span>
                <Icon name="bag" size={16} /> Pet shop
              </span>
              {location && (
                <span>
                  <span className="explorer-location-dot" />
                  Your location
                </span>
              )}
            </div>
            <p id="location-status" role="status">
              {locationError ||
                (locating
                  ? "Waiting for your browser’s location…"
                  : location
                    ? `Location marked${location.accuracyMetres !== undefined ? ` · accuracy approximately ${Math.max(1, Math.round(location.accuracyMetres))} m` : ""}`
                    : "Select a facility to explore its details.")}
            </p>
          </div>
        </div>
        {facility && (
          <section
            className="explorer-detail"
            id="facility-detail-panel"
            aria-label={`Details for ${facility.name}`}
          >
            <div className="explorer-detail-heading">
              <div>
                <Badge tone="neutral">{facility.type}</Badge>
                <h2>{facility.name}</h2>
                <p>{facility.address}</p>
              </div>
              <button
                type="button"
                className="explorer-dismiss"
                onClick={() => {
                  setSelected("");
                  document
                    .getElementById(
                      view === "map"
                        ? "explorer-view-map"
                        : `facility-result-${encodeURIComponent(facility.id)}`,
                    )
                    ?.focus();
                }}
                aria-label="Close facility details"
              >
                <Icon name="close" />
              </button>
            </div>
            <dl className="explorer-facts">
              <div>
                <dt>Licence number</dt>
                <dd>{facility.licence_no || "Not supplied"}</dd>
              </div>
              <div>
                <dt>Verification source</dt>
                <dd>{facility.source || "Not supplied"}</dd>
              </div>
              <div>
                <dt>Last checked</dt>
                <dd>
                  {facility.last_checked_at
                    ? displayDate(facility.last_checked_at)
                    : "Not supplied"}
                </dd>
              </div>
            </dl>
            <div className="explorer-detail-actions">
              <a
                className="button"
                target="_blank"
                rel="noopener noreferrer"
                href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(facility.latitude !== null && facility.longitude !== null ? `${facility.latitude},${facility.longitude}` : facility.address)}`}
              >
                Get directions
                <Icon name="arrow" size={17} />
              </a>
              {source && (
                <a
                  className="text-link"
                  href={source}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Verification source ↗
                </a>
              )}
              {website && (
                <a
                  className="text-link"
                  href={website}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Website ↗
                </a>
              )}
              {facility.phone && (
                <a
                  className="text-link"
                  href={`tel:${facility.phone.replace(/[^+0-9]/g, "")}`}
                >
                  Call {facility.phone}
                </a>
              )}
            </div>
          </section>
        )}
        <p className="explorer-note">
          {localUI
            ? "These listings are fictional and unverified; pins show approximate sample locations. Your device location stays in this page’s memory. Directions open an external map."
            : "Licence information reflects the source and check date shown. Contact the facility to confirm current services and opening hours. Your device location stays in this page’s memory."}
        </p>
      </ResourceState>
    </div>
  );
}
