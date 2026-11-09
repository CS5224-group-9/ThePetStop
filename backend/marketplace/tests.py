from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from config.lambda_handler import manage

from .models import Category, Merchant, Product, ProductGroup

User = get_user_model()


class CatalogueApiTests(APITestCase):
    def setUp(self):
        self.food = Category.objects.create(name="Food", slug="food")
        self.treats = Category.objects.create(name="Treats", slug="treats")
        self.shop = Merchant.objects.create(name="Harbour Paws", slug="harbour-paws")
        self.other_shop = Merchant.objects.create(
            name="Little Paws", slug="little-paws"
        )
        self.inactive_shop = Merchant.objects.create(
            name="Closed Shop", slug="closed-shop", active=False
        )
        self.group = ProductGroup.objects.create(
            canonical_name="Salmon food for cats, 2 kg"
        )
        self.product = Product.objects.create(
            merchant=self.shop,
            category=self.food,
            group=self.group,
            name="Salmon recipe",
            slug="salmon-recipe",
            description="Complete dry food for indoor cats",
            species="cat",
            size="2 kg",
            price_cents=2200,
            stock=5,
        )
        self.other_offer = Product.objects.create(
            merchant=self.other_shop,
            category=self.food,
            group=self.group,
            name="Salmon recipe 2 kg",
            slug="salmon-recipe-2-kg",
            description="Fictional matching catalogue item",
            species="cat",
            size="2 kg",
            price_cents=1800,
            stock=0,
        )
        Product.objects.create(
            merchant=self.inactive_shop,
            category=self.food,
            group=self.group,
            name="Hidden offer",
            slug="hidden-offer",
            price_cents=1000,
            stock=10,
        )
        Product.objects.create(
            merchant=self.shop,
            category=self.treats,
            name="Chicken bites",
            slug="chicken-bites",
            description="Training treats for dogs",
            species="dog",
            size="80 g",
            price_cents=900,
            stock=12,
        )

    def test_product_search_and_filters_are_applied_together(self):
        response = self.client.get(
            "/api/v1/products/",
            {
                "q": "  indoor cats  ",
                "category": "food",
                "merchant": "harbour-paws",
                "min_price": "2000",
                "max_price": "2300",
                "species": "cat",
                "sort": "price_asc",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.product.pk)
        self.assertEqual(response.data["results"][0]["size"], "2 kg")

    def test_product_detail_returns_active_comparable_offers_with_own_specs(self):
        response = self.client.get(f"/api/v1/products/{self.product.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["also_sold_by"][0]["id"], self.other_offer.pk)
        self.assertEqual(response.data["also_sold_by"][0]["name"], "Salmon recipe 2 kg")
        self.assertEqual(response.data["also_sold_by"][0]["size"], "2 kg")
        self.assertEqual(response.data["also_sold_by"][0]["species"], "cat")
        self.assertEqual(
            response.data["also_sold_by"][0]["merchant"]["slug"], "little-paws"
        )
        self.assertNotIn(
            "closed-shop",
            [offer["merchant"]["slug"] for offer in response.data["also_sold_by"]],
        )

    def test_merchant_storefront_lists_only_its_active_products(self):
        response = self.client.get("/api/v1/merchants/harbour-paws/products/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            {row["merchant"]["slug"] for row in response.data["results"]},
            {"harbour-paws"},
        )

    def test_unknown_merchant_storefront_returns_not_found(self):
        response = self.client.get("/api/v1/merchants/not-a-shop/products/")

        self.assertEqual(response.status_code, 404)


class LoadCatalogueTests(TestCase):
    def test_manage_lambda_loads_fixtures_repeatably(self):
        manage({"command": "load_catalogue"}, None)
        counts = (Merchant.objects.count(), Product.objects.count())
        result = manage({"command": "load_catalogue"}, None)

        self.assertIn("Catalogue loaded", result["output"])
        self.assertGreater(counts[1], 0)
        self.assertEqual((Merchant.objects.count(), Product.objects.count()), counts)


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
