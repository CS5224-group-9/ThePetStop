// TEST ONLY: an in-process API/OIDC contract fixture. Never part of the app bundle.
import http from "node:http";
import { createHash, randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";
export function createContractServer() {
  const issuer = "http://127.0.0.1:4174/issuer",
    web = "http://127.0.0.1:4173";
  const codes = new Map(),
    tokens = new Map(),
    refreshes = new Map();
  let role = "owner";
  const requests = [];
  const m1 = { id: "m1", slug: "shop-a", name: "Contract Shop A" },
    m2 = { id: "m2", slug: "shop-b", name: "Contract Shop B" };
  const c = { id: "c1", slug: "food", name: "Food" };
  const products = [
    {
      id: "p1",
      name: "Contract Salmon Food",
      category: c,
      merchant: m1,
      description: "Contract-test product",
      price_cents: 1200,
      stock: 20,
      species: "dog",
      size: "2 kg",
      image_url: null,
    },
    {
      id: "p2",
      name: "Contract Salmon Food",
      category: c,
      merchant: m2,
      description: "Contract-test offer",
      price_cents: 1500,
      stock: 20,
      species: "dog",
      size: "2 kg",
      image_url: null,
    },
  ];
  const pet = {
    id: "pet-1",
    name: "Contract Pet",
    species: "dog",
    breed: "Mixed breed",
    sex: "male",
    date_of_birth: "2023-01-01",
    microchip_no: "702000000000001",
    allergies: [],
    diet_notes: "",
  };
  const records = new Map([["pet-1", []]]),
    pets = [pet],
    reminders = [],
    orders = [],
    cart = [],
    docs = [],
    files = new Map();
  const json = (res, body, status = 200) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };
  const page = (results) => ({
    count: results.length,
    next: null,
    previous: null,
    results,
  });
  const error = (res, status, message) =>
    json(
      res,
      { error: { code: `error_${status}`, message, details: {} } },
      status,
    );
  const server = http.createServer(async (req, res) => {
    res.setHeader("Access-Control-Allow-Origin", web);
    res.setHeader(
      "Access-Control-Allow-Methods",
      "GET,POST,PATCH,DELETE,PUT,OPTIONS",
    );
    res.setHeader(
      "Access-Control-Allow-Headers",
      "Authorization,Content-Type,Idempotency-Key",
    );
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }
    const url = new URL(req.url, "http://127.0.0.1:4174");
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const raw = Buffer.concat(chunks);
    const body =
      raw.length && req.headers["content-type"]?.includes("application/json")
        ? JSON.parse(raw.toString())
        : {};
    requests.push({
      method: req.method,
      path: url.pathname,
      authenticated: Boolean(req.headers.authorization),
    });
    if (url.pathname === "/__test__/merchant") {
      role = "merchant";
      return json(res, { ok: true });
    }
    if (url.pathname === "/__test__/requests") return json(res, requests);
    if (url.pathname === "/oauth2/authorize") {
      const redirect = url.searchParams.get("redirect_uri");
      if (redirect !== web + "/auth/callback/")
        return error(res, 400, "Invalid redirect");
      const code = randomUUID();
      codes.set(code, {
        challenge: url.searchParams.get("code_challenge"),
        nonce: url.searchParams.get("nonce"),
        role,
      });
      const target = new URL(redirect);
      target.searchParams.set("code", code);
      target.searchParams.set("state", url.searchParams.get("state"));
      res.writeHead(302, { Location: target.href });
      res.end();
      return;
    }
    if (url.pathname === "/oauth2/token") {
      const params = new URLSearchParams(raw.toString());
      let subject;
      if (params.get("grant_type") === "refresh_token")
        subject = refreshes.get(params.get("refresh_token"));
      else {
        const code = params.get("code"),
          entry = codes.get(code);
        codes.delete(code);
        if (
          !entry ||
          createHash("sha256")
            .update(params.get("code_verifier") || "")
            .digest("base64url") !== entry.challenge
        )
          return error(res, 400, "PKCE verification failed");
        subject = entry;
      }
      if (!subject) return error(res, 400, "Invalid grant");
      const token = randomUUID(),
        refresh = randomUUID();
      tokens.set(token, subject);
      refreshes.set(refresh, subject);
      const now = Math.floor(Date.now() / 1000);
      const payload = {
        iss: issuer,
        sub: subject.role === "merchant" ? "merchant-1" : "owner-1",
        aud: "contract-client",
        exp: now + 3600,
        iat: now,
        auth_time: now,
        email: "contract@example.test",
        ...(subject.nonce ? { nonce: subject.nonce } : {}),
      };
      const jwt = [
        Buffer.from(JSON.stringify({ alg: "RS256", kid: "test" })).toString(
          "base64url",
        ),
        Buffer.from(JSON.stringify(payload)).toString("base64url"),
        "dGVzdC1vbmx5",
      ].join(".");
      return json(res, {
        access_token: token,
        refresh_token: refresh,
        id_token: jwt,
        token_type: "Bearer",
        expires_in: 3600,
        scope: "openid email profile",
      });
    }
    if (url.pathname === "/oauth2/revoke") {
      res.writeHead(200);
      res.end();
      return;
    }
    if (url.pathname === "/logout") {
      res.writeHead(302, { Location: web + "/" });
      res.end();
      return;
    }
    if (url.pathname.startsWith("/storage/")) {
      if (req.headers.authorization)
        return error(
          res,
          400,
          "Storage must not receive application authorization",
        );
      if (req.method === "PUT") {
        files.set(url.pathname, raw);
        res.writeHead(200);
        res.end();
        return;
      }
      res.writeHead(200, { "content-type": "application/pdf" });
      res.end(files.get(url.pathname) || Buffer.from("%PDF-1.4 test"));
      return;
    }
    const path = url.pathname.replace("/api/v1/", "");
    const user = tokens.get(req.headers.authorization?.replace(/^Bearer /, ""));
    const publicRoute = /^(categories|merchants|products|facilities)\//.test(
      path,
    );
    if (!publicRoute && !user) return error(res, 401, "Sign in required");
    if (path === "categories/") return json(res, page([c]));
    if (path === "merchants/") return json(res, page([m1, m2]));
    if (path === "products/") return json(res, page(products));
    if (/^products\/[^/]+\/$/.test(path)) {
      const p = products.find((p) => p.id === path.split("/")[1]);
      return p
        ? json(res, {
            ...p,
            also_sold_by: products.filter((x) => x.id !== p.id),
          })
        : error(res, 404, "Not found");
    }
    if (path === "facilities/")
      return json(
        res,
        page([
          {
            id: "f1",
            facility_type: "vet",
            name: "Contract Veterinary Centre",
            licence_no: "",
            address: "Bishan, Singapore",
            postal_code: "570001",
            latitude: "1.35",
            longitude: "103.84",
            phone: "",
            website: "",
            source: "Contract test fixture",
            source_url: "",
            last_checked_at: null,
            verification_status: "unverified",
            is_24_hours: true,
          },
        ]),
      );
    if (path === "me/")
      return json(res, {
        id: user.role === "merchant" ? "merchant-1" : "owner-1",
        display_name:
          user.role === "merchant" ? "Contract Merchant" : "Contract Owner",
        email: "contract@example.test",
        groups: user.role === "merchant" ? ["merchant"] : ["owner"],
        merchant: user.role === "merchant" ? m1 : null,
      });
    if (path === "pets/") {
      if (req.method === "POST") {
        const p = { ...body, id: "pet-" + randomUUID() };
        pets.push(p);
        records.set(p.id, []);
        return json(res, p, 201);
      }
      return json(res, page(user.role === "merchant" ? [] : pets));
    }
    if (/^pets\/[^/]+\/records\/$/.test(path)) {
      const petId = path.split("/")[1];
      if (req.method === "POST") {
        const record = { ...body, id: randomUUID() };
        records.get(petId)?.push(record);
        if (record.next_due)
          reminders.push({
            id: randomUUID(),
            pet: petId,
            title: record.name,
            due_at: record.next_due + "T09:00:00+08:00",
            done: false,
          });
        return json(res, record, 201);
      }
      return json(res, page(records.get(petId) || []));
    }
    if (path === "reminders/") {
      if (req.method === "POST") {
        const reminder = { ...body, id: randomUUID(), done: false };
        reminders.push(reminder);
        return json(res, reminder, 201);
      }
      return json(res, page(user.role === "merchant" ? [] : reminders));
    }
    if (/^reminders\/[^/]+\/$/.test(path)) {
      const rem = reminders.find((r) => r.id === path.split("/")[1]);
      if (!rem) return error(res, 404, "Not found");
      rem.done = body.done;
      return json(res, rem);
    }
    if (/^pets\/[^/]+\/documents\/$/.test(path)) {
      if (req.method === "POST") {
        const doc = {
          id: randomUUID(),
          title: body.title,
          content_type: body.content_type,
          size_bytes: body.size_bytes,
          uploaded_at: new Date().toISOString(),
          download_url: "http://127.0.0.1:4174/storage/test",
        };
        docs.push(doc);
        return json(res, { document: doc, upload_url: doc.download_url }, 201);
      }
      return json(res, page(docs));
    }
    if (path === "cart/")
      return json(res, {
        merchants: [m1, m2]
          .map((merchant) => ({
            merchant,
            items: cart.filter((i) => i.product.merchant.id === merchant.id),
          }))
          .filter((m) => m.items.length),
        total_cents: cart.reduce(
          (sum, i) => sum + i.quantity * i.product.price_cents,
          0,
        ),
      });
    if (path === "cart/items/" && req.method === "POST") {
      const p = products.find((p) => p.id === body.product);
      if (!p) return error(res, 404, "Not found");
      const item = cart.find((i) => i.product.id === p.id);
      if (item) item.quantity += body.quantity;
      else cart.push({ product: p, quantity: body.quantity });
      return json(res, {}, 201);
    }
    if (/^cart\/items\/[^/]+\/$/.test(path)) {
      const index = cart.findIndex((i) => i.product.id === path.split("/")[2]);
      if (index < 0) return error(res, 404, "Not found");
      if (req.method === "DELETE") cart.splice(index, 1);
      else cart[index].quantity = body.quantity;
      res.writeHead(204);
      res.end();
      return;
    }
    if (path === "checkout/" && req.method === "POST") {
      if (!cart.length) return error(res, 400, "Basket empty");
      const order = {
        ...body,
        status: "paid",
        id: "order-" + randomUUID(),
        created_at: new Date().toISOString(),
        total_cents: cart.reduce(
          (sum, i) => sum + i.quantity * i.product.price_cents,
          0,
        ),
        merchant_orders: [m1, m2]
          .map((m) => ({
            id: randomUUID(),
            merchant: m,
            status: "processing",
            items: cart
              .filter((i) => i.product.merchant.id === m.id)
              .map((i) => ({
                product: i.product.id,
                product_name: i.product.name,
                quantity: i.quantity,
                unit_price_cents: i.product.price_cents,
              })),
          }))
          .filter((m) => m.items.length),
      };
      orders.push(order);
      cart.splice(0);
      return json(res, order, 201);
    }
    if (path === "orders/") return json(res, page(orders));
    if (/^orders\/[^/]+\/$/.test(path)) {
      const order = orders.find((o) => o.id === path.split("/")[1]);
      return order ? json(res, order) : error(res, 404, "Not found");
    }
    if (path.startsWith("merchant/") && user.role !== "merchant")
      return error(res, 403, "Merchant access required");
    if (path === "merchant/products/")
      return json(res, page(products.filter((p) => p.merchant.id === m1.id)));
    if (/^merchant\/products\/[^/]+\/$/.test(path)) {
      const p = products.find(
        (p) => p.id === path.split("/")[2] && p.merchant.id === m1.id,
      );
      if (!p) return error(res, 404, "Not found");
      Object.assign(p, body);
      return json(res, p);
    }
    if (path === "merchant/orders/")
      return json(
        res,
        page(
          orders.flatMap((o) =>
            o.merchant_orders
              .filter((m) => m.merchant.id === m1.id)
              .map((m) => ({
                ...m,
                created_at: o.created_at,
                subtotal_cents: m.items.reduce(
                  (sum, i) => sum + i.quantity * i.unit_price_cents,
                  0,
                ),
              })),
          ),
        ),
      );
    if (/^merchant\/orders\/[^/]+\/$/.test(path)) {
      const m = orders
        .flatMap((o) => o.merchant_orders)
        .find((m) => m.id === path.split("/")[2]);
      if (!m) return error(res, 404, "Not found");
      m.status = body.status;
      return json(res, m);
    }
    error(res, 404, "Not found");
  });
  return { server, requests };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const { server } = createContractServer();
  server.listen(4174, "127.0.0.1", () =>
    console.log("Test-only contract fixture listening on 4174"),
  );
}
