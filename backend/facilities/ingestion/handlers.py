import os

from facilities.ingestion.fetch import handler as fetch_handler
from facilities.ingestion.geocoding import handler as geocode_handler


def fetch(event, context):
    return fetch_handler(event, context)


def geocode(event, context):
    return geocode_handler(event, context)


def load(event, context):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from facilities.ingestion.loading import load_s3_event

    return load_s3_event(event)


def reconcile(event, context):
    from facilities.ingestion.recovery import handler

    return handler(event, context)


def failure(event, context):
    from facilities.ingestion.recovery import failure_handler

    return failure_handler(event, context)
