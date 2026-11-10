from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.authentication import get_dev_user
from marketplace.models import Merchant


class Command(BaseCommand):
    help = "Assign an unowned demo shop to Mira for local merchant testing."

    def add_arguments(self, parser):
        parser.add_argument("--shop", default="harbour-paws")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEV_AUTH_ENABLED:
            raise CommandError(
                "seed_merchant requires local DJANGO_DEBUG=True and DJANGO_DEV_AUTH=true."
            )
        shop = (
            Merchant.objects.select_for_update()
            .filter(slug=options["shop"], active=True)
            .first()
        )
        if shop is None:
            raise CommandError("Shop not found. Run load_catalogue first.")
        user = get_dev_user("mira")
        if shop.owner_id not in (None, user.pk):
            raise CommandError("This shop already belongs to another user.")
        shop.owner = user
        shop.save(update_fields=["owner"])
        self.stdout.write(self.style.SUCCESS(f"Mira now manages {shop.name}."))
