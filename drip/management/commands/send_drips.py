from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        from drip.models import Drip
        Drip.objects.filter(enabled=True).send()
