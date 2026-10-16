import requests
import re
from django.urls import reverse
from urllib.parse import urlencode
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import *
from .models import Profile, Intrests, Airport


@login_required
def edit_profile(request):
    profile, _ = Profile.objects.get_or_create(author=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            names = [n.strip() for n in form.cleaned_data["intrests_text"].split(",") if n.strip()]
            interest_objs = [Intrests.objects.get_or_create(intrests=n)[0] for n in names]
            profile.intrests.set(interest_objs)
            messages.success(request, "Profile saved.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile, initial={
        "intrests_text": ", ".join(i.intrests for i in profile.intrests.all())
    })

    return render(request, "wayfare/edit_profile.html", {"form": form})

@login_required
def profile(request):
    profile, _ = Profile.objects.get_or_create(author=request.user)
    intrests = profile.intrests.all()
    home = profile.home
    currency = profile.currency
    type = profile.type

    context={'Intrests':intrests,
          'Home':home,
          'currency':currency,
          'Type':type, }
       
    return render(request, 'wayfare/profile.html', context)

@login_required
def airport_search_form(request):
    if request.method == "POST":
        form = FlightSearchForm(request.POST)
        trip_type = request.POST.get("type")

        expected = None
        if trip_type == "3":
            try:
                expected = int(request.POST.get("destination_amount", ""))
            except ValueError:
                expected = None

        formset = MultiStopFormSet(request.POST, expected=expected)

        form_ok = form.is_valid()
        formset_ok = formset.is_valid() if trip_type == "3" else True

        if form_ok and formset_ok:
            data = form.cleaned_data.copy()
            # handle multi-city legs separately, see note below
            return redirect(f"{reverse('results')}?{urlencode(data)}")
    else:
        form = FlightSearchForm()
        formset = MultiStopFormSet(expected=None)

    return render(request, "wayfare/search.html", {"form": form, "formset": formset})

@login_required
def flight_results(request):
    departure_id = request.GET.get("departure_id")
    arrival_id = request.GET.get("arrival_id")
    outbound_date = request.GET.get("outbound_date")
    return_date = request.GET.get("return_date")
    trip_type = request.GET.get("type")
    travel_class = request.GET.get("travel_class")
    stops = request.GET.get("stops")
    outbound_time_range = request.GET.get("outbound_time_range")
    return_time_range = request.GET.get("return_time_range")
    layover_duration = request.GET.get("layover_duration")

    params = {
        "engine": "google_flights",
        "no_cache": False,
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "currency": "GBP",
        "type": trip_type,
        "travel_class": travel_class,
        "show_hidden": True,
        "deep_search":True,
        "api_key": settings.SERPAPI_KEY,
    }

    if trip_type == "1":
        params["return_date"] = return_date

    if stops and stops != "0":
        params["stops"] = stops

    if outbound_time_range:
        params["outbound_times"] = outbound_time_range

    if trip_type == "1" and return_time_range:
        params["return_times"] = return_time_range

    if layover_duration:
        params["layover_duration"] = layover_duration

    try:
        print(f"GET Params: {params}")
        response = requests.get("https://serpapi.com/search", params=params, timeout=10)
        print(f"Request URL: {response.request.url}")
        print(f"Status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return render(request, "wayfare/results.html", {
            "error": "Couldn't reach the flight search service — try again shortly.",
            "flights": [],
        })

    best_flights = data.get("best_flights", [])
    other_flights = data.get("other_flights", [])

    if not best_flights and not other_flights:
        return render(request, "wayfare/results.html", {
            "error": "No flights found for that search.",
            "flights": [],
        })

    return render(request, "wayfare/results.html", {
        "flights": best_flights + other_flights,
    })

@login_required
def airport_search(request):
    STOP_DEPARTURE_RE = re.compile(r"^form-(\d+)-m_departure_id$")
    if "departure_id" in request.GET:
        q = request.GET["departure_id"]
        target_input_id = "id_departure_id"
    elif "arrival_id" in request.GET:
        q = request.GET.get("arrival_id", "")
        target_input_id = "id_arrival_id"
    else:
        q = ""
        target_input_id = None
        for key in request.GET:
            match = STOP_DEPARTURE_RE.match(key)
            if match:
                q = request.GET[key]
                target_input_id = f"id_{key}"
                break

    airports = Airport.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))[:10] if q else []

    return render(request, "wayfare/_airport_results.html", {
        "airports": airports,
        "target_input_id": target_input_id,
    })

