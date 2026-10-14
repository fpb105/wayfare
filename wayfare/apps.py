from django.apps import AppConfig


class WayfareConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wayfare'

    def ready(self):
            from . import signals



    