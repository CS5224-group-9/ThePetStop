import { localUI } from "../data-source.ts";
import { documentProblem, photoProblem } from "../pet-input.ts";
import { localServices } from "./local-services.ts";
import {
  api,
  ApiError,
  transferPrivateFile,
  createApiClient,
} from "./client.ts";
import * as map from "./adapters.ts";
import type {
  Category,
  DocumentUpdate,
  HealthRecord,
  Merchant,
  NewPetInput,
  Pet,
  PetDocument,
  PetInput,
  RecordInput,
  ReminderUpdate,
  ShippingInput,
} from "./types.ts";
const id = (value: string) => encodeURIComponent(value);
const privateRequest = { auth: true };
const STORAGE_UNAVAILABLE =
  "File storage is unavailable right now. Please try again later.";
const isStorageUnavailable = (error: unknown) =>
  error instanceof ApiError && error.code === "storage_unavailable";
// 5xx messages are masked by the client, but the error code survives.
const storageError = (error: unknown) =>
  isStorageUnavailable(error) ? new Error(STORAGE_UNAVAILABLE) : error;
const EXTENSIONS: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
};
function downloadName(title: string, contentType: string) {
  const extensions = EXTENSIONS[contentType];
  if (!extensions) return title;
  const lower = title.toLowerCase();
  return extensions.some((ext) => lower.endsWith(ext))
    ? title
    : title + extensions[0];
}
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
    async pets(): Promise<Pet[]> {
      const pets = (await client.list("pets/", privateRequest)).map((v) =>
        map.pet(v),
      );
      return Promise.all(
        pets.map(async (p) => ({ ...p, records: await service.records(p.id) })),
      );
    },
    async records(petId: string): Promise<HealthRecord[]> {
      return (
        await client.list(`pets/${id(petId)}/records/`, privateRequest)
      ).map(map.healthRecord);
    },
    async createPet(input: NewPetInput): Promise<Pet> {
      return map.pet(
        await client.request("pets/", {
          ...privateRequest,
          method: "POST",
          json: input,
        }),
      );
    },
    /** The returned pet has no records; callers keep their own. */
    async updatePet(petId: string, input: Partial<PetInput>): Promise<Pet> {
      return map.pet(
        await client.request(`pets/${id(petId)}/`, {
          ...privateRequest,
          method: "PATCH",
          json: input,
        }),
      );
    },
    async deletePet(petId: string): Promise<void> {
      await client.request(`pets/${id(petId)}/`, {
        ...privateRequest,
        method: "DELETE",
      });
    },
    async uploadPetPhoto(petId: string, file: File): Promise<Pet> {
      const problem = photoProblem(file);
      if (problem) throw new Error(problem);
      let ticket: map.Row;
      try {
        ticket = map.object(
          await client.request(`pets/${id(petId)}/photo-upload/`, {
            ...privateRequest,
            method: "POST",
            json: { content_type: file.type, size_bytes: file.size },
          }),
        );
      } catch (error) {
        throw storageError(error);
      }
      if (typeof ticket.upload_url !== "string")
        throw new Error("The upload could not be prepared.");
      // No cleanup on failure: the next upload request replaces the pending
      // upload, and stale pending uploads are purged by the server.
      await transferPrivateFile(ticket.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });
      let row: unknown;
      try {
        row = await client.request(`pets/${id(petId)}/photo-upload/complete/`, {
          ...privateRequest,
          method: "POST",
        });
      } catch (error) {
        throw isStorageUnavailable(error)
          ? new Error(STORAGE_UNAVAILABLE)
          : new Error("The photo could not be verified. Please try again.");
      }
      return map.pet(row);
    },
    async removePetPhoto(petId: string): Promise<void> {
      await client.request(`pets/${id(petId)}/photo/`, {
        ...privateRequest,
        method: "DELETE",
      });
    },
    async addRecord(petId: string, input: RecordInput): Promise<HealthRecord> {
      return map.healthRecord(
        await client.request(`pets/${id(petId)}/records/`, {
          ...privateRequest,
          method: "POST",
          json: input,
        }),
      );
    },
    async updateRecord(
      petId: string,
      recordId: string,
      input: Partial<RecordInput>,
    ): Promise<HealthRecord> {
      return map.healthRecord(
        await client.request(`pets/${id(petId)}/records/${id(recordId)}/`, {
          ...privateRequest,
          method: "PATCH",
          json: input,
        }),
      );
    },
    async deleteRecord(petId: string, recordId: string): Promise<void> {
      await client.request(`pets/${id(petId)}/records/${id(recordId)}/`, {
        ...privateRequest,
        method: "DELETE",
      });
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
    async updateReminder(
      reminderId: string,
      input: ReminderUpdate,
    ): Promise<void> {
      await client.request(`reminders/${id(reminderId)}/`, {
        ...privateRequest,
        method: "PATCH",
        json: input,
      });
    },
    async deleteReminder(reminderId: string): Promise<void> {
      await client.request(`reminders/${id(reminderId)}/`, {
        ...privateRequest,
        method: "DELETE",
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
    async documents(petId: string): Promise<PetDocument[]> {
      return (
        await client.list(`pets/${id(petId)}/documents/`, privateRequest)
      ).map(map.document);
    },
    async uploadDocument(
      petId: string,
      file: File,
      title: string,
      healthRecordId?: string,
    ): Promise<void> {
      const problem = documentProblem(file);
      if (problem) throw new Error(problem);
      let response: map.Row;
      try {
        response = map.object(
          await client.request(`pets/${id(petId)}/documents/`, {
            ...privateRequest,
            method: "POST",
            json: {
              title,
              filename: file.name,
              content_type: file.type,
              size_bytes: file.size,
              ...(healthRecordId ? { health_record: healthRecordId } : {}),
            },
          }),
        );
      } catch (error) {
        throw storageError(error);
      }
      const doc = map.document(response.document);
      const path = `pets/${id(petId)}/documents/${id(doc.id)}/`;
      // Best effort: a pending document that never completes is purged later.
      const discard = () =>
        client
          .request(path, { ...privateRequest, method: "DELETE" })
          .catch(() => {});
      if (typeof response.upload_url !== "string") {
        await discard();
        throw new Error("The upload could not be prepared.");
      }
      try {
        await transferPrivateFile(response.upload_url, {
          method: "PUT",
          headers: { "Content-Type": file.type },
          body: file,
        });
      } catch (error) {
        await discard();
        throw error;
      }
      try {
        await client.request(`${path}complete/`, {
          ...privateRequest,
          method: "POST",
        });
      } catch (error) {
        await discard();
        throw isStorageUnavailable(error)
          ? new Error(STORAGE_UNAVAILABLE)
          : new Error("The upload could not be verified. Please try again.");
      }
    },
    async updateDocument(
      petId: string,
      documentId: string,
      input: DocumentUpdate,
    ): Promise<PetDocument> {
      return map.document(
        await client.request(`pets/${id(petId)}/documents/${id(documentId)}/`, {
          ...privateRequest,
          method: "PATCH",
          json: input,
        }),
      );
    },
    async deleteDocument(petId: string, documentId: string): Promise<void> {
      await client.request(`pets/${id(petId)}/documents/${id(documentId)}/`, {
        ...privateRequest,
        method: "DELETE",
      });
    },
    async downloadDocument(
      petId: string,
      documentId: string,
    ): Promise<{ blob: Blob; name: string }> {
      const doc = map.document(
        await client.request(
          `pets/${id(petId)}/documents/${id(documentId)}/`,
          privateRequest,
        ),
      );
      if (!doc.download_url)
        throw new Error("This document is not available right now.");
      const response = await transferPrivateFile(doc.download_url);
      return {
        blob: await response.blob(),
        name: downloadName(doc.title, doc.content_type),
      };
    },
  };
  return service;
}
export const services = localUI ? localServices : createServices(api);
