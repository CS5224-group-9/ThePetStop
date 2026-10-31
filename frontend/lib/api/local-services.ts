import type { createServices } from "./services.ts";
import type {
  AppState,
  HealthRecord,
  Order,
  Pet,
  PetDocument,
  PetInput,
  Product,
  RecordInput,
  Reminder,
} from "./types.ts";
import { emptyState } from "./types.ts";
import { petView, recordView } from "./adapters.ts";
import { reminderStatus } from "../reminders.ts";
import { documentProblem, photoProblem } from "../pet-input.ts";

type Store = AppState & { checkoutKeys: Record<string, string> };
// v2: pets carry raw `values` for the edit form; v1 sample data is discarded.
const storageKey = "petstop.ui.v2";
let memory: Store | null = null;
// Documents and photos stay in memory only (lost on reload).
const files = new Map<
  string,
  { pet: string; document: PetDocument; file: File }
>();
const photos = new Map<string, { file: File; url: string; version: string }>();
const uid = () => crypto.randomUUID();
const noPhoto = { photo_url: null, photo_version: null };
function withStatus(reminder: Omit<Reminder, "is_overdue" | "is_due_soon">) {
  return {
    ...reminder,
    health_record_id: reminder.health_record_id ?? "",
    ...reminderStatus(reminder.due_date, reminder.done),
  };
}
function withPhoto(pet: Pet): Pet {
  const photo = photos.get(pet.id);
  return photo
    ? { ...pet, photo_url: photo.url, photo_version: photo.version }
    : pet;
}
function dropPhoto(petId: string) {
  const photo = photos.get(petId);
  if (photo) URL.revokeObjectURL(photo.url);
  photos.delete(petId);
}
function recordInput(record: HealthRecord): RecordInput {
  return {
    name: record.title,
    record_type: record.record_type,
    date: record.date,
    next_due: record.next_due || null,
    clinic: record.clinic,
    notes: record.notes,
  };
}
// Drops keys explicitly set to undefined, so they do not erase stored values.
function defined<T extends object>(input: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(input).filter(([, value]) => value !== undefined),
  ) as Partial<T>;
}
export function seedLocalState(): Store {
  const merchants = [
    "The Happy Tail",
    "Whisker & Co.",
    "Little Paws",
    "Paw Pantry",
    "Good Pet Supply",
    "The Pet Edit",
  ].map((name, i) => ({ id: `m${i}`, name, slug: `shop-${i}` }));
  const categories = [
    "Food",
    "Treats",
    "Health",
    "Grooming",
    "Toys",
    "Essentials",
  ].map((name, i) => ({ id: `c${i}`, name, slug: name.toLowerCase() }));
  const names = [
    [
      "Salmon & brown rice kibble",
      "Indoor cat chicken recipe",
      "Timothy hay blend",
      "Gentle digestion recipe",
    ],
    [
      "Freeze-dried salmon bites",
      "Chicken training treats",
      "Apple & herb nibble sticks",
      "Dental care chews",
    ],
    [
      "Daily omega oil",
      "Digestive care powder",
      "Skin & coat supplement",
      "Joint support bites",
    ],
    [
      "Gentle oatmeal shampoo",
      "Soft bristle brush",
      "Paw cleansing foam",
      "Everyday grooming comb",
    ],
    [
      "Natural rubber fetch ball",
      "Feather wand",
      "Willow chew tunnel",
      "Treat puzzle",
    ],
    [
      "Everyday walking harness",
      "Stainless steel bowl",
      "Soft travel carrier",
      "Washable resting mat",
    ],
  ];
  const products: Product[] = merchants.flatMap((merchant, m) =>
    categories.flatMap((category, c) =>
      names[c].map((name, n) => ({
        id: `p-${m}-${c}-${n}`,
        name,
        category: category.name,
        category_id: category.id,
        species: ["dog", "cat", "rabbit", "dog"][n],
        size:
          c === 0
            ? ["2 kg", "1.5 kg", "500 g", "2 kg"][n]
            : c === 1
              ? "80 g"
              : "Standard",
        description: `${name}, selected for everyday pet care. Compare the same item across our six fictional shops. Sample catalogue for exploring the product experience.`,
        color: ["green", "purple", "amber", "rose"][n],
        price_cents: 950 + c * 430 + n * 260 + m * 125,
        stock: 18 + m,
        merchant: merchant.name,
        merchant_id: merchant.id,
        image_url: null,
        offers: [],
      })),
    ),
  );
  const facilities = [
    [
      "f0",
      "Bishan Companion Vet",
      "Veterinary centre",
      "Bishan",
      1.35,
      103.848,
      true,
    ],
    [
      "f1",
      "Tampines Family Vet",
      "Veterinary centre",
      "Tampines",
      1.353,
      103.945,
      false,
    ],
    [
      "f2",
      "Holland Village Pet Care",
      "Veterinary centre",
      "Holland Village",
      1.312,
      103.796,
      false,
    ],
    [
      "f3",
      "Little Paws Toa Payoh",
      "Pet shop",
      "Toa Payoh",
      1.334,
      103.855,
      false,
    ],
    ["f4", "Whisker & Co. Bedok", "Pet shop", "Bedok", 1.325, 103.931, false],
    [
      "f5",
      "The Happy Tail Jurong",
      "Pet shop",
      "Jurong East",
      1.333,
      103.743,
      false,
    ],
  ].map(([id, name, type, area, latitude, longitude, emergency]) => ({
    id: String(id),
    name: String(name),
    type: String(type),
    address: `${area}, Singapore (sample location)`,
    area: String(area),
    latitude: Number(latitude),
    longitude: Number(longitude),
    emergency: Boolean(emergency),
    phone: "",
    website: "",
    licence_no: "",
    source: "Fictional listing · UI preview",
    source_url: "",
    last_checked_at: null,
    verification_status: "unverified",
  }));
  return {
    ...emptyState(),
    role: "owner",
    profile: {
      id: "local-owner",
      display_name: "Alex",
      email: "",
      groups: ["owner"],
      merchant: merchants[0],
    },
    merchants,
    categories,
    products,
    facilities,
    pets: [
      petView(
        "kopi",
        {
          name: "Kopi",
          species: "dog",
          breed: "Singapore Special",
          sex: "male",
          date_of_birth: "2022-04-12",
          microchip_no: null,
          allergies: ["Chicken"],
          diet_notes: "Salmon-based dry food",
          weight_kg: 14.2,
        },
        {
          ...noPhoto,
          records: [
            recordView("r1", {
              name: "Annual vaccination",
              record_type: "vaccination",
              date: "2026-06-12",
              next_due: "2027-06-12",
              clinic: "Sample veterinary centre",
              notes: "",
            }),
          ],
        },
      ),
      petView(
        "mochi",
        {
          name: "Mochi",
          species: "cat",
          breed: "Domestic Shorthair",
          sex: "female",
          date_of_birth: "2023-08-20",
          microchip_no: null,
          allergies: [],
          diet_notes: "Indoor cat food",
          weight_kg: null,
        },
        { ...noPhoto, records: [] },
      ),
      petView(
        "sesame",
        {
          name: "Sesame",
          species: "rabbit",
          breed: "Holland Lop",
          sex: "female",
          date_of_birth: "2024-02-15",
          microchip_no: null,
          allergies: [],
          diet_notes: "Timothy hay and leafy greens",
          weight_kg: null,
        },
        { ...noPhoto, records: [] },
      ),
    ],
    reminders: [
      withStatus({
        id: "rem1",
        pet_id: "kopi",
        title: "Monthly flea & tick care",
        due_date: "2026-10-25",
        done: false,
        health_record_id: "",
      }),
      withStatus({
        id: "rem2",
        pet_id: "mochi",
        title: "Annual health check",
        due_date: "2026-11-05",
        done: false,
        health_record_id: "",
      }),
    ],
    checkoutKeys: {},
  };
}
function read(): Store {
  if (memory) return memory;
  if (typeof window !== "undefined") {
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Store;
        if (
          Array.isArray(parsed.products) &&
          Array.isArray(parsed.pets) &&
          parsed.pets.every((p) => p?.values) &&
          Array.isArray(parsed.reminders) &&
          parsed.checkoutKeys &&
          parsed.profile?.id === "local-owner"
        )
          return (memory = parsed);
      }
    } catch {
      /* Storage may be blocked; keep the UI usable in memory. */
    }
  }
  return (memory = seedLocalState());
}
function write(change: (state: Store) => void) {
  const next = structuredClone(read());
  change(next);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      throw new Error(
        "Browser storage is unavailable or full. Allow site storage to save changes.",
      );
    }
  }
  memory = next;
}
function required<T>(value: T | undefined): T {
  if (!value) throw new Error("This item could not be found.");
  return value;
}
function offer(product: Product): Product {
  return {
    ...product,
    offers: read()
      .products.filter((p) => p.name === product.name)
      .map((p) => ({
        id: p.id,
        merchant: p.merchant,
        merchant_id: p.merchant_id,
        price_cents: p.price_cents,
        stock: p.stock,
      })),
  };
}
function quantity(value: number, stock: number) {
  if (!Number.isInteger(value) || value < 1 || value > stock)
    throw new Error(`Choose a quantity between 1 and ${stock}.`);
}
const copy = <T>(value: T): T => structuredClone(value);
export const localServices: ReturnType<typeof createServices> = {
  async catalogue() {
    const s = read();
    return copy({
      products: s.products.map(offer),
      categories: s.categories,
      merchants: s.merchants,
    });
  },
  async facilities() {
    return copy(read().facilities);
  },
  async me() {
    return copy(required(read().profile ?? undefined));
  },
  async pets() {
    return copy(read().pets).map(withPhoto);
  },
  async records(pet) {
    return copy(required(read().pets.find((p) => p.id === pet)).records);
  },
  async createPet(input) {
    if (!input.name.trim()) throw new Error("Enter your pet’s name.");
    const pet = petView(uid(), copy(input), { ...noPhoto, records: [] });
    write((s) => {
      s.pets.push(pet);
    });
    return copy(pet);
  },
  async updatePet(id, input) {
    if (input.name !== undefined && !input.name.trim())
      throw new Error("Enter your pet’s name.");
    let pet!: Pet;
    write((s) => {
      const index = s.pets.findIndex((p) => p.id === id);
      const current = required(s.pets[index]);
      const values: PetInput = { ...current.values, ...copy(defined(input)) };
      pet = petView(id, values, { ...noPhoto, records: current.records });
      s.pets[index] = pet;
    });
    return withPhoto(copy(pet));
  },
  async deletePet(id) {
    write((s) => {
      required(s.pets.find((p) => p.id === id));
      s.pets = s.pets.filter((p) => p.id !== id);
      s.reminders = s.reminders.filter((r) => r.pet_id !== id);
    });
    for (const [key, entry] of files) if (entry.pet === id) files.delete(key);
    dropPhoto(id);
  },
  async uploadPetPhoto(id, file) {
    const problem = photoProblem(file);
    if (problem) throw new Error(problem);
    const pet = required(read().pets.find((p) => p.id === id));
    dropPhoto(id);
    photos.set(id, { file, url: URL.createObjectURL(file), version: uid() });
    return withPhoto(copy(pet));
  },
  async removePetPhoto(id) {
    required(read().pets.find((p) => p.id === id));
    dropPhoto(id);
  },
  async addRecord(pet, input) {
    if (!input.name.trim()) throw new Error("Enter a record name.");
    const record = recordView(uid(), input);
    write((s) => {
      required(s.pets.find((p) => p.id === pet)).records.push(record);
    });
    return copy(record);
  },
  async updateRecord(pet, id, input) {
    if (input.name !== undefined && !input.name.trim())
      throw new Error("Enter a record name.");
    let record!: HealthRecord;
    write((s) => {
      const records = required(s.pets.find((p) => p.id === pet)).records;
      const index = records.findIndex((r) => r.id === id);
      const merged = { ...recordInput(required(records[index])), ...input };
      if (merged.next_due && merged.next_due < merged.date)
        throw new Error("Next due date cannot be before the date of care.");
      record = recordView(id, merged);
      records[index] = record;
    });
    return copy(record);
  },
  async deleteRecord(pet, id) {
    write((s) => {
      const p = required(s.pets.find((p) => p.id === pet));
      required(p.records.find((r) => r.id === id));
      p.records = p.records.filter((r) => r.id !== id);
      for (const r of s.reminders)
        if (r.health_record_id === id) r.health_record_id = "";
    });
    for (const entry of files.values())
      if (entry.document.health_record_id === id)
        entry.document.health_record_id = "";
  },
  async reminders() {
    return copy(read().reminders).map(withStatus);
  },
  async createReminder(input) {
    if (!input.title.trim()) throw new Error("Enter a reminder name.");
    const reminder = withStatus({
      id: uid(),
      pet_id: input.pet,
      title: input.title,
      due_date: input.due_at.slice(0, 10),
      done: false,
      health_record_id: input.health_record ?? "",
    });
    write((s) => {
      required(s.pets.find((p) => p.id === input.pet));
      s.reminders.push(reminder);
    });
    return copy(reminder);
  },
  async setReminder(id, done) {
    write((s) => {
      required(s.reminders.find((r) => r.id === id)).done = done;
    });
  },
  async updateReminder(id, input) {
    if (input.title !== undefined && !input.title.trim())
      throw new Error("Enter a reminder name.");
    write((s) => {
      const r = required(s.reminders.find((r) => r.id === id));
      if (input.title !== undefined) r.title = input.title;
      if (input.due_at !== undefined) r.due_date = input.due_at.slice(0, 10);
      if (input.done !== undefined) r.done = input.done;
      if (input.health_record !== undefined)
        r.health_record_id = input.health_record ?? "";
    });
  },
  async deleteReminder(id) {
    write((s) => {
      required(s.reminders.find((r) => r.id === id));
      s.reminders = s.reminders.filter((r) => r.id !== id);
    });
  },
  async product(id) {
    return copy(offer(required(read().products.find((p) => p.id === id))));
  },
  async cart() {
    return copy(read().cart);
  },
  async addCart(id, amount = 1) {
    write((s) => {
      const p = required(s.products.find((p) => p.id === id)),
        item = s.cart.find((i) => i.product_id === id);
      quantity((item?.quantity || 0) + amount, p.stock);
      if (item) item.quantity += amount;
      else
        s.cart.push({
          product_id: p.id,
          product_name: p.name,
          merchant: p.merchant,
          merchant_id: p.merchant_id,
          price_cents: p.price_cents,
          stock: p.stock,
          quantity: amount,
          product: copy(p),
        });
    });
  },
  async updateCart(id, amount) {
    write((s) => {
      const item = required(s.cart.find((i) => i.product_id === id));
      quantity(amount, required(s.products.find((p) => p.id === id)).stock);
      item.quantity = amount;
    });
  },
  async removeCart(id) {
    write((s) => {
      s.cart = s.cart.filter((i) => i.product_id !== id);
    });
  },
  async checkout(input, key) {
    const existing = read().checkoutKeys[key];
    if (existing)
      return copy(required(read().orders.find((o) => o.id === existing)));
    let order!: Order;
    write((s) => {
      if (!s.cart.length)
        throw new Error("Add a product to your basket first.");
      const items = s.cart.map((i) => {
        const p = required(s.products.find((p) => p.id === i.product_id));
        quantity(i.quantity, p.stock);
        return { ...i, price_cents: p.price_cents };
      });
      order = {
        id: uid(),
        status: "Paid",
        placed_at: new Date().toISOString(),
        items,
        total_cents: items.reduce(
          (sum, i) => sum + i.price_cents * i.quantity,
          0,
        ),
        shipping: `${input.shipping_name} · ${input.shipping_address}, Singapore ${input.shipping_postal_code}`,
        statuses: Object.fromEntries(
          items.map((i) => [i.merchant_id, "Processing"]),
        ),
        merchant_names: Object.fromEntries(
          items.map((i) => [i.merchant_id, i.merchant]),
        ),
      };
      for (const i of items)
        required(s.products.find((p) => p.id === i.product_id)).stock -=
          i.quantity;
      s.orders.unshift(order);
      s.cart = [];
      s.checkoutKeys[key] = order.id;
    });
    return copy(order);
  },
  async orders() {
    return copy(read().orders);
  },
  async order(id) {
    return copy(required(read().orders.find((o) => o.id === id)));
  },
  async merchantProducts() {
    return copy(read().products.filter((p) => p.merchant_id === "m0"));
  },
  async merchantOrders() {
    return copy(
      read()
        .orders.filter((o) => o.items.some((i) => i.merchant_id === "m0"))
        .map((o) => ({
          ...o,
          items: o.items.filter((i) => i.merchant_id === "m0"),
          total_cents: o.items
            .filter((i) => i.merchant_id === "m0")
            .reduce((sum, i) => sum + i.quantity * i.price_cents, 0),
          statuses: { m0: o.statuses.m0 },
          merchant_names: { m0: o.merchant_names.m0 },
        })),
    );
  },
  async updateProduct(id, price_cents, stock) {
    if (
      !Number.isSafeInteger(price_cents) ||
      price_cents < 0 ||
      !Number.isSafeInteger(stock) ||
      stock < 0
    )
      throw new Error("Enter a valid price and stock quantity.");
    write((s) => {
      const p = required(
        s.products.find((p) => p.id === id && p.merchant_id === "m0"),
      );
      Object.assign(p, { price_cents, stock });
    });
  },
  async updateMerchantOrder(id, status) {
    if (!["processing", "shipped", "delivered"].includes(status))
      throw new Error("Choose a valid order status.");
    write((s) => {
      required(s.orders.find((o) => o.id === id)).statuses.m0 =
        status[0].toUpperCase() + status.slice(1);
    });
  },
  async documents(pet) {
    return [...files.values()]
      .filter((f) => f.pet === pet)
      .map((f) => copy(f.document));
  },
  async uploadDocument(pet, file, title, healthRecordId) {
    const problem = documentProblem(file);
    if (problem) throw new Error(problem);
    required(read().pets.find((p) => p.id === pet));
    const id = uid();
    files.set(id, {
      pet,
      file,
      document: {
        id,
        title: title || file.name,
        content_type: file.type,
        size_bytes: file.size,
        uploaded_at: new Date().toISOString(),
        download_url: "",
        health_record_id: healthRecordId ?? "",
      },
    });
  },
  async updateDocument(pet, id, input) {
    const entry = files.get(id);
    if (!entry || entry.pet !== pet)
      throw new Error("This document could not be found.");
    if (input.title !== undefined) {
      if (!input.title.trim()) throw new Error("Enter a document title.");
      entry.document.title = input.title;
    }
    if (input.health_record !== undefined)
      entry.document.health_record_id = input.health_record ?? "";
    return copy(entry.document);
  },
  async deleteDocument(pet, id) {
    const entry = files.get(id);
    if (!entry || entry.pet !== pet)
      throw new Error("This document could not be found.");
    files.delete(id);
  },
  async downloadDocument(pet, id) {
    const entry = required(files.get(id));
    if (entry.pet !== pet) throw new Error("This document could not be found.");
    return { blob: entry.file, name: entry.file.name };
  },
};
