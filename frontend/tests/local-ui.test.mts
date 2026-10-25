import test from "node:test";
import assert from "node:assert/strict";
import { currentLocation } from "../lib/location.ts";
import {
  localServices as service,
  seedLocalState,
} from "../lib/api/local-services.ts";

test("device location preserves coordinates and accuracy and bounds requests", async () => {
  const result = await currentLocation(
    {
      getCurrentPosition(success, _error, options) {
        assert.equal(options?.timeout, 10000);
        assert.equal(options?.enableHighAccuracy, true);
        success({
          coords: { latitude: 1.35, longitude: 103.83, accuracy: 25 },
        } as GeolocationPosition);
      },
    },
    true,
  );
  assert.equal(result.latitude, 1.35);
  assert.equal(result.longitude, 103.83);
  assert.equal(result.accuracyMetres, 25);
  assert.equal(result.source, "device");
});

test("device location reports unsupported browsers, insecure contexts and position errors", async () => {
  await assert.rejects(currentLocation(undefined, true), /does not support/);
  await assert.rejects(currentLocation(undefined, false), /HTTPS/);
  for (const [code, message] of [
    [1, /permission was denied/],
    [2, /unavailable/],
    [3, /timed out/],
  ] as const) {
    await assert.rejects(
      currentLocation(
        {
          getCurrentPosition(_success, error) {
            error!({ code } as GeolocationPositionError);
          },
        },
        true,
      ),
      message,
    );
  }
});

test("device location rejects coordinates outside map coverage and malformed coordinates", async () => {
  for (const [latitude, longitude] of [
    [51.5, -0.12],
    [NaN, 103.83],
    [1.35, Infinity],
  ]) {
    await assert.rejects(
      currentLocation(
        {
          getCurrentPosition(success) {
            success({
              coords: { latitude, longitude, accuracy: 10 },
            } as GeolocationPosition);
          },
        },
        true,
      ),
      /outside/,
    );
  }
});

test("standalone catalogue covers all merchants/categories and exposes comparison offers", async () => {
  const seeded = seedLocalState();
  assert.equal(seeded.merchants.length, 6);
  assert.equal(seeded.categories.length, 6);
  assert.equal(seeded.products.length, 144);
  for (const merchant of seeded.merchants)
    assert.equal(
      seeded.products.filter((p) => p.merchant_id === merchant.id).length,
      24,
    );
  const catalogue = await service.catalogue();
  assert.equal(catalogue.products[0].offers.length, 6);
  assert.ok(
    (await service.facilities()).every(
      (f) =>
        f.verification_status !== "verified" && f.source.includes("Fictional"),
    ),
  );
});

test("pet creation, care records and reminders work without a network", async () => {
  const pet = await service.createPet({
    name: "UI test pet",
    species: "dog",
    breed: "Mixed",
    sex: "male",
    date_of_birth: "2024-01-01",
    microchip_no: null,
    allergies: ["Chicken"],
    diet_notes: "Fish",
  });
  const record = await service.addRecord(pet.id, {
    name: "Vaccination",
    record_type: "vaccination",
    date: "2026-10-19",
    next_due: "2027-10-19",
    clinic: "Sample clinic",
  });
  assert.ok(
    (await service.pets())
      .find((p) => p.id === pet.id)
      ?.records.some((r) => r.id === record.id),
  );
  const reminder = await service.createReminder({
    pet: pet.id,
    title: "Next dose",
    due_at: "2027-10-19T09:00:00+08:00",
  });
  await service.setReminder(reminder.id, true);
  assert.equal(
    (await service.reminders()).find((r) => r.id === reminder.id)?.done,
    true,
  );
});

test("local checkout validates stock, splits merchants and is idempotent", async () => {
  const products = (await service.catalogue()).products;
  const first = products[0],
    second = products.find((p) => p.merchant_id !== first.merchant_id)!;
  await service.addCart(first.id);
  await assert.rejects(service.updateCart(first.id, first.stock + 1));
  await service.addCart(second.id);
  const shipping = {
    shipping_name: "Sample Owner",
    shipping_phone: "81234567",
    shipping_address: "Sample address",
    shipping_postal_code: "123456",
  };
  const order = await service.checkout(shipping, "local-ui-checkout");
  assert.equal(order.total_cents, first.price_cents + second.price_cents);
  assert.equal(Object.keys(order.statuses).length, 2);
  assert.equal((await service.cart([], [])).length, 0);
  assert.equal(
    (await service.checkout(shipping, "local-ui-checkout")).id,
    order.id,
  );
  assert.equal((await service.order(order.id)).status, "Paid");
  await service.updateMerchantOrder(order.id, "shipped");
  assert.equal((await service.merchantOrders())[0].statuses.m0, "Shipped");
  assert.equal(
    (await service.product(first.id, [], [])).stock,
    first.stock - 1,
  );
  await assert.rejects(service.checkout(shipping, "empty-cart"));
});
