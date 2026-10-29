"use client";
import "./facility-explorer.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  searchLocations,
  type LocationResult,
} from "@/lib/api/location-services";
import { ApiError } from "@/lib/api/client";
import { nearbyFacilities } from "@/lib/facility-search";
import {
  approvedAnimalLabels,
  type ApprovedAnimal,
} from "@/lib/facility-animals";
import { currentLocation, type SearchLocation } from "@/lib/location";
import { services } from "@/lib/api/services";
import type { Facility } from "@/lib/api/types";
import { Badge, Empty, Icon } from "./ui";

import { FacilityMap } from "./facility-map";
import { displayDate, safeExternalUrl } from "@/lib/format";
export function Directory() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [facilityError, setFacilityError] = useState("");
  const [facilityLoading, setFacilityLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [animal, setAnimal] = useState<ApprovedAnimal | "">("");
  const [selected, setSelected] = useState("");
  const [location, setLocation] = useState<SearchLocation | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [showLocationPrompt, setShowLocationPrompt] = useState(true);
  const [radiusKm, setRadiusKm] = useState<number | null>(5);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [placeResults, setPlaceResults] = useState<LocationResult[]>([]);
  const [placeSearching, setPlaceSearching] = useState(false);
  const [placeSearched, setPlaceSearched] = useState(false);
  const [placeError, setPlaceError] = useState("");
  const placeRequest = useRef(0);
  const placeController = useRef<AbortController | null>(null);
  const locationRequest = useRef(0);
  const pendingLocation = useRef(false);
  const resultsList = useRef<HTMLDivElement>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const selectionTrigger = useRef<HTMLElement | null>(null);
  const selectMapFacility = useCallback(
    (id: string, trigger: HTMLButtonElement) => {
      selectionTrigger.current = trigger;
      setSelected(id);
      const list = resultsList.current;
      const row = document.getElementById(
        `facility-result-${encodeURIComponent(id)}`,
      );
      if (list && row) {
        const bounds = list.getBoundingClientRect();
        const item = row.getBoundingClientRect();
        if (item.top < bounds.top || item.bottom > bounds.bottom)
          list.scrollTo({
            top:
              list.scrollTop +
              item.top -
              bounds.top -
              Math.max(0, (list.clientHeight - item.height) / 2),
            behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
              .matches
              ? "instant"
              : "smooth",
          });
      }
      requestAnimationFrame(() =>
        detailHeading.current?.focus({ preventScroll: true }),
      );
    },
    [],
  );
  useEffect(
    () => () => {
      locationRequest.current += 1;
      placeRequest.current += 1;
      placeController.current?.abort();
    },
    [],
  );
  async function locate() {
    if (pendingLocation.current) return;
    cancelPlaceSearch();
    setSuggestionsOpen(false);
    setQuery("");
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
      setSelected("");
      setLocation(result);
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
  function cancelPlaceSearch() {
    placeRequest.current += 1;
    placeController.current?.abort();
    setPlaceSearching(false);
    setPlaceResults([]);
    setPlaceSearched(false);
    setPlaceError("");
  }
  async function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    cancelPlaceSearch();
    setSuggestionsOpen(true);
    if (query.trim().length < 2) return;
    const request = ++placeRequest.current;
    const controller = new AbortController();
    placeController.current = controller;
    setPlaceSearching(true);
    try {
      const results = await searchLocations(query, controller.signal);
      if (request !== placeRequest.current) return;
      setPlaceResults(results);
      setPlaceSearched(true);
    } catch (error) {
      if (request !== placeRequest.current) return;
      setPlaceError(
        error instanceof ApiError && error.code === "not_configured"
          ? "Address search is not available yet. You can still browse facilities or use your current location."
          : error instanceof Error
            ? error.message
            : "Location search failed. Please try again.",
      );
    } finally {
      if (request === placeRequest.current) setPlaceSearching(false);
    }
  }
  function selectPlace(result: LocationResult) {
    locationRequest.current += 1;
    setLocating(false);
    setLocationError("");
    setSelected("");
    setLocation(result);
    setShowLocationPrompt(false);
    setQuery(result.label.slice(0, 120));
    setSuggestionsOpen(false);
    cancelPlaceSearch();
    document.getElementById("facility-search")?.focus();
  }
  function selectFacility(id: string, trigger: HTMLButtonElement) {
    const match = facilities.find((item) => item.id === id);
    if (!match) return;
    locationRequest.current += 1;
    setLocating(false);
    setLocationError("");
    cancelPlaceSearch();
    setSuggestionsOpen(false);
    selectionTrigger.current = trigger;
    setSelected(id);
    requestAnimationFrame(() => {
      detailHeading.current?.focus({ preventScroll: true });
      if (window.matchMedia("(max-width: 700px)").matches)
        detailHeading.current?.closest(".explorer-map")?.scrollIntoView({
          block: "start",
          behavior: "instant",
        });
    });
  }
  function closeDetails() {
    const trigger = selectionTrigger.current;
    const row = document.getElementById(
      `facility-result-${encodeURIComponent(selected)}`,
    );
    setSelected("");
    requestAnimationFrame(() => {
      const target = trigger?.isConnected ? trigger : row;
      target?.focus({ preventScroll: true });
      if (
        target?.classList.contains("explorer-row") &&
        window.matchMedia("(max-width: 700px)").matches
      )
        target.scrollIntoView({ block: "nearest", behavior: "instant" });
    });
  }
  function clearSearch() {
    cancelPlaceSearch();
    setSuggestionsOpen(false);
    setQuery("");
    setLocation(null);
    setSelected("");
    locationRequest.current += 1;
    setLocating(false);
    setLocationError("");
  }
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (type) params.set("type", type === "Pet shop" ? "pet_shop" : "vet");
    if (animal) params.set("animal", animal);
    if (location) {
      params.set("lat", String(location.latitude));
      params.set("lng", String(location.longitude));
      if (radiusKm !== null) params.set("radius_km", String(radiusKm));
    }
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setFacilityLoading(true);
      setFacilityError("");
      setFacilities([]);
    });
    services
      .facilities(params, controller.signal)
      .then(setFacilities)
      .catch((error) => {
        if (!controller.signal.aborted)
          setFacilityError(
            error instanceof Error
              ? error.message
              : "Unable to load facilities.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setFacilityLoading(false);
      });
    return () => controller.abort();
  }, [type, animal, location, radiusKm, retry]);
  const filtered = useMemo(
    () => nearbyFacilities(facilities, { type: "" }, location, null),
    [facilities, location],
  );
  const facility = filtered.find((f) => f.id === selected);
  const source = safeExternalUrl(facility?.source_url);
  const website = safeExternalUrl(facility?.website);
  function resetFilters() {
    setType("");
    setAnimal("");
    setSelected("");
    setRadiusKm(5);
  }
  const hasFilters = Boolean(type || animal || (location && radiusKm !== 5));
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
      <div aria-busy={facilityLoading}>
        {facilityLoading && <p role="status">Loading facilities�</p>}
        {facilityError && (
          <div role="alert">
            <p>{facilityError}</p>
            <button type="button" onClick={() => setRetry(retry + 1)}>
              Try again
            </button>
          </div>
        )}
        <div className="explorer-workspace">
          <div className="explorer-controls">
            <form
              className="explorer-unified-search"
              onSubmit={search}
              role="search"
              aria-label="Find a search location"
            >
              <label
                className="explorer-search-label"
                htmlFor="facility-search"
              >
                Find facilities near a location
              </label>
              <div className="explorer-searchbar">
                <div className="explorer-search">
                  <Icon name="search" size={20} />
                  <input
                    id="facility-search"
                    type="search"
                    placeholder="Enter an address, landmark or postal code…"
                    value={query}
                    maxLength={120}
                    required
                    aria-describedby="search-status"
                    aria-controls={
                      suggestionsOpen ? "facility-search-results" : undefined
                    }
                    onChange={(event) => {
                      if (!event.target.value.trim()) {
                        clearSearch();
                        return;
                      }
                      cancelPlaceSearch();
                      setQuery(event.target.value);
                      setSuggestionsOpen(Boolean(event.target.value.trim()));
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.preventDefault();
                        cancelPlaceSearch();
                        setSuggestionsOpen(false);
                      }
                    }}
                  />
                  {query && (
                    <button
                      type="button"
                      className="explorer-search-clear"
                      aria-label="Clear search"
                      onClick={() => {
                        clearSearch();
                        document.getElementById("facility-search")?.focus();
                      }}
                    >
                      <Icon name="close" size={18} />
                    </button>
                  )}
                </div>
                <button
                  type="submit"
                  className="button"
                  disabled={placeSearching || query.trim().length < 2}
                >
                  {placeSearching ? "Searching…" : "Search"}
                </button>
                <button
                  type="button"
                  className="explorer-locate"
                  id="explorer-locate"
                  onClick={locate}
                  disabled={locating}
                  aria-describedby="location-status"
                >
                  <Icon name="pin" size={18} />
                  {locating ? "Finding location…" : "Use my location"}
                </button>
              </div>
              <p
                className="explorer-search-status"
                id="search-status"
                role="status"
              >
                {suggestionsOpen
                  ? placeSearching
                    ? "Finding matching locations…"
                    : placeSearched
                      ? `${placeResults.length} locations found. Choose one to see nearby facilities.`
                      : "Press Search, then choose a matching location."
                  : location
                    ? `Showing ${filtered.length} facilities ${radiusKm === null ? "across Singapore" : `within ${radiusKm} km`}, nearest first. Distances are straight-line.`
                    : "Search for a location or use your current location to find facilities within a radius."}
              </p>
              {suggestionsOpen && (
                <div
                  className="explorer-search-results"
                  id="facility-search-results"
                >
                  <section aria-labelledby="place-matches-heading">
                    <h2 id="place-matches-heading">Choose a location</h2>
                    {placeResults.length ? (
                      <ul>
                        {placeResults.map((result) => (
                          <li
                            key={`${result.label}-${result.latitude}-${result.longitude}`}
                          >
                            <button
                              type="button"
                              onClick={() => selectPlace(result)}
                            >
                              <Icon name="pin" size={18} />
                              <span>{result.label}</span>
                              <Icon name="arrow" size={16} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p role={placeError ? "alert" : undefined}>
                        {placeError ||
                          (placeSearching
                            ? "Searching for places…"
                            : placeSearched
                              ? "No places found. Try another address or postal code."
                              : "Press Search to find matching addresses and postal codes.")}
                      </p>
                    )}
                  </section>
                </div>
              )}
            </form>
            <div className="explorer-filterbar">
              <label className="explorer-radius">
                Within
                <select
                  aria-label="Search radius"
                  value={radiusKm === null ? "all" : String(radiusKm)}
                  disabled={!location}
                  aria-describedby="search-status"
                  onChange={(event) =>
                    setRadiusKm(
                      event.target.value === "all"
                        ? null
                        : Number(event.target.value),
                    )
                  }
                >
                  {[1, 2, 5, 10, 20].map((km) => (
                    <option key={km} value={km}>
                      {km} km
                    </option>
                  ))}
                  <option value="all">All Singapore</option>
                </select>
              </label>
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
                    onClick={() => {
                      setType(value);
                      setAnimal("");
                      setSelected("");
                    }}
                  >
                    <Icon name={icon} size={16} />
                    {label}
                  </button>
                ))}
              </div>
              {type === "Pet shop" && (
                <label className="explorer-radius">
                  Approved animals
                  <select
                    aria-label="Filter pet shops by approved animal"
                    value={animal}
                    onChange={(event) => {
                      setAnimal(event.target.value as ApprovedAnimal | "");
                      setSelected("");
                    }}
                  >
                    <option value="">All animals</option>
                    {Object.entries(approvedAnimalLabels).map(
                      ([code, label]) => (
                        <option key={code} value={code}>
                          {label}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              )}
            </div>
          </div>
          <div
            className="explorer-panes"
            onKeyDown={(event) => {
              if (event.key === "Escape" && facility) {
                event.preventDefault();
                event.stopPropagation();
                closeDetails();
              }
            }}
          >
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
                  <span>{location ? "Nearest first" : "Singapore"}</span>
                )}
              </div>
              <div className="explorer-rows" ref={resultsList}>
                {filtered.length ? (
                  filtered.map((f) => (
                    <button
                      type="button"
                      className="explorer-row"
                      key={f.id}
                      id={`facility-result-${encodeURIComponent(f.id)}`}
                      aria-pressed={facility?.id === f.id}
                      aria-controls={
                        facility?.id === f.id
                          ? "facility-detail-panel"
                          : undefined
                      }
                      aria-expanded={facility?.id === f.id}
                      onClick={(event) =>
                        selectFacility(f.id, event.currentTarget)
                      }
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
                        </span>
                        <strong>{f.name}</strong>
                        {location && (
                          <span className="explorer-distance">
                            {f.distance_km === null
                              ? "Distance unavailable"
                              : f.distance_km < 1
                                ? `${Math.round(f.distance_km * 1000)} m away`
                                : `${f.distance_km.toFixed(1)} km away`}
                          </span>
                        )}
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
                            ? "Selected · details open"
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
                    {location
                      ? "Try a larger radius or "
                      : "Try selecting a location or "}
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
              <div
                className="explorer-map-body"
                data-detail-open={Boolean(facility)}
              >
                <div className="explorer-map-canvas">
                  <FacilityMap
                    facilities={filtered}
                    selected={facility?.id || ""}
                    onSelect={selectMapFacility}
                    location={location}
                    radiusKm={radiusKm}
                  />
                </div>
                {facility && (
                  <aside
                    key={facility.id}
                    className="explorer-detail"
                    id="facility-detail-panel"
                    aria-labelledby="facility-detail-title"
                  >
                    <div className="explorer-detail-toolbar">
                      <Badge tone="neutral">{facility.type}</Badge>
                      <button
                        type="button"
                        className="explorer-dismiss"
                        onClick={closeDetails}
                        aria-label="Close facility details"
                      >
                        <Icon name="close" />
                      </button>
                    </div>
                    <div className="explorer-detail-heading">
                      <h2
                        id="facility-detail-title"
                        ref={detailHeading}
                        tabIndex={-1}
                      >
                        {facility.name}
                      </h2>
                      <p>{facility.address}</p>
                    </div>
                    {facility.type === "Pet shop" && (
                      <section
                        className="explorer-approved-animals"
                        aria-label="Approved animals for sale"
                      >
                        <h3>Approved animals for sale</h3>
                        {facility.approved_animals?.length ? (
                          <>
                            <ul>
                              {facility.approved_animals.map((code) => (
                                <li key={code}>{approvedAnimalLabels[code]}</li>
                              ))}
                            </ul>
                            <p>
                              Approval does not confirm current availability.
                            </p>
                          </>
                        ) : (
                          <p>Animal approval information not available.</p>
                        )}
                      </section>
                    )}
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
                    <details className="explorer-registry-details">
                      <summary>Registry details</summary>
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
                    </details>
                  </aside>
                )}
              </div>
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
                  <span
                    className={
                      location.source === "device"
                        ? "explorer-location-dot"
                        : "explorer-search-pin"
                    }
                  />
                  {location.source === "device"
                    ? "Your location"
                    : "Search centre"}
                </span>
              )}
            </div>
            <p id="location-status" role="status">
              {locationError ||
                (locating
                  ? "Waiting for your browser’s location…"
                  : location
                    ? `${location.label}${location.accuracyMetres !== undefined ? ` · accuracy approximately ${Math.max(1, Math.round(location.accuracyMetres))} m` : ""}`
                    : "Select a facility to explore its details.")}
            </p>
          </div>
        </div>
        <p className="explorer-note">
          Licence information reflects the source and check date shown. Contact
          the facility to confirm current services and opening hours. Your
          device location stays in this page’s memory.
        </p>
      </div>
    </div>
  );
}
