"use client";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { localUI } from "@/lib/data-source";
import { todaySG } from "@/lib/format";
import { formError } from "@/lib/form-error";
import { parseAllergies, photoProblem } from "@/lib/pet-input";
import type { Pet, PetInput } from "@/lib/api/types";
import { useApp } from "./app-provider";
import { FormError } from "./resource-state";
import { Icon, PetAvatar } from "./ui";

/** A file input with nothing chosen still submits an empty, unnamed File. */
function chosenFile(value: FormDataEntryValue | null): File | null {
  return value instanceof File && (value.name !== "" || value.size > 0)
    ? value
    : null;
}

/** The create and edit form for a pet's identity and care preferences. */
export function PetForm({
  initial,
  busy,
  submitLabel,
  busyLabel,
  cancelHref,
  withPhoto = false,
  error = "",
  children,
  onSubmit,
}: {
  initial?: PetInput;
  busy: boolean;
  submitLabel: string;
  busyLabel: string;
  cancelHref: string;
  withPhoto?: boolean;
  error?: string;
  /** Optional introduction shown above the fields. */
  children?: ReactNode;
  onSubmit: (input: PetInput, photo: File | null) => void | Promise<void>;
}) {
  const [problem, setProblem] = useState("");
  return (
    <form
      className="panel form-panel"
      onSubmit={(e) => {
        e.preventDefault();
        if (busy) return;
        const data = new FormData(e.currentTarget);
        const text = (name: string) => String(data.get(name) ?? "").trim();
        const allergies = parseAllergies(text("allergies"));
        const photo = withPhoto ? chosenFile(data.get("photo")) : null;
        const found =
          allergies.problem || (photo ? photoProblem(photo) : null) || "";
        setProblem(found);
        if (found) return;
        const weight = text("weight");
        void onSubmit(
          {
            name: text("name"),
            species: String(data.get("species")),
            breed: text("breed"),
            sex: String(data.get("sex")),
            date_of_birth: text("birth") || null,
            microchip_no: text("microchip") || null,
            allergies: allergies.allergies,
            diet_notes: text("diet"),
            weight_kg: weight ? Number(weight) : null,
          },
          photo,
        );
      }}
    >
      {children}
      <FormError message={problem || error} />
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
              defaultValue={initial?.name ?? ""}
            />
          </label>
          <label>
            Species
            <select name="species" defaultValue={initial?.species ?? "dog"}>
              <option value="dog">Dog</option>
              <option value="cat">Cat</option>
              <option value="rabbit">Rabbit</option>
              <option value="bird">Bird</option>
              <option value="fish">Fish</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Breed
            <input
              name="breed"
              maxLength={80}
              autoComplete="off"
              defaultValue={initial?.breed ?? ""}
            />
          </label>
          <label>
            Sex
            <select name="sex" defaultValue={initial?.sex || "unknown"}>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label>
            Date of birth<small>Optional</small>
            <input
              name="birth"
              type="date"
              max={todaySG()}
              defaultValue={initial?.date_of_birth ?? ""}
            />
          </label>
          <label>
            Microchip number<small>Optional · 15 digits</small>
            <input
              name="microchip"
              inputMode="numeric"
              pattern="[0-9]{15}"
              maxLength={15}
              autoComplete="off"
              defaultValue={initial?.microchip_no ?? ""}
            />
          </label>
          <label>
            Weight (kg)<small>Optional</small>
            <input
              name="weight"
              type="number"
              inputMode="decimal"
              min={0.01}
              max={500}
              step={0.01}
              defaultValue={initial?.weight_kg ?? ""}
            />
          </label>
          <label>
            Allergies
            <small>Optional · up to 20, separated by commas</small>
            <input
              name="allergies"
              maxLength={1100}
              defaultValue={initial?.allergies.join(", ") ?? ""}
            />
          </label>
          <label>
            Dietary preferences<small>Optional</small>
            <input
              name="diet"
              maxLength={500}
              defaultValue={initial?.diet_notes ?? ""}
            />
          </label>
          {withPhoto && (
            <label>
              Profile photo
              <small>Optional · JPEG or PNG · up to 5 MB</small>
              <input type="file" name="photo" accept="image/jpeg,image/png" />
            </label>
          )}
        </div>
        <div className="form-footer">
          <Link className="button secondary" href={cancelHref}>
            Cancel
          </Link>
          <button className="button" type="submit">
            {busy ? busyLabel : submitLabel}
            <Icon name="arrow" size={17} />
          </button>
        </div>
      </fieldset>
    </form>
  );
}

/** Upload, replace or remove a pet's profile photo. */
export function PetPhotoField({ pet }: { pet: Pet }) {
  const { actions, pending } = useApp();
  const [error, setError] = useState("");
  const busy = pending.includes(`pet-photo:${pet.id}`);
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>
          <Icon name="user" />
          Profile photo
        </h2>
      </div>
      <FormError message={error} />
      <div className="photo-field">
        <PetAvatar
          species={pet.species}
          petId={pet.id}
          photoUrl={pet.photo_url}
          photoVersion={pet.photo_version}
          large
        />
        <form
          className="inline-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy) return;
            const form = e.currentTarget;
            const photo = chosenFile(new FormData(form).get("photo"));
            const problem = photo
              ? photoProblem(photo)
              : "Choose a JPEG or PNG photo up to 5 MB.";
            if (problem || !photo) {
              setError(problem ?? "");
              return;
            }
            setError("");
            try {
              await actions.uploadPetPhoto(pet.id, photo);
              form.reset();
            } catch (cause) {
              setError(
                formError(
                  cause,
                  "Unable to upload this photo. Please try again.",
                ),
              );
            }
          }}
        >
          <p className="full-width">
            {localUI
              ? "Photos stay in this tab until you reload."
              : "JPEG or PNG · up to 5 MB. Photos are private to your account."}
          </p>
          <label>
            New photo
            <input
              type="file"
              name="photo"
              accept="image/jpeg,image/png"
              required
              disabled={busy}
            />
          </label>
          <button className="button secondary" type="submit" disabled={busy}>
            {busy ? "Uploading…" : "Upload photo"}
          </button>
          {pet.photo_version && (
            <button
              type="button"
              className="text-button danger"
              disabled={busy}
              onClick={async () => {
                if (!window.confirm("Remove this photo?")) return;
                setError("");
                try {
                  await actions.removePetPhoto(pet.id);
                } catch (cause) {
                  setError(
                    formError(
                      cause,
                      "Unable to remove this photo. Please try again.",
                    ),
                  );
                }
              }}
            >
              Remove photo
            </button>
          )}
        </form>
      </div>
    </section>
  );
}
