from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Category, Merchant, Product

User = get_user_model()


class MerchantProductApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="shop-owner")
        self.other = User.objects.create_user(username="other-owner")
        self.customer = User.objects.create_user(username="customer")
        self.category = Category.objects.create(name="Treats", slug="treats")
        self.shop = Merchant.objects.create(
            name="The Happy Tail", slug="happy-tail", owner=self.owner
        )
        self.other_shop = Merchant.objects.create(
            name="Whisker & Co.", slug="whisker", owner=self.other
        )
        self.own_product = Product.objects.create(
            merchant=self.shop,
            category=self.category,
            name="Dental chews",
            slug="dental-chews",
            price_cents=1290,
            stock=12,
        )
        self.other_product = Product.objects.create(
            merchant=self.other_shop,
            category=self.category,
            name="Salmon bites",
            slug="salmon-bites",
            price_cents=1500,
            stock=4,
        )

    def test_anonymous_is_unauthorized(self):
        response = self.client.get("/api/v1/merchant/products/")
        self.assertEqual(response.status_code, 401)

    def test_non_merchant_is_forbidden(self):
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/v1/merchant/products/")
        self.assertEqual(response.status_code, 403)

    def test_list_only_own_active_products(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/v1/merchant/products/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()["results"]]
        self.assertEqual(ids, [self.own_product.pk])

    def test_create_assigns_owner_shop(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/merchant/products/",
            {
                "name": "House-brand dental chews",
                "description": "Everyday treats",
                "category": self.category.pk,
                "price_cents": 1290,
                "stock": 12,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "House-brand dental chews")
        self.assertEqual(body["merchant"]["id"], self.shop.pk)
        product = Product.objects.get(pk=body["id"])
        self.assertEqual(product.merchant, self.shop)
        self.assertEqual(product.slug, "house-brand-dental-chews")

    def test_patch_price_and_stock(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            f"/api/v1/merchant/products/{self.own_product.pk}/",
            {"price_cents": 1400, "stock": 3},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.own_product.refresh_from_db()
        self.assertEqual(self.own_product.price_cents, 1400)
        self.assertEqual(self.own_product.stock, 3)

    def test_cannot_edit_another_merchant_product(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            f"/api/v1/merchant/products/{self.other_product.pk}/",
            {"price_cents": 1, "stock": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.other_product.refresh_from_db()
        self.assertEqual(self.other_product.price_cents, 1500)

    def test_delete_hides_own_product(self):
        self.client.force_authenticate(self.owner)
        response = self.client.delete(
            f"/api/v1/merchant/products/{self.own_product.pk}/"
        )
        self.assertEqual(response.status_code, 204)
        self.own_product.refresh_from_db()
        self.assertFalse(self.own_product.active)
        listed = self.client.get("/api/v1/merchant/products/")
        self.assertEqual(listed.json()["results"], [])

    def test_cannot_delete_another_merchant_product(self):
        self.client.force_authenticate(self.owner)
        response = self.client.delete(
            f"/api/v1/merchant/products/{self.other_product.pk}/"
        )
        self.assertEqual(response.status_code, 404)
        self.other_product.refresh_from_db()
        self.assertTrue(self.other_product.active)

    def test_me_includes_owned_merchant(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["merchant"],
            {"id": self.shop.pk, "name": "The Happy Tail", "slug": "happy-tail"},
        )
