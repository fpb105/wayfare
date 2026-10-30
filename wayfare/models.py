from django.conf import settings
from django.db import models
#from django.contrib.auth.models import User   use settings.AUTH_USER_MODEL as it is on documentation

# Create your models here.
class Intrests(models.Model):
    intrests = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.intrests

class Profile(models.Model):
    class UserPreference(models.TextChoices):
        BUDGET = 'BUDGET', 'Budget'
        COMFORT = 'COMFORT', 'Comfort'
        LUXURY = 'LUXURY', 'Luxury'

    author = models.OneToOneField(settings.AUTH_USER_MODEL, 
                                  on_delete=models.CASCADE, 
                                  related_name="profile")
    intrests = models.ManyToManyField(Intrests, blank=True)
    type = models.CharField(max_length=10, choices=UserPreference, default=UserPreference.BUDGET, blank=True)

    def __str__(self):
        return f"Profile of {self.author}"

class City(models.Model):
    name = models.CharField(max_length=255, unique=True)
    known_for = models.ManyToManyField(Intrests, blank=True)
    budget = models.CharField(max_length=10, choices=Profile.UserPreference, default=Profile.UserPreference.BUDGET, blank=True)

    def __str__(self):
        return self.name

class Airport(models.Model):
    code = models.CharField(max_length=3, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name="airports")
    flights = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.code} — {self.name} — {self.city}"

class FlightQuery(models.Model):
    params = models.CharField(max_length=5000)   # urlencode(cleaned_data)
    results = models.JSONField()                # the raw flights list SerpAPI returned
    date_till_expire = models.DateField(blank=False)    # api results arent valid if the current day exceeds reulst outbound time