"use client";
import Link from "next/link";
import { localUI } from "@/lib/data-source";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { useApp } from "./app-provider";
import {
  Badge,
  Empty,
  Icon,
  PageHeading,
  PetAvatar,
  ReminderBadge,
} from "./ui";
import { FormError } from "./resource-state";
import { PetForm, PetPhotoField } from "./pet-form";
import { displayDate, todaySG } from "@/lib/format";
import { formError } from "@/lib/form-error";
import { recordHasReminder, reminderStatus } from "@/lib/reminders";
import { services } from "@/lib/api/services";
import { useResource } from "@/lib/api/use-resource";
import type { HealthRecord, RecordInput, Reminder } from "@/lib/api/types";
const detailHref = (id: string) => `/pets/detail/?id=${encodeURIComponent(id)}`;
const overdueCount = (petId: string, reminders: Reminder[]) =>
  reminders.filter((r) => r.pet_id === petId && r.is_overdue).length;
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
          {state.pets.map((pet) => {
            const overdue = overdueCount(pet.id, state.reminders);
            return (
              <Link className="pet-card" href={detailHref(pet.id)} key={pet.id}>
                <div className="pet-card-art">
                  <span className="pet-species">
                    {pet.species.toUpperCase()} PASSPORT
                  </span>
                  <PetAvatar
                    species={pet.species}
                    petId={pet.id}
                    photoUrl={pet.photo_url}
                    photoVersion={pet.photo_version}
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
                    {overdue > 0 ? (
                      <Badge tone="rose">{overdue} overdue</Badge>
                    ) : (
                      <Badge tone="neutral">Personal profile</Badge>
                    )}
                  </div>
                </div>
              </Link>
            );
          })}
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
  const { actions, pending, notify } = useApp();
  const router = useRouter();
  const [error, setError] = useState("");
  // Held until the page changes, so a second click cannot create a duplicate
  // pet while the photo uploads.
  const [submitting, setSubmitting] = useState<"" | "pet" | "photo">("");
  const busy = submitting !== "" || pending.includes("pet:create");
  return (
    <>
      <PageHeading
        eyebrow="PET PASSPORTS / NEW PROFILE"
        title="Register a new pet"
        description="Create a personal pet profile. Add health records after registration."
      />
      <PetForm
        withPhoto
        busy={busy}
        submitLabel="Create pet passport"
        busyLabel={submitting === "photo" ? "Uploading photo…" : "Saving pet…"}
        cancelHref="/pets/"
        error={error}
        onSubmit={async (input, photo) => {
          if (busy) return;
          setError("");
          setSubmitting("pet");
          let id: string;
          try {
            id = await actions.createPet(input);
          } catch (cause) {
            setError(
              formError(cause, "Unable to save this pet. Please try again."),
            );
            setSubmitting("");
            return;
          }
          if (photo) {
            setSubmitting("photo");
            try {
              await actions.uploadPetPhoto(id, photo);
            } catch (cause) {
              notify(
                `Pet saved, but the photo was not uploaded: ${formError(cause, "please try again")} Try again from Edit profile.`,
              );
            }
          }
          router.push(detailHref(id));
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
      </PetForm>
    </>
  );
}
// Keyed like PetDetail, so the uncontrolled form never carries one pet's
// values over to another.
export function EditPet() {
  const id = useSearchParams().get("id");
  return <PetEditor key={id ?? ""} id={id} />;
}
function PetEditor({ id }: { id: string | null }) {
  const { state, actions, pending } = useApp();
  const router = useRouter();
  const pet = state.pets.find((p) => p.id === id);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  if (!pet)
    return deleting ? (
      <p role="status">Deleting pet passport…</p>
    ) : (
      <Empty title="Pet passport not found">
        <Link href="/pets/">Return to pet profiles</Link>
      </Empty>
    );
  const href = detailHref(pet.id);
  const busy = deleting || pending.includes(`pet:${pet.id}`);
  return (
    <>
      <PageHeading
        eyebrow="PET PASSPORTS / EDIT PROFILE"
        title={`Edit ${pet.name}’s passport`}
        description="Update identity details, care preferences and the profile photo."
      />
      <PetForm
        initial={pet.values}
        busy={busy}
        submitLabel="Save changes"
        busyLabel="Saving…"
        cancelHref={href}
        error={error}
        onSubmit={async (input) => {
          if (busy) return;
          setError("");
          try {
            await actions.updatePet(pet.id, input);
            router.push(href);
          } catch (cause) {
            setError(
              formError(
                cause,
                "Unable to save these changes. Please try again.",
              ),
            );
          }
        }}
      />
      <PetPhotoField pet={pet} />
      <section className="panel danger-zone">
        <h2>Delete this pet passport</h2>
        <p>
          Permanently removes {pet.name}’s care records, documents, reminders
          and photo.
        </p>
        <FormError message={deleteError} />
        <button
          className="button danger"
          disabled={busy}
          onClick={async () => {
            if (
              !window.confirm(
                `Delete ${pet.name}’s passport? This permanently removes its care records, documents, reminders and photo.`,
              )
            )
              return;
            setDeleting(true);
            setDeleteError("");
            try {
              await actions.deletePet(pet.id);
              router.push("/pets/");
            } catch (cause) {
              setDeleting(false);
              setDeleteError(
                formError(
                  cause,
                  "Unable to delete this pet. Please try again.",
                ),
              );
            }
          }}
        >
          {deleting ? "Deleting…" : "Delete pet"}
        </button>
      </section>
    </>
  );
}
/** Reads the shared add/edit care record form. */
function readRecord(form: HTMLFormElement): RecordInput {
  const d = new FormData(form);
  return {
    name: String(d.get("title") ?? "").trim(),
    record_type: String(d.get("kind")),
    date: String(d.get("date")),
    next_due: String(d.get("next_due") ?? "") || null,
    clinic: String(d.get("clinic") ?? "").trim(),
    notes: String(d.get("notes") ?? "").trim(),
  };
}
function RecordFields({ record }: { record?: HealthRecord }) {
  return (
    <div className="form-grid">
      <label>
        Record name
        <input
          name="title"
          required
          maxLength={100}
          defaultValue={record?.title ?? ""}
        />
      </label>
      <label>
        Care type
        <select name="kind" defaultValue={record?.record_type ?? "vaccination"}>
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
          defaultValue={record?.date ?? ""}
        />
      </label>
      <label>
        Next due
        <small>Optional · suggests a care reminder</small>
        <input
          name="next_due"
          type="date"
          min={record ? undefined : todaySG()}
          defaultValue={record?.next_due ?? ""}
        />
      </label>
      <label>
        Clinic or provider
        <input
          name="clinic"
          maxLength={100}
          defaultValue={record?.clinic ?? ""}
        />
      </label>
      <label className="full-width">
        Notes<small>Optional</small>
        <textarea
          name="notes"
          maxLength={1000}
          rows={3}
          defaultValue={record?.notes ?? ""}
        />
      </label>
    </div>
  );
}
// Next keeps the page mounted when only ?id= changes, so the key gives each
// pet fresh forms, errors and document state.
export function PetDetail() {
  const id = useSearchParams().get("id");
  return <PetPassport key={id ?? ""} id={id} />;
}
function PetPassport({ id }: { id: string | null }) {
  const { state, actions, pending } = useApp();
  const pet = state.pets.find((p) => p.id === id);
  const [tab, setTab] = useState("Overview");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState("");
  const [editError, setEditError] = useState("");
  const [recordError, setRecordError] = useState("");
  if (!pet)
    return (
      <Empty title="Pet passport not found">
        <Link href="/pets/">Return to pet profiles</Link>
      </Empty>
    );
  const reminders = state.reminders.filter(
    (r) => r.pet_id === pet.id && !r.done,
  );
  const overdue = reminders.filter((r) => r.is_overdue).length;
  const records = [...pet.records].sort(
    (a, b) => b.date.localeCompare(a.date) || a.title.localeCompare(b.title),
  );
  const busy = pending.includes(`record:${pet.id}`);
  const openAddForm = (open: boolean) => {
    setAdding(open);
    if (open) setEditing("");
  };
  return (
    <>
      <PageHeading
        eyebrow="PET PASSPORTS / IDENTITY & HEALTH"
        title={`${pet.name}’s passport`}
        description="Identity, health history and care information in one personal record."
        action={
          <div className="heading-actions">
            <Link
              className="button secondary"
              href={`/pets/edit/?id=${encodeURIComponent(pet.id)}`}
            >
              Edit profile
            </Link>
            <Link className="button secondary" href="/pets/">
              All pets
              <Icon name="paw" size={16} />
            </Link>
          </div>
        }
      />
      <div className="pet-switcher">
        {state.pets.map((p) => (
          <Link
            className={`chip ${p.id === pet.id ? "selected" : ""}`}
            href={detailHref(p.id)}
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
            <PetAvatar
              species={pet.species}
              petId={pet.id}
              photoUrl={pet.photo_url}
              photoVersion={pet.photo_version}
              large
            />
            <div>
              <Badge tone="neutral">PERSONAL PET RECORD</Badge>
              {overdue > 0 && <Badge tone="rose">{overdue} overdue</Badge>}
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
                    onClick={() => openAddForm(!adding)}
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
                      const input = readRecord(e.currentTarget);
                      setError("");
                      try {
                        await actions.addRecord(pet.id, input);
                        setAdding(false);
                      } catch (cause) {
                        setError(
                          formError(cause, "Unable to save this record."),
                        );
                      }
                    }}
                  >
                    <FormError message={error} />
                    <fieldset className="form-fieldset" disabled={busy}>
                      <RecordFields />
                      <button className="button" type="submit">
                        {busy ? "Saving record…" : "Save care record"}
                      </button>
                    </fieldset>
                  </form>
                )}
                <FormError message={recordError} />
                {records.length ? (
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
                          <th scope="col">ACTIONS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((r) => {
                          const rowKey = `record:${pet.id}:${r.id}`;
                          const rowBusy = pending.includes(rowKey);
                          if (editing === r.id)
                            return (
                              <tr className="record-edit-row" key={r.id}>
                                <td colSpan={6}>
                                  <form
                                    className="record-form"
                                    aria-label={`Edit ${r.title}`}
                                    onSubmit={async (e) => {
                                      e.preventDefault();
                                      if (rowBusy) return;
                                      const input = readRecord(e.currentTarget);
                                      setEditError("");
                                      try {
                                        await actions.updateRecord(
                                          pet.id,
                                          r.id,
                                          input,
                                        );
                                        setEditing("");
                                      } catch (cause) {
                                        setEditError(
                                          formError(
                                            cause,
                                            "Unable to update this record.",
                                          ),
                                        );
                                      }
                                    }}
                                  >
                                    <FormError message={editError} />
                                    <fieldset
                                      className="form-fieldset"
                                      disabled={rowBusy}
                                    >
                                      <RecordFields record={r} />
                                      <div className="form-footer">
                                        <button
                                          className="button secondary"
                                          type="button"
                                          onClick={() => setEditing("")}
                                        >
                                          Cancel
                                        </button>
                                        <button
                                          className="button"
                                          type="submit"
                                        >
                                          {rowBusy ? "Saving…" : "Save changes"}
                                        </button>
                                      </div>
                                    </fieldset>
                                  </form>
                                </td>
                              </tr>
                            );
                          const due = r.next_due
                            ? reminderStatus(r.next_due, false)
                            : null;
                          return (
                            <tr key={r.id}>
                              <td>
                                <strong>{r.title}</strong>
                                {r.notes && (
                                  <p className="record-notes">{r.notes}</p>
                                )}
                              </td>
                              <td>
                                <Badge tone="neutral">{r.kind}</Badge>
                              </td>
                              <td>{displayDate(r.date)}</td>
                              <td>{r.clinic || "Not recorded"}</td>
                              <td className="next-due-cell">
                                {r.next_due ? (
                                  <>
                                    <strong>{displayDate(r.next_due)}</strong>
                                    <Badge
                                      tone={due?.is_overdue ? "rose" : "green"}
                                    >
                                      {due?.is_overdue
                                        ? "Overdue"
                                        : "Scheduled"}
                                    </Badge>
                                    {!recordHasReminder(
                                      pet.id,
                                      r,
                                      state.reminders,
                                    ) && (
                                      <Link
                                        className="text-link"
                                        href={`/pets/reminders/?record=${encodeURIComponent(r.id)}`}
                                      >
                                        Add reminder
                                      </Link>
                                    )}
                                  </>
                                ) : (
                                  "Not scheduled"
                                )}
                              </td>
                              <td>
                                <div className="row-actions">
                                  <button
                                    className="text-button"
                                    disabled={rowBusy}
                                    aria-label={`Edit ${r.title}`}
                                    onClick={() => {
                                      setEditError("");
                                      setEditing(r.id);
                                      setAdding(false);
                                    }}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    className="text-button danger"
                                    disabled={rowBusy}
                                    aria-label={`Delete ${r.title}`}
                                    onClick={async () => {
                                      if (
                                        !window.confirm(
                                          "Delete this care record? Linked reminders and documents are kept.",
                                        )
                                      )
                                        return;
                                      setRecordError("");
                                      try {
                                        await actions.deleteRecord(
                                          pet.id,
                                          r.id,
                                        );
                                      } catch (cause) {
                                        setRecordError(
                                          formError(
                                            cause,
                                            "Unable to delete this record.",
                                          ),
                                        );
                                      }
                                    }}
                                  >
                                    {rowBusy ? "Deleting…" : "Delete"}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
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
            {tab === "Documents" && (
              <PetDocuments petId={pet.id} records={records} />
            )}
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
                openAddForm(true);
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
                  <ReminderBadge reminder={r} upcomingTone="green" />
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
function PetDocuments({
  petId,
  records,
}: {
  petId: string;
  records: HealthRecord[];
}) {
  const loader = useCallback(() => services.documents(petId), [petId]);
  const { data, loading, error, reload } = useResource(
    `documents:${petId}`,
    loader,
  );
  // The running action, so each button can name it; "" when idle.
  const [running, setRunning] = useState<
    "" | "upload" | "download" | "rename" | "delete"
  >("");
  const busy = running !== "";
  const [actionError, setActionError] = useState("");
  const [renaming, setRenaming] = useState("");
  async function run(
    kind: Exclude<typeof running, "">,
    work: () => Promise<void>,
    fallback: string,
  ) {
    if (busy) return;
    setRunning(kind);
    setActionError("");
    try {
      await work();
    } catch (cause) {
      setActionError(formError(cause, fallback));
    } finally {
      setRunning("");
    }
  }
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
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget,
            d = new FormData(form),
            file = d.get("file"),
            record = String(d.get("record") ?? "");
          if (!(file instanceof File)) return;
          void run(
            "upload",
            async () => {
              await services.uploadDocument(
                petId,
                file,
                String(d.get("title")).trim(),
                record || undefined,
              );
              form.reset();
              reload();
            },
            "Unable to upload this document.",
          );
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
            <label>
              Related care record<small>Optional</small>
              <select name="record" defaultValue="">
                <option value="">None</option>
                {records.map((r) => (
                  <option value={r.id} key={r.id}>
                    {r.title} · {displayDate(r.date)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button className="button" type="submit">
            {running === "upload" ? "Uploading…" : "Upload document"}
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
        data.map((doc) => {
          const related = records.find((r) => r.id === doc.health_record_id);
          if (renaming === doc.id)
            return (
              <div className="record-row" key={doc.id}>
                <Icon name="file" />
                <form
                  className="inline-form"
                  aria-label={`Rename ${doc.title}`}
                  onSubmit={(e) => {
                    e.preventDefault();
                    const title = String(
                      new FormData(e.currentTarget).get("title") ?? "",
                    ).trim();
                    void run(
                      "rename",
                      async () => {
                        await services.updateDocument(petId, doc.id, { title });
                        setRenaming("");
                        reload();
                      },
                      "Unable to rename this document.",
                    );
                  }}
                >
                  <label>
                    Document title
                    <input
                      name="title"
                      required
                      maxLength={150}
                      defaultValue={doc.title}
                    />
                  </label>
                  <button
                    className="button small"
                    type="submit"
                    disabled={busy}
                  >
                    {running === "rename" ? "Saving…" : "Save"}
                  </button>
                  <button
                    className="button secondary small"
                    type="button"
                    onClick={() => setRenaming("")}
                  >
                    Cancel
                  </button>
                </form>
              </div>
            );
          return (
            <div className="record-row" key={doc.id}>
              <Icon name="file" />
              <div>
                <h3>{doc.title}</h3>
                <p>
                  {displayDate(doc.uploaded_at)} ·{" "}
                  {Math.ceil(doc.size_bytes / 1024)} KB
                  {related ? ` · ${related.title}` : ""}
                </p>
              </div>
              <div className="row-actions">
                <button
                  className="button secondary small"
                  disabled={busy}
                  onClick={() =>
                    void run(
                      "download",
                      async () => {
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
                      },
                      "Unable to download this document.",
                    )
                  }
                >
                  Download
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  aria-label={`Rename ${doc.title}`}
                  onClick={() => {
                    setActionError("");
                    setRenaming(doc.id);
                  }}
                >
                  Rename
                </button>
                <button
                  className="text-button danger"
                  disabled={busy}
                  aria-label={`Delete ${doc.title}`}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "Delete this document? This cannot be undone.",
                      )
                    )
                      return;
                    void run(
                      "delete",
                      async () => {
                        await services.deleteDocument(petId, doc.id);
                        reload();
                      },
                      "Unable to delete this document.",
                    );
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })
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
  const params = useSearchParams();
  const fromRecord = params.get("record") ?? "";
  const [showDone, setShowDone] = useState(false);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(fromRecord !== "");
  const [suggestion, setSuggestion] = useState(fromRecord);
  const [editing, setEditing] = useState("");
  const [editError, setEditError] = useState("");
  const rows = state.reminders
    .filter((r) => showDone || !r.done)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  const suggestions = state.pets.flatMap((p) =>
    p.records
      .filter((r) => r.next_due && !recordHasReminder(p.id, r, state.reminders))
      .map((r) => ({
        pet: p.id,
        pet_name: p.name,
        record: r.id,
        title: r.title,
        date: r.next_due,
      })),
  );
  const selected = suggestions.find((s) => s.record === suggestion);
  // Prefilled inputs remount when the suggestion, or its availability after
  // pets load, changes.
  const prefill = (field: string) =>
    `${field}-${suggestion}:${selected ? 1 : 0}`;
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
                setError(formError(cause, "Unable to create this reminder."));
              }
            }}
          >
            <fieldset className="form-fieldset" disabled={creating}>
              <div className="form-grid">
                {suggestions.length > 0 && (
                  <label className="full-width">
                    Suggested from a care record
                    <select
                      value={selected ? suggestion : ""}
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
                  {/* A suggestion fixes the pet, so its care record always
                      belongs to the submitted pet. */}
                  <select
                    name="pet"
                    key={prefill("pet")}
                    defaultValue={selected?.pet || state.pets[0]?.id}
                    disabled={Boolean(selected)}
                    required
                  >
                    {state.pets.map((p) => (
                      <option value={p.id} key={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                  {selected && (
                    <input type="hidden" name="pet" value={selected.pet} />
                  )}
                </label>
                <label>
                  Reminder name
                  <input
                    name="title"
                    key={prefill("title")}
                    defaultValue={selected?.title || ""}
                    required
                    maxLength={150}
                  />
                </label>
                <label>
                  Due date
                  <input
                    name="date"
                    key={prefill("date")}
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
          rows.map((r) => {
            const rowBusy = pending.includes(`reminder:${r.id}`);
            const petName =
              state.pets.find((p) => p.id === r.pet_id)?.name || "Pet";
            if (editing === r.id)
              return (
                <div className="record-row" key={r.id}>
                  <form
                    className="inline-form"
                    aria-label={`Edit ${r.title}`}
                    onSubmit={async (e) => {
                      e.preventDefault();
                      if (rowBusy) return;
                      const data = new FormData(e.currentTarget);
                      setEditError("");
                      try {
                        await actions.updateReminder(r.id, {
                          title: String(data.get("title")).trim(),
                          due_at: `${data.get("date")}T09:00:00+08:00`,
                        });
                        setEditing("");
                      } catch (cause) {
                        setEditError(
                          formError(cause, "Unable to update this reminder."),
                        );
                      }
                    }}
                  >
                    <FormError message={editError} />
                    <label>
                      Reminder name
                      <input
                        name="title"
                        required
                        maxLength={150}
                        defaultValue={r.title}
                      />
                    </label>
                    <label>
                      Due date
                      <input
                        name="date"
                        type="date"
                        required
                        defaultValue={r.due_date}
                      />
                    </label>
                    <button
                      className="button small"
                      type="submit"
                      disabled={rowBusy}
                    >
                      {rowBusy ? "Saving…" : "Save"}
                    </button>
                    <button
                      className="button secondary small"
                      type="button"
                      onClick={() => setEditing("")}
                    >
                      Cancel
                    </button>
                  </form>
                </div>
              );
            return (
              <div
                className={`record-row ${r.done ? "completed" : ""}`}
                key={r.id}
              >
                <span
                  className={`stat-icon ${r.is_overdue ? "rose-soft" : "green-soft"}`}
                >
                  <Icon name="bell" />
                </span>
                <div>
                  <h3>{r.title}</h3>
                  <p>
                    {petName} · {displayDate(r.due_date)}
                  </p>
                </div>
                <ReminderBadge reminder={r} upcomingTone="neutral" />
                <div className="row-actions">
                  <button
                    className="button secondary small"
                    disabled={rowBusy}
                    onClick={async () => {
                      setError("");
                      try {
                        await actions.setReminder(r.id, !r.done);
                      } catch (cause) {
                        setError(
                          formError(cause, "Unable to update this reminder."),
                        );
                      }
                    }}
                  >
                    {rowBusy ? "Saving…" : r.done ? "Reopen" : "Mark done"}
                  </button>
                  <button
                    className="text-button"
                    disabled={rowBusy}
                    aria-label={`Edit ${r.title}`}
                    onClick={() => {
                      setEditError("");
                      setEditing(r.id);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="text-button danger"
                    disabled={rowBusy}
                    aria-label={`Delete ${r.title}`}
                    onClick={async () => {
                      if (!window.confirm("Delete this reminder?")) return;
                      setError("");
                      try {
                        await actions.deleteReminder(r.id);
                      } catch (cause) {
                        setError(
                          formError(cause, "Unable to delete this reminder."),
                        );
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })
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
