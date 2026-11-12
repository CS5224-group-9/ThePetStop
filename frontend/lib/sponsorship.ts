import type { Product } from "./api/types.ts";

// shortcut: fixed demo sponsors for the two seed catalogues, use API-managed placements for real campaigns.
export function sponsoredProduct(products: Product[]): Product | undefined {
  return products.find(
    (product) =>
      product.stock > 0 &&
      ((product.id === "p-0-0-0" && product.merchant_id === "m0") ||
        (product.merchant === "Harbour Paws Supply" &&
          product.name === "Balanced chicken dry dog food 2 kg")),
  );
}
