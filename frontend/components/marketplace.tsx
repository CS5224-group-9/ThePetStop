"use client";
import Image from "next/image";
import { localUI } from "@/lib/data-source";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { useApp } from "./app-provider";
import { Badge, Empty, Icon, PageHeading } from "./ui";
import { FormError, ResourceState } from "./resource-state";
import { money, displayDate, safeExternalUrl } from "@/lib/format";
import { services } from "@/lib/api/services";
import { useResource } from "@/lib/api/use-resource";
import type { Product } from "@/lib/api/types";
export function ProductArt({ product }: { product: Product }) {
  const source = safeExternalUrl(product.image_url);
  if (localUI)
    return (
      <div
        className={`product-art ${["sage", "lilac", "sand", "rose"][product.name.length % 4]}`}
        aria-hidden="true"
      >
        <div className="food-bag">
          <span className="bag-top" />
          <span className="package-brand">PETSTOP / EVERYDAY CARE</span>
          <Icon
            name={product.category === "Health" ? "medical" : "paw"}
            size={32}
          />
          <span className="package-title">{product.name}</span>
          <span className="package-rule" />
          <span className="package-size">{product.size}</span>
        </div>
      </div>
    );
  return (
    <div className="product-art">
      {source ? (
        <Image src={source} width={400} height={320} alt={product.name} />
      ) : (
        <div className="product-placeholder">
          <Icon name="box" size={54} />
          <span>Product image unavailable</span>
        </div>
      )}
    </div>
  );
}
function useBasket() {
  const { state, actions, notify } = useApp();
  const router = useRouter();
  return async (productId: string) => {
    if (!state.role) {
      router.push(
        `/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`,
      );
      return;
    }
    try {
      await actions.addCart(productId);
    } catch (cause) {
      notify(
        cause instanceof Error
          ? cause.message
          : "Unable to add this item. Please try again.",
      );
    }
  };
}
export function Shop({ storefront = false }: { storefront?: boolean }) {
  const { state, pending } = useApp();
  const add = useBasket();
  const params = useSearchParams();
  const merchantSlug = storefront ? params.get("merchant") : null;
  const merchant = state.merchants.find((item) => item.slug === merchantSlug);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [species, setSpecies] = useState("");
  const [merchantId, setMerchantId] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sort, setSort] = useState("catalogue");
  const toCents = (value: string) => {
    if (!value) return null;
    const amount = Number(value);
    return Number.isFinite(amount) && amount >= 0
      ? Math.round(amount * 100)
      : null;
  };
  const minCents = toCents(minPrice);
  const maxCents = toCents(maxPrice);
  const reset = () => {
    setQuery("");
    setCategory("");
    setSpecies("");
    setMerchantId("");
    setMinPrice("");
    setMaxPrice("");
    setSort("catalogue");
  };
  const filtered = state.products
    .filter(
      (p) =>
        (!category || p.category_id === category) &&
        (!species || p.species === species) &&
        (!merchantId || p.merchant_id === merchantId) &&
        (minCents === null || p.price_cents >= minCents) &&
        (maxCents === null || p.price_cents <= maxCents) &&
        (!storefront || Boolean(merchant && p.merchant_id === merchant.id)) &&
        `${p.name} ${p.category} ${p.merchant}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "low"
        ? a.price_cents - b.price_cents
        : sort === "high"
          ? b.price_cents - a.price_cents
          : 0,
    );
  if (storefront && state.merchants.length && (!merchantSlug || !merchant))
    return (
      <Empty title="Shop not found">
        <Link href="/shop/">Return to the product catalogue</Link>
      </Empty>
    );
  return (
    <>
      <PageHeading
        eyebrow={
          storefront ? "MARKETPLACE / SHOP" : "MARKETPLACE / PRODUCT CATALOGUE"
        }
        title={
          merchant?.name ||
          (storefront ? "Merchant storefront" : "Pet nutrition & everyday care")
        }
        description={
          storefront
            ? "Browse this shop's products and compare equivalent items across merchants."
            : "Browse supplies and compare offers from participating merchants. Prices are in SGD."
        }
        action={
          <Link className="button secondary" href="/cart/">
            <Icon name="bag" size={18} />
            View basket
          </Link>
        }
      />
      <ResourceState domain="catalogue">
        <section className="catalogue-context">
          <span className="stat-icon green-solid">
            <Icon name="shield" size={25} />
          </span>
          <div>
            <h2>
              {merchant
                ? `Shop ${merchant.name}`
                : "One basket across your favourite shops"}
            </h2>
            <p>
              Review each merchant’s price and stock before checkout. Payment is
              simulated for this MVP.
            </p>
          </div>
        </section>
        <div className="catalogue-layout">
          <aside className="catalogue-filters" aria-label="Product filters">
            <div className="section-heading">
              <h2>
                <Icon name="filter" size={18} />
                Filters
              </h2>
              <button className="text-button" onClick={reset}>
                Reset all
              </button>
            </div>
            <h3 className="filter-label">PRODUCT CATEGORIES</h3>
            <div className="category-tabs">
              <button
                className={`category-option ${!category ? "selected" : ""}`}
                aria-pressed={!category}
                onClick={() => setCategory("")}
              >
                <Icon name="bag" size={17} />
                <span>All essentials</span>
                <span className="filter-count">{state.products.length}</span>
              </button>
              {state.categories.map((c) => (
                <button
                  className={`category-option ${category === c.id ? "selected" : ""}`}
                  aria-pressed={category === c.id}
                  onClick={() => setCategory(c.id)}
                  key={c.id}
                >
                  <Icon name="box" size={17} />
                  <span>{c.name}</span>
                  <span className="filter-count">
                    {
                      state.products.filter((p) => p.category_id === c.id)
                        .length
                    }
                  </span>
                </button>
              ))}
            </div>
            <label className="filter-label">
              SPECIES
              <select
                aria-label="Filter by species"
                value={species}
                onChange={(e) => setSpecies(e.target.value)}
              >
                <option value="">All companions</option>
                {Array.from(new Set(state.products.map((p) => p.species)))
                  .filter((s) => s !== "All pets")
                  .map((s) => (
                    <option key={s}>{s}</option>
                  ))}
              </select>
            </label>
            {!storefront && (
              <label className="filter-label">
                SHOP
                <select
                  aria-label="Filter by shop"
                  value={merchantId}
                  onChange={(event) => setMerchantId(event.target.value)}
                >
                  <option value="">All shops</option>
                  {state.merchants.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="filter-label">
              MINIMUM PRICE (SGD)
              <input
                aria-label="Minimum price in Singapore dollars"
                type="number"
                min="0"
                step="0.01"
                value={minPrice}
                onChange={(event) => setMinPrice(event.target.value)}
              />
            </label>
            <label className="filter-label">
              MAXIMUM PRICE (SGD)
              <input
                aria-label="Maximum price in Singapore dollars"
                type="number"
                min="0"
                step="0.01"
                value={maxPrice}
                onChange={(event) => setMaxPrice(event.target.value)}
              />
            </label>
            <div className="filter-info">
              <Icon name="shield" size={22} />
              <h3>Clear, comparable pricing</h3>
              <p>
                Open a product to compare available offers. Stock and final
                order totals are confirmed by the service.
              </p>
            </div>
          </aside>
          <section className="catalogue-results" aria-label="Product results">
            <div className="directory-toolbar">
              <label className="search-field">
                <Icon name="search" size={20} />
                <input
                  aria-label="Search products"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search products, categories or merchants…"
                />
                {query && (
                  <button
                    className="clear-search"
                    onClick={() => setQuery("")}
                    aria-label="Clear product search"
                  >
                    <Icon name="close" size={16} />
                  </button>
                )}
              </label>
              <select
                aria-label="Sort products"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                <option value="catalogue">Catalogue order</option>
                <option value="low">Price: low to high</option>
                <option value="high">Price: high to low</option>
              </select>
            </div>
            <div className="results-header">
              <strong aria-live="polite">{filtered.length} products</strong>
              <span>{state.merchants.length} merchants</span>
            </div>
            {filtered.length ? (
              <div className="product-grid">
                {filtered.map((p) => (
                  <article className="product-card" key={p.id}>
                    <Link
                      href={`/shop/product/?id=${encodeURIComponent(p.id)}`}
                      aria-label={`View ${p.name}`}
                    >
                      <ProductArt product={p} />
                      <span className="product-category-badge">
                        {p.category}
                      </span>
                    </Link>
                    <div className="product-body">
                      <span className="product-specs">
                        {p.species}
                        {p.size ? ` · ${p.size}` : ""}
                      </span>
                      <Link
                        href={`/shop/product/?id=${encodeURIComponent(p.id)}`}
                      >
                        <h3>{p.name}</h3>
                      </Link>
                      {(() => {
                        const shop = state.merchants.find(
                          (item) => item.id === p.merchant_id,
                        );
                        return shop ? (
                          <Link
                            className="text-link"
                            href={`/shop/store/?merchant=${encodeURIComponent(shop.slug)}`}
                          >
                            {p.merchant}
                          </Link>
                        ) : (
                          <p>{p.merchant}</p>
                        );
                      })()}
                      <div className="product-tags">
                        <Badge tone={p.stock ? "green" : "rose"}>
                          {p.stock ? "In stock" : "Out of stock"}
                        </Badge>
                      </div>
                      <div className="price-row">
                        <strong>{money(p.price_cents)}</strong>
                        <Link
                          className="compare-link"
                          href={`/shop/product/?id=${encodeURIComponent(p.id)}`}
                        >
                          View offers
                          <Icon name="arrow" size={14} />
                        </Link>
                      </div>
                      <button
                        className="button full-width"
                        disabled={!p.stock || pending.includes(`cart:${p.id}`)}
                        onClick={() => void add(p.id)}
                      >
                        <Icon name="bag" size={17} />
                        {pending.includes(`cart:${p.id}`)
                          ? "Adding…"
                          : p.stock
                            ? "Add to basket"
                            : "Out of stock"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty title="No products found">
                Try another search or{" "}
                <button className="text-button" onClick={reset}>
                  reset the filters
                </button>
                .
              </Empty>
            )}
          </section>
        </div>
        {state.cart.length > 0 && (
          <div className="basket-bar">
            <span className="stat-icon">
              <Icon name="bag" size={24} />
            </span>
            <div>
              <strong>
                Basket · {state.cart.reduce((sum, i) => sum + i.quantity, 0)}{" "}
                items
              </strong>
              <small>
                {new Set(state.cart.map((i) => i.merchant_id)).size} merchant(s)
              </small>
            </div>
            <Link className="button light" href="/cart/">
              Review basket
              <Icon name="arrow" size={18} />
            </Link>
          </div>
        )}
      </ResourceState>
    </>
  );
}
export function ProductDetail() {
  const { state, pending } = useApp();
  const params = useSearchParams();
  const id = params.get("id") || "";
  const add = useBasket();
  const loader = useCallback(
    () => services.product(id, state.categories, state.merchants),
    [id, state.categories, state.merchants],
  );
  const {
    data: p,
    loading,
    error,
    reload,
  } = useResource(`product:${id}`, loader);
  if (!id)
    return (
      <Empty title="Product not found">
        <Link href="/shop/">Return to the catalogue</Link>
      </Empty>
    );
  if (loading)
    return (
      <div className="panel" role="status">
        Loading product…
      </div>
    );
  if (error || !p)
    return (
      <div className="panel" role="alert">
        <h1>Unable to load this product</h1>
        <p>{error}</p>
        <button className="button secondary" onClick={reload}>
          Try again
        </button>
        <Link className="text-link" href="/shop/">
          Return to catalogue
        </Link>
      </div>
    );
  const merchantStore = state.merchants.find(
    (item) => item.id === p.merchant_id,
  );
  return (
    <>
      <PageHeading
        eyebrow={`MARKETPLACE / ${p.category.toUpperCase()}`}
        title={p.name}
        description="Product information and available merchant offers."
        action={
          <Link className="button secondary" href="/shop/">
            Continue browsing
          </Link>
        }
      />
      <div className="product-detail-grid">
        <ProductArt product={p} />
        <section className="panel">
          <Badge tone="green">
            {merchantStore ? (
              <Link
                href={`/shop/store/?merchant=${encodeURIComponent(merchantStore.slug)}`}
              >
                {p.merchant}
              </Link>
            ) : (
              p.merchant
            )}
          </Badge>
          <h2>{p.name}</h2>
          <p>{p.description}</p>
          <div className="product-detail-price">
            {money(p.price_cents)}
            <small>Current merchant price</small>
          </div>
          <div className="detail-facts">
            <div>
              <span>SIZE</span>
              <strong>{p.size || "See product details"}</strong>
            </div>
            <div>
              <span>FOR</span>
              <strong>{p.species}</strong>
            </div>
            <div>
              <span>AVAILABLE STOCK</span>
              <strong>{p.stock}</strong>
            </div>
          </div>
          <button
            className="button"
            disabled={!p.stock || pending.includes(`cart:${p.id}`)}
            onClick={() => void add(p.id)}
          >
            <Icon name="bag" size={18} />
            {pending.includes(`cart:${p.id}`)
              ? "Adding…"
              : `Add from ${p.merchant}`}
          </button>
        </section>
      </div>
      <section className="panel comparison-panel">
        <div className="section-heading">
          <div>
            <h2>Compare merchant offers</h2>
            <p>
              Choose which merchant to buy from. Prices and stock can change.
            </p>
          </div>
          <Badge tone="neutral">{p.offers.length} offer(s)</Badge>
        </div>
        {p.offers.map((offer, index) => (
          <div className="offer-row" key={offer.id}>
            <span className="merchant-initial">
              {offer.merchant.slice(0, 1)}
            </span>
            <div>
              <h3>{offer.merchant}</h3>
              <p>{offer.stock ? `${offer.stock} available` : "Out of stock"}</p>
            </div>
            {index === 0 && <Badge tone="green">Lowest listed price</Badge>}
            <strong>{money(offer.price_cents)}</strong>
            <button
              className="button secondary small"
              disabled={!offer.stock || pending.includes(`cart:${offer.id}`)}
              onClick={() => void add(offer.id)}
            >
              {pending.includes(`cart:${offer.id}`)
                ? "Adding…"
                : "Add to basket"}
              <Icon name="plus" size={15} />
            </button>
          </div>
        ))}
      </section>
    </>
  );
}
export function Cart() {
  const { state, actions, pending } = useApp();
  const [error, setError] = useState("");
  const total = state.cart.reduce(
    (sum, i) => sum + i.quantity * i.price_cents,
    0,
  );
  const merchants = Array.from(new Set(state.cart.map((i) => i.merchant_id)));
  return (
    <>
      <PageHeading
        eyebrow="MARKETPLACE / BASKET"
        title="Shopping basket"
        description="Review current prices and quantities, grouped by merchant."
        action={
          <Link className="button secondary" href="/shop/">
            Continue browsing
            <Icon name="arrow" size={16} />
          </Link>
        }
      />
      <FormError message={error} />
      {state.cart.length ? (
        <div className="detail-columns">
          <div>
            {merchants.map((merchantId) => (
              <section className="panel" key={merchantId}>
                <div className="section-heading">
                  <h2>
                    <Icon name="bag" />
                    {
                      state.cart.find((i) => i.merchant_id === merchantId)
                        ?.merchant
                    }
                  </h2>
                </div>
                {state.cart
                  .filter((i) => i.merchant_id === merchantId)
                  .map((i) => (
                    <div className="cart-row" key={i.product_id}>
                      {i.product && (
                        <Link
                          href={`/shop/product/?id=${encodeURIComponent(i.product_id)}`}
                        >
                          <ProductArt product={i.product} />
                        </Link>
                      )}
                      <div>
                        <Link
                          href={`/shop/product/?id=${encodeURIComponent(i.product_id)}`}
                        >
                          <h3>{i.product_name}</h3>
                        </Link>
                        <p>{money(i.price_cents)} each</p>
                        {i.stock < i.quantity && (
                          <Badge tone="rose">
                            Only {i.stock} currently available
                          </Badge>
                        )}
                        <button
                          className="remove-link"
                          disabled={pending.includes(`cart:${i.product_id}`)}
                          onClick={async () => {
                            setError("");
                            try {
                              await actions.removeCart(i.product_id);
                            } catch (cause) {
                              setError(
                                cause instanceof Error
                                  ? cause.message
                                  : "Unable to remove this item.",
                              );
                            }
                          }}
                        >
                          Remove
                        </button>
                      </div>
                      <form
                        className="quantity-form"
                        onSubmit={async (e) => {
                          e.preventDefault();
                          setError("");
                          const quantity = Number(
                            new FormData(e.currentTarget).get("quantity"),
                          );
                          try {
                            await actions.updateCart(i.product_id, quantity);
                          } catch (cause) {
                            setError(
                              cause instanceof Error
                                ? cause.message
                                : "Unable to update this quantity.",
                            );
                          }
                        }}
                      >
                        <label className="quantity-label">
                          Quantity
                          <input
                            key={`${i.product_id}-${i.quantity}`}
                            name="quantity"
                            type="number"
                            min={1}
                            max={Math.max(1, i.stock)}
                            step={1}
                            defaultValue={i.quantity}
                            required
                            disabled={pending.includes(`cart:${i.product_id}`)}
                            aria-label={`Quantity of ${i.product_name}`}
                          />
                        </label>
                        <button
                          className="text-button"
                          disabled={pending.includes(`cart:${i.product_id}`)}
                          type="submit"
                        >
                          Update
                        </button>
                      </form>
                      <strong>{money(i.price_cents * i.quantity)}</strong>
                    </div>
                  ))}
              </section>
            ))}
          </div>
          <aside className="panel order-summary">
            <h2>Order summary</h2>
            <div>
              <span>Items</span>
              <strong>{money(total)}</strong>
            </div>
            <div className="summary-total">
              <span>Estimated total</span>
              <strong>{money(total)}</strong>
            </div>
            <Link className="button" href="/checkout/">
              Continue to checkout
              <Icon name="arrow" size={17} />
            </Link>
            <p>
              Final stock and total are confirmed at checkout. Payment is
              simulated.
            </p>
          </aside>
        </div>
      ) : (
        <Empty title="Your basket is empty">
          <Link className="button" href="/shop/">
            Browse products
            <Icon name="arrow" size={16} />
          </Link>
        </Empty>
      )}
    </>
  );
}
export function Checkout() {
  const { state, actions, pending } = useApp();
  const router = useRouter();
  const key = useRef("");
  const submitting = useRef(false);
  const [error, setError] = useState("");
  const busy = pending.includes("checkout");
  const total = state.cart.reduce(
    (sum, i) => sum + i.price_cents * i.quantity,
    0,
  );
  if (!state.cart.length)
    return (
      <Empty title="Your basket is empty">
        <Link href="/shop/">Browse the marketplace</Link>
      </Empty>
    );
  return (
    <>
      <PageHeading
        eyebrow="BASKET / CHECKOUT"
        title="Delivery & simulated payment"
        description="Confirm delivery details and review your order before placing it."
      />
      <div className="directory-notice">
        <Icon name="shield" size={18} />
        <span>
          This MVP uses simulated payment. No real money is transferred.
        </span>
      </div>
      <form
        className="detail-columns"
        onSubmit={async (e) => {
          e.preventDefault();
          if (submitting.current) return;
          submitting.current = true;
          const d = new FormData(e.currentTarget);
          setError("");
          key.current ||= crypto.randomUUID();
          try {
            const id = await actions.checkout(
              {
                shipping_name: String(d.get("name")).trim(),
                shipping_phone: String(d.get("phone")).trim(),
                shipping_address: String(d.get("address")).trim(),
                shipping_postal_code: String(d.get("postal")),
              },
              key.current,
            );
            router.push(`/orders/detail/?id=${encodeURIComponent(id)}`);
          } catch (cause) {
            setError(
              `${cause instanceof Error ? cause.message : "Unable to place your order."} If the connection was interrupted, check your order history before trying again.`,
            );
            submitting.current = false;
          }
        }}
      >
        <section className="panel">
          <div className="section-heading">
            <h2>
              <Icon name="box" />
              Delivery details
            </h2>
          </div>
          <FormError message={error} />
          <fieldset disabled={busy} className="form-fieldset">
            <div className="form-grid">
              <label className="full-width">
                Recipient name
                <input
                  name="name"
                  autoComplete="shipping name"
                  required
                  maxLength={80}
                />
              </label>
              <label>
                Phone number
                <input
                  name="phone"
                  type="tel"
                  autoComplete="shipping tel"
                  required
                  maxLength={20}
                  pattern="[+0-9]{8,15}"
                />
              </label>
              <label>
                Singapore postal code
                <input
                  name="postal"
                  inputMode="numeric"
                  autoComplete="shipping postal-code"
                  required
                  pattern="[0-9]{6}"
                  maxLength={6}
                />
              </label>
              <label className="full-width">
                Street address & unit number
                <input
                  name="address"
                  autoComplete="shipping street-address"
                  required
                  maxLength={200}
                />
              </label>
            </div>
            <div className="simulation-box">
              <span className="stat-icon green-soft">
                <Icon name="shield" />
              </span>
              <div>
                <h3>Simulated payment</h3>
                <p>
                  The service records your order with a simulated payment
                  reference. No payment details are required.
                </p>
              </div>
            </div>
            <label className="check-label">
              <input type="checkbox" required />I understand that payment is
              simulated and no money will be charged.
            </label>
          </fieldset>
        </section>
        <aside className="panel order-summary">
          <h2>Order summary</h2>
          {state.cart.map((i) => (
            <div key={i.product_id}>
              <span>
                {i.product_name} × {i.quantity}
                <small>{i.merchant}</small>
              </span>
              <strong>{money(i.price_cents * i.quantity)}</strong>
            </div>
          ))}
          <div className="summary-total">
            <span>Estimated total</span>
            <strong>{money(total)}</strong>
          </div>
          <button className="button" type="submit" disabled={busy}>
            {busy ? "Placing order…" : "Place order · simulated payment"}
            <Icon name="arrow" size={17} />
          </button>
          <p>
            Stock and prices are validated by the service before an order is
            confirmed.
          </p>
          <Link className="text-link" href="/orders/">
            View order history
          </Link>
        </aside>
      </form>
    </>
  );
}
export function Orders({ detail = false }: { detail?: boolean }) {
  const { state } = useApp();
  const params = useSearchParams();
  return detail ? (
    <OrderDetail id={params.get("id") || ""} />
  ) : (
    <>
      <PageHeading
        eyebrow="YOUR ORDERS"
        title="Order history"
        description="Review past purchases and each merchant’s fulfilment status."
        action={
          <Link className="button secondary" href="/shop/">
            Browse products
            <Icon name="arrow" size={16} />
          </Link>
        }
      />
      {state.orders.length ? (
        <section className="panel">
          {state.orders.map((o) => (
            <Link
              className="record-row order-link"
              href={`/orders/detail/?id=${encodeURIComponent(o.id)}`}
              key={o.id}
            >
              <span className="stat-icon green-soft">
                <Icon name="box" />
              </span>
              <div>
                <h3>Order {o.id}</h3>
                <p>
                  {displayDate(o.placed_at)} · {Object.keys(o.statuses).length}{" "}
                  merchant(s)
                </p>
              </div>
              <strong>{money(o.total_cents)}</strong>
              <Icon name="arrow" size={18} />
            </Link>
          ))}
        </section>
      ) : (
        <Empty title="No orders yet">
          <Link href="/shop/">
            Browse the marketplace to start your first order.
          </Link>
        </Empty>
      )}
    </>
  );
}
function OrderDetail({ id }: { id: string }) {
  const loader = useCallback(() => services.order(id), [id]);
  const {
    data: order,
    loading,
    error,
    reload,
  } = useResource(`order:${id}`, loader);
  if (!id)
    return (
      <Empty title="Order not found">
        <Link href="/orders/">View order history</Link>
      </Empty>
    );
  if (loading)
    return (
      <div className="panel" role="status">
        Loading order…
      </div>
    );
  if (error || !order)
    return (
      <div className="panel" role="alert">
        <h1>Unable to load this order</h1>
        <p>{error}</p>
        <button className="button secondary" onClick={reload}>
          Try again
        </button>
        <Link className="text-link" href="/orders/">
          View order history
        </Link>
      </div>
    );
  return (
    <>
      <PageHeading
        eyebrow="ORDERS / ORDER DETAILS"
        title="Order details"
        description="Your order and each merchant’s latest fulfilment status."
        action={
          <Link className="button secondary" href="/orders/">
            All orders
          </Link>
        }
      />
      <section className="confirmation-banner">
        <span className="confirmation-check">
          <Icon name={order.status === "Paid" ? "check" : "box"} size={30} />
        </span>
        <div>
          <Badge tone={order.status === "Paid" ? "green" : "neutral"}>
            {order.status === "Paid"
              ? "SIMULATED PAYMENT RECORDED"
              : order.status || "Order received"}
          </Badge>
          <h2>Order {order.id}</h2>
          <p>
            {displayDate(order.placed_at)} · {money(order.total_cents)}
          </p>
        </div>
      </section>
      <div className="detail-columns">
        <div>
          {Object.entries(order.statuses).map(([merchant, status]) => (
            <section className="panel" key={merchant}>
              <div className="section-heading">
                <h2>
                  <Icon name="bag" />
                  {order.merchant_names[merchant] || merchant}
                </h2>
                <Badge>{status}</Badge>
              </div>
              {order.items
                .filter((i) => i.merchant_id === merchant)
                .map((i) => (
                  <div className="record-row" key={i.product_id}>
                    <div>
                      <h3>{i.product_name}</h3>
                      <p>
                        Quantity {i.quantity} · {money(i.price_cents)} each
                      </p>
                    </div>
                    <strong>{money(i.price_cents * i.quantity)}</strong>
                  </div>
                ))}
            </section>
          ))}
        </div>
        <aside className="panel order-summary">
          <h2>Delivery details</h2>
          <p>{order.shipping}</p>
          <div className="summary-total">
            <span>Order total</span>
            <strong>{money(order.total_cents)}</strong>
          </div>
          <p>Checkout uses simulated payment. No real money is transferred.</p>
        </aside>
      </div>
    </>
  );
}
