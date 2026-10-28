import requests
import re
from django.urls import reverse
from urllib.parse import urlencode
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import HttpResponseBadRequest, JsonResponse
from datetime import date, timedelta

from .forms import *
from .models import Profile, Intrests, City, Airport


@login_required
def edit_profile(request):
    profile, _ = Profile.objects.get_or_create(author=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            messages.success(request, "Profile saved.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile) 

    return render(request, "wayfare/edit_profile.html", {"form": form})

@login_required
def profile(request):
    profile, _ = Profile.objects.get_or_create(author=request.user)
    intrests = profile.intrests.all()
    type = profile.type

    context={'Intrests':intrests,
          'Type':type, }
       
    return render(request, 'wayfare/profile.html', context)

@login_required
def flight_search(request):
    trip_type = request.GET.get("type") or request.POST.get("type")

    is_post = request.method == "POST"

    one_way_form = OneWayForm(request.POST if is_post and trip_type == "2" else None)
    return_form  = ReturnForm(request.POST if is_post and trip_type == "1" else None)
    multi_form   = MultiCityMainForm(request.POST if is_post and trip_type == "3" else None)

    expected = None
    if is_post and trip_type == "3":
        try:
            expected = int(request.POST.get("amount_of_stops", ""))
        except ValueError:
            expected = None
    formset = MultiStopFormSet(request.POST if is_post and trip_type == "3" else None, expected=expected)

    if is_post:
        active_form = {"2": one_way_form, "1": return_form, "3": multi_form}.get(trip_type)
        if active_form is None:
            messages.error(request, "Pick a trip type.")
        else:
            form_ok = active_form.is_valid()
            formset_ok = formset.is_valid() if trip_type == "3" else True
            if form_ok and formset_ok:
                data = active_form.cleaned_data.copy()
                if trip_type == "3":
                    data.update({k: v for k, v in request.POST.items() if k.startswith("form-")})
                data["type"] = trip_type
                return redirect(f"{reverse('results')}?{urlencode(data)}")

    return render(request, "wayfare/search.html", {
        "trip_type": trip_type,
        "one_way_form": one_way_form,
        "return_form": return_form,
        "multi_form": multi_form,
        "formset": formset,
    })

@login_required
def flight_results(request):
    trip_type = request.GET.get("type")

    form_classes = {"2": OneWayForm, "1": ReturnForm, "3": MultiCityMainForm}
    form_class = form_classes.get(trip_type)
    if form_class is None:
        return HttpResponseBadRequest("Invalid trip type")

    form = form_class(request.GET)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid parameters")

    data = form.cleaned_data

    departure_id = data["departure_id"]
    travel_class = data["travel_class"]
    outbound_date = data["outbound_date"] 
    params = {
        "engine": "google_flights",
        "deep_search": True,
        "api_key": settings.SERPAPI_KEY,
        "type": trip_type,
        "departure_id": departure_id,
        "outbound_date": outbound_date,
        "travel_class": travel_class,
    }

    if trip_type == "1" or trip_type=="2":
        arrival_id = data["arrival_id"]
        layovers = data["layovers"]
        outbound_time_range = data["outbound_time_range"]
        layover_duration = data["layover_duration"]
        params["arrival_id"] = arrival_id
        params["stops"] = layovers
        params["outbound_times"] = outbound_time_range
        params["layover_duration"] = layover_duration

    if trip_type == "1": #return
        return_date = data["return_date"]
        return_time_range = data["return_time_range"]
        params["return_date"] = return_date
        params["return_times"] = return_time_range
    elif trip_type == "3": #multi city
        amount_of_stops = data["amount_of_stops"]
        formset = MultiStopFormSet(request.GET, expected=data["amount_of_stops"])
        if not formset.is_valid():
            return HttpResponseBadRequest("Invalid stop parameters")
        stops = {i + 1: f.cleaned_data for i, f in enumerate(formset.forms)}
    elif trip_type == "2":
        pass #nothign needs to be done
    else:
        return HttpResponseBadRequest("Invalid trip type")

    flights = {}

    if trip_type != "3":
        response = requests.get("https://serpapi.com/search", params=params, timeout=10)
        response.raise_for_status()
        result = response.json()

        flights[0] = result.get("best_flights", []) + result.get("other_flights", [])
        
        print(flights)
        return render(request, "wayfare/results.html", {"flights": flights})
            
    elif trip_type == "3":
        params["type"] = "2"                      # each leg is a one-way search
        current_departure = departure_id
        current_date = outbound_date

        for i in range(int(amount_of_stops)):
            stop = stops[i + 1]

            params["departure_id"] = current_departure
            params["arrival_id"] = stop["stop_id"]
            params["outbound_date"] = current_date.isoformat()
            params["outbound_times"] = stop["outbound_time_range"]

            response = requests.get("https://serpapi.com/search", params=params, timeout=30)
            response.raise_for_status()
            result = response.json()

            flights[i] = result.get("best_flights", []) + result.get("other_flights", [])

            current_departure = stop["stop_id"]
            current_date += timedelta(days=stop["days_at_stop"])

        params["arrival_id"] = departure_id
        params["outbound_date"] = current_date.isoformat()
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        result = response.json()

        flights[i+1] = result.get("best_flights", []) + result.get("other_flights", [])

    else:
        return HttpResponseBadRequest("Invalid trip type") #just incase

    print(flights)
    return render(request, "wayfare/results.html", {"flights": flights})

@login_required
def airport_search(request):
    STOP_DEPARTURE_RE = re.compile(r"^form-(\d+)-stop_id$")
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

    airports = Airport.objects.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(city__name__icontains=q)).order_by("-flights")[:10] if q else []

    return render(request, "wayfare/_airport_results.html", {
        "airports": airports,
        "target_input_id": target_input_id,
    })

@login_required
def user_preferences(request):
    profile, _ = Profile.objects.get_or_create(author=request.user)
    return JsonResponse({"type": profile.type})

@login_required
def user_intrests(request):
    profile, _ = Profile.objects.get_or_create(author=request.user)
    data = list(profile.intrests.values_list("intrests", flat=True))
    return JsonResponse(data, safe=False)

@login_required
def city_detail(request):
    name = request.GET.get("name")
    city = City.objects.filter(name__icontains=name).first() if name else None
    if city is None:
        return JsonResponse({"error": "city not found"}, status=404)

    data = {
        "id": city.id,
        "name": city.name,
        "known_for": list(city.known_for.values_list("intrests", flat=True)),
        "budget": city.budget,
    }
    return JsonResponse(data)

@login_required
def city_search(request):
    cities = City.objects.all()

    known_for = request.GET.get("known_for")
    if known_for:
        cities = cities.filter(known_for__intrests__iexact=known_for)

    budget = request.GET.get("budget")
    if budget:
        cities = cities.filter(budget=budget)

    data = [
        {
            "id": city.id,
            "name": city.name,
            "known_for": list(city.known_for.values_list("intrests", flat=True)),
            "budget": city.budget,
        }
        for city in cities[:20]
    ]
    return JsonResponse(data, safe=False)

@login_required
def city_airports(request, city_id):
    airports = Airport.objects.filter(city_id=city_id)
    data = [
        {"code": airport.code, "name": airport.name, "flights": airport.flights}
        for airport in airports
    ]
    return JsonResponse(data, safe=False)

def chat(request):
    pass