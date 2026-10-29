import { localUI } from "../data-source.ts";
import { localServices } from "./local-services.ts";
import { api, transferPrivateFile, createApiClient } from "./client.ts";
import * as map from "./adapters.ts";
import type {
  Category,
  Merchant,
  NewPetInput,
  ShippingInput,
} from "./types.ts";
const id = (value: string) => encodeURIComponent(value);
const privateRequest = { auth: true };
export function createServices(client: ReturnType<typeof createApiClient>) {
  const service = {
    async catalogue() {
      const [categoryRows, merchantRows] = await Promise.all([
        client.list("categories/"),
        client.list("merchants/"),
      ]);
      const categories = categoryRows.map(map.category),
        merchants = merchantRows.map(map.merchant);
      const rows = await client.list("products/");
      return {
        categories,
        merchants,
        products: rows.map((v) => map.product(v, categories, merchants)),
      };
    },
    async facilities() {
      return (await client.list("facilities/")).map(map.facility);
    },
    async me() {
      return map.profile(await client.request("me/", privateRequest));
    },
    async pets() {
      const pets = (await client.list("pets/", privateRequest)).map((v) =>
        map.pet(v),
      );
      return Promise.all(
        pets.map(async (p) => ({
          ...p,
          records: (
            await client.list(`pets/${id(p.id)}/records/`, privateRequest)
          ).map(map.healthRecord),
        })),
      );
    },
    async createPet(input: NewPetInput) {
      return map.pet(
        await client.request("pets/", {
          ...privateRequest,
          method: "POST",
          json: input,
        }),
      );
    },
    async addRecord(
      petId: string,
      input: {
        name: string;
        record_type: string;
        date: string;
        next_due: string | null;
        clinic: string;
      },
    ) {
      return map.healthRecord(
        await client.request(`pets/${id(petId)}/records/`, {
          ...privateRequest,
          method: "POST",
          json: input,
        }),
      );
    },
    async reminders() {
      return (await client.list("reminders/", privateRequest)).map(
        map.reminder,
      );
    },
    async createReminder(input: {
      pet: string;
      title: string;
      due_at: string;
      health_record?: string;
    }) {
      return map.reminder(
        await client.request("reminders/", {
          ...privateRequest,
          method: "POST",
          json: input,
        }),
      );
    },
    async setReminder(reminderId: string, done: boolean) {
      await client.request(`reminders/${id(reminderId)}/`, {
        ...privateRequest,
        method: "PATCH",
        json: { done },
      });
    },
    async product(
      productId: string,
      categories: Category[],
      merchants: Merchant[],
    ) {
      return map.product(
        await client.request(`products/${id(productId)}/`),
        categories,
        merchants,
      );
    },
    async cart(categories: Category[], merchants: Merchant[]) {
      return map.cart(
        await client.request("cart/", privateRequest),
        categories,
        merchants,
      );
    },
    async addCart(productId: string, quantity = 1) {
      await client.request("cart/items/", {
        ...privateRequest,
        method: "POST",
        json: { product: productId, quantity },
      });
    },
    async updateCart(productId: string, quantity: number) {
      await client.request(`cart/items/${id(productId)}/`, {
        ...privateRequest,
        method: "PATCH",
        json: { quantity },
      });
    },
    async removeCart(productId: string) {
      await client.request(`cart/items/${id(productId)}/`, {
        ...privateRequest,
        method: "DELETE",
      });
    },
    async checkout(shipping: ShippingInput, key: string) {
      return map.order(
        await client.request("checkout/", {
          ...privateRequest,
          method: "POST",
          headers: { "Idempotency-Key": key },
          json: shipping,
        }),
      );
    },
    async orders() {
      return (await client.list("orders/", privateRequest)).map(map.order);
    },
    async order(orderId: string) {
      return map.order(
        await client.request(`orders/${id(orderId)}/`, privateRequest),
      );
    },
    async merchantProducts(categories: Category[], merchants: Merchant[]) {
      return (await client.list("merchant/products/", privateRequest)).map(
        (v) => map.product(v, categories, merchants),
      );
    },
    async merchantOrders() {
      return (await client.list("merchant/orders/", privateRequest)).map(
        map.merchantOrder,
      );
    },
    async updateProduct(productId: string, price_cents: number, stock: number) {
      await client.request(`merchant/products/${id(productId)}/`, {
        ...privateRequest,
        method: "PATCH",
        json: { price_cents, stock },
      });
    },
    async updateMerchantOrder(orderId: string, status: string) {
      await client.request(`merchant/orders/${id(orderId)}/`, {
        ...privateRequest,
        method: "PATCH",
        json: { status },
      });
    },
    async documents(petId: string) {
      return (
        await client.list(`pets/${id(petId)}/documents/`, privateRequest)
      ).map(map.document);
    },
    async uploadDocument(petId: string, file: File, title: string) {
      if (
        !["application/pdf", "image/jpeg", "image/png"].includes(file.type) ||
        file.size < 1 ||
        file.size > 10 * 1024 * 1024
      )
        throw new Error("Choose a PDF, JPEG or PNG file up to 10 MB.");
      const response = map.object(
        await client.request(`pets/${id(petId)}/documents/`, {
          ...privateRequest,
          method: "POST",
          json: {
            title,
            filename: file.name,
            content_type: file.type,
            size_bytes: file.size,
          },
        }),
      );
      const doc = map.document(response.document);
      if (typeof response.upload_url !== "string")
        throw new Error("The upload could not be prepared.");
      try {
        await transferPrivateFile(response.upload_url, {
          method: "PUT",
          headers: { "Content-Type": file.type },
          body: file,
        });
      } catch (error) {
        await client
          .request(`pets/${id(petId)}/documents/${id(doc.id)}/`, {
            ...privateRequest,
            method: "DELETE",
          })
          .catch(() => {});
        throw error;
      }
    },
    async downloadDocument(
      petId: string,
      documentId: string,
    ): Promise<{ blob: Blob; name: string }> {
      const docs = await service.documents(petId);
      const doc = docs.find((d) => d.id === documentId);
      if (!doc) throw new Error("This document is no longer available.");
      const response = await transferPrivateFile(doc.download_url);
      return { blob: await response.blob(), name: doc.title };
    },
  };
  return service;
}
const apiServices = createServices(api);
export const services = localUI
  ? { ...localServices, facilities: apiServices.facilities }
  : apiServices;
