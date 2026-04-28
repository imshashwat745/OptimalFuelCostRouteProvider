from django.apps import AppConfig


class SpotterConfig(AppConfig):
    name = 'spotter'

    def ready(self):
        """Pre-warm station cache + spatial index at startup."""
        import os
        from django.conf import settings
        from .core.config import FUEL_CSV_FILENAME
        csv_path = os.path.join(settings.BASE_DIR, "spotter", "data", FUEL_CSV_FILENAME)
        try:
            from .utils.routing import _load_stations_cached
            _load_stations_cached(csv_path)
        except Exception:
            pass  # Don't crash startup if CSV is missing
