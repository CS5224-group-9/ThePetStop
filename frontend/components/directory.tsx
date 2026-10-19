"use client";
import { localUI } from "@/lib/data-source";
import { useMemo, useState } from "react";
import { useApp } from "./app-provider";
import { Badge, Empty, Icon, PageHeading } from "./ui";
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
  const facility = filtered.find((f) => f.id === selected) || filtered[0];
  const source = safeExternalUrl(facility?.source_url);
  const website = safeExternalUrl(facility?.website);
  return (
    <>
      <PageHeading
        eyebrow="SINGAPORE FACILITY DIRECTORY"
        title="Singapore facility directory"
        description={
          localUI
            ? "Explore sample veterinary centres and pet shops. These fictional listings demonstrate search, filters and facility details."
            : "Find veterinary centres and pet shops. Review each listing’s verification source and last-checked date."
        }
      />
      <ResourceState domain="facilities">
        <div className="directory-toolbar">
          <label className="search-field">
            <Icon name="search" size={20} />
            <input
              aria-label="Search facilities by name or neighbourhood"
              placeholder="Search by name, neighbourhood or postal code…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Facility type"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="">All facilities</option>
            <option>Veterinary centre</option>
            <option>Pet shop</option>
          </select>
          <label className="check-label emergency-filter">
            <input
              type="checkbox"
              checked={emergency}
              onChange={(e) => setEmergency(e.target.checked)}
            />
            24-hour emergency
          </label>
        </div>
        <div className="directory-viewbar">
          <div
            className="view-toggle"
            role="group"
            aria-label="Directory layout"
          >
            {[
              ["split", "Split view"],
              ["map", "Map only"],
              ["list", "List only"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={view === value ? "selected" : ""}
                aria-pressed={view === value}
                onClick={() => setView(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            className="text-button"
            onClick={() => {
              setQuery("");
              setType("");
              setEmergency(false);
            }}
          >
            Reset filters
          </button>
        </div>
        <div className="directory-layout" data-view={view}>
          <section className="directory-list" aria-label="Facility results">
            <div className="results-header">
              <strong aria-live="polite">{filtered.length} facilities</strong>
              <span>Singapore</span>
            </div>
            {filtered.length ? (
              filtered.map((f) => (
                <button
                  className={`facility-card ${facility?.id === f.id ? "selected" : ""}`}
                  key={f.id}
                  aria-pressed={facility?.id === f.id}
                  onClick={() => setSelected(f.id)}
                >
                  <div className="facility-top">
                    <span
                      className={`stat-icon ${f.emergency ? "rose-soft" : "green-soft"}`}
                    >
                      <Icon name={f.type === "Pet shop" ? "bag" : "medical"} />
                    </span>
                    <Badge
                      tone={
                        f.verification_status === "verified" &&
                        Boolean(f.last_checked_at)
                          ? "green"
                          : "amber"
                      }
                    >
                      {f.verification_status === "verified" && f.last_checked_at
                        ? "Registry checked"
                        : "Not verified"}
                    </Badge>
                  </div>
                  <h2>{f.name}</h2>
                  <p>
                    <Icon name="pin" size={15} />
                    {f.address}
                  </p>
                  <div className="facility-bottom">
                    <span>{f.type}</span>
                    <span>View details ↗</span>
                  </div>
                  <small>
                    Source: {f.source || "Not supplied"}
                    <br />
                    Last checked:{" "}
                    {f.last_checked_at
                      ? displayDate(f.last_checked_at)
                      : "Not supplied"}
                  </small>
                </button>
              ))
            ) : (
              <Empty title="No facilities found">
                Try another search or reset the filters.
              </Empty>
            )}
          </section>
          <section
            className="map-container live-map-container"
            aria-label="Map and selected facility"
          >
            <FacilityMap
              facilities={filtered}
              selected={facility?.id || ""}
              onSelect={setSelected}
            />
            {facility && (
              <div className="map-detail">
                <div className="section-heading">
                  <Badge tone={facility.emergency ? "rose" : "neutral"}>
                    {facility.emergency
                      ? "24-hour emergency"
                      : "Facility information"}
                  </Badge>
                </div>
                <h2>{facility.name}</h2>
                <p>
                  <Icon name="pin" size={15} />
                  {facility.address}
                </p>
                <div className="detail-facts">
                  <div>
                    <span>FACILITY TYPE</span>
                    <strong>{facility.type}</strong>
                  </div>
                  <div>
                    <span>LICENCE NUMBER</span>
                    <strong>{facility.licence_no || "Not supplied"}</strong>
                  </div>
                </div>
                <p className="source-note">
                  Verification source: {facility.source || "Not supplied"}
                  <br />
                  Last checked:{" "}
                  {facility.last_checked_at
                    ? displayDate(facility.last_checked_at)
                    : "Not supplied"}
                </p>
                <div className="facility-actions">
                  {source && (
                    <a
                      className="text-link"
                      href={source}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View verification source ↗
                    </a>
                  )}
                  {website && (
                    <a
                      className="text-link"
                      href={website}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Facility website ↗
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
                <a
                  className="button"
                  target="_blank"
                  rel="noopener noreferrer"
                  href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(facility.latitude !== null && facility.longitude !== null ? `${facility.latitude},${facility.longitude}` : facility.address)}`}
                >
                  Get directions
                  <Icon name="arrow" size={17} />
                </a>
              </div>
            )}
          </section>
        </div>
        <p className="page-note">
          {localUI
            ? "All listings are fictional and unverified. Map positions are approximate sample locations; directions open an external map."
            : "Licence information reflects the displayed source and check date. Contact the facility to confirm current services and opening hours."}
        </p>
      </ResourceState>
    </>
  );
}
