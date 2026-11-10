import threading
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase

from . import checkout
from .models import CartItem, Merchant, MerchantOrder, Order, OrderItem, Product
from .serializers import MerchantProductUpdateSerializer
from .test_cart import API, MarketplaceFixtures

SHIPPING = {
    "shipping_name": "Alice Tan",
    "shipping_phone": "+6591234567",
    "shipping_address": "1 Pet Lane, #01-01",
    "shipping_postal_code": "123456",
}
KEY = "checkout-key-0001"


class CheckoutApiTests(MarketplaceFixtures, APITestCase):
    def setUp(self):
        self.make_fixtures()
        self.client.force_authenticate(self.alice)

    def checkout(self, key=KEY, data=SHIPPING):
        headers = {"Idempotency-Key": key} if key is not None else {}
        return self.client.post(API + "checkout/", data, format="json", headers=headers)

    def test_requires_sign_in(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.checkout().status_code, 401)

    def test_multi_merchant_checkout(self):
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.treats, 1)
        self.add(self.alice, self.toy, 3)
        self.add(self.bob, self.kibble, 1)

        response = self.checkout()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        self.assertEqual(body["status"], "paid")
        self.assertEqual(body["total_cents"], 2 * 2200 + 650 + 3 * 900)
        self.assertRegex(body["payment_ref"], r"^SIM-[0-9A-F]{12}$")
        self.assertIsNotNone(body["paid_at"])
        self.assertNotIn("idempotency_key", body)
        for field, value in SHIPPING.items():
            self.assertEqual(body[field], value)

        groups = body["merchant_orders"]
        self.assertEqual(
            [(g["merchant"]["slug"], g["status"], g["subtotal_cents"]) for g in groups],
            [("harbour", "paid", 2 * 2200 + 650), ("island", "paid", 3 * 900)],
        )
        self.assertEqual(
            groups[0]["items"],
            [
                {
                    "product": self.kibble.pk,
                    "product_name": "Salmon kibble",
                    "unit_price_cents": 2200,
                    "quantity": 2,
                },
                {
                    "product": self.treats.pk,
                    "product_name": "Chicken treats",
                    "unit_price_cents": 650,
                    "quantity": 1,
                },
            ],
        )

        stock = dict(Product.objects.values_list("pk", "stock"))
        self.assertEqual(stock[self.kibble.pk], 3)
        self.assertEqual(stock[self.treats.pk], 9)
        self.assertEqual(stock[self.toy.pk], 0)
        self.assertFalse(CartItem.objects.filter(user=self.alice).exists())
        self.assertTrue(CartItem.objects.filter(user=self.bob).exists())

    def test_order_keeps_prices_after_catalogue_edits(self):
        self.add(self.alice, self.kibble, 1)
        order_id = self.checkout().json()["id"]
        Product.objects.filter(pk=self.kibble.pk).update(
            name="Renamed", price_cents=9999
        )

        body = self.client.get(API + f"orders/{order_id}/").json()
        item = body["merchant_orders"][0]["items"][0]
        self.assertEqual(
            (item["product_name"], item["unit_price_cents"]), ("Salmon kibble", 2200)
        )
        self.assertEqual(body["total_cents"], 2200)

    def test_same_key_returns_same_order(self):
        self.add(self.alice, self.kibble, 2)
        first = self.checkout()
        # The cart is empty now, so a second order could not be placed anyway;
        # add an item to prove the retry does not place one
        self.add(self.alice, self.toy, 1)
        retry = self.checkout()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Product.objects.get(pk=self.kibble.pk).stock, 3)
        self.assertTrue(CartItem.objects.filter(product=self.toy).exists())

    def test_keys_are_per_user(self):
        self.add(self.alice, self.kibble, 1)
        self.add(self.bob, self.toy, 1)
        self.checkout()
        self.client.force_authenticate(self.bob)

        response = self.checkout()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["merchant_orders"][0]["merchant"]["slug"], "island"
        )
        self.assertEqual(Order.objects.count(), 2)

    def test_new_key_with_empty_cart(self):
        self.add(self.alice, self.kibble, 1)
        self.checkout()
        response = self.checkout(key="checkout-key-0002")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "cart_empty")
        self.assertEqual(response.json()["error"]["message"], "Your basket is empty.")

    def test_rejects_missing_or_malformed_key(self):
        self.add(self.alice, self.kibble, 1)
        for key in (None, "", "short", "has spaces in it", "x" * 81):
            with self.subTest(key=key):
                response = self.checkout(key=key)
                self.assertEqual(response.status_code, 400)
                self.assertIn("idempotency_key", response.json()["error"]["details"])
        self.assertFalse(Order.objects.exists())

    def test_validates_shipping(self):
        self.add(self.alice, self.kibble, 1)
        cases = {
            "shipping_name": "",
            "shipping_phone": "12ab",
            "shipping_address": "",
            "shipping_postal_code": "12345",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                response = self.checkout(data={**SHIPPING, field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["error"]["details"])
        self.assertFalse(Order.objects.exists())

    def assert_rejected(self, response, code, message):
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], code)
        self.assertEqual(response.json()["error"]["message"], message)
        # Nothing changed: no order, stock and cart untouched
        self.assertFalse(Order.objects.exists())
        self.assertFalse(MerchantOrder.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.assertEqual(Product.objects.get(pk=self.kibble.pk).stock, 5)
        self.assertEqual(CartItem.objects.filter(user=self.alice).count(), 2)

    def test_rejects_stock_shortfall_atomically(self):
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.toy, 3)
        Product.objects.filter(pk=self.toy.pk).update(stock=2)
        self.assert_rejected(
            self.checkout(),
            "insufficient_stock",
            "Only 2 of Rope toy from Island Pets left. "
            "Lower the quantity in your basket to continue.",
        )

    def test_rejects_sold_out_item(self):
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.toy, 1)
        Product.objects.filter(pk=self.toy.pk).update(stock=0)
        self.assert_rejected(
            self.checkout(),
            "insufficient_stock",
            "Rope toy from Island Pets is out of stock. "
            "Remove it from your basket to continue.",
        )

    def test_rejects_withdrawn_product_or_closed_shop(self):
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.toy, 1)
        message = (
            "Rope toy from Island Pets is no longer available. "
            "Remove it from your basket to continue."
        )
        Product.objects.filter(pk=self.toy.pk).update(active=False)
        self.assert_rejected(self.checkout(), "product_unavailable", message)

        Product.objects.filter(pk=self.toy.pk).update(active=True)
        self.island.active = False
        self.island.save()
        self.assert_rejected(self.checkout(), "product_unavailable", message)

    def test_failed_checkout_can_retry_with_same_key(self):
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.toy, 4)
        self.assertEqual(self.checkout().status_code, 409)
        CartItem.objects.filter(product=self.toy).update(quantity=3)
        self.assertEqual(self.checkout().status_code, 201)


class OrderApiTests(MarketplaceFixtures, APITestCase):
    def setUp(self):
        self.make_fixtures()

    def place(self, user, product, key):
        self.add(user, product, 1)
        order, _ = checkout.place_order(user, SHIPPING, key)
        return order

    def test_requires_sign_in(self):
        order = self.place(self.alice, self.kibble, KEY)
        for path in ("orders/", f"orders/{order.pk}/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(API + path).status_code, 401)

    def test_lists_own_orders_newest_first(self):
        first = self.place(self.alice, self.kibble, "alice-key-0001")
        second = self.place(self.alice, self.toy, "alice-key-0002")
        self.place(self.bob, self.treats, "bob-key-00001")
        self.client.force_authenticate(self.alice)

        response = self.client.get(API + "orders/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual([o["id"] for o in body["results"]], [second.pk, first.pk])
        self.assertEqual(
            body["results"][0]["merchant_orders"][0]["merchant"]["slug"], "island"
        )

    def test_detail_hides_other_users_orders(self):
        mine = self.place(self.alice, self.kibble, "alice-key-0001")
        theirs = self.place(self.bob, self.toy, "bob-key-00001")
        self.client.force_authenticate(self.alice)

        self.assertEqual(self.client.get(API + f"orders/{mine.pk}/").status_code, 200)
        response = self.client.get(API + f"orders/{theirs.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_orders_are_read_only(self):
        order = self.place(self.alice, self.kibble, KEY)
        self.client.force_authenticate(self.alice)
        for method in ("post", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(API + f"orders/{order.pk}/")
                self.assertEqual(response.status_code, 405)


class ConcurrentCheckoutTests(MarketplaceFixtures, TransactionTestCase):
    """Real transactions, so row locks and the unique key are exercised."""

    def setUp(self):
        self.make_fixtures()

    def run_together(self, *jobs):
        barrier = threading.Barrier(len(jobs))
        results = [None] * len(jobs)

        def run(i, user, key):
            client = APIClient()
            client.force_authenticate(user)
            barrier.wait()
            try:
                results[i] = client.post(
                    API + "checkout/",
                    SHIPPING,
                    format="json",
                    headers={"Idempotency-Key": key},
                ).status_code
            finally:
                connection.close()

        threads = [
            threading.Thread(target=run, args=(i, *job)) for i, job in enumerate(jobs)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return sorted(results)

    def test_double_submit_places_one_order(self):
        self.add(self.alice, self.kibble, 2)
        statuses = self.run_together((self.alice, KEY), (self.alice, KEY))
        self.assertEqual(statuses, [200, 201])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Product.objects.get(pk=self.kibble.pk).stock, 3)

    def test_two_buyers_cannot_oversell(self):
        self.add(self.alice, self.toy, 2)
        self.add(self.bob, self.toy, 2)
        statuses = self.run_together(
            (self.alice, "alice-key-0001"), (self.bob, "bob-key-00001")
        )
        self.assertEqual(statuses, [201, 409])
        self.assertEqual(Product.objects.get(pk=self.toy.pk).stock, 1)

    def overlap(self, pause_at, first, second):
        """Pause `first` at `pause_at`, run `second`, then let `first` finish.

        `first` resumes once `second` is done, or once `second` is blocked on a
        lock, which means `first` holds it. Each job is (user, send(client)).
        """
        owner, name = pause_at
        original = getattr(owner, name)
        paused, second_done = threading.Event(), threading.Event()

        def second_is_blocked():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE NOT granted)"
                )
                return cursor.fetchone()[0]

        def pause(*args, **kwargs):
            paused.set()
            deadline = time.monotonic() + 30
            while not (second_done.is_set() or second_is_blocked()):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.05)
            return original(*args, **kwargs)

        results = {}

        def run(label, user, send):
            client = APIClient()
            client.force_authenticate(user)
            try:
                results[label] = send(client).status_code
            finally:
                connection.close()
                if label == "second":
                    second_done.set()

        with mock.patch.object(owner, name, pause):
            a = threading.Thread(target=run, args=("first", *first))
            a.start()
            self.assertTrue(paused.wait(timeout=30))
            b = threading.Thread(target=run, args=("second", *second))
            b.start()
            a.join()
            b.join()
        return results["first"], results["second"]

    def checkout_as(self, key):
        return lambda client: client.post(
            API + "checkout/",
            SHIPPING,
            format="json",
            headers={"Idempotency-Key": key},
        )

    def test_price_edit_during_checkout_keeps_sold_stock(self):
        owner = get_user_model().objects.create_user(username="harbour-owner")
        Merchant.objects.filter(pk=self.harbour.pk).update(owner=owner)
        self.add(self.alice, self.kibble, 2)

        def edit_price(client):
            return client.patch(
                API + f"merchant/products/{self.kibble.pk}/",
                {"price_cents": 2400},
                format="json",
            )

        statuses = self.overlap(
            (MerchantProductUpdateSerializer, "update"),
            (owner, edit_price),
            (self.alice, self.checkout_as(KEY)),
        )
        self.assertEqual(statuses, (200, 201))
        kibble = Product.objects.get(pk=self.kibble.pk)
        self.assertEqual((kibble.price_cents, kibble.stock), (2400, 3))
