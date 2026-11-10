from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import CartItem, Category, Merchant, Product

API = "/api/v1/"


class MarketplaceFixtures:
    """Two shops, three products and two users, shared by the order tests."""

    def make_fixtures(self):
        users = get_user_model().objects
        self.alice = users.create_user(username="alice", email="alice@example.test")
        self.bob = users.create_user(username="bob", email="bob@example.test")
        self.food = Category.objects.create(name="Food", slug="food")
        self.harbour = Merchant.objects.create(name="Harbour Paws", slug="harbour")
        self.island = Merchant.objects.create(name="Island Pets", slug="island")
        self.kibble = self.product(self.harbour, "Salmon kibble", 2200, stock=5)
        self.treats = self.product(self.harbour, "Chicken treats", 650, stock=10)
        self.toy = self.product(self.island, "Rope toy", 900, stock=3)

    def product(self, merchant, name, price_cents, stock, **extra):
        return Product.objects.create(
            merchant=merchant,
            category=self.food,
            name=name,
            slug=name.lower().replace(" ", "-"),
            price_cents=price_cents,
            stock=stock,
            **extra,
        )

    def add(self, user, product, quantity):
        return CartItem.objects.create(user=user, product=product, quantity=quantity)


class CartApiTests(MarketplaceFixtures, APITestCase):
    def setUp(self):
        self.make_fixtures()
        self.client.force_authenticate(self.alice)

    def test_requires_sign_in(self):
        self.client.force_authenticate(None)
        for method, path in (
            ("get", "cart/"),
            ("delete", "cart/"),
            ("post", "cart/items/"),
            ("patch", f"cart/items/{self.kibble.pk}/"),
            ("delete", f"cart/items/{self.kibble.pk}/"),
        ):
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(API + path)
                self.assertEqual(response.status_code, 401)

    def test_empty_cart(self):
        response = self.client.get(API + "cart/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"merchants": [], "total_cents": 0})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_cart_groups_lines_by_merchant(self):
        self.add(self.alice, self.toy, 1)
        self.add(self.alice, self.kibble, 2)
        self.add(self.alice, self.treats, 1)
        self.add(self.bob, self.kibble, 4)

        body = self.client.get(API + "cart/").json()

        self.assertEqual(body["total_cents"], 2 * 2200 + 650 + 900)
        self.assertEqual(
            [g["merchant"] for g in body["merchants"]],
            [
                {"id": self.harbour.pk, "name": "Harbour Paws", "slug": "harbour"},
                {"id": self.island.pk, "name": "Island Pets", "slug": "island"},
            ],
        )
        harbour_items = body["merchants"][0]["items"]
        self.assertEqual(
            [(i["product"]["id"], i["quantity"]) for i in harbour_items],
            [(self.treats.pk, 1), (self.kibble.pk, 2)],
        )
        product = harbour_items[1]["product"]
        self.assertEqual(product["price_cents"], 2200)
        self.assertEqual(product["stock"], 5)
        self.assertEqual(product["category"]["slug"], "food")

    def test_add_creates_then_increases_quantity(self):
        response = self.client.post(
            API + "cart/items/", {"product": self.kibble.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["total_cents"], 2200)

        self.client.post(
            API + "cart/items/",
            {"product": self.kibble.pk, "quantity": 3},
            format="json",
        )
        self.assertEqual(
            CartItem.objects.get(user=self.alice, product=self.kibble).quantity, 4
        )

    def test_add_rejects_more_than_stock(self):
        self.add(self.alice, self.kibble, 4)
        response = self.client.post(
            API + "cart/items/",
            {"product": self.kibble.pk, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["details"],
            {"quantity": ["Only 5 left in stock."]},
        )
        self.assertEqual(CartItem.objects.get(product=self.kibble).quantity, 4)

    def test_add_rejects_out_of_stock(self):
        empty = self.product(self.harbour, "Sold out bed", 4000, stock=0)
        response = self.client.post(
            API + "cart/items/", {"product": empty.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["details"],
            {"quantity": ["This item is out of stock."]},
        )

    def test_add_rejects_inactive_and_unknown_products(self):
        hidden = self.product(self.harbour, "Hidden", 100, stock=5, active=False)
        closed_shop = Merchant.objects.create(name="Closed", slug="c", active=False)
        closed = self.product(closed_shop, "Closed item", 100, stock=5)
        for product_id in (hidden.pk, closed.pk, 999999):
            with self.subTest(product_id=product_id):
                response = self.client.post(
                    API + "cart/items/", {"product": product_id}, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("product", response.json()["error"]["details"])
        self.assertFalse(CartItem.objects.exists())

    def test_add_rejects_bad_quantities(self):
        for quantity in (0, -1, 100, "two"):
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    API + "cart/items/",
                    {"product": self.treats.pk, "quantity": quantity},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("quantity", response.json()["error"]["details"])

    def test_add_caps_total_quantity(self):
        big = self.product(self.harbour, "Bulk pads", 100, stock=500)
        self.add(self.alice, big, 98)
        response = self.client.post(
            API + "cart/items/", {"product": big.pk, "quantity": 2}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_sets_quantity(self):
        self.add(self.alice, self.kibble, 1)
        response = self.client.patch(
            API + f"cart/items/{self.kibble.pk}/", {"quantity": 3}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_cents"], 3 * 2200)

    def test_patch_validates_quantity_and_stock(self):
        self.add(self.alice, self.kibble, 1)
        for quantity, status in ((0, 400), (6, 400), (5, 200)):
            with self.subTest(quantity=quantity):
                response = self.client.patch(
                    API + f"cart/items/{self.kibble.pk}/",
                    {"quantity": quantity},
                    format="json",
                )
                self.assertEqual(response.status_code, status)

    def test_patch_rejects_product_withdrawn_since_added(self):
        self.add(self.alice, self.kibble, 1)
        Product.objects.filter(pk=self.kibble.pk).update(active=False)
        response = self.client.patch(
            API + f"cart/items/{self.kibble.pk}/", {"quantity": 2}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.json()["error"]["details"])

    def test_item_routes_only_touch_own_cart(self):
        self.add(self.bob, self.kibble, 2)
        patch = self.client.patch(
            API + f"cart/items/{self.kibble.pk}/", {"quantity": 1}, format="json"
        )
        delete = self.client.delete(API + f"cart/items/{self.kibble.pk}/")
        self.assertEqual(patch.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        self.assertEqual(CartItem.objects.get(user=self.bob).quantity, 2)

    def test_delete_item_and_empty_cart(self):
        self.add(self.alice, self.kibble, 1)
        self.add(self.alice, self.toy, 1)
        self.add(self.bob, self.toy, 1)

        response = self.client.delete(API + f"cart/items/{self.kibble.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            list(CartItem.objects.filter(user=self.alice).values_list("product")),
            [(self.toy.pk,)],
        )

        response = self.client.delete(API + "cart/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(CartItem.objects.filter(user=self.alice).exists())
        self.assertTrue(CartItem.objects.filter(user=self.bob).exists())
