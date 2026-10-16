import requests
from django.urls import reverse
from urllib.parse import urlencode
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfileForm, FlightSearchForm
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
        if form.is_valid():
            return redirect(f"{reverse('results')}?{urlencode(form.cleaned_data)}")
    else:
        form = FlightSearchForm()

    return render(request, "wayfare/search.html", {"form": form})

@login_required
def flight_results(request):
    departure_id = request.GET.get("departure_id")
    arrival_id = request.GET.get("arrival_id")
    outbound_date = request.GET.get("outbound_date")
    arriving_date = request.GET.get("arriving_date")
    trip_type = request.GET.get("type")
    travel_class = request.GET.get("travel_class")

    params = {
        "engine": "google_flights",
        "no_cache": False,
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "currency": "GBP",
        "type": trip_type,
        "travel_class": travel_class,
        "api_key": settings.SERPAPI_KEY,
    }

    if trip_type == "ROUND":
        params["return_date"] = arriving_date

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
    if "departure_id" in request.GET:
        q = request.GET["departure_id"]
        target_input_id = "id_departure_id"
    else:
        q = request.GET.get("arrival_id", "")
        target_input_id = "id_arrival_id"

    airports = Airport.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))[:10] if q else []

    return render(request, "wayfare/_airport_results.html", {
        "airports": airports,
        "target_input_id": target_input_id,
    })

