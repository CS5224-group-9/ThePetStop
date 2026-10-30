import { test } from "node:test";
import assert from "node:assert/strict";
import {
  localServices as service,
  seedLocalState,
} from "../lib/api/local-services.ts";
import { addDays, recordHasReminder } from "../lib/reminders.ts";
import { todaySG } from "../lib/format.ts";
import type { HealthRecord, Reminder } from "../lib/api/types.ts";

// There is no `window` under node --test, so local services run in memory.
const input = {
  name: "Biscuit",
  species: "dog",
  breed: "",
  sex: "female",
  date_of_birth: null,
  microchip_no: null,
  allergies: ["Chicken", "Beef"],
  diet_notes: "",
  weight_kg: null,
};
const newPet = (name = "Biscuit") => service.createPet({ ...input, name });
const record = {
  name: "Rabies vaccination",
  record_type: "vaccination",
  date: "2026-06-12",
  next_due: "2027-06-12",
  clinic: "Sample clinic",
};

test("the seeded state has three pets and Kopi carries raw values", async () => {
  const seeded = seedLocalState();
  assert.equal(seeded.pets.length, 3);
  const kopi = seeded.pets.find((p) => p.id === "kopi")!;
  assert.equal(kopi.species, "Dog");
  assert.equal(kopi.weight, "14.2 kg");
  assert.equal(kopi.values.species, "dog");
  assert.equal(kopi.values.weight_kg, 14.2);
  assert.deepEqual(kopi.values.allergies, ["Chicken"]);
  assert.equal(kopi.photo_version, null);
  assert.equal(kopi.records[0].record_type, "vaccination");
  assert.equal(kopi.records[0].kind, "Vaccination");
  assert.equal(kopi.records[0].notes, "");
  assert.ok(seeded.reminders.every((r) => r.health_record_id === ""));
  const stored = await service.pets();
  assert.deepEqual(
    stored.map((p) => p.id),
    ["kopi", "mochi", "sesame"],
  );
  assert.equal(stored[0].values.name, "Kopi");
});

test("createPet stores labelled display fields and raw values", async () => {
  const pet = await newPet();
  assert.equal(pet.species, "Dog");
  assert.equal(pet.sex, "Female");
  assert.equal(pet.breed, "Not recorded");
  assert.equal(pet.date_of_birth, "");
  assert.equal(pet.microchip, "");
  assert.equal(pet.allergies, "Chicken, Beef");
  assert.equal(pet.weight, "Not recorded");
  assert.equal(pet.photo_url, null);
  assert.equal(pet.photo_version, null);
  assert.deepEqual(pet.values, input);
  assert.deepEqual(
    (await service.pets()).find((p) => p.id === pet.id)?.values,
    input,
  );
  await assert.rejects(newPet("   "), /Enter your pet’s name/);
});

test("updatePet changes values and display and rejects a blank name", async () => {
  const pet = await newPet();
  await service.addRecord(pet.id, record);
  const updated = await service.updatePet(pet.id, {
    name: "Biscuit II",
    species: "cat",
    weight_kg: 4.5,
    microchip_no: "702000000000099",
  });
  assert.equal(updated.name, "Biscuit II");
  assert.equal(updated.species, "Cat");
  assert.equal(updated.weight, "4.5 kg");
  assert.equal(updated.microchip, "702000000000099");
  assert.equal(updated.values.species, "cat");
  assert.deepEqual(updated.values.allergies, ["Chicken", "Beef"]);
  assert.equal(updated.records.length, 1);
  const stored = (await service.pets()).find((p) => p.id === pet.id)!;
  assert.equal(stored.values.weight_kg, 4.5);
  assert.equal(stored.records.length, 1);
  await assert.rejects(
    service.updatePet(pet.id, { name: " " }),
    /Enter your pet’s name/,
  );
  await assert.rejects(service.updatePet("missing", { name: "X" }));
});

test("deletePet removes the pet and its reminders", async () => {
  const pet = await newPet();
  const other = await newPet("Other");
  await service.createReminder({
    pet: pet.id,
    title: "Booster",
    due_at: "2027-01-01T09:00:00+08:00",
  });
  const kept = await service.createReminder({
    pet: other.id,
    title: "Kept",
    due_at: "2027-01-01T09:00:00+08:00",
  });
  await service.deletePet(pet.id);
  assert.equal(
    (await service.pets()).some((p) => p.id === pet.id),
    false,
  );
  const reminders = await service.reminders();
  assert.equal(
    reminders.some((r) => r.pet_id === pet.id),
    false,
  );
  assert.ok(reminders.some((r) => r.id === kept.id));
  await assert.rejects(service.deletePet(pet.id));
});

test("records can be listed, edited and deleted; deleting unlinks reminders", async () => {
  const pet = await newPet();
  const added = await service.addRecord(pet.id, { ...record, notes: "First" });
  assert.equal(added.notes, "First");
  assert.equal(added.record_type, "vaccination");
  const updated = await service.updateRecord(pet.id, added.id, {
    notes: "Mild swelling",
  });
  assert.equal(updated.notes, "Mild swelling");
  assert.equal(updated.title, record.name);
  assert.equal(updated.next_due, record.next_due);
  await assert.rejects(
    service.updateRecord(pet.id, added.id, { next_due: "2026-01-01" }),
    /^Error: Next due date cannot be before the date of care\.$/,
  );
  const cleared = await service.updateRecord(pet.id, added.id, {
    next_due: null,
  });
  assert.equal(cleared.next_due, "");
  assert.deepEqual(
    (await service.records(pet.id)).map((r) => r.notes),
    ["Mild swelling"],
  );
  const linked = await service.createReminder({
    pet: pet.id,
    title: "Booster",
    due_at: "2027-06-12T09:00:00+08:00",
    health_record: added.id,
  });
  assert.equal(linked.health_record_id, added.id);
  await service.deleteRecord(pet.id, added.id);
  assert.deepEqual(await service.records(pet.id), []);
  assert.equal(
    (await service.reminders()).find((r) => r.id === linked.id)
      ?.health_record_id,
    "",
  );
});

test("reminders can be rescheduled, renamed and deleted, with computed flags", async () => {
  const pet = await newPet();
  const today = todaySG();
  const due = (date: string) => `${date}T09:00:00+08:00`;
  const reminder = await service.createReminder({
    pet: pet.id,
    title: "Booster",
    due_at: due(addDays(today, 30)),
  });
  await service.updateReminder(reminder.id, {
    title: "Annual booster",
    due_at: due(addDays(today, -1)),
  });
  let saved = (await service.reminders()).find((r) => r.id === reminder.id)!;
  assert.equal(saved.title, "Annual booster");
  assert.equal(saved.due_date, addDays(today, -1));
  assert.equal(saved.is_overdue, true);
  assert.equal(saved.is_due_soon, false);

  await service.updateReminder(reminder.id, { due_at: due(addDays(today, 1)) });
  saved = (await service.reminders()).find((r) => r.id === reminder.id)!;
  assert.equal(saved.is_overdue, false);
  assert.equal(saved.is_due_soon, true);

  await service.updateReminder(reminder.id, {
    due_at: due(addDays(today, -1)),
    done: true,
  });
  saved = (await service.reminders()).find((r) => r.id === reminder.id)!;
  assert.equal(saved.done, true);
  assert.equal(saved.is_overdue, false);
  assert.equal(saved.is_due_soon, false);

  await service.deleteReminder(reminder.id);
  assert.equal(
    (await service.reminders()).some((r) => r.id === reminder.id),
    false,
  );
});

test("blank record names and reminder titles are rejected, as in API mode", async () => {
  const pet = await newPet();
  await assert.rejects(
    service.addRecord(pet.id, { ...record, name: "   " }),
    /^Error: Enter a record name\.$/,
  );
  const added = await service.addRecord(pet.id, record);
  await assert.rejects(
    service.updateRecord(pet.id, added.id, { name: " " }),
    /^Error: Enter a record name\.$/,
  );
  const due_at = "2027-01-01T09:00:00+08:00";
  await assert.rejects(
    service.createReminder({ pet: pet.id, title: "  ", due_at }),
    /^Error: Enter a reminder name\.$/,
  );
  const reminder = await service.createReminder({
    pet: pet.id,
    title: "Booster",
    due_at,
  });
  await assert.rejects(
    service.updateReminder(reminder.id, { title: "" }),
    /^Error: Enter a reminder name\.$/,
  );
  assert.deepEqual(
    (await service.records(pet.id)).map((r) => r.title),
    [record.name],
  );
  assert.deepEqual(
    (await service.reminders())
      .filter((r) => r.pet_id === pet.id)
      .map((r) => r.title),
    ["Booster"],
  );
});

test("documents keep their care record link and can be renamed and deleted", async () => {
  const pet = await newPet();
  const added = await service.addRecord(pet.id, record);
  await service.uploadDocument(
    pet.id,
    new File(["%PDF"], "report.pdf", { type: "application/pdf" }),
    "Vet report",
    added.id,
  );
  await assert.rejects(
    service.uploadDocument(
      pet.id,
      new File(["GIF8"], "x.gif", { type: "image/gif" }),
      "Scan",
    ),
    /PDF, JPEG or PNG file up to 10 MB/,
  );
  const [doc] = await service.documents(pet.id);
  assert.equal(doc.title, "Vet report");
  assert.equal(doc.health_record_id, added.id);
  const renamed = await service.updateDocument(pet.id, doc.id, {
    title: "Rabies certificate",
  });
  assert.equal(renamed.title, "Rabies certificate");
  assert.equal(renamed.health_record_id, added.id);
  assert.equal(
    (await service.documents(pet.id))[0].title,
    "Rabies certificate",
  );
  await service.deleteDocument(pet.id, doc.id);
  assert.deepEqual(await service.documents(pet.id), []);
});

test("profile photos stay in memory as blob URLs with a changing version", async () => {
  const pet = await newPet();
  await assert.rejects(
    service.uploadPetPhoto(
      pet.id,
      new File(["GIF8"], "x.gif", { type: "image/gif" }),
    ),
    /^Error: Choose a JPEG or PNG photo up to 5 MB\.$/,
  );
  const png = () =>
    new File([new Uint8Array([137, 80, 78, 71])], "pet.png", {
      type: "image/png",
    });
  const first = await service.uploadPetPhoto(pet.id, png());
  assert.ok(first.photo_url?.startsWith("blob:"));
  assert.ok(first.photo_version);
  const listed = (await service.pets()).find((p) => p.id === pet.id)!;
  assert.ok(listed.photo_url?.startsWith("blob:"));
  assert.equal(listed.photo_version, first.photo_version);
  const second = await service.uploadPetPhoto(pet.id, png());
  assert.notEqual(second.photo_version, first.photo_version);
  const renamed = await service.updatePet(pet.id, { name: "Photo kept" });
  assert.equal(renamed.photo_version, second.photo_version);
  await service.removePetPhoto(pet.id);
  const cleared = (await service.pets()).find((p) => p.id === pet.id)!;
  assert.equal(cleared.photo_url, null);
  assert.equal(cleared.photo_version, null);
});

test("recordHasReminder recognises linked and matching reminders of the same pet", () => {
  const care: HealthRecord = {
    id: "r1",
    title: "Booster",
    kind: "Vaccination",
    record_type: "vaccination",
    date: "2026-06-12",
    next_due: "2027-06-12",
    clinic: "",
    notes: "",
  };
  const base: Reminder = {
    id: "rem1",
    pet_id: "p1",
    title: "Booster",
    due_date: "2027-06-12",
    done: false,
    health_record_id: "r1",
    is_overdue: false,
    is_due_soon: false,
  };
  assert.equal(recordHasReminder("p1", care, [base]), true);
  assert.equal(recordHasReminder("p1", care, [{ ...base, done: true }]), true);
  assert.equal(
    recordHasReminder("p1", care, [
      {
        ...base,
        title: "Something else",
        due_date: "2027-07-01",
        done: true,
      },
    ]),
    true,
  );
  assert.equal(
    recordHasReminder("p1", care, [{ ...base, health_record_id: "" }]),
    true,
  );
  assert.equal(recordHasReminder("p2", care, [base]), false);
  assert.equal(
    recordHasReminder("p1", care, [
      {
        ...base,
        health_record_id: "",
        title: "Renamed booster",
        due_date: "2027-07-01",
      },
    ]),
    false,
  );
  assert.equal(recordHasReminder("p1", care, []), false);
});
