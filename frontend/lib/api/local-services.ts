import type { createServices } from "./services.ts";
import type { AppState, Order, PetDocument, Product } from "./types.ts";
import { emptyState } from "./types.ts";

type Store = AppState & { checkoutKeys: Record<string, string> };
const storageKey = "petstop.ui.v1";
let memory: Store | null = null;
const files = new Map<
  string,
  { pet: string; document: PetDocument; file: File }
>();
const uid = () => crypto.randomUUID();
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
    facilities: [],
    pets: [
      {
        id: "kopi",
        name: "Kopi",
        species: "dog",
        breed: "Singapore Special",
        sex: "male",
        date_of_birth: "2022-04-12",
        microchip: "",
        photo_url: null,
        weight: "",
        allergies: "Chicken",
        diet: "Salmon-based dry food",
        records: [
          {
            id: "r1",
            title: "Annual vaccination",
            kind: "vaccination",
            date: "2026-06-12",
            next_due: "2027-06-12",
            clinic: "Sample veterinary centre",
          },
        ],
      },
      {
        id: "mochi",
        name: "Mochi",
        species: "cat",
        breed: "Domestic Shorthair",
        sex: "female",
        date_of_birth: "2023-08-20",
        microchip: "",
        photo_url: null,
        weight: "",
        allergies: "None recorded",
        diet: "Indoor cat food",
        records: [],
      },
      {
        id: "sesame",
        name: "Sesame",
        species: "rabbit",
        breed: "Holland Lop",
        sex: "female",
        date_of_birth: "2024-02-15",
        microchip: "",
        photo_url: null,
        weight: "",
        allergies: "None recorded",
        diet: "Timothy hay and leafy greens",
        records: [],
      },
    ],
    reminders: [
      {
        id: "rem1",
        pet_id: "kopi",
        title: "Monthly flea & tick care",
        due_date: "2026-10-25",
        done: false,
      },
      {
        id: "rem2",
        pet_id: "mochi",
        title: "Annual health check",
        due_date: "2026-11-05",
        done: false,
      },
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
          parsed.checkoutKeys &&
          parsed.profile?.id === "local-owner"
        ) {
          parsed.facilities = [];
          return (memory = parsed);
        }
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
    return [];
  },
  async me() {
    return copy(required(read().profile ?? undefined));
  },
  async pets() {
    return copy(read().pets);
  },
  async createPet(input) {
    if (!input.name.trim()) throw new Error("Enter your pet’s name.");
    const pet = {
      ...input,
      id: uid(),
      microchip: input.microchip_no || "",
      allergies: input.allergies.join(", "),
      diet: input.diet_notes,
      records: [],
      photo_url: null,
      weight: "",
    };
    write((s) => {
      s.pets.push(pet);
    });
    return copy(pet);
  },
  async addRecord(pet, input) {
    const record = {
      id: uid(),
      title: input.name,
      kind: input.record_type,
      date: input.date,
      next_due: input.next_due || "",
      clinic: input.clinic,
    };
    write((s) => {
      required(s.pets.find((p) => p.id === pet)).records.push(record);
    });
    return copy(record);
  },
  async reminders() {
    return copy(read().reminders);
  },
  async createReminder(input) {
    const reminder = {
      id: uid(),
      pet_id: input.pet,
      title: input.title,
      due_date: input.due_at.slice(0, 10),
      done: false,
    };
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
  async uploadDocument(pet, file, title) {
    if (
      !["application/pdf", "image/jpeg", "image/png"].includes(file.type) ||
      file.size < 1 ||
      file.size > 10 * 1024 * 1024
    )
      throw new Error("Choose a PDF, JPEG or PNG file up to 10 MB.");
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
      },
    });
  },
  async downloadDocument(pet, id) {
    const entry = required(files.get(id));
    if (entry.pet !== pet) throw new Error("This document could not be found.");
    return { blob: entry.file, name: entry.file.name };
  },
};
