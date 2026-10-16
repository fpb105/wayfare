from django import forms
from .models import Profile
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
)

class ProfileForm(forms.ModelForm):
    intrests_text = forms.CharField(
        required=False,
        label="Interests",
        help_text="Comma-separated, e.g. hiking, museums, food",
    )
    class Meta:
        model = Profile
        fields = ["home", "currency", "type"]

class FlightSearchForm(forms.Form):
    departure_id = forms.CharField(
        required=True, 
        label="departure_id", 
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#departure-results",
    }))
    arrival_id = forms.CharField(
        required=True,
        label="arrival_id",
        widget=forms.TextInput(attrs={
        "hx-get": "/api/airports/search",
        "hx-trigger": "keyup changed delay:300ms",
        "hx-target": "#arrival-results",
    }))
    type = forms.ChoiceField(
        required=True,
        label="Trip type",
        choices=(TRAVEL_TYPE_CHOICES)
    )
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
        required=False,
        label="Return date",
        input_formats=["%Y-%m-%d"],
        help_text="YYYY-MM-DD eg. 2000-04-06",
    )
    outbound_times = forms.TimeField(
        required=False,
        label="Leaving time",
        input_formats=["%H:%M"],
    )
    arrival_times = forms.TimeField(
        required=False,
        label="Return time",
        input_formats=["%H:%M"],
    )

    def clean(self):
        cleaned_data = super().clean()
        l_type = cleaned_data.get("type")
        l_outbound_date = cleaned_data.get('outbound_date')
        l_return_date = cleaned_data.get('return_date')
        if l_type == "1" and not l_return_date:
            self.add_error("return_date", "Return date is required for a round trip.")

    #non external api options (do later)
    """
    min_stops = forms.IntegerField(
        localize=True,
        required=False,
        initial = 0,
        label="Minimum stops",
        help_text="Leave empty for direct",
    )

    max_stops = forms.IntegerField(
        localize=True,
        required=False,
        initial = 0,
        label="Maximum stops",
    )

    time_at_stops = forms.IntegerField(
        localize=True,
        required=False,
        initial = 0,
        label="Time at stops",
    )
    """