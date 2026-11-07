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
  const storage = "http://127.0.0.1:4174/storage/";
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
    weight_kg: null,
    photo_version: null,
  };
  const records = new Map([["pet-1", []]]),
    pets = [pet],
    reminders = [],
    orders = [],
    cart = [],
    docs = new Map([["pet-1", []]]),
    pendingPhotos = new Map(),
    files = new Map();
  const json = (res, body, status = 200) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };
  const empty = (res) => {
    res.writeHead(204);
    res.end();
  };
  const page = (results) => ({
    count: results.length,
    next: null,
    previous: null,
    results,
  });
  const error = (res, status, message, code = `error_${status}`) =>
    json(res, { error: { code, message, details: {} } }, status);
  // Asia/Singapore calendar dates, like the backend's reminder flags.
  const todaySG = () =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Singapore",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  const plusDays = (date, days) => {
    const [y, m, d] = date.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
  };
  const reminderRow = (r) => {
    const due = String(r.due_at).slice(0, 10),
      today = todaySG();
    return {
      ...r,
      is_overdue: !r.done && due < today,
      is_due_soon: !r.done && due >= today && due <= plusDays(today, 7),
    };
  };
  const petRow = (p) => ({
    ...p,
    // A fresh "presigned" URL on every response; photo_version is the cache key.
    photo_url: p.photo_version
      ? `${storage}photos/${p.id}/${p.photo_version}?sig=${randomUUID()}`
      : null,
  });
  const docRow = (d) => ({
    ...d,
    download_url:
      d.status === "ready" ? `${storage}documents/${d.pet}/${d.id}` : null,
  });
  const pick = (body, fields) =>
    Object.fromEntries(
      Object.entries(body).filter(([key]) => fields.includes(key)),
    );
  const petFields = [
    "name",
    "species",
    "breed",
    "sex",
    "date_of_birth",
    "microchip_no",
    "allergies",
    "diet_notes",
    "weight_kg",
  ];
  const recordFields = [
    "name",
    "record_type",
    "date",
    "next_due",
    "clinic",
    "notes",
  ];
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
        files.set(url.pathname, {
          raw,
          type: req.headers["content-type"] || "application/octet-stream",
        });
        res.writeHead(200);
        res.end();
        return;
      }
      const file = files.get(url.pathname);
      res.writeHead(200, {
        "content-type": file?.type || "application/pdf",
        "cache-control": "private, no-store",
      });
      res.end(file?.raw || Buffer.from("%PDF-1.4 test"));
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
    const ownPet = (petId) =>
      user.role === "merchant" ? undefined : pets.find((p) => p.id === petId);
    if (path === "pets/") {
      if (req.method === "POST") {
        const p = {
          breed: "",
          sex: "unknown",
          date_of_birth: null,
          microchip_no: null,
          allergies: [],
          diet_notes: "",
          weight_kg: null,
          ...pick(body, petFields),
          id: "pet-" + randomUUID(),
          photo_version: null,
        };
        pets.push(p);
        records.set(p.id, []);
        docs.set(p.id, []);
        return json(res, petRow(p), 201);
      }
      return json(res, page(user.role === "merchant" ? [] : pets.map(petRow)));
    }
    if (/^pets\/[^/]+\//.test(path)) {
      const [, petId, section, itemId, action] = path.split("/");
      const p = ownPet(petId);
      if (!p) return error(res, 404, "Not found", "not_found");
      if (section === "" && path === `pets/${petId}/`) {
        if (req.method === "PATCH") Object.assign(p, pick(body, petFields));
        if (req.method === "DELETE") {
          pets.splice(pets.indexOf(p), 1);
          records.delete(petId);
          docs.delete(petId);
          pendingPhotos.delete(petId);
          for (let i = reminders.length - 1; i >= 0; i--)
            if (reminders[i].pet === petId) reminders.splice(i, 1);
          return empty(res);
        }
        return json(res, petRow(p));
      }
      if (path === `pets/${petId}/photo-upload/` && req.method === "POST") {
        const uploadUrl = `${storage}photos/${petId}/${randomUUID()}`;
        pendingPhotos.set(petId, uploadUrl);
        return json(res, {
          upload_url: uploadUrl,
          upload_headers: { "Content-Type": body.content_type },
        });
      }
      if (
        path === `pets/${petId}/photo-upload/complete/` &&
        req.method === "POST"
      ) {
        const pending = pendingPhotos.get(petId);
        if (!pending || !files.has(new URL(pending).pathname))
          return error(
            res,
            409,
            "The file has not finished uploading. Try again.",
            "upload_incomplete",
          );
        p.photo_version = pending.split("/").pop();
        pendingPhotos.delete(petId);
        return json(res, petRow(p));
      }
      if (path === `pets/${petId}/photo/` && req.method === "DELETE") {
        p.photo_version = null;
        pendingPhotos.delete(petId);
        return empty(res);
      }
      if (section === "records") {
        const list = records.get(petId);
        if (path === `pets/${petId}/records/`) {
          if (req.method === "POST") {
            const record = {
              clinic: "",
              notes: "",
              next_due: null,
              ...pick(body, recordFields),
              id: randomUUID(),
              pet: petId,
            };
            list.push(record);
            return json(res, record, 201);
          }
          return json(res, page(list));
        }
        const record = list.find((r) => r.id === itemId);
        if (!record || action !== "")
          return error(res, 404, "Not found", "not_found");
        if (req.method === "PATCH")
          Object.assign(record, pick(body, recordFields));
        if (req.method === "DELETE") {
          list.splice(list.indexOf(record), 1);
          for (const r of reminders)
            if (r.health_record === record.id) r.health_record = null;
          for (const d of docs.get(petId))
            if (d.health_record === record.id) d.health_record = null;
          return empty(res);
        }
        return json(res, record);
      }
      if (section === "documents") {
        const list = docs.get(petId);
        if (path === `pets/${petId}/documents/`) {
          if (req.method === "POST") {
            const doc = {
              id: randomUUID(),
              pet: petId,
              health_record: body.health_record ?? null,
              title: body.title,
              content_type: body.content_type,
              size_bytes: body.size_bytes,
              status: "pending",
              uploaded_at: null,
              created_at: new Date().toISOString(),
            };
            list.push(doc);
            return json(
              res,
              {
                document: docRow(doc),
                upload_url: `${storage}documents/${petId}/${doc.id}`,
                upload_headers: { "Content-Type": body.content_type },
              },
              201,
            );
          }
          return json(
            res,
            page(list.filter((d) => d.status === "ready").map(docRow)),
          );
        }
        const doc = list.find((d) => d.id === itemId);
        if (!doc) return error(res, 404, "Not found", "not_found");
        if (action === "complete" && req.method === "POST") {
          if (!files.has(`/storage/documents/${petId}/${doc.id}`))
            return error(
              res,
              409,
              "The file has not finished uploading. Try again.",
              "upload_incomplete",
            );
          if (doc.status !== "ready") {
            doc.status = "ready";
            doc.uploaded_at = new Date().toISOString();
          }
          return json(res, docRow(doc));
        }
        if (action !== "") return error(res, 404, "Not found", "not_found");
        if (req.method === "DELETE") {
          list.splice(list.indexOf(doc), 1);
          return empty(res);
        }
        if (doc.status !== "ready")
          return error(res, 404, "Not found", "not_found");
        if (req.method === "PATCH")
          Object.assign(doc, pick(body, ["title", "health_record"]));
        return json(res, docRow(doc));
      }
      return error(res, 404, "Not found", "not_found");
    }
    if (path === "reminders/") {
      if (req.method === "POST") {
        const reminder = {
          health_record: null,
          ...pick(body, ["pet", "title", "due_at", "health_record"]),
          id: randomUUID(),
          done: body.done === true,
        };
        if (!ownPet(reminder.pet))
          return error(res, 400, "Some fields are invalid.", "invalid");
        reminders.push(reminder);
        return json(res, reminderRow(reminder), 201);
      }
      return json(
        res,
        page(user.role === "merchant" ? [] : reminders.map(reminderRow)),
      );
    }
    if (/^reminders\/[^/]+\/$/.test(path)) {
      const rem = reminders.find(
        (r) => r.id === path.split("/")[1] && ownPet(r.pet),
      );
      if (!rem) return error(res, 404, "Not found", "not_found");
      if (req.method === "PATCH")
        Object.assign(
          rem,
          pick(body, ["title", "due_at", "done", "health_record"]),
        );
      if (req.method === "DELETE") {
        reminders.splice(reminders.indexOf(rem), 1);
        return empty(res);
      }
      return json(res, reminderRow(rem));
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
