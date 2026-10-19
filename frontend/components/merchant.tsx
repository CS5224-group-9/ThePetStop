"use client";
import { useState } from "react";
import { useApp } from "./app-provider";
import { Badge, Empty, Icon, PageHeading } from "./ui";
import { FormError } from "./resource-state";
import { money } from "@/lib/format";
export function Merchant() {
  const { state, actions, pending } = useApp();
  const [tab, setTab] = useState("Catalogue");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  return (
    <>
      <PageHeading
        eyebrow="MERCHANT WORKSPACE"
        title={state.profile?.merchant?.name || "Merchant dashboard"}
        description="Manage your shop’s prices, stock and order fulfilment."
      />
      <div className="tabs">
        {["Catalogue", "Orders"].map((t) => (
          <button
            key={t}
            aria-pressed={tab === t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <FormError message={error} />
      {tab === "Catalogue" ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Product catalogue</h2>
            <label className="search-field compact">
              <Icon name="search" size={17} />
              <input
                aria-label="Find a merchant product"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Find a product…"
              />
            </label>
          </div>
          <div className="merchant-table">
            <div className="merchant-table-head">
              <span>PRODUCT</span>
              <span>PRICE (SGD)</span>
              <span>STOCK</span>
              <span />
            </div>
            {state.merchant_products
              .filter((p) => p.name.toLowerCase().includes(query.toLowerCase()))
              .map((p) => (
                <form
                  className="merchant-row"
                  key={`${p.id}-${p.price_cents}-${p.stock}`}
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const d = new FormData(e.currentTarget);
                    setError("");
                    try {
                      await actions.updateProduct(
                        p.id,
                        Math.round(Number(d.get("price")) * 100),
                        Number(d.get("stock")),
                      );
                    } catch (cause) {
                      setError(
                        cause instanceof Error
                          ? cause.message
                          : "Unable to update this product.",
                      );
                    }
                  }}
                >
                  <div>
                    <h3>{p.name}</h3>
                    <p>{p.category}</p>
                  </div>
                  <label>
                    <span className="sr-only">Price for {p.name}</span>
                    <input
                      name="price"
                      type="number"
                      min="0.01"
                      max="10000"
                      step="0.01"
                      defaultValue={(p.price_cents / 100).toFixed(2)}
                      required
                      disabled={pending.includes(`product:${p.id}`)}
                    />
                  </label>
                  <label>
                    <span className="sr-only">Stock for {p.name}</span>
                    <input
                      name="stock"
                      type="number"
                      min="0"
                      max="9999"
                      step="1"
                      defaultValue={p.stock}
                      required
                      disabled={pending.includes(`product:${p.id}`)}
                    />
                  </label>
                  <button
                    className="button secondary small"
                    type="submit"
                    disabled={pending.includes(`product:${p.id}`)}
                  >
                    {pending.includes(`product:${p.id}`) ? "Saving…" : "Save"}
                  </button>
                </form>
              ))}
          </div>
          {!state.merchant_products.length && (
            <Empty title="No products yet">
              Your shop’s products will appear here when they are available.
            </Empty>
          )}
        </section>
      ) : state.merchant_orders.length ? (
        <section className="panel">
          {state.merchant_orders.map((o) => {
            const status = Object.values(o.statuses)[0] || "";
            const next =
              status === "Paid"
                ? "processing"
                : status === "Processing"
                  ? "shipped"
                  : status === "Shipped"
                    ? "delivered"
                    : null;
            return (
              <div className="record-row" key={o.id}>
                <span className="stat-icon green-soft">
                  <Icon name="box" />
                </span>
                <div>
                  <h3>Order {o.id}</h3>
                  <p>Your items: {money(o.total_cents)}</p>
                </div>
                <Badge>{status}</Badge>
                <button
                  className="button secondary small"
                  disabled={!next || pending.includes(`order:${o.id}`)}
                  onClick={async () => {
                    if (!next) return;
                    setError("");
                    try {
                      await actions.updateMerchantOrder(o.id, next);
                    } catch (cause) {
                      setError(
                        cause instanceof Error
                          ? cause.message
                          : "Unable to update this order.",
                      );
                    }
                  }}
                >
                  {pending.includes(`order:${o.id}`)
                    ? "Updating…"
                    : next
                      ? `Mark ${next}`
                      : status}
                </button>
              </div>
            );
          })}
        </section>
      ) : (
        <Empty title="No merchant orders yet">
          Orders for your shop will appear here.
        </Empty>
      )}
    </>
  );
}
