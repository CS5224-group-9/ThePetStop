import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from marketplace.models import Category, Merchant, Product, ProductGroup


class Command(BaseCommand):
    help = "Load the fictional marketplace catalogue fixtures (safe to run repeatedly)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture-dir",
            default=str(
                Path(settings.BASE_DIR) / "marketplace" / "fixtures" / "catalogue"
            ),
            help="Catalogue fixture directory",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        root = Path(options["fixture_dir"])
        try:
            categories = json.loads(
                (root / "categories.json").read_text(encoding="utf-8")
            )
            groups = json.loads(
                (root / "product_groups.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read catalogue shared fixtures: {exc}") from exc

        for row in categories:
            Category.objects.update_or_create(
                slug=row["slug"],
                defaults={"name": row["name"], "sort_order": row["sort_order"]},
            )
        for row in groups:
            ProductGroup.objects.update_or_create(
                canonical_name=row["canonical_name"], defaults={}
            )

        merchant_files = sorted((root / "merchants").glob("shop-*.json"))
        for fixture in merchant_files:
            try:
                payload = json.loads(fixture.read_text(encoding="utf-8"))
                merchant_data = payload["merchant"]
            except (OSError, json.JSONDecodeError, KeyError) as exc:
                raise CommandError(
                    f"Invalid merchant fixture {fixture.name}: {exc}"
                ) from exc
            merchant, _ = Merchant.objects.update_or_create(
                slug=merchant_data["slug"],
                defaults={
                    "name": merchant_data["name"],
                    "description": merchant_data.get("description", ""),
                    "logo_key": merchant_data.get("logo_key", ""),
                    "active": merchant_data.get("active", True),
                },
            )
            for row in payload.get("products", []):
                try:
                    category = Category.objects.get(slug=row["category"])
                    group = (
                        ProductGroup.objects.get(canonical_name=row["group"])
                        if row.get("group")
                        else None
                    )
                    Product.objects.update_or_create(
                        merchant=merchant,
                        slug=row["slug"],
                        defaults={
                            "category": category,
                            "group": group,
                            "name": row["name"],
                            "description": row.get("description", ""),
                            "species": row.get("species", "all pets"),
                            "size": row.get("size", ""),
                            "price_cents": row["price_cents"],
                            "stock": row.get("stock", 0),
                            "image_key": row.get("image_key", ""),
                            "product_type": row.get("product_type", Product.PRODUCT),
                            "duration_minutes": row.get("duration_minutes"),
                            "active": row.get("active", True),
                        },
                    )
                except (
                    KeyError,
                    Category.DoesNotExist,
                    ProductGroup.DoesNotExist,
                ) as exc:
                    raise CommandError(
                        f"Invalid product in {fixture.name}: {row.get('slug', '(no slug)')}: {exc}"
                    ) from exc
            count = len(payload.get("products", []))
            self.stdout.write(f"Loaded {merchant.name}: {count} products")

        self.stdout.write(
            self.style.SUCCESS(
                f"Catalogue loaded: {Category.objects.count()} categories, "
                f"{ProductGroup.objects.count()} product groups, "
                f"{Merchant.objects.filter(active=True).count()} active merchants."
            )
        )
