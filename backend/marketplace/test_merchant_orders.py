from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework.test import APITestCase

from api.authentication import get_dev_user

from . import checkout
from .models import MerchantOrder
from .test_cart import API, MarketplaceFixtures

SHIPPING = {
    "shipping_name": "Demo Owner",
    "shipping_phone": "81234567",
    "shipping_address": "123 Test Street",
    "shipping_postal_code": "123456",
}


class MerchantOrderTests(MarketplaceFixtures, APITestCase):
    def setUp(self):
        self.make_fixtures()
        self.harbour.owner = self.bob
        self.harbour.save()
        self.island.owner = self.alice
        self.island.save()
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.toy, 1)
        order, _ = checkout.place_order(self.alice, SHIPPING, "merchant-test-0001")
        self.mine = order.merchant_orders.get(merchant=self.harbour)
        self.theirs = order.merchant_orders.get(merchant=self.island)
        self.client.force_authenticate(self.bob)

    def test_list_contains_only_owned_suborders_and_frontend_fields(self):
        response = self.client.get(API + "merchant/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        rows = response.json()["results"]
        self.assertEqual([row["id"] for row in rows], [self.mine.pk])
        self.assertEqual(rows[0]["subtotal_cents"], 4400)
        self.assertEqual(rows[0]["merchant"]["id"], self.harbour.pk)
        self.assertEqual(rows[0]["items"][0]["quantity"], 2)
        self.assertIn("created_at", rows[0])
        self.assertNotIn("shipping_address", rows[0])

    def test_fulfilment_requires_each_transition_and_preserves_customer_order(self):
        for status in ("processing", "shipped", "delivered"):
            response = self.client.patch(
                API + f"merchant/orders/{self.mine.pk}/",
                {"status": status},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], status)
        self.mine.order.refresh_from_db()
        self.theirs.refresh_from_db()
        self.assertEqual(self.mine.order.status, "paid")
        self.assertEqual(self.theirs.status, "paid")

    def test_cannot_skip_reverse_repeat_or_cancel(self):
        for status in ("shipped", "delivered", "paid", "cancelled", "unknown"):
            response = self.client.patch(
                API + f"merchant/orders/{self.mine.pk}/",
                {"status": status},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, MerchantOrder.PAID)

    def test_foreign_suborder_is_hidden(self):
        response = self.client.patch(
            API + f"merchant/orders/{self.theirs.pk}/",
            {"status": "processing"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_nonmerchant_and_inactive_shop_are_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(API + "merchant/orders/").status_code, 401)
        self.harbour.active = False
        self.harbour.save()
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get(API + "merchant/orders/").status_code, 403)
        self.assertEqual(
            self.client.patch(
                API + f"merchant/orders/{self.mine.pk}/",
                {"status": "processing"},
                format="json",
            ).status_code,
            403,
        )


class SeedMerchantTests(MarketplaceFixtures, APITestCase):
    def setUp(self):
        self.make_fixtures()

    @override_settings(DEV_AUTH_ENABLED=True)
    def test_links_mira_idempotently_without_resetting_products(self):
        for _ in range(2):
            call_command("seed_merchant", shop="harbour", stdout=StringIO())
        self.harbour.refresh_from_db()
        self.kibble.refresh_from_db()
        self.assertEqual(self.harbour.owner, get_dev_user("mira"))
        self.assertEqual(self.kibble.stock, 5)

    @override_settings(DEV_AUTH_ENABLED=True)
    def test_does_not_take_another_users_shop(self):
        self.harbour.owner = self.alice
        self.harbour.save()
        with self.assertRaises(CommandError):
            call_command("seed_merchant", shop="harbour", stdout=StringIO())
        self.harbour.refresh_from_db()
        self.assertEqual(self.harbour.owner, self.alice)

    @override_settings(DEV_AUTH_ENABLED=False)
    def test_requires_local_dev_auth(self):
        with self.assertRaises(CommandError):
            call_command("seed_merchant", shop="harbour", stdout=StringIO())
