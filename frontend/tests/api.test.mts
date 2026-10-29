import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ApiError,
  createApiClient,
  transferPrivateFile,
} from "../lib/api/client.ts";
import { createServices } from "../lib/api/services.ts";
import { facility, order, product } from "../lib/api/adapters.ts";
import { nextPath, safeExternalUrl } from "../lib/format.ts";
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
const origin = "https://api.example.test/api/v1/";
test("animal approvals tolerate older APIs and reject malformed values", () => {
  assert.equal(
    facility({ id: "old", facility_type: "pet_shop" }).approved_animals,
    null,
  );
  assert.deepEqual(
    facility({
      id: "new",
      facility_type: "pet_shop",
      approved_animals: ["cat", "bird"],
    }).approved_animals,
    ["cat", "bird"],
  );
  for (const animals of [["dragon"], ["cat", "cat"], "cat", [["cat"]], []])
    assert.throws(
      () => facility({ id: "invalid", approved_animals: animals }),
      /invalid animal approvals/,
    );
});
const merchant = { id: "m1", name: "Shop A", slug: "shop-a" };
const result = {
  status: "paid",
  id: "o1",
  created_at: "2026-10-19T10:00:00+08:00",
  total_cents: 4242,
  shipping_name: "Test",
  shipping_address: "Test Street",
  shipping_postal_code: "123456",
  merchant_orders: [
    {
      merchant,
      status: "processing",
      items: [
        {
          product: "p1",
          product_name: "Original name",
          quantity: 1,
          unit_price_cents: 1000,
        },
      ],
    },
  ],
};
test("public requests preserve headers, never send credentials, disable caching and reject redirects", async () => {
  let captured: RequestInit | undefined;
  const client = createApiClient({
    baseUrl: origin,
    fetcher: async (_url, init) => {
      captured = init;
      return json({ ok: true });
    },
  });
  await client.request("products/", {
    headers: new Headers({ "X-Trace": "test" }),
  });
  assert.equal(new Headers(captured?.headers).get("X-Trace"), "test");
  assert.equal(new Headers(captured?.headers).has("Authorization"), false);
  assert.equal(captured?.cache, "no-store");
  assert.equal(captured?.credentials, "omit");
  assert.equal(captured?.redirect, "error");
});
test("facility listings come from the public paginated API and map backend fields", async () => {
  const client = createApiClient({
    baseUrl: origin,
    fetcher: async (url, init) => {
      assert.equal(String(url), origin + "facilities/");
      assert.equal(new Headers(init?.headers).has("Authorization"), false);
      return json({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: "facility-1",
            facility_type: "vet",
            name: "Bishan Veterinary Centre",
            address: "1 Bishan Street",
            postal_code: "570001",
            latitude: "1.35",
            longitude: "103.84",
            licence_no: "V001",
            phone: "61234567",
            website: "https://example.test",
            source: "AVS",
            source_url: "https://example.test/registry",
            last_checked_at: "2026-10-28T00:00:00Z",
            verification_status: "verified",
          },
        ],
      });
    },
  });
  const [facility] = await createServices(client).facilities();
  assert.equal(facility.id, "facility-1");
  assert.equal(facility.type, "Veterinary centre");
  assert.equal(facility.latitude, 1.35);
  assert.equal(facility.verification_status, "verified");
});
test("facility filters are sent with each paginated request", async () => {
  const urls: string[] = [];
  const client = createApiClient({
    baseUrl: origin,
    fetcher: async (url) => {
      urls.push(String(url));
      return json({
        results: [],
        next:
          urls.length === 1
            ? origin +
              "facilities/?type=vet&lat=1.35&lng=103.84&radius_km=5&page=2"
            : null,
      });
    },
  });
  await createServices(client).facilities(
    new URLSearchParams({
      type: "vet",
      lat: "1.35",
      lng: "103.84",
      radius_km: "5",
    }),
  );
  assert.equal(urls.length, 2);
  for (const url of urls) {
    const params = new URL(url).searchParams;
    assert.equal(params.get("type"), "vet");
    assert.equal(params.get("radius_km"), "5");
  }
});
test("private requests require a token and report expired sessions", async () => {
  let calls = 0;
  let expired = 0;
  const anonymous = createApiClient({
    baseUrl: origin,
    fetcher: async () => {
      calls++;
      return json({});
    },
  });
  await assert.rejects(
    anonymous.request("pets/", { auth: true }),
    (e: unknown) => e instanceof ApiError && e.status === 401,
  );
  assert.equal(calls, 0);
  const signedIn = createApiClient({
    baseUrl: origin,
    getToken: async () => "access-token",
    onUnauthorized: () => expired++,
    fetcher: async (_url, init) => {
      assert.equal(
        new Headers(init?.headers).get("Authorization"),
        "Bearer access-token",
      );
      return json({ error: { code: "token_expired" } }, 401);
    },
  });
  await assert.rejects(
    signedIn.request("pets/", { auth: true }),
    (e: unknown) => e instanceof ApiError && e.status === 401,
  );
  assert.equal(expired, 1);
});
test("all list pages are collected without leaking a token outside the API origin or prefix", async () => {
  let calls = 0;
  const pages = [
    { results: [{ id: 1 }], next: origin + "products/?page=2" },
    { results: [{ id: 2 }], next: null },
  ];
  const client = createApiClient({
    baseUrl: origin,
    fetcher: async () => json(pages[calls++]),
  });
  assert.deepEqual(await client.list("products/"), [{ id: 1 }, { id: 2 }]);
  for (const next of [
    "https://other.example.test/steal",
    "https://api.example.test/outside/",
  ]) {
    let requests = 0;
    const unsafe = createApiClient({
      baseUrl: origin,
      getToken: async () => "token",
      fetcher: async () => {
        requests++;
        return json({ results: [], next });
      },
    });
    await assert.rejects(unsafe.list("pets/", { auth: true }), /invalid link/);
    assert.equal(requests, 1);
  }
});
test("missing configuration, malformed lists and cyclic pagination fail explicitly", async () => {
  await assert.rejects(
    createApiClient({}).request("products/"),
    (e: unknown) => e instanceof ApiError && e.code === "not_configured",
  );
  await assert.rejects(
    createApiClient({
      baseUrl: origin,
      fetcher: async () => json({ items: [] }),
    }).list("products/"),
    /unexpected result list/,
  );
  await assert.rejects(
    createApiClient({
      baseUrl: origin,
      fetcher: async () => json({ results: [], next: "products/" }),
    }).list("products/"),
    /invalid result list/,
  );
});
test("HTTP permission and not-found errors remain distinguishable and server internals are hidden", async () => {
  for (const status of [403, 404, 500]) {
    const client = createApiClient({
      baseUrl: origin,
      fetcher: async () =>
        json(
          { error: { code: "test", message: "internal stack trace" } },
          status,
        ),
    });
    await assert.rejects(
      client.request("pets/"),
      (e: unknown) =>
        e instanceof ApiError &&
        e.status === status &&
        !e.message.includes("stack trace"),
    );
  }
});
test("checkout sends delivery details and idempotency key; prices, merchant split and success come only from the server", async () => {
  let body: unknown;
  let captured: RequestInit | undefined;
  const client = createApiClient({
    baseUrl: origin,
    getToken: async () => "token",
    fetcher: async (url, init) => {
      assert.equal(String(url), origin + "checkout/");
      captured = init;
      body = JSON.parse(String(init?.body));
      return json(result);
    },
  });
  const shipping = {
    shipping_name: "Test",
    shipping_phone: "81234567",
    shipping_address: "Test Street",
    shipping_postal_code: "123456",
  };
  const saved = await createServices(client).checkout(
    shipping,
    "transaction-key",
  );
  assert.deepEqual(body, shipping);
  assert.equal(
    new Headers(captured?.headers).get("Idempotency-Key"),
    "transaction-key",
  );
  assert.equal(saved.total_cents, 4242);
  assert.equal(saved.items[0].price_cents, 1000);
  assert.equal(saved.items[0].product_name, "Original name");
  assert.deepEqual(saved.statuses, { m1: "Processing" });
});
test("cart requests send identifiers and quantities, never client-calculated prices or merchant ownership", async () => {
  const calls: { url: string; body: unknown }[] = [];
  const client = createApiClient({
    baseUrl: origin,
    getToken: async () => "token",
    fetcher: async (url, init) => {
      calls.push({ url: String(url), body: JSON.parse(String(init?.body)) });
      return new Response(null, { status: 204 });
    },
  });
  const services = createServices(client);
  await services.addCart("p1");
  await services.updateCart("p1", 2);
  await services.updateProduct("p1", 1200, 4);
  assert.deepEqual(
    calls.map((c) => c.body),
    [
      { product: "p1", quantity: 1 },
      { quantity: 2 },
      { price_cents: 1200, stock: 4 },
    ],
  );
  assert.equal(calls[2].url, origin + "merchant/products/p1/");
});
test("invalid server money is rejected and order history uses the server snapshot", () => {
  assert.throws(
    () => product({ id: 1, price_cents: 1.5, stock: 3 }),
    /invalid amount/,
  );
  assert.throws(
    () => product({ id: 1, price_cents: -1, stock: 3 }),
    /invalid amount/,
  );
  assert.equal(order(result).items[0].product_name, "Original name");
});
test("return paths and external links reject executable URLs, network-path redirects and control characters", () => {
  for (const path of [
    "https://evil.test/",
    "//evil.test/",
    "/" + String.fromCharCode(92) + "evil.test",
    "/x" + String.fromCharCode(10),
    "/auth/callback/",
    "/login/",
  ])
    assert.equal(nextPath(path), "/pets/");
  assert.equal(nextPath("/shop/product/?id=p1"), "/shop/product/?id=p1");
  assert.equal(safeExternalUrl("javascript:alert(1)"), null);
  assert.equal(
    safeExternalUrl("https://example.test/"),
    "https://example.test/",
  );
});
test("signed storage requests omit application authorization and referrers", async () => {
  const original = globalThis.fetch;
  let captured: RequestInit | undefined;
  globalThis.fetch = async (_url, init) => {
    captured = init;
    return new Response("file");
  };
  try {
    await transferPrivateFile(
      "https://storage.example.test/private?signature=test",
      { headers: { Authorization: "must-not-leak" } },
    );
    assert.equal(new Headers(captured?.headers).has("Authorization"), false);
    assert.equal(captured?.referrerPolicy, "no-referrer");
    assert.equal(captured?.credentials, "omit");
    assert.equal(captured?.cache, "no-store");
  } finally {
    globalThis.fetch = original;
  }
});

test("merchant sub-orders stay separate when two merchants share a display name", () => {
  const duplicate = {
    ...result,
    merchant_orders: [
      ...result.merchant_orders,
      {
        merchant: { id: "m2", name: "Shop A", slug: "shop-b" },
        status: "shipped",
        items: [
          {
            product: "p2",
            product_name: "Other product",
            quantity: 1,
            unit_price_cents: 2000,
          },
        ],
      },
    ],
  };
  const saved = order(duplicate);
  assert.equal(saved.status, "Paid");
  assert.deepEqual(saved.statuses, { m1: "Processing", m2: "Shipped" });
  assert.equal(saved.items[1].merchant_id, "m2");
});

test("live location search encodes the query, normalizes results and never sends account tokens", async () => {
  const { createLocationService } =
    await import("../lib/api/location-services.ts");
  const controller = new AbortController();
  const search = createLocationService(
    createApiClient({
      baseUrl: origin,
      getToken: async () => "private-account-token",
      fetcher: async (url, init) => {
        const parsed = new URL(String(url));
        assert.equal(parsed.pathname, "/api/v1/locations/search/");
        assert.equal(parsed.searchParams.get("q"), "Bishan & Ang Mo Kio");
        assert.equal(new Headers(init?.headers).has("Authorization"), false);
        assert.equal(init?.credentials, "omit");
        assert.equal(init?.cache, "no-store");
        assert.ok(init?.signal);
        return json({
          results: [
            {
              label: "BISHAN",
              postal_code: "570001",
              latitude: 1.35,
              longitude: 103.83,
            },
          ],
        });
      },
    }),
  );
  assert.deepEqual(await search("  Bishan & Ang Mo Kio  ", controller.signal), [
    {
      label: "BISHAN",
      postal_code: "570001",
      latitude: 1.35,
      longitude: 103.83,
      source: "search",
    },
  ]);
});

test("location search distinguishes no matches, invalid results and unavailable services", async () => {
  const { createLocationService } =
    await import("../lib/api/location-services.ts");
  const searchFor = (body: unknown, status = 200) =>
    createLocationService(
      createApiClient({
        baseUrl: origin,
        fetcher: async () => json(body, status),
      }),
    );
  assert.deepEqual(await searchFor({ results: [] })("nothing"), []);
  for (const body of [
    {},
    { results: null },
    {
      results: [{ label: "bad", postal_code: null, latitude: 0, longitude: 0 }],
    },
    {
      results: [
        {
          label: "bad",
          latitude: "1.35",
          longitude: 103.83,
          postal_code: null,
        },
      ],
    },
  ]) {
    await assert.rejects(
      searchFor(body)("Bishan"),
      (e: unknown) => e instanceof ApiError && e.code === "invalid_response",
    );
  }
  await assert.rejects(
    searchFor(
      {
        error: {
          code: "location_search_unavailable",
          message: "private upstream details",
        },
      },
      503,
    )("Bishan"),
    (e: unknown) =>
      e instanceof ApiError &&
      e.status === 503 &&
      !e.message.includes("private"),
  );
  await assert.rejects(
    createLocationService(createApiClient({}))("Bishan"),
    (e: unknown) => e instanceof ApiError && e.code === "not_configured",
  );
});

test("location search honours cancellation instead of showing stale results", async () => {
  const { createLocationService } =
    await import("../lib/api/location-services.ts");
  const controller = new AbortController();
  const search = createLocationService(
    createApiClient({
      baseUrl: origin,
      fetcher: async (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("cancelled", "AbortError")),
            { once: true },
          );
        }),
    }),
  );
  const pending = search("Bishan", controller.signal);
  controller.abort();
  await assert.rejects(
    pending,
    (e: unknown) => e instanceof DOMException && e.name === "AbortError",
  );
});
