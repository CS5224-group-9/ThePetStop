"""Transactional checkout and simulated payment (docs/data-model.md#checkout-rules).

`place_order` turns the user's cart into one `Order`, one `MerchantOrder` per
shop and an `OrderItem` per line, with names and prices copied so later catalogue
edits do not change history. Everything runs in one transaction: a rejected
checkout changes nothing, so the client may retry with the same key.

Concurrency: the user's row is locked first, so two checkouts by one user run one
after the other, and the second sees the first's order under the same key. Product
rows are then locked in primary-key order, so checkouts by different users that
share products wait for each other instead of deadlocking. Merchant product edits
take the same product lock, so they never save stock read before a checkout.

Payment is simulated. No money moves; the `SIM-` reference says so.
"""

import uuid
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import CartItem, MerchantOrder, Order, OrderItem, Product


class CartEmpty(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "cart_empty"
    default_detail = "Your basket is empty."


class ProductUnavailable(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "product_unavailable"
    default_detail = "An item in your basket is no longer available."


class InsufficientStock(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "insufficient_stock"
    default_detail = "An item in your basket does not have enough stock."


def find_order(user, key: str) -> Order | None:
    return Order.objects.filter(user=user, idempotency_key=key).first()


def place_order(user, shipping: dict, key: str) -> tuple[Order, bool]:
    """Return (order, created). A key the user already used returns its order."""
    existing = find_order(user, key)
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            # Serialises this user's checkouts; re-check the key once we hold it
            get_user_model().objects.select_for_update().filter(pk=user.pk).first()
            existing = find_order(user, key)
            if existing is not None:
                return existing, False
            return _create_order(user, shipping, key), True
    except IntegrityError:
        # Defensive: the unique (user, key) constraint caught a concurrent insert
        existing = find_order(user, key)
        if existing is None:
            raise
        return existing, False


def _create_order(user, shipping: dict, key: str) -> Order:
    lines = list(CartItem.objects.filter(user=user).order_by("product_id"))
    if not lines:
        raise CartEmpty()

    products = {
        p.pk: p
        for p in Product.objects.select_for_update(of=("self",))
        .select_related("merchant")
        .filter(pk__in=[line.product_id for line in lines])
        .order_by("pk")
    }
    for line in lines:
        _check_line(products[line.product_id], line.quantity)

    by_merchant = defaultdict(list)
    for line in lines:
        product = products[line.product_id]
        by_merchant[product.merchant].append((product, line.quantity))

    order = Order.objects.create(
        user=user,
        total_cents=sum(p.price_cents * q for p, q in _all(by_merchant)),
        idempotency_key=key,
        **shipping,
    )
    order_items = []
    for merchant in sorted(by_merchant, key=lambda m: (m.name, m.pk)):
        rows = by_merchant[merchant]
        merchant_order = MerchantOrder.objects.create(
            order=order,
            merchant=merchant,
            subtotal_cents=sum(p.price_cents * q for p, q in rows),
        )
        order_items += [
            OrderItem(
                merchant_order=merchant_order,
                product=product,
                product_name=product.name,
                unit_price_cents=product.price_cents,
                quantity=quantity,
            )
            for product, quantity in rows
        ]
    OrderItem.objects.bulk_create(order_items)

    now = timezone.now()
    for product, quantity in _all(by_merchant):
        product.stock -= quantity
        product.updated_at = now
    Product.objects.bulk_update(
        [p for p, _ in _all(by_merchant)], ["stock", "updated_at"]
    )
    CartItem.objects.filter(user=user).delete()

    simulate_payment(order)
    return order


def _check_line(product: Product, quantity: int) -> None:
    where = f"{product.name} from {product.merchant.name}"
    if not (product.active and product.merchant.active):
        raise ProductUnavailable(
            f"{where} is no longer available. Remove it from your basket to continue."
        )
    if product.stock == 0:
        raise InsufficientStock(
            f"{where} is out of stock. Remove it from your basket to continue."
        )
    if quantity > product.stock:
        raise InsufficientStock(
            f"Only {product.stock} of {where} left. "
            "Lower the quantity in your basket to continue."
        )


def _all(by_merchant):
    return (row for rows in by_merchant.values() for row in rows)


def simulate_payment(order: Order) -> None:
    """Mark the order paid. Simulated: nothing is charged."""
    order.payment_ref = f"SIM-{uuid.uuid4().hex[:12].upper()}"
    order.paid_at = timezone.now()
    order.status = Order.PAID
    order.save(update_fields=["payment_ref", "paid_at", "status"])
    order.merchant_orders.update(status=MerchantOrder.PAID)
