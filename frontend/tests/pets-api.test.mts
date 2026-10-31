import { test } from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiError, createApiClient } from "../lib/api/client.ts";
import { createServices } from "../lib/api/services.ts";
import { pet, reminder } from "../lib/api/adapters.ts";
import { createPhotoCache } from "../lib/api/photo-cache.ts";
import {
  devSignInError,
  isDevAuthAllowed,
  useDevAuthEnabled,
} from "../lib/auth/dev.ts";
import { formError } from "../lib/form-error.ts";
import { addDays } from "../lib/reminders.ts";
import { todaySG } from "../lib/format.ts";
import {
  documentProblem,
  parseAllergies,
  photoProblem,
} from "../lib/pet-input.ts";

const origin = "https://api.example.test/api/v1/";
const storage = "https://bucket.example.test/";
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
const noContent = () => new Response(null, { status: 204 });
const failure = (status: number, code: string) =>
  json({ error: { code, message: "server detail", details: {} } }, status);
const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

type Call = {
  method: string;
  url: string;
  body: unknown;
  headers: Headers;
};
// Every request (API and storage) in the order it was made.
function harness(api: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const record = (url: unknown, init?: RequestInit): Call => {
    const body =
      typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
    const call = {
      method: init?.method ?? "GET",
      url: String(url),
      body,
      headers: new Headers(init?.headers),
    };
    calls.push(call);
    return call;
  };
  const client = createApiClient({
    baseUrl: origin,
    getToken: async () => "token",
    fetcher: async (url, init) => api(record(url, init)),
  });
  return { calls, record, services: createServices(client) };
}
// transferPrivateFile uses the global fetch; stub it and always restore it.
async function withStorage<T>(
  record: (url: unknown, init?: RequestInit) => Call,
  respond: (call: Call) => Response,
  run: () => Promise<T>,
): Promise<T> {
  const original = globalThis.fetch;
  globalThis.fetch = (async (url: unknown, init?: RequestInit) =>
    respond(record(url, init))) as typeof fetch;
  try {
    return await run();
  } finally {
    globalThis.fetch = original;
  }
}
const route = (call: Call) =>
  `${call.method} ${call.url.replace(origin, "").replace(storage, "storage:")}`;

const wirePet = {
  id: "p1",
  name: "Nemo",
  species: "fish",
  breed: "",
  sex: "unknown",
  date_of_birth: null,
  microchip_no: null,
  allergies: ["Chicken", 3, "Beef"],
  diet_notes: "",
  weight_kg: 14.2,
  photo_url: storage + "pets/p1/photos/v1.jpg?X-Amz-Signature=1",
  photo_version: "v1",
  created_at: "2026-10-30T10:15:00.123456+08:00",
  updated_at: "2026-10-30T10:15:00.123456+08:00",
};
const wireRecord = {
  id: "r1",
  pet: "p1",
  name: "DHPPiL booster",
  record_type: "vaccination",
  date: "2026-06-12",
  next_due: "2027-06-12",
  clinic: "Sample clinic",
  notes: "Mild swelling",
};
const wireDocument = {
  id: "d1",
  pet: "p1",
  health_record: null,
  title: "Vet report",
  content_type: "application/pdf",
  size_bytes: 4,
  status: "pending",
  uploaded_at: null,
  created_at: "2026-10-30T10:20:00+08:00",
  download_url: null,
};
const pdf = () => new File(["%PDF"], "report.pdf", { type: "application/pdf" });
const png = () =>
  new File([new Uint8Array([137, 80, 78, 71])], "kopi.png", {
    type: "image/png",
  });

test("pet() maps a full wire row to labels plus raw values", () => {
  const mapped = pet(wirePet);
  assert.equal(mapped.id, "p1");
  assert.equal(mapped.species, "Fish");
  assert.equal(mapped.breed, "Not recorded");
  assert.equal(mapped.sex, "Unknown");
  assert.equal(mapped.weight, "14.2 kg");
  assert.equal(mapped.microchip, "");
  assert.equal(mapped.date_of_birth, "");
  assert.equal(mapped.allergies, "Chicken, Beef");
  assert.equal(mapped.diet, "Not recorded");
  assert.equal(mapped.photo_url, wirePet.photo_url);
  assert.equal(mapped.photo_version, "v1");
  assert.deepEqual(mapped.records, []);
  assert.deepEqual(mapped.values, {
    name: "Nemo",
    species: "fish",
    breed: "",
    sex: "unknown",
    date_of_birth: null,
    microchip_no: null,
    allergies: ["Chicken", "Beef"],
    diet_notes: "",
    weight_kg: 14.2,
  });
  const sparse = pet({
    id: "p2",
    name: "Kopi",
    species: "dog",
    microchip_no: "",
    weight_kg: "14.2",
    photo_version: "",
  });
  assert.equal(sparse.values.sex, "unknown");
  assert.equal(sparse.values.microchip_no, null);
  assert.equal(sparse.values.weight_kg, null);
  assert.equal(sparse.weight, "Not recorded");
  assert.equal(sparse.photo_url, null);
  assert.equal(sparse.photo_version, null);
});

test("createPet POSTs the exact body with a bearer token", async () => {
  const { calls, services } = harness(() => json(wirePet, 201));
  const input = {
    name: "Nemo",
    species: "fish",
    breed: "",
    sex: "unknown",
    date_of_birth: null,
    microchip_no: null,
    allergies: [],
    diet_notes: "",
    weight_kg: 14.2,
  };
  const created = await services.createPet(input);
  assert.equal(calls.length, 1);
  assert.equal(route(calls[0]), "POST pets/");
  assert.deepEqual(calls[0].body, input);
  assert.equal(calls[0].headers.get("Authorization"), "Bearer token");
  assert.equal(created.species, "Fish");
});

test("updatePet PATCHes only the given fields and deletePet accepts 204", async () => {
  const { calls, services } = harness((call) =>
    call.method === "DELETE"
      ? noContent()
      : json({ ...wirePet, id: "p 1", name: "Nemo II" }),
  );
  const updated = await services.updatePet("p 1", { name: "Nemo II" });
  assert.equal(route(calls[0]), "PATCH pets/p%201/");
  assert.deepEqual(calls[0].body, { name: "Nemo II" });
  assert.equal(updated.name, "Nemo II");
  assert.equal(updated.values.name, "Nemo II");
  assert.deepEqual(updated.records, []);
  assert.equal(await services.deletePet("p 1"), undefined);
  assert.equal(route(calls[1]), "DELETE pets/p%201/");
});

test("pets() fetches each pet's records; records keep raw record_type and notes", async () => {
  const { calls, services } = harness((call) => {
    const path = route(call);
    if (path === "GET pets/")
      return json(page([wirePet, { ...wirePet, id: "p2" }]));
    if (path === "GET pets/p1/records/") return json(page([wireRecord]));
    if (path === "GET pets/p2/records/") return json(page([]));
    throw new Error(`Unexpected ${path}`);
  });
  const pets = await services.pets();
  assert.deepEqual(calls.map(route).sort(), [
    "GET pets/",
    "GET pets/p1/records/",
    "GET pets/p2/records/",
  ]);
  const [record] = pets[0].records;
  assert.equal(record.title, "DHPPiL booster");
  assert.equal(record.kind, "Vaccination");
  assert.equal(record.record_type, "vaccination");
  assert.equal(record.notes, "Mild swelling");
  assert.equal(record.next_due, "2027-06-12");
  assert.deepEqual(pets[1].records, []);
  calls.length = 0;
  const records = await services.records("p1");
  assert.equal(route(calls[0]), "GET pets/p1/records/");
  assert.equal(records[0].id, "r1");
  const empty = await harness(() =>
    json(page([{ ...wireRecord, next_due: null, notes: undefined }])),
  ).services.records("p1");
  assert.equal(empty[0].next_due, "");
  assert.equal(empty[0].notes, "");
});

test("updateRecord and deleteRecord use the record URL and body", async () => {
  const { calls, services } = harness((call) =>
    call.method === "DELETE"
      ? noContent()
      : json({ ...wireRecord, notes: "Recovered" }),
  );
  const updated = await services.updateRecord("p1", "r1", {
    notes: "Recovered",
  });
  assert.equal(route(calls[0]), "PATCH pets/p1/records/r1/");
  assert.deepEqual(calls[0].body, { notes: "Recovered" });
  assert.equal(updated.notes, "Recovered");
  await services.deleteRecord("p1", "r1");
  assert.equal(route(calls[1]), "DELETE pets/p1/records/r1/");
});

test("reminder() prefers the server flags and computes them when absent", () => {
  const today = todaySG();
  const row = {
    id: "rem1",
    pet: "p1",
    health_record: "r1",
    title: "Booster",
    due_at: `${addDays(today, 30)}T09:00:00+08:00`,
    done: false,
  };
  const server = reminder({ ...row, is_overdue: true, is_due_soon: false });
  assert.equal(server.is_overdue, true);
  assert.equal(server.is_due_soon, false);
  assert.equal(server.health_record_id, "r1");
  assert.equal(server.due_date, addDays(today, 30));
  const overdue = reminder({
    ...row,
    health_record: null,
    due_at: `${addDays(today, -1)}T09:00:00+08:00`,
  });
  assert.equal(overdue.health_record_id, "");
  assert.equal(overdue.is_overdue, true);
  assert.equal(overdue.is_due_soon, false);
  const soon = reminder({ ...row, due_at: `${today}T09:00:00+08:00` });
  assert.equal(soon.is_overdue, false);
  assert.equal(soon.is_due_soon, true);
  const done = reminder({
    ...row,
    done: true,
    due_at: `${addDays(today, -1)}T09:00:00+08:00`,
  });
  assert.equal(done.is_overdue, false);
  assert.equal(done.is_due_soon, false);
});

test("updateReminder PATCHes the given fields and deleteReminder uses the reminder URL", async () => {
  const { calls, services } = harness((call) =>
    call.method === "DELETE" ? noContent() : json({}),
  );
  await services.updateReminder("rem1", {
    title: "Annual vaccination",
    due_at: "2027-11-02T09:00:00+08:00",
  });
  assert.equal(route(calls[0]), "PATCH reminders/rem1/");
  assert.deepEqual(calls[0].body, {
    title: "Annual vaccination",
    due_at: "2027-11-02T09:00:00+08:00",
  });
  await services.deleteReminder("rem1");
  assert.equal(route(calls[1]), "DELETE reminders/rem1/");
});

test("uploadDocument requests the upload, PUTs to storage without Authorization, then completes", async () => {
  const { calls, record, services } = harness((call) =>
    route(call) === "POST pets/p1/documents/"
      ? json(
          {
            document: wireDocument,
            upload_url: storage + "put?X-Amz-Signature=1",
            upload_headers: { "Content-Type": "application/pdf" },
          },
          201,
        )
      : json({ ...wireDocument, status: "ready" }),
  );
  await withStorage(
    record,
    () => new Response(null, { status: 200 }),
    () => services.uploadDocument("p1", pdf(), "Vet report", "r1"),
  );
  assert.deepEqual(calls.map(route), [
    "POST pets/p1/documents/",
    "PUT storage:put?X-Amz-Signature=1",
    "POST pets/p1/documents/d1/complete/",
  ]);
  assert.deepEqual(calls[0].body, {
    title: "Vet report",
    filename: "report.pdf",
    content_type: "application/pdf",
    size_bytes: 4,
    health_record: "r1",
  });
  assert.equal(calls[1].headers.get("Content-Type"), "application/pdf");
  assert.equal(calls[1].headers.has("Authorization"), false);
  assert.equal(calls[2].headers.get("Authorization"), "Bearer token");
  calls.length = 0;
  await withStorage(
    record,
    () => new Response(null, { status: 200 }),
    () => services.uploadDocument("p1", pdf(), "Vet report"),
  );
  assert.equal("health_record" in (calls[0].body as object), false);
});

test("uploadDocument cleans up after a failed PUT or completion and maps storage errors", async () => {
  const ticket = () =>
    json(
      {
        document: wireDocument,
        upload_url: storage + "put",
        upload_headers: { "Content-Type": "application/pdf" },
      },
      201,
    );
  const scenario = async (
    complete: () => Response,
    storageStatus: number,
  ): Promise<{ calls: Call[]; error: unknown }> => {
    const { calls, record, services } = harness((call) => {
      const path = route(call);
      if (path === "POST pets/p1/documents/") return ticket();
      if (path === "DELETE pets/p1/documents/d1/") return noContent();
      return complete();
    });
    const error = await withStorage(
      record,
      () => new Response(null, { status: storageStatus }),
      () => services.uploadDocument("p1", pdf(), "Vet report"),
    ).then(
      () => assert.fail("expected a rejection"),
      (e: unknown) => e,
    );
    return { calls, error };
  };

  const putFailed = await scenario(() => noContent(), 403);
  assert.deepEqual(putFailed.calls.map(route), [
    "POST pets/p1/documents/",
    "PUT storage:put",
    "DELETE pets/p1/documents/d1/",
  ]);
  assert.ok(
    putFailed.error instanceof ApiError &&
      putFailed.error.code === "file_transfer_failed",
  );

  const incomplete = await scenario(
    () => failure(409, "upload_incomplete"),
    200,
  );
  assert.deepEqual(incomplete.calls.map(route), [
    "POST pets/p1/documents/",
    "PUT storage:put",
    "POST pets/p1/documents/d1/complete/",
    "DELETE pets/p1/documents/d1/",
  ]);
  assert.equal(
    (incomplete.error as Error).message,
    "The upload could not be verified. Please try again.",
  );

  const unavailable = await scenario(
    () => failure(503, "storage_unavailable"),
    200,
  );
  assert.equal(
    route(unavailable.calls.at(-1)!),
    "DELETE pets/p1/documents/d1/",
  );
  assert.equal(
    (unavailable.error as Error).message,
    "File storage is unavailable right now. Please try again later.",
  );

  const { calls, record, services } = harness(() =>
    failure(503, "storage_unavailable"),
  );
  await withStorage(
    record,
    () => new Response(null, { status: 200 }),
    () =>
      assert.rejects(
        services.uploadDocument("p1", pdf(), "Vet report"),
        /^Error: File storage is unavailable right now\. Please try again later\.$/,
      ),
  );
  assert.deepEqual(calls.map(route), ["POST pets/p1/documents/"]);
});

test("uploadDocument rejects a bad type or an oversized file before any request", async () => {
  const { calls, services } = harness(() => json({}));
  await assert.rejects(
    services.uploadDocument(
      "p1",
      new File(["GIF8"], "x.gif", { type: "image/gif" }),
      "Scan",
    ),
    /PDF, JPEG or PNG file up to 10 MB/,
  );
  await assert.rejects(
    services.uploadDocument(
      "p1",
      new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.pdf", {
        type: "application/pdf",
      }),
      "Big",
    ),
    /PDF, JPEG or PNG file up to 10 MB/,
  );
  await assert.rejects(
    services.uploadDocument(
      "p1",
      new File([], "empty.pdf", { type: "application/pdf" }),
      "Empty",
    ),
    /up to 10 MB/,
  );
  assert.equal(calls.length, 0);
});

test("uploadPetPhoto requests, PUTs and completes the photo, and maps failures", async () => {
  const photoTicket = () =>
    json({
      upload_url: storage + "photo-put",
      upload_headers: { "Content-Type": "image/png" },
    });
  const { calls, record, services } = harness((call) =>
    route(call) === "POST pets/p1/photo-upload/"
      ? photoTicket()
      : json({ ...wirePet, photo_version: "v2" }),
  );
  const updated = await withStorage(
    record,
    () => new Response(null, { status: 200 }),
    () => services.uploadPetPhoto("p1", png()),
  );
  assert.deepEqual(calls.map(route), [
    "POST pets/p1/photo-upload/",
    "PUT storage:photo-put",
    "POST pets/p1/photo-upload/complete/",
  ]);
  assert.deepEqual(calls[0].body, { content_type: "image/png", size_bytes: 4 });
  assert.equal(calls[1].headers.get("Content-Type"), "image/png");
  assert.equal(calls[1].headers.has("Authorization"), false);
  assert.equal(updated.photo_version, "v2");
  assert.equal(updated.species, "Fish");

  calls.length = 0;
  await assert.rejects(
    services.uploadPetPhoto(
      "p1",
      new File(["GIF8"], "x.gif", { type: "image/gif" }),
    ),
    /^Error: Choose a JPEG or PNG photo up to 5 MB\.$/,
  );
  await assert.rejects(
    services.uploadPetPhoto(
      "p1",
      new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.png", {
        type: "image/png",
      }),
    ),
    /up to 5 MB/,
  );
  assert.equal(calls.length, 0);

  const completing = (response: () => Response) =>
    harness((call) =>
      route(call) === "POST pets/p1/photo-upload/" ? photoTicket() : response(),
    );
  for (const [response, message] of [
    [
      () => failure(409, "upload_incomplete"),
      /^Error: The photo could not be verified\. Please try again\.$/,
    ],
    [
      () => failure(503, "storage_unavailable"),
      /^Error: File storage is unavailable right now\. Please try again later\.$/,
    ],
  ] as const) {
    const h = completing(response);
    await withStorage(
      h.record,
      () => new Response(null, { status: 200 }),
      () => assert.rejects(h.services.uploadPetPhoto("p1", png()), message),
    );
    assert.equal(h.calls.length, 3);
  }
  const unavailable = harness(() => failure(503, "storage_unavailable"));
  await withStorage(
    unavailable.record,
    () => new Response(null, { status: 200 }),
    () =>
      assert.rejects(
        unavailable.services.uploadPetPhoto("p1", png()),
        /File storage is unavailable right now/,
      ),
  );
  assert.deepEqual(unavailable.calls.map(route), [
    "POST pets/p1/photo-upload/",
  ]);
});

test("removePetPhoto, updateDocument and deleteDocument use their URLs", async () => {
  const { calls, services } = harness((call) =>
    call.method === "DELETE"
      ? noContent()
      : json({
          ...wireDocument,
          status: "ready",
          title: "Renamed",
          health_record: "r1",
          download_url: storage + "get",
        }),
  );
  await services.removePetPhoto("p1");
  const doc = await services.updateDocument("p1", "d1", { title: "Renamed" });
  await services.deleteDocument("p1", "d1");
  assert.deepEqual(calls.map(route), [
    "DELETE pets/p1/photo/",
    "PATCH pets/p1/documents/d1/",
    "DELETE pets/p1/documents/d1/",
  ]);
  assert.deepEqual(calls[1].body, { title: "Renamed" });
  assert.equal(doc.title, "Renamed");
  assert.equal(doc.health_record_id, "r1");
});

test("downloadDocument retrieves a fresh URL, fetches it without Authorization and names the file", async () => {
  const ready = {
    ...wireDocument,
    status: "ready",
    title: "Vet report",
    uploaded_at: "2026-10-30T10:21:00+08:00",
    download_url: storage + "get?X-Amz-Signature=1",
  };
  const { calls, record, services } = harness(() => json(ready));
  const result = await withStorage(
    record,
    () =>
      new Response("%PDF", { headers: { "content-type": "application/pdf" } }),
    () => services.downloadDocument("p1", "d1"),
  );
  assert.deepEqual(calls.map(route), [
    "GET pets/p1/documents/d1/",
    "GET storage:get?X-Amz-Signature=1",
  ]);
  assert.equal(calls[1].headers.has("Authorization"), false);
  assert.equal(result.name, "Vet report.pdf");
  assert.equal(await result.blob.text(), "%PDF");

  const named = harness(() => json({ ...ready, title: "scan.PDF" }));
  const same = await withStorage(
    named.record,
    () => new Response("%PDF"),
    () => named.services.downloadDocument("p1", "d1"),
  );
  assert.equal(same.name, "scan.PDF");

  const missing = harness(() => json({ ...ready, download_url: null }));
  await assert.rejects(
    missing.services.downloadDocument("p1", "d1"),
    /^Error: This document is not available right now\.$/,
  );
  assert.equal(missing.calls.length, 1);
});

test("getAuthorization sends the exact header value, and null rejects without a request", async () => {
  let header: string | null = null;
  const dev = createApiClient({
    baseUrl: origin,
    getAuthorization: async () => "Dev alice",
    fetcher: async (_url, init) => {
      header = new Headers(init?.headers).get("Authorization");
      return json({});
    },
  });
  await dev.request("me/", { auth: true });
  assert.equal(header, "Dev alice");

  let requests = 0,
    unauthorized = 0;
  const signedOut = createApiClient({
    baseUrl: origin,
    getAuthorization: async () => null,
    getToken: async () => "ignored",
    onUnauthorized: () => unauthorized++,
    fetcher: async () => {
      requests++;
      return json({});
    },
  });
  await assert.rejects(
    signedOut.request("me/", { auth: true }),
    (e: unknown) =>
      e instanceof ApiError &&
      e.status === 401 &&
      e.code === "authentication_required",
  );
  assert.equal(requests, 0);
  assert.equal(unauthorized, 1);
});

test("isDevAuthAllowed requires the flag, API mode and a loopback hostname", () => {
  assert.equal(isDevAuthAllowed(true, true, "localhost"), true);
  assert.equal(isDevAuthAllowed(true, true, "127.0.0.1"), true);
  assert.equal(isDevAuthAllowed(false, true, "localhost"), false);
  assert.equal(isDevAuthAllowed(true, false, "localhost"), false);
  assert.equal(isDevAuthAllowed(true, true, "example.com"), false);
  assert.equal(isDevAuthAllowed(true, true, "localhost.example.com"), false);
  assert.equal(isDevAuthAllowed(true, true, undefined), false);
});

test("useDevAuthEnabled renders a hostname-free value on the server", async () => {
  const render = (hook: () => boolean | null) =>
    renderToStaticMarkup(createElement(() => String(hook())));
  // This process has no NEXT_PUBLIC_DEV_AUTH, like every deployed build.
  assert.equal(render(useDevAuthEnabled), "false");
  const saved = {
    flag: process.env.NEXT_PUBLIC_DEV_AUTH,
    source: process.env.NEXT_PUBLIC_DATA_SOURCE,
  };
  process.env.NEXT_PUBLIC_DEV_AUTH = "true";
  process.env.NEXT_PUBLIC_DATA_SOURCE = "api";
  try {
    // A fresh module instance reads the flags at load, as a dev build does.
    const built: typeof import("../lib/auth/dev.ts") = await import(
      new URL("../lib/auth/dev.ts?dev-build", import.meta.url).href
    );
    // Unknown until hydrated, so server and first client render agree.
    assert.equal(render(built.useDevAuthEnabled), "null");
  } finally {
    for (const [name, value] of [
      ["NEXT_PUBLIC_DEV_AUTH", saved.flag],
      ["NEXT_PUBLIC_DATA_SOURCE", saved.source],
    ] as const)
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
  }
});

test("devSignInError explains rejected and unreachable development sign-ins", () => {
  assert.match(
    devSignInError(new ApiError(401, "not_authenticated", "Sign in")),
    /DJANGO_DEBUG=True and DJANGO_DEV_AUTH=true/,
  );
  assert.equal(
    devSignInError(new ApiError(0, "network_error", "offline")),
    "Cannot reach the API at NEXT_PUBLIC_API_BASE_URL. Is Django running?",
  );
  assert.equal(devSignInError(new Error("x")), "x");
  assert.equal(
    devSignInError("boom"),
    "Development sign-in failed. Please try again.",
  );
});

test("formError labels the first field message, including nested list errors", () => {
  const invalid = (details: Record<string, unknown>) =>
    new ApiError(400, "invalid", "Some fields are invalid.", details);
  assert.equal(
    formError(
      invalid({ microchip_no: ["Enter exactly 15 digits."] }),
      "fallback",
    ),
    "Some fields are invalid. Microchip number: Enter exactly 15 digits.",
  );
  assert.equal(
    formError(
      invalid({
        allergies: {
          "3": ["Ensure this field has no more than 50 characters."],
        },
      }),
      "fallback",
    ),
    "Some fields are invalid. Allergies: Ensure this field has no more than 50 characters.",
  );
  assert.equal(
    formError(
      invalid({
        non_field_errors: ["This item changed. Refresh and try again."],
      }),
      "fallback",
    ),
    "This item changed. Refresh and try again.",
  );
  assert.equal(
    formError(
      invalid({
        health_record: ['Invalid pk "abc" - object does not exist.'],
      }),
      "fallback",
    ),
    "Some fields are invalid. Care record: This item is no longer available. Refresh and try again.",
  );
  assert.equal(
    formError(invalid({ clinic_name: ["Too long."] }), "fallback"),
    "Some fields are invalid. Clinic name: Too long.",
  );
  assert.equal(formError(invalid({}), "fallback"), "Some fields are invalid.");
  assert.equal(
    formError(new ApiError(404, "not_found", "Not here."), "fallback"),
    "Not here.",
  );
  assert.equal(formError(new Error("Plain"), "fallback"), "Plain");
  assert.equal(formError("nope", "fallback"), "fallback");
});

test("createPhotoCache keys object URLs by pet and version", async () => {
  let fetches = 0,
    created = 0;
  const revoked: string[] = [];
  const pending: ((blob: Blob) => void)[] = [];
  let deferred = false;
  const cache = createPhotoCache({
    fetchBlob: async () => {
      fetches++;
      if (deferred)
        return new Promise<Blob>((resolve) => pending.push(resolve));
      return new Blob(["img"], { type: "image/png" });
    },
    createUrl: () => `blob:test/${++created}`,
    revokeUrl: (url) => revoked.push(url),
  });

  const first = await cache.load("p1", "v1", storage + "a");
  const again = await cache.load("p1", "v1", storage + "b");
  assert.equal(fetches, 1);
  assert.equal(first, "blob:test/1");
  assert.equal(again, first);
  assert.equal(cache.peek("p1", "v1"), first);
  assert.equal(cache.peek("p1", "v2"), null);
  assert.equal(await cache.load("p1", "v1", null), first);

  const second = await cache.load("p1", "v2", storage + "c");
  assert.equal(second, "blob:test/2");
  assert.deepEqual(revoked, ["blob:test/1"]);
  assert.equal(await cache.load("p2", "v1", null), null);
  assert.equal(cache.peek("p2", "v1"), null);
  const other = await cache.load("p2", "v1", storage + "d");

  cache.clear();
  assert.deepEqual(revoked.slice(1).sort(), [second, other].sort());
  assert.equal(cache.peek("p1", "v2"), null);

  deferred = true;
  const late = cache.load("p3", "v1", storage + "e");
  cache.clear();
  pending.shift()!(new Blob(["img"], { type: "image/png" }));
  assert.equal(await late, null);
  assert.equal(revoked.at(-1), `blob:test/${created}`);
  assert.equal(cache.peek("p3", "v1"), null);

  deferred = false;
  const before = fetches;
  const notImage = createPhotoCache({
    fetchBlob: async () => {
      fetches++;
      return new Blob(["<html>"], {
        type: fetches === before + 1 ? "text/html" : "image/jpeg",
      });
    },
    createUrl: () => "blob:test/ok",
    revokeUrl: () => {},
  });
  assert.equal(await notImage.load("p1", "v1", storage + "f"), null);
  assert.equal(await notImage.load("p1", "v1", storage + "f"), "blob:test/ok");
  assert.equal(fetches, before + 2);

  const failing = createPhotoCache({
    fetchBlob: async () => {
      throw new ApiError(403, "file_transfer_failed", "Expired.");
    },
    createUrl: () => "unused",
    revokeUrl: () => {},
  });
  assert.equal(await failing.load("p1", "v1", storage + "g"), null);
  assert.equal(failing.peek("p1", "v1"), null);
});

test("photo, document and allergy checks mirror the API limits", () => {
  assert.equal(photoProblem({ type: "image/png", size: 1 }), null);
  assert.equal(
    photoProblem({ type: "image/jpeg", size: 5 * 1024 * 1024 }),
    null,
  );
  for (const file of [
    { type: "image/gif", size: 10 },
    { type: "image/png", size: 0 },
    { type: "image/png", size: 5 * 1024 * 1024 + 1 },
    { type: "application/pdf", size: 10 },
  ])
    assert.equal(photoProblem(file), "Choose a JPEG or PNG photo up to 5 MB.");
  assert.equal(
    documentProblem({ type: "application/pdf", size: 10 * 1024 * 1024 }),
    null,
  );
  for (const file of [
    { type: "image/gif", size: 10 },
    { type: "application/pdf", size: 0 },
    { type: "application/pdf", size: 10 * 1024 * 1024 + 1 },
  ])
    assert.equal(
      documentProblem(file),
      "Choose a PDF, JPEG or PNG file up to 10 MB.",
    );

  assert.deepEqual(parseAllergies(" Chicken , chicken,Beef"), {
    allergies: ["Chicken", "Beef"],
    problem: null,
  });
  assert.deepEqual(parseAllergies(" , ,"), { allergies: [], problem: null });
  const many = Array.from({ length: 21 }, (_, i) => `Item ${i}`).join(",");
  assert.equal(
    parseAllergies(many).problem,
    "List up to 20 allergies, separated by commas.",
  );
  assert.equal(
    parseAllergies(Array.from({ length: 20 }, (_, i) => `I${i}`).join(","))
      .problem,
    null,
  );
  assert.equal(
    parseAllergies(`Fish, ${"x".repeat(51)}`).problem,
    "Each allergy can be up to 50 characters. Separate allergies with commas.",
  );
  assert.equal(parseAllergies("x".repeat(50)).problem, null);
});
