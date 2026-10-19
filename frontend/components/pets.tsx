"use client";
import Link from "next/link";
import { localUI } from "@/lib/data-source";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { useApp } from "./app-provider";
import { Badge, Empty, Icon, PageHeading, PetAvatar } from "./ui";
import { FormError } from "./resource-state";
import { displayDate, todaySG } from "@/lib/format";
import { services } from "@/lib/api/services";
import { useResource } from "@/lib/api/use-resource";
export function Pets() {
  const { state } = useApp();
  return (
    <>
      <PageHeading
        eyebrow="PET PASSPORTS"
        title="Pet passports"
        description="Manage identity details, vaccination records and care preferences."
        action={
          <Link className="button" href="/pets/new/">
            <Icon name="plus" size={18} />
            Add a pet
          </Link>
        }
      />
      {state.pets.length ? (
        <div className="pet-card-grid roster">
          {state.pets.map((pet) => (
            <Link
              className="pet-card"
              href={`/pets/detail/?id=${encodeURIComponent(pet.id)}`}
              key={pet.id}
            >
              <div className="pet-card-art">
                <span className="pet-species">
                  {pet.species.toUpperCase()} PASSPORT
                </span>
                <PetAvatar
                  species={pet.species}
                  photoUrl={pet.photo_url}
                  large
                />
              </div>
              <div className="pet-card-body">
                <h2>
                  {pet.name}
                  <span>↗</span>
                </h2>
                <p>{pet.breed}</p>
                <div className="pet-meta">
                  <span>{pet.sex}</span>
                  <Badge tone="neutral">Personal profile</Badge>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Empty title="Add your first pet">
          <Link className="button" href="/pets/new/">
            Create a pet passport
          </Link>
        </Empty>
      )}
    </>
  );
}
export function NewPet() {
  const { actions, pending } = useApp();
  const router = useRouter();
  const [error, setError] = useState("");
  const busy = pending.includes("pet:create");
  return (
    <>
      <PageHeading
        eyebrow="PET PASSPORTS / NEW PROFILE"
        title="Register a new pet"
        description="Create a personal pet profile. Add health records after registration."
      />
      <form
        className="panel form-panel"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          const data = new FormData(e.currentTarget);
          setError("");
          try {
            const id = await actions.createPet({
              name: String(data.get("name")).trim(),
              species: String(data.get("species")),
              breed: String(data.get("breed")).trim(),
              sex: String(data.get("sex")),
              date_of_birth: String(data.get("birth")),
              microchip_no: String(data.get("microchip")) || null,
              allergies: String(data.get("allergies"))
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean),
              diet_notes: String(data.get("diet")),
            });
            router.push(`/pets/detail/?id=${encodeURIComponent(id)}`);
          } catch (cause) {
            setError(
              cause instanceof Error
                ? cause.message
                : "Unable to save this pet. Please try again.",
            );
          }
        }}
      >
        <div className="form-intro">
          <span className="stat-icon green-soft">
            <Icon name="paw" size={26} />
          </span>
          <div>
            <h2>Pet identity & care preferences</h2>
            <p>
              Microchip numbers are checked for format. Saving a profile does
              not register a pet with AVS or verify a licence.
            </p>
          </div>
        </div>
        <FormError message={error} />
        <fieldset disabled={busy} className="form-fieldset">
          <div className="form-grid">
            <label>
              Pet’s name
              <input
                name="name"
                required
                maxLength={50}
                pattern=".*\S.*"
                autoComplete="off"
              />
            </label>
            <label>
              Species
              <select name="species">
                <option value="dog">Dog</option>
                <option value="cat">Cat</option>
                <option value="rabbit">Rabbit</option>
                <option value="bird">Bird</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              Breed
              <input name="breed" maxLength={80} autoComplete="off" />
            </label>
            <label>
              Sex
              <select name="sex">
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
            <label>
              Date of birth
              <input name="birth" type="date" required max={todaySG()} />
            </label>
            <label>
              Microchip number<small>Optional · 15 digits</small>
              <input
                name="microchip"
                inputMode="numeric"
                pattern="[0-9]{15}"
                maxLength={15}
                autoComplete="off"
              />
            </label>
            <label>
              Allergies
              <small>Optional · separate ingredients with commas</small>
              <input name="allergies" maxLength={500} />
            </label>
            <label>
              Dietary preferences<small>Optional</small>
              <input name="diet" maxLength={500} />
            </label>
          </div>
          <div className="form-footer">
            <Link className="button secondary" href="/pets/">
              Cancel
            </Link>
            <button className="button" type="submit">
              {busy ? "Saving pet…" : "Create pet passport"}
              <Icon name="arrow" size={17} />
            </button>
          </div>
        </fieldset>
      </form>
    </>
  );
}
export function PetDetail() {
  const { state, actions, pending } = useApp();
  const params = useSearchParams();
  const pet = state.pets.find((p) => p.id === params.get("id"));
  const [tab, setTab] = useState("Overview");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  if (!pet)
    return (
      <Empty title="Pet passport not found">
        <Link href="/pets/">Return to pet profiles</Link>
      </Empty>
    );
  const reminders = state.reminders.filter(
    (r) => r.pet_id === pet.id && !r.done,
  );
  const busy = pending.includes(`record:${pet.id}`);
  return (
    <>
      <PageHeading
        eyebrow="PET PASSPORTS / IDENTITY & HEALTH"
        title={`${pet.name}’s passport`}
        description="Identity, health history and care information in one personal record."
        action={
          <Link className="button secondary" href="/pets/">
            All pets
            <Icon name="paw" size={16} />
          </Link>
        }
      />
      <div className="pet-switcher">
        {state.pets.map((p) => (
          <Link
            className={`chip ${p.id === pet.id ? "selected" : ""}`}
            href={`/pets/detail/?id=${encodeURIComponent(p.id)}`}
            key={p.id}
          >
            <Icon name="paw" size={14} />
            {p.name}
          </Link>
        ))}
        <Link className="chip" href="/pets/new/">
          <Icon name="plus" size={14} />
          Add pet
        </Link>
      </div>
      <div className="detail-columns">
        <div>
          <section className="panel identity-panel">
            <PetAvatar species={pet.species} photoUrl={pet.photo_url} large />
            <div>
              <Badge tone="neutral">PERSONAL PET RECORD</Badge>
              <h2>{pet.name}</h2>
              <p>{pet.breed}</p>
              <div className="identity-meta">
                <span>
                  <small>SEX</small>
                  {pet.sex}
                </span>
                <span>
                  <small>RECORDED WEIGHT</small>
                  {pet.weight}
                </span>
                <span>
                  <small>DATE OF BIRTH</small>
                  {displayDate(pet.date_of_birth)}
                </span>
              </div>
            </div>
          </section>
          <div
            className="tabs"
            role="tablist"
            aria-label="Pet passport sections"
          >
            {["Overview", "Health records", "Documents"].map((t) => (
              <button
                role="tab"
                aria-selected={tab === t}
                id={`tab-${t.replaceAll(" ", "-")}`}
                aria-controls="pet-tab-panel"
                tabIndex={tab === t ? 0 : -1}
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
                onKeyDown={(event) => {
                  const names = ["Overview", "Health records", "Documents"];
                  let index = names.indexOf(t);
                  if (event.key === "ArrowRight")
                    index = (index + 1) % names.length;
                  else if (event.key === "ArrowLeft")
                    index = (index + names.length - 1) % names.length;
                  else if (event.key === "Home") index = 0;
                  else if (event.key === "End") index = names.length - 1;
                  else return;
                  event.preventDefault();
                  setTab(names[index]);
                  document
                    .getElementById(`tab-${names[index].replaceAll(" ", "-")}`)
                    ?.focus();
                }}
              >
                {t}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id="pet-tab-panel"
            aria-labelledby={`tab-${tab.replaceAll(" ", "-")}`}
          >
            {tab === "Overview" && (
              <>
                <section className="panel">
                  <div className="section-heading">
                    <h2>
                      <Icon name="shield" />
                      Microchip & registration details
                    </h2>
                    <Badge tone="neutral">Owner-provided</Badge>
                  </div>
                  <div className="info-grid">
                    <div>
                      <span>MICROCHIP NUMBER</span>
                      <strong className="mono">
                        {pet.microchip || "Not recorded"}
                      </strong>
                    </div>
                    <div>
                      <span>SPECIES</span>
                      <strong>{pet.species}</strong>
                    </div>
                    <div>
                      <span>DATE OF BIRTH</span>
                      <strong>{displayDate(pet.date_of_birth)}</strong>
                    </div>
                    <div>
                      <span>LICENCE VERIFICATION</span>
                      <strong>Not verified by PetStop</strong>
                    </div>
                  </div>
                  <p className="info-note">
                    A personal care record, not an official licensing
                    certificate.
                  </p>
                </section>
                <section className="panel">
                  <div className="section-heading">
                    <h2>
                      <Icon name="heart" />
                      Clinical & dietary overview
                    </h2>
                  </div>
                  <div className="wellbeing-grid">
                    <div className="allergy-box">
                      <span>ALLERGIES & SENSITIVITIES</span>
                      <strong>{pet.allergies}</strong>
                      <p>Owner-provided information</p>
                    </div>
                    <div className="diet-box">
                      <span>DIETARY PREFERENCES</span>
                      <strong>{pet.diet}</strong>
                      <p>Owner-provided dietary information</p>
                    </div>
                  </div>
                </section>
              </>
            )}
            {tab === "Health records" && (
              <section className="panel">
                <div className="section-heading">
                  <div>
                    <h2>Vaccination & care records</h2>
                    <p>Vaccinations, check-ups and everyday care.</p>
                  </div>
                  <button
                    className="button small"
                    onClick={() => setAdding(!adding)}
                  >
                    {adding ? "Close form" : "Add record"}
                    <Icon name="plus" size={15} />
                  </button>
                </div>
                {adding && (
                  <form
                    className="record-form"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      if (busy) return;
                      const d = new FormData(e.currentTarget);
                      setError("");
                      try {
                        await actions.addRecord(pet.id, {
                          name: String(d.get("title")).trim(),
                          record_type: String(d.get("kind")),
                          date: String(d.get("date")),
                          next_due: String(d.get("next_due")) || null,
                          clinic: String(d.get("clinic")),
                        });
                        setAdding(false);
                      } catch (cause) {
                        setError(
                          cause instanceof Error
                            ? cause.message
                            : "Unable to save this record.",
                        );
                      }
                    }}
                  >
                    <FormError message={error} />
                    <fieldset className="form-fieldset" disabled={busy}>
                      <div className="form-grid">
                        <label>
                          Record name
                          <input name="title" required maxLength={100} />
                        </label>
                        <label>
                          Care type
                          <select name="kind">
                            <option value="vaccination">Vaccination</option>
                            <option value="checkup">Check-up</option>
                            <option value="deworming">Deworming</option>
                            <option value="grooming">Grooming</option>
                            <option value="other">Other</option>
                          </select>
                        </label>
                        <label>
                          Date of care
                          <input
                            name="date"
                            type="date"
                            required
                            max={todaySG()}
                          />
                        </label>
                        <label>
                          Next due
                          <small>Optional · suggests a care reminder</small>
                          <input name="next_due" type="date" min={todaySG()} />
                        </label>
                        <label>
                          Clinic or provider
                          <input name="clinic" maxLength={100} />
                        </label>
                      </div>
                      <button className="button" type="submit">
                        {busy ? "Saving record…" : "Save care record"}
                      </button>
                    </fieldset>
                  </form>
                )}
                {pet.records.length ? (
                  <div className="table-scroll">
                    <table className="records-table">
                      <caption className="sr-only">
                        {pet.name}’s care records
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">CARE RECORD</th>
                          <th scope="col">TYPE</th>
                          <th scope="col">DATE OF CARE</th>
                          <th scope="col">CLINIC / PROVIDER</th>
                          <th scope="col">NEXT DUE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pet.records.map((r) => (
                          <tr key={r.id}>
                            <td>
                              <strong>{r.title}</strong>
                            </td>
                            <td>
                              <Badge tone="neutral">{r.kind}</Badge>
                            </td>
                            <td>{displayDate(r.date)}</td>
                            <td>{r.clinic || "Not recorded"}</td>
                            <td>
                              {r.next_due ? (
                                <>
                                  <strong>{displayDate(r.next_due)}</strong>
                                  <Badge
                                    tone={
                                      r.next_due < todaySG() ? "rose" : "green"
                                    }
                                  >
                                    {r.next_due < todaySG()
                                      ? "Overdue"
                                      : "Scheduled"}
                                  </Badge>
                                </>
                              ) : (
                                "Not scheduled"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty title="No care records yet">
                    Add a vaccination, check-up or other care record.
                  </Empty>
                )}
              </section>
            )}
            {tab === "Documents" && <PetDocuments petId={pet.id} />}
          </div>
        </div>
        <aside>
          <section className="panel passport-summary">
            <div className="section-heading">
              <h2>
                <Icon name="shield" />
                Passport summary
              </h2>
            </div>
            <div className="passport-seal">
              <Icon name="medical" size={36} />
              <span>PERSONAL PET RECORD</span>
              <strong>{pet.name}</strong>
            </div>
            <div className="summary-metrics">
              <div>
                <strong>{pet.records.length}</strong>
                <span>Care records</span>
              </div>
              <div>
                <strong>{reminders.length}</strong>
                <span>Pending reminders</span>
              </div>
            </div>
            <button
              className="button full-width"
              onClick={() => {
                setTab("Health records");
                setAdding(true);
              }}
            >
              Add care record
              <Icon name="plus" size={17} />
            </button>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>
                <Icon name="bell" />
                Upcoming care
              </h2>
            </div>
            {reminders.length ? (
              reminders.map((r) => (
                <div className="mini-reminder" key={r.id}>
                  <strong>{r.title}</strong>
                  <p>{displayDate(r.due_date)}</p>
                  <Badge tone={r.due_date < todaySG() ? "rose" : "green"}>
                    {r.due_date < todaySG() ? "Overdue" : "Upcoming"}
                  </Badge>
                </div>
              ))
            ) : (
              <p>No outstanding care reminders.</p>
            )}
            <Link className="text-link" href="/pets/reminders/">
              Manage reminders
              <Icon name="arrow" size={16} />
            </Link>
          </section>
          <section className="green-panel">
            <Icon name="map" size={28} />
            <h2>Find a care provider</h2>
            <p>Search veterinary centres and pet shops in Singapore.</p>
            <Link className="button light" href="/map/">
              Explore facilities
              <Icon name="arrow" size={16} />
            </Link>
          </section>
        </aside>
      </div>
    </>
  );
}
function PetDocuments({ petId }: { petId: string }) {
  const loader = useCallback(() => services.documents(petId), [petId]);
  const { data, loading, error, reload } = useResource(
    `documents:${petId}`,
    loader,
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>
          <Icon name="file" />
          Veterinary documents
        </h2>
      </div>
      <p>
        {localUI
          ? "PDF, JPEG or PNG · Up to 10 MB. Files stay in this tab until you reload; they are not uploaded. Use sample files."
          : "PDF, JPEG or PNG · Up to 10 MB per file. Documents are private to your account."}
      </p>
      <FormError message={actionError} />
      <form
        className="record-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          const form = e.currentTarget,
            d = new FormData(form),
            file = d.get("file");
          if (!(file instanceof File)) return;
          setBusy(true);
          setActionError("");
          try {
            await services.uploadDocument(
              petId,
              file,
              String(d.get("title")).trim(),
            );
            form.reset();
            reload();
          } catch (cause) {
            setActionError(
              cause instanceof Error
                ? cause.message
                : "Unable to upload this document.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={busy} className="form-fieldset">
          <div className="form-grid">
            <label>
              Document title
              <input name="title" required maxLength={150} />
            </label>
            <label>
              File
              <input
                type="file"
                name="file"
                required
                accept="application/pdf,image/jpeg,image/png"
              />
            </label>
          </div>
          <button className="button" type="submit">
            {busy ? "Uploading…" : "Upload document"}
            <Icon name="plus" size={17} />
          </button>
        </fieldset>
      </form>
      {loading ? (
        <p role="status">Loading documents…</p>
      ) : error ? (
        <div role="alert">
          <p>{error}</p>
          <button className="button secondary" onClick={reload}>
            Try again
          </button>
        </div>
      ) : data?.length ? (
        data.map((doc) => (
          <div className="record-row" key={doc.id}>
            <Icon name="file" />
            <div>
              <h3>{doc.title}</h3>
              <p>
                {displayDate(doc.uploaded_at)} ·{" "}
                {Math.ceil(doc.size_bytes / 1024)} KB
              </p>
            </div>
            <button
              className="button secondary small"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setActionError("");
                try {
                  const { blob, name } = await services.downloadDocument(
                    petId,
                    doc.id,
                  );
                  const url = URL.createObjectURL(blob);
                  const link = document.createElement("a");
                  link.href = url;
                  link.download = name;
                  document.body.appendChild(link);
                  link.click();
                  link.remove();
                  setTimeout(() => URL.revokeObjectURL(url), 1000);
                } catch (cause) {
                  setActionError(
                    cause instanceof Error
                      ? cause.message
                      : "Unable to download this document.",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              Download
            </button>
          </div>
        ))
      ) : (
        <Empty title="No documents yet">
          Upload a veterinary report to keep it with this pet’s care records.
        </Empty>
      )}
    </section>
  );
}
export function Reminders() {
  const { state, actions, pending } = useApp();
  const [showDone, setShowDone] = useState(false);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [suggestion, setSuggestion] = useState("");
  const rows = state.reminders
    .filter((r) => showDone || !r.done)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  const suggestions = state.pets.flatMap((p) =>
    p.records
      .filter(
        (r) =>
          r.next_due &&
          !state.reminders.some(
            (rem) =>
              rem.pet_id === p.id &&
              rem.title === r.title &&
              rem.due_date === r.next_due,
          ),
      )
      .map((r) => ({
        pet: p.id,
        pet_name: p.name,
        record: r.id,
        title: r.title,
        date: r.next_due,
      })),
  );
  const selected = suggestions.find((s) => s.record === suggestion);
  const creating = pending.includes("reminder:create");
  return (
    <>
      <PageHeading
        eyebrow="PET CARE / REMINDERS"
        title="Care reminders"
        description="Review upcoming and overdue care tasks across your pet profiles."
        action={
          <button className="button" onClick={() => setAdding(!adding)}>
            <Icon name="plus" size={17} />
            {adding ? "Close form" : "Add reminder"}
          </button>
        }
      />
      <section className="panel">
        <FormError message={error} />
        {adding && (
          <form
            className="record-form"
            onSubmit={async (e) => {
              e.preventDefault();
              if (creating) return;
              const data = new FormData(e.currentTarget);
              setError("");
              try {
                await actions.createReminder({
                  pet: String(data.get("pet")),
                  title: String(data.get("title")).trim(),
                  due_at: `${data.get("date")}T09:00:00+08:00`,
                  ...(selected ? { health_record: selected.record } : {}),
                });
                setAdding(false);
                setSuggestion("");
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "Unable to create this reminder.",
                );
              }
            }}
          >
            <fieldset className="form-fieldset" disabled={creating}>
              <div className="form-grid">
                {suggestions.length > 0 && (
                  <label className="full-width">
                    Suggested from a care record
                    <select
                      value={suggestion}
                      onChange={(e) => setSuggestion(e.target.value)}
                    >
                      <option value="">Custom reminder</option>
                      {suggestions.map((s) => (
                        <option value={s.record} key={s.record}>
                          {s.pet_name} · {s.title} · {displayDate(s.date)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label>
                  Pet
                  <select
                    name="pet"
                    key={`pet-${suggestion}`}
                    defaultValue={selected?.pet || state.pets[0]?.id}
                    required
                  >
                    {state.pets.map((p) => (
                      <option value={p.id} key={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Reminder name
                  <input
                    name="title"
                    key={`title-${suggestion}`}
                    defaultValue={selected?.title || ""}
                    required
                    maxLength={150}
                  />
                </label>
                <label>
                  Due date
                  <input
                    name="date"
                    key={`date-${suggestion}`}
                    type="date"
                    defaultValue={selected?.date || ""}
                    required
                  />
                </label>
              </div>
              <button className="button" type="submit">
                {creating ? "Saving…" : "Save reminder"}
              </button>
            </fieldset>
          </form>
        )}
        <div className="section-heading">
          <h2>Care checklist</h2>
          <label className="check-label">
            <input
              type="checkbox"
              checked={showDone}
              onChange={(e) => setShowDone(e.target.checked)}
            />
            Show completed
          </label>
        </div>
        {rows.length ? (
          rows.map((r) => (
            <div
              className={`record-row ${r.done ? "completed" : ""}`}
              key={r.id}
            >
              <span
                className={`stat-icon ${r.due_date < todaySG() && !r.done ? "rose-soft" : "green-soft"}`}
              >
                <Icon name="bell" />
              </span>
              <div>
                <h3>{r.title}</h3>
                <p>
                  {state.pets.find((p) => p.id === r.pet_id)?.name || "Pet"} ·{" "}
                  {displayDate(r.due_date)}
                </p>
              </div>
              <Badge
                tone={
                  r.done ? "green" : r.due_date < todaySG() ? "rose" : "amber"
                }
              >
                {r.done
                  ? "Completed"
                  : r.due_date < todaySG()
                    ? "Overdue"
                    : "Upcoming"}
              </Badge>
              <button
                className="button secondary small"
                disabled={pending.includes(`reminder:${r.id}`)}
                onClick={async () => {
                  setError("");
                  try {
                    await actions.setReminder(r.id, !r.done);
                  } catch (cause) {
                    setError(
                      cause instanceof Error
                        ? cause.message
                        : "Unable to update this reminder.",
                    );
                  }
                }}
              >
                {pending.includes(`reminder:${r.id}`)
                  ? "Saving…"
                  : r.done
                    ? "Reopen"
                    : "Mark done"}
              </button>
            </div>
          ))
        ) : (
          <Empty title="No outstanding reminders">
            Create a reminder, or use a suggested next due date from a care
            record.
          </Empty>
        )}
      </section>
    </>
  );
}
