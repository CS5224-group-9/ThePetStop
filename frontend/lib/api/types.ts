export type HealthRecord = {
  id: string;
  title: string;
  kind: string;
  date: string;
  next_due: string;
  clinic: string;
  /** Raw enum value (for example "vaccination"); `kind` is its display label. */
  record_type: string;
  notes: string;
};
/** Raw, writable pet values as sent to and received from the API. */
export type PetInput = {
  name: string;
  species: string;
  breed: string;
  sex: string;
  date_of_birth: string | null;
  microchip_no: string | null;
  allergies: string[];
  diet_notes: string;
  weight_kg?: number | null;
};
export type Pet = {
  id: string;
  name: string;
  species: string;
  breed: string;
  sex: string;
  date_of_birth: string;
  microchip: string;
  photo_url: string | null;
  /** Changes only when a new photo is completed; the photo cache key. */
  photo_version: string | null;
  weight: string;
  allergies: string;
  diet: string;
  records: HealthRecord[];
  /** Raw values for edit forms; the fields above are display labels. */
  values: PetInput;
};
export type NewPetInput = PetInput;
export type RecordInput = {
  name: string;
  record_type: string;
  date: string;
  next_due: string | null;
  clinic: string;
  notes?: string;
};
export type Reminder = {
  id: string;
  pet_id: string;
  title: string;
  due_date: string;
  done: boolean;
  /** "" when the reminder is not linked to a care record. */
  health_record_id: string;
  is_overdue: boolean;
  is_due_soon: boolean;
};
export type ReminderUpdate = {
  title?: string;
  due_at?: string;
  done?: boolean;
  health_record?: string | null;
};
export type Merchant = { id: string; slug: string; name: string };
export type Category = { id: string; slug: string; name: string };
export type ProductOffer = {
  id: string;
  merchant: string;
  merchant_id: string;
  price_cents: number;
  stock: number;
};
export type Product = {
  id: string;
  name: string;
  category: string;
  category_id: string;
  species: string;
  size: string;
  description: string;
  color: string;
  price_cents: number;
  stock: number;
  merchant: string;
  merchant_id: string;
  image_url: string | null;
  offers: ProductOffer[];
};
export type CartItem = {
  product_id: string;
  product_name: string;
  merchant: string;
  merchant_id: string;
  quantity: number;
  price_cents: number;
  stock: number;
  product?: Product;
};
export type Order = {
  status: string;
  merchant_names: Record<string, string>;
  id: string;
  placed_at: string;
  items: CartItem[];
  total_cents: number;
  shipping: string;
  statuses: Record<string, string>;
};
export type Profile = {
  id: string;
  display_name: string;
  email: string;
  groups: string[];
  merchant: Merchant | null;
};
export type Facility = {
  id: string;
  name: string;
  type: string;
  address: string;
  area: string;
  emergency: boolean;
  latitude: number | null;
  longitude: number | null;
  phone: string;
  website: string;
  licence_no: string;
  source: string;
  source_url: string;
  last_checked_at: string | null;
  verification_status: string;
};
export type PetDocument = {
  id: string;
  title: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
  download_url: string;
  /** "" when the document is not linked to a care record. */
  health_record_id: string;
};
export type DocumentUpdate = { title?: string; health_record?: string | null };
export type ShippingInput = {
  shipping_name: string;
  shipping_phone: string;
  shipping_address: string;
  shipping_postal_code: string;
};
export type Domain =
  | "catalogue"
  | "facilities"
  | "pets"
  | "reminders"
  | "cart"
  | "orders"
  | "merchant";
export type AppState = {
  role: "owner" | "merchant" | null;
  profile: Profile | null;
  pets: Pet[];
  reminders: Reminder[];
  cart: CartItem[];
  orders: Order[];
  products: Product[];
  categories: Category[];
  merchants: Merchant[];
  facilities: Facility[];
  merchant_products: Product[];
  merchant_orders: Order[];
};
export type ResourceStatus = {
  loading: boolean;
  error: string | null;
  loaded: boolean;
};
export const emptyState = (): AppState => ({
  role: null,
  profile: null,
  pets: [],
  reminders: [],
  cart: [],
  orders: [],
  products: [],
  categories: [],
  merchants: [],
  facilities: [],
  merchant_products: [],
  merchant_orders: [],
});
