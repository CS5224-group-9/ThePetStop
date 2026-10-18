import { ApiError } from "./client.ts";
import type {
  CartItem,
  Category,
  Facility,
  HealthRecord,
  Merchant,
  Order,
  Pet,
  PetDocument,
  Product,
  Profile,
  Reminder,
} from "./types.ts";
export type Row = Record<string, unknown>;
export function object(value: unknown): Row {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(
      502,
      "invalid_response",
      "The service returned an unexpected record.",
    );
  return value as Row;
}
const text = (value: unknown, fallback = "") =>
  typeof value === "string" ? value : fallback;
export function identifier(value: unknown): string {
  if (
    (typeof value !== "string" || !value) &&
    (typeof value !== "number" || !Number.isSafeInteger(value))
  )
    throw new ApiError(
      502,
      "invalid_response",
      "A service record is missing its identifier.",
    );
  return String(value);
}
const optionalId = (value: unknown) =>
  value === null || value === undefined
    ? ""
    : typeof value === "object"
      ? identifier(object(value).id)
      : identifier(value);
function amount(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new ApiError(
      502,
      "invalid_response",
      "The service returned an invalid amount or quantity.",
    );
  return value;
}
const rows = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const label = (value: string) =>
  value ? value[0].toUpperCase() + value.slice(1).replaceAll("_", " ") : "";
export function merchant(value: unknown): Merchant {
  const v = object(value);
  return { id: identifier(v.id), name: text(v.name), slug: text(v.slug) };
}
export function category(value: unknown): Category {
  const v = object(value);
  return { id: identifier(v.id), name: text(v.name), slug: text(v.slug) };
}
export function profile(value: unknown): Profile {
  const v = object(value);
  if (!Array.isArray(v.groups))
    throw new ApiError(
      502,
      "invalid_profile",
      "Your account profile could not be verified.",
    );
  return {
    id: identifier(v.id),
    display_name: text(v.display_name, text(v.email, "PetStop member")),
    email: text(v.email),
    groups: v.groups.filter((x): x is string => typeof x === "string"),
    merchant: v.merchant ? merchant(v.merchant) : null,
  };
}
export function healthRecord(value: unknown): HealthRecord {
  const v = object(value);
  return {
    id: identifier(v.id),
    title: text(v.name),
    kind: label(text(v.record_type)),
    date: text(v.date),
    next_due: text(v.next_due),
    clinic: text(v.clinic),
  };
}
export function pet(value: unknown, records: HealthRecord[] = []): Pet {
  const v = object(value);
  return {
    id: identifier(v.id),
    name: text(v.name),
    species: label(text(v.species)),
    breed: text(v.breed, "Not recorded"),
    sex: label(text(v.sex, "unknown")),
    date_of_birth: text(v.date_of_birth),
    microchip: text(v.microchip_no),
    photo_url: typeof v.photo_url === "string" ? v.photo_url : null,
    weight:
      typeof v.weight_kg === "number" ? `${v.weight_kg} kg` : "Not recorded",
    allergies:
      rows(v.allergies)
        .filter((x) => typeof x === "string")
        .join(", ") || "None recorded",
    diet: text(v.diet_notes, "Not recorded"),
    records,
  };
}
export function reminder(value: unknown): Reminder {
  const v = object(value);
  return {
    id: identifier(v.id),
    pet_id: optionalId(v.pet),
    title: text(v.title),
    due_date: text(v.due_at).slice(0, 10),
    done: v.done === true,
  };
}
export function product(
  value: unknown,
  categories: Category[] = [],
  merchants: Merchant[] = [],
): Product {
  const v = object(value);
  const categoryId = optionalId(v.category);
  const merchantId = optionalId(v.merchant);
  const c =
    typeof v.category === "object" && v.category
      ? text(object(v.category).name)
      : categories.find((c) => c.id === categoryId)?.name || "Uncategorised";
  const m =
    typeof v.merchant === "object" && v.merchant
      ? text(object(v.merchant).name)
      : merchants.find((m) => m.id === merchantId)?.name || "Merchant";
  const result: Product = {
    id: identifier(v.id),
    name: text(v.name),
    category: c,
    category_id: categoryId,
    species: label(text(v.species, "all pets")),
    size: text(v.size),
    description: text(v.description),
    color: "sage",
    price_cents: amount(v.price_cents),
    stock: amount(v.stock),
    merchant: m,
    merchant_id: merchantId,
    image_url: typeof v.image_url === "string" ? v.image_url : null,
    offers: [],
  };
  result.offers = [
    {
      id: result.id,
      merchant: m,
      merchant_id: merchantId,
      price_cents: result.price_cents,
      stock: result.stock,
    },
    ...rows(v.also_sold_by).map((o) => {
      const offer = product(o, categories, merchants);
      return {
        id: offer.id,
        merchant: offer.merchant,
        merchant_id: offer.merchant_id,
        price_cents: offer.price_cents,
        stock: offer.stock,
      };
    }),
  ];
  result.offers = Array.from(
    new Map(result.offers.map((o) => [o.id, o])).values(),
  ).sort((a, b) => a.price_cents - b.price_cents);
  return result;
}
export function cart(
  value: unknown,
  categories: Category[] = [],
  merchants: Merchant[] = [],
): CartItem[] {
  const v = object(value);
  if (!Array.isArray(v.merchants))
    throw new ApiError(
      502,
      "invalid_response",
      "The service returned an unexpected basket.",
    );
  return v.merchants.flatMap((group) => {
    const g = object(group);
    const groupMerchant = merchant(g.merchant);
    return rows(g.items).map((item) => {
      const i = object(item);
      const p = product(
        { ...object(i.product), merchant: groupMerchant },
        categories,
        merchants,
      );
      return {
        product_id: p.id,
        product_name: p.name,
        merchant: p.merchant,
        merchant_id: p.merchant_id,
        quantity: amount(i.quantity),
        price_cents: p.price_cents,
        stock: p.stock,
        product: p,
      };
    });
  });
}
export function order(value: unknown): Order {
  const v = object(value);
  const groups = rows(v.merchant_orders);
  if (!Array.isArray(v.merchant_orders))
    throw new ApiError(
      502,
      "invalid_response",
      "The service returned an unexpected order.",
    );
  return {
    status: label(text(v.status)),
    merchant_names: Object.fromEntries(
      groups.map((raw) => {
        const m = merchant(object(raw).merchant);
        return [m.id, m.name];
      }),
    ),
    id: identifier(v.id),
    placed_at: text(v.created_at),
    total_cents: amount(v.total_cents),
    shipping: [v.shipping_name, v.shipping_address, v.shipping_postal_code]
      .filter(Boolean)
      .join(", "),
    statuses: Object.fromEntries(
      groups.map((raw) => {
        const g = object(raw);
        return [merchant(g.merchant).id, label(text(g.status))];
      }),
    ),
    items: groups.flatMap((raw) => {
      const g = object(raw),
        m = merchant(g.merchant);
      return rows(g.items).map((rawItem) => {
        const i = object(rawItem);
        return {
          product_id: optionalId(i.product),
          product_name: text(i.product_name),
          merchant: m.name,
          merchant_id: m.id,
          quantity: amount(i.quantity),
          price_cents: amount(i.unit_price_cents),
          stock: 0,
        };
      });
    }),
  };
}
export function merchantOrder(value: unknown): Order {
  const v = object(value),
    m = merchant(v.merchant);
  return order({
    ...v,
    created_at: v.created_at,
    total_cents: v.subtotal_cents,
    merchant_orders: [{ ...v, merchant: m }],
  });
}
export function facility(value: unknown): Facility {
  const v = object(value);
  const coordinate = (x: unknown, min: number, max: number) => {
    const n = Number(x);
    return x !== null &&
      x !== undefined &&
      x !== "" &&
      Number.isFinite(n) &&
      n >= min &&
      n <= max
      ? n
      : null;
  };
  return {
    id: identifier(v.id),
    name: text(v.name),
    type: v.facility_type === "vet" ? "Veterinary centre" : "Pet shop",
    address: text(v.address),
    area: text(v.postal_code),
    emergency: v.is_24_hours === true,
    latitude: coordinate(v.latitude, -90, 90),
    longitude: coordinate(v.longitude, -180, 180),
    phone: text(v.phone),
    website: text(v.website),
    licence_no: text(v.licence_no),
    source: text(v.source),
    source_url: text(v.source_url),
    last_checked_at:
      typeof v.last_checked_at === "string" ? v.last_checked_at : null,
    verification_status: text(v.verification_status, "unverified"),
  };
}
export function document(value: unknown): PetDocument {
  const v = object(value);
  return {
    id: identifier(v.id),
    title: text(v.title),
    content_type: text(v.content_type),
    size_bytes: amount(v.size_bytes),
    uploaded_at: text(v.uploaded_at),
    download_url: text(v.download_url),
  };
}
