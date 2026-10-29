from rest_framework.test import APITestCase

from .models import Category, Merchant, Product, ProductGroup


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
