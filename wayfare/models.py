from django.conf import settings
from django.db import models
#from django.contrib.auth.models import User   use settings.AUTH_USER_MODEL as it is on documentation

# Create your models here.
class Intrests(models.Model):
    intrests = models.CharField(max_length=255, unique=True)

class Profile(models.Model):
    class UserPreference(models.TextChoices):
        BUDGET = 'BUDGET', 'Budget'
        COMFORT = 'COMFORT', 'Comfort'
        LUXURY = 'LUXURY', 'Luxury'

    author = models.OneToOneField(settings.AUTH_USER_MODEL, 
                                  on_delete=models.CASCADE, 
                                  related_name="profile")
    intrests = models.ManyToManyField(Intrests, blank=True)
    home = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=3, blank=True, default='GBP')
    type = models.CharField(max_length=10, choices=UserPreference, default=UserPreference.BUDGET, blank=True)

    def __str__(self):
        return f"Profile of {self.author}"

class Airport(models.Model):
    code = models.CharField(max_length=3, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=255, blank=True)
    flights = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.code} — {self.name} — {self.city}"