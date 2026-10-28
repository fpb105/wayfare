from django import forms
from .models import Profile, Intrests
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory
import datetime

TRAVEL_CLASS_CHOICES = (
    ("1", "Economy"),
    ("2", "Premium Economy"),
    ("3", "Business"),
    ("4", "First"),
)

TRAVEL_TYPE_CHOICES = (
    ("2", "One-Way"),
    ("1", "Round Trip"),
    ("3", "Multi city")
)

STOPS_CHOICES = (
    ("0", "Any number of stops"),
    ("1", "Nonstop only"),
    ("2", "1 stop or fewer"),
    ("3", "2 stops or fewer"),
)

SORT_BY_CHOICES = (
    ("1", "Top flights"),
    ("2", "Price"),
    ("3", "Departure time"),
    ("4", "Arrival time"),
    ("5", "Duration"),
    ("6", "Emissions"),
)

class ProfileForm(forms.ModelForm):
    class Meta:
            model = Profile
            fields = ['intrests', 'type']
            widgets = {
                'intrests': forms.CheckboxSelectMultiple(),
            }
            labels = {
                'type': "Travel type",
            }

class TripTypeForm(forms.Form):
    type = forms.ChoiceField(
        required=True,
        label="Trip type",
        choices=(TRAVEL_TYPE_CHOICES)
    )

class OneWayForm(forms.Form):
    # --- Core route/date fields ---
    departure_id = forms.CharField(
        required=True, 
        label="From: ", 
        help_text="Departure airport",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#departure-results",
    }))
    arrival_id = forms.CharField(
        required=True,
        label="To:",
        help_text="Destination Airport",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#arrival-results",
    }))
    travel_class = forms.ChoiceField(
        required=True,
        label="Class",
        choices=(TRAVEL_CLASS_CHOICES)
    )
    outbound_date = forms.DateField(
        required=True,
        label="Leaving date",
        input_formats=["%Y-%m-%d"],
        help_text="YYYY-MM-DD eg. 2000-04-06",
    )
    # --- Filters ---
    layovers = forms.ChoiceField(
        required=False,
        choices=STOPS_CHOICES,
        initial="0",
        label="Stops",
    )
    outbound_time_range = forms.CharField(
        required=False,
        label="Departure time range",
        help_text="24h range as start,end, e.g. 4,18 for 4AM-6PM.",
    )
    layover_duration = forms.CharField(
        required=False,
        label="Layover duration (minutes)",
        help_text="min,max e.g. 90,330",
    )  

class ReturnForm(forms.Form):
    # --- Core route/date fields ---
    departure_id = forms.CharField(
        required=True, 
        label="From: ", 
        help_text="Departure airport",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#departure-results",
    }))
    arrival_id = forms.CharField(
        required=True,
        label="To:",
        help_text="Destination Airport",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#arrival-results",
    }))
    travel_class = forms.ChoiceField(
        required=True,
        label="Class",
        choices=(TRAVEL_CLASS_CHOICES)
    )
    outbound_date = forms.DateField(
        required=True,
        label="Leaving date",
        input_formats=["%Y-%m-%d"],
        help_text="YYYY-MM-DD eg. 2000-04-06",
    )
    return_date = forms.DateField(
        required=True,
        label="Return date",
        input_formats=["%Y-%m-%d"],
        help_text="YYYY-MM-DD eg. 2000-04-06",
    )
    # --- Filters ---
    layovers = forms.ChoiceField(
        required=False,
        choices=STOPS_CHOICES,
        initial="0",
        label="Stops",
    )
    outbound_time_range = forms.CharField(
        required=False,
        label="Departure time range",
        help_text="24h range as start,end, e.g. 4,18 for 4AM-6PM.",
    )
    return_time_range = forms.CharField(
        required=False,
        label="Return time range",
        help_text="24h range as start,end, e.g. 4,18 for 4AM-6PM.",
    )
    layover_duration = forms.CharField(
        required=False,
        label="Layover duration (minutes)",
        help_text="min,max e.g. 90,330",
    )  

class MultiCityMainForm(forms.Form):
    departure_id = forms.CharField(
        required=True, 
        label="From: ", 
        help_text="Departure airport",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#departure-results",
    }))
    travel_class = forms.ChoiceField(
        required=True,
        label="Class",
        choices=(TRAVEL_CLASS_CHOICES)
    )
    outbound_date = forms.DateField(
        required=True,
        label="Leaving date",
        input_formats=["%Y-%m-%d"],
        help_text="YYYY-MM-DD eg. 2000-04-06",
    )
    amount_of_stops = forms.IntegerField(
        min_value=1,
        max_value=3,
        required=True,
        label="Amount of stops",
        help_text="how many stops you want",
    )

class MultiCityInfo(forms.Form):
    # --- Multi-City ---
    #because i hate how everyone does it.
    stop_id = forms.CharField(
        required=True, 
        label="From: ", 
        help_text="Departure airport",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "next .departure-results",
    }))
    days_at_stop = forms.IntegerField(
        required=True,
        label="Full days at stop (day you land is day 0)",
        min_value=1,
        max_value=5,
    )
    outbound_time_range = forms.CharField(
        required=False,
        label="Departure time range",
        help_text="24h range as start,end, e.g. 4,18 for 4AM-6PM. One-way only.",
    )


class BaseFullForm(BaseFormSet):
    def __init__(self, *args, expected=None, **kwargs):
        self.expected = expected
        super().__init__(*args, **kwargs)

    def clean(self):
        if any(self.errors) or self.expected is None:
            return
        filled = [f for f in self.forms if f.has_changed()]
        if len(self.forms) != self.expected or len(filled) != self.expected:
            raise ValidationError(f"Please fill in exactly {self.expected} city field(s).")

MultiStopFormSet = formset_factory(
    MultiCityInfo, formset=BaseFullForm, extra=0,
    max_num=3, validate_max=True,
)