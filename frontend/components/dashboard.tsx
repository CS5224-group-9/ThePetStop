"use client";
import Link from "next/link";
import { useApp } from "./app-provider";
import { Badge, Icon, PageHeading, PetAvatar } from "./ui";
import { displayDate, todaySG } from "@/lib/format";
import { ResourceState } from "./resource-state";
export function Dashboard() {
  const { state, resources } = useApp();
  const data = state;
  if (!state.role)
    return (
      <>
        <PageHeading
          eyebrow="SINGAPORE PET CARE"
          title="Your pet care workspace"
          description="Keep pet profiles, health records and everyday essentials together."
          action={
            <Link className="button" href="/login/">
              Sign in
              <Icon name="arrow" size={18} />
            </Link>
          }
        />
        <section className="workspace-intro">
          <span className="stat-icon green-solid">
            <Icon name="shield" size={25} />
          </span>
          <div>
            <h2>Care that stays organised</h2>
            <p>
              Sign in to manage your pets and care reminders. Facility discovery
              and product browsing are open to everyone.
            </p>
          </div>
        </section>
        <div className="explore-grid">
          <Link className="explore-card" href="/map/">
            <Icon name="map" size={28} />
            <div>
              <h2>Find a facility</h2>
              <p>Search veterinary centres and pet shops in Singapore.</p>
            </div>
          </Link>
          <Link className="explore-card" href="/shop/">
            <Icon name="bag" size={28} />
            <div>
              <h2>Browse the marketplace</h2>
              <p>Compare supplies from participating merchants.</p>
            </div>
          </Link>
        </div>
      </>
    );
  const count = (domain: "pets" | "reminders" | "facilities", value: number) =>
    resources[domain].loading || resources[domain].error ? "—" : value;
  const reminders = data.reminders
    .filter((r) => !r.done)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  const overdue = reminders.filter((r) => r.due_date < todaySG());
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE / OVERVIEW"
        title="Pet care overview"
        description="Pet profiles, upcoming care and everyday essentials in one workspace."
        action={
          <Link className="button" href="/pets/new/">
            <Icon name="plus" size={18} />
            Register a pet
          </Link>
        }
      />
      <section className="workspace-intro">
        <span className="stat-icon green-solid">
          <Icon name="shield" size={25} />
        </span>
        <div>
          <h2>
            {`Welcome back, ${state.profile?.display_name || "pet parent"}.`}
          </h2>
          <p>
            {state.role
              ? "Review your pets’ care schedule and pick up where you left off."
              : "Manage your pet profiles and care schedule."}
          </p>
        </div>
        <span className="date-label">
          <Icon name="calendar" size={17} />
          {displayDate(todaySG())}
        </span>
      </section>
      <div className="stat-grid">
        <Link className="stat-card" href="/pets/">
          <span className="eyebrow">PET PASSPORTS</span>
          <strong>
            {count("pets", data.pets.length)}
            <small>Registered companions</small>
          </strong>
          <Icon name="paw" />
        </Link>
        <Link className="stat-card" href="/pets/reminders/">
          <span className="eyebrow">UPCOMING CARE</span>
          <strong>
            {count("reminders", reminders.length - overdue.length)}
            <small>Scheduled reminders</small>
          </strong>
          <Icon name="calendar" />
        </Link>
        <Link className="stat-card attention" href="/pets/reminders/">
          <span className="eyebrow">NEEDS ATTENTION</span>
          <strong>
            {count("reminders", overdue.length)}
            <small>Overdue care tasks</small>
          </strong>
          <Icon name="bell" />
        </Link>
        <Link className="stat-card" href="/map/">
          <span className="eyebrow">FACILITY DIRECTORY</span>
          <strong>
            {count("facilities", state.facilities.length)}
            <small>Directory listings</small>
          </strong>
          <Icon name="map" />
        </Link>
      </div>
      <div className="dashboard-columns">
        <section>
          <div className="section-heading">
            <div>
              <h2>Pet passports</h2>
              <p>Identity, health records and care preferences.</p>
            </div>
            <Link href="/pets/">
              View all pets <Icon name="arrow" size={16} />
            </Link>
          </div>
          <ResourceState domain="pets">
            <div className="dashboard-pets">
              {data.pets.slice(0, 3).map((pet) => (
                <Link
                  className="dossier-card"
                  key={pet.id}
                  href={`/pets/detail/?id=${pet.id}`}
                >
                  <div className="dossier-identity">
                    <PetAvatar
                      species={pet.species}
                      photoUrl={pet.photo_url}
                      large
                    />
                    <div>
                      <Badge tone="neutral">
                        {pet.species} · Personal profile
                      </Badge>
                      <h3>{pet.name}</h3>
                      <p>{pet.breed}</p>
                      <span className="dossier-chip">
                        Microchip{" "}
                        <strong>{pet.microchip || "Not recorded"}</strong>
                      </span>
                    </div>
                    <Icon name="arrow" size={19} />
                  </div>
                  <div className="dossier-fields">
                    <div>
                      <span>SEX</span>
                      <strong>{pet.sex}</strong>
                    </div>
                    <div>
                      <span>WEIGHT</span>
                      <strong>{pet.weight}</strong>
                    </div>
                    <div>
                      <span>CARE RECORDS</span>
                      <strong>{pet.records.length} recorded</strong>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </ResourceState>
          <Link className="add-pet-link" href="/pets/new/">
            <Icon name="plus" size={18} />
            Register another pet
          </Link>
        </section>
        <aside className="panel reminder-panel">
          <div className="section-heading">
            <div>
              <h2>
                <Icon name="bell" />
                Care reminders
              </h2>
              <p>Ordered by the next due date.</p>
            </div>
            <Badge tone="neutral">{reminders.length} pending</Badge>
          </div>
          <ResourceState domain="reminders">
            <div className="reminder-list">
              {reminders.slice(0, 4).map((r) => (
                <Link
                  className="reminder-item"
                  href="/pets/reminders/"
                  key={r.id}
                >
                  <span
                    className={`reminder-dot ${r.due_date < todaySG() ? "overdue" : ""}`}
                  >
                    <Icon name="calendar" size={19} />
                  </span>
                  <div>
                    <strong>{r.title}</strong>
                    <p>
                      {data.pets.find((p) => p.id === r.pet_id)?.name} ·{" "}
                      {displayDate(r.due_date)}
                    </p>
                    <Badge tone={r.due_date < todaySG() ? "rose" : "green"}>
                      {r.due_date < todaySG() ? "Overdue" : "Upcoming"}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          </ResourceState>
          <Link className="button secondary full-width" href="/pets/reminders/">
            Manage reminders <Icon name="arrow" size={16} />
          </Link>
        </aside>
      </div>
      <section className="explore-section">
        <div className="section-heading">
          <h2>Explore PetStop SG</h2>
        </div>
        <div className="explore-grid">
          <Link className="explore-card" href="/map/">
            <span className="stat-icon lilac-soft">
              <Icon name="map" size={25} />
            </span>
            <div>
              <h3>Singapore facility directory</h3>
              <p>Browse veterinary centres and pet shops by neighbourhood.</p>
              <span className="text-link">
                Find a facility <Icon name="arrow" size={16} />
              </span>
            </div>
          </Link>
          <Link className="explore-card" href="/shop/">
            <span className="stat-icon lilac-soft">
              <Icon name="bag" size={25} />
            </span>
            <div>
              <h3>Multi-merchant marketplace</h3>
              <p>Compare product prices across participating shops.</p>
              <span className="text-link">
                Browse products <Icon name="arrow" size={16} />
              </span>
            </div>
          </Link>
        </div>
      </section>
    </>
  );
}
