import requests
import re
import json
import uuid
from django.urls import reverse
from urllib.parse import urlencode
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import HttpResponseBadRequest, JsonResponse
from datetime import date, timedelta
from django.core.cache import caches

from .forms import *
from .models import Profile, Intrests, City, Airport, FlightQuery

CHAT_MODEL = "qwen2.5:7b"
CHAT_MAX_HIDDEN_STEPS = 10

CHAT_SYSTEM_PROMPT = """While you are still reasoning or need more information, you must respond using only this structure — a strict two-element list [hidden, apis], nothing else, no extra text before or after it:
hidden (boolean): always true in this format. It means "I am not ready to answer yet."
apis (list): a list of API calls you want to make this turn. Each entry is itself a two-element list [api, values], where api is one of the names below and values is an object holding that API's parameters (or an empty object {} if it takes none). Leave apis as an empty list [] only if you are not calling anything this turn — but see below, this should basically never happen.
Available APIs:
Valid budget values are BUDGET, COMFORT, LUXURY.
"user_preferences" — no parameters. Returns the current user's own saved budget preference, as one of the values above.
"user_intrests" — no parameters. Returns the current user's own saved interests.
"city_detail" — required parameter: name (a string, e.g. "Narnia"). Looks up a specific city and returns its known_for/budget. Use this when the user asked about a named city.
"city_search" — optional parameters: known_for (a string matching an interest, e.g. "juggling"), budget (one of "BUDGET", "COMFORT", "LUXURY"). Omit either to not filter on it. Returns up to 20 matching cities — it is not the full list, so do not describe it as all available cities. Use this when the user asked for recommendations, not a specific city.
"city_airports" — required parameter: city_id (integer). Returns the airports located in that city.
Only call an API when you need its data to answer the user. Never fabricate API results — wait for the actual response before reasoning about it further.
Hard rule, no exceptions: you must never pass a known_for or budget value into city_search unless that exact value came from a user_intrests or user_preferences result earlier in this conversation. You are never allowed to decide for yourself what the user likes or what budget they prefer — not from the city's name, not from common sense, not from general knowledge about the destination. If this is the first time city_search is relevant, your very next step must be to call user_intrests and/or user_preferences first, before city_search, every single time, with no exceptions — even if you think you already know the answer.
You can send [true, apis] as many times in a row as you need — planning, calling APIs, reading their results, and reasoning about them. There is no limit on how many of these steps you take.
Once you have enough information to answer, respond with exactly [false, []] and nothing else. Do not put your answer inside this list. You will then be asked, separately, to give your actual answer — at that point, and only at that point, write normally in plain language like a regular assistant, with no brackets, no JSON, and no mention of this list format.
Never describe an API call you intend to make without also making it in the same [true, apis] response. A step with an empty apis list accomplishes nothing, so send [true, []] only if you are genuinely still thinking and about to call something on your very next turn — otherwise either call something now or send [false, []] now.
The example city names below are illustrative only, not real data — never copy or reuse their facts. Every answer you give must be built only from API results you actually called and received earlier in this conversation. If you have not called any APIs yet for this question, you are not ready to answer — send [true, apis] with a real call instead.
Example — step calling two APIs:
[true, [["city_search", {"known_for": "stuff", "budget": "trillionaire"}], ["user_preferences", {}]]]
Example — another step after reading those results, still not ready to answer:
[true, [["city_detail", {"name": "Poland"}]]]
Example — ready to answer:
[false, []]"""


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
    FlightQuery.objects.filter(date_till_expire__lt=date.today()).delete()
    try:
        trip_type = request.GET.get("type")

        form_classes = {"2": OneWayForm, "1": ReturnForm, "3": MultiCityMainForm}
        form_class = form_classes.get(trip_type)
        if form_class is None:
            return HttpResponseBadRequest("Invalid trip type")

        form = form_class(request.GET)
        if not form.is_valid():
            return HttpResponseBadRequest("Invalid parameters")

        data = form.cleaned_data

        stops = {}
        if trip_type == "3":
            formset = MultiStopFormSet(request.GET, expected=data["amount_of_stops"])
            if not formset.is_valid():
                return HttpResponseBadRequest("Invalid stop parameters")
            stops = {i + 1: f.cleaned_data for i, f in enumerate(formset.forms)}

        query_data = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in data.items()}
        for i, stop in stops.items():
            for k, v in stop.items():
                query_data[f"stop_{i}_{k}"] = v.isoformat() if hasattr(v, "isoformat") else v
        query_key = urlencode(sorted(query_data.items()))

        cached = FlightQuery.objects.filter(params=query_key, date_till_expire__gte=date.today()).first()

        if cached:
            flights = cached.results
            return render(request, "wayfare/results.html", {"flights": flights})
        else:
            params_list = []

            if trip_type == "2":
                params_list.append({
                    "engine": "google_flights",
                    "deep_search": True,
                    "api_key": settings.SERPAPI_KEY,
                    "type": trip_type,
                    "departure_id": data["departure_id"],
                    "outbound_date": data["outbound_date"],
                    "travel_class": data["travel_class"],
                    "arrival_id": data["arrival_id"],
                    "stops": data["layovers"],
                    "outbound_times": data["outbound_time_range"],
                    "layover_duration": data["layover_duration"],
                })

            elif trip_type == "1":
                params_list.append({
                    "engine": "google_flights",
                    "deep_search": True,
                    "api_key": settings.SERPAPI_KEY,
                    "type": trip_type,
                    "departure_id": data["departure_id"],
                    "outbound_date": data["outbound_date"],
                    "travel_class": data["travel_class"],
                    "arrival_id": data["arrival_id"],
                    "stops": data["layovers"],
                    "outbound_times": data["outbound_time_range"],
                    "layover_duration": data["layover_duration"],
                    "return_date": data["return_date"],
                    "return_times": data["return_time_range"],
                })

            elif trip_type == "3":
                current_departure = data["departure_id"]
                current_date = data["outbound_date"]

                for i in range(int(data["amount_of_stops"])):
                    stop = stops[i + 1]
                    params_list.append({
                        "engine": "google_flights",
                        "deep_search": True,
                        "api_key": settings.SERPAPI_KEY,
                        "type": "2",
                        "travel_class": data["travel_class"],
                        "departure_id": current_departure,
                        "arrival_id": stop["stop_id"],
                        "outbound_date": current_date.isoformat(),
                        "outbound_times": stop["outbound_time_range"],
                    })
                    current_departure = stop["stop_id"]
                    current_date += timedelta(days=stop["days_at_stop"])

                params_list.append({
                    "engine": "google_flights",
                    "deep_search": True,
                    "api_key": settings.SERPAPI_KEY,
                    "type": "2",
                    "travel_class": data["travel_class"],
                    "departure_id": current_departure,
                    "arrival_id": data["departure_id"],
                    "outbound_date": current_date.isoformat(),
                })

            flights = []
            for params in params_list:
                response = requests.get("https://serpapi.com/search", params=params, timeout=30)
                response.raise_for_status()
                result = response.json()
                flights.append(result.get("best_flights", []) + result.get("other_flights", []))

            FlightQuery.objects.create(
                params=query_key,
                results=flights,
                date_till_expire=data["outbound_date"],
            )
            return render(request, "wayfare/results.html", {"flights": flights})
    except:
        return HttpResponseBadRequest("Something went wrong!")

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

def _user_preferences_data(user):
    profile, _ = Profile.objects.get_or_create(author=user)
    return {"type": profile.type}

def _user_intrests_data(user):
    profile, _ = Profile.objects.get_or_create(author=user)
    return list(profile.intrests.values_list("intrests", flat=True))

def _city_detail_data(name):
    city = City.objects.filter(name__icontains=name).first() if name else None
    if city is None:
        return None
    return {
        "id": city.id,
        "name": city.name,
        "known_for": list(city.known_for.values_list("intrests", flat=True)),
        "budget": city.budget,
    }

def _city_search_data(known_for=None, budget=None):
    cities = City.objects.all()
    if known_for:
        cities = cities.filter(known_for__intrests__iexact=known_for)
    if budget:
        cities = cities.filter(budget=budget)

    return [
        {
            "id": city.id,
            "name": city.name,
            "known_for": list(city.known_for.values_list("intrests", flat=True)),
            "budget": city.budget,
        }
        for city in cities[:20]
    ]

def _city_airports_data(city_id):
    return [
        {"code": airport.code, "name": airport.name, "flights": airport.flights}
        for airport in Airport.objects.filter(city_id=city_id)
    ]

@login_required
def user_preferences(request):
    return JsonResponse(_user_preferences_data(request.user))

@login_required
def user_intrests(request):
    return JsonResponse(_user_intrests_data(request.user), safe=False)

@login_required
def city_detail(request):
    data = _city_detail_data(request.GET.get("name"))
    if data is None:
        return JsonResponse({"error": "city not found"}, status=404)
    return JsonResponse(data)

@login_required
def city_search(request):
    data = _city_search_data(request.GET.get("known_for"), request.GET.get("budget"))
    return JsonResponse(data, safe=False)

@login_required
def city_airports(request, city_id):
    return JsonResponse(_city_airports_data(city_id), safe=False)

def _chat_call_api(user, api, values):
    if api == "user_preferences":
        return _user_preferences_data(user)
    elif api == "user_intrests":
        return _user_intrests_data(user)
    elif api == "city_detail":
        data = _city_detail_data(values.get("name"))
        return data if data is not None else {"error": "city not found"}
    elif api == "city_search":
        return _city_search_data(values.get("known_for"), values.get("budget"))
    elif api == "city_airports":
        return _city_airports_data(values.get("city_id"))
    else:
        return {"error": f"unknown api '{api}'"}

def _chat_parse_reply(content):
    try:
        parsed = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reply is not valid JSON: {content!r}") from exc

    if not (isinstance(parsed, list) and len(parsed) == 2
            and isinstance(parsed[0], bool) and isinstance(parsed[1], list)):
        raise ValueError(f"Reply is not a strict [hidden, apis] list: {content!r}")

    hidden, apis = parsed
    return hidden, apis

def _chat_ask_ollama(messages):
    response = requests.post(
        settings.CHAT_OLLAMA_URL,
        json={"model": CHAT_MODEL, "messages": messages, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]

def _run_chat_loop(chat_messages, user):
    empty_streak = 0

    for _ in range(CHAT_MAX_HIDDEN_STEPS):
        reply = _chat_ask_ollama(chat_messages)
        chat_messages.append({"role": "assistant", "content": reply})
        
        hidden, apis = _chat_parse_reply(reply)

        if not hidden:
            chat_messages.append({"role": "user", "content":
                "Give your answer now in plain, normal language. Do not use the [hidden, apis] list "
                "format for this response — no brackets, no JSON."})
            reply_text = _chat_ask_ollama(chat_messages)
            chat_messages.append({"role": "assistant", "content": reply_text})
            return reply_text

        empty_streak = empty_streak + 1 if not apis else 0

        results = [
            {"api": api, "values": values, "result": _chat_call_api(user, api, values)}
            for api, values in apis
        ]

        if empty_streak >= 2:
            reminder = (
                "You have taken multiple steps in a row with no API calls and no progress. "
                "You must now either put a real API call in apis, or stop and send [false, []] "
                "based on whatever you already know."
            )
        else:
            reminder = "Respond with ONLY the [hidden, apis] list — no other text, no explanation of this data."
        chat_messages.append({"role": "user", "content": json.dumps({"api_results": results, "reminder": reminder})})

    raise RuntimeError(f"Model did not reach a final answer within {CHAT_MAX_HIDDEN_STEPS} steps.")

@login_required
def chat_page(request):
    chat_id = uuid.uuid4().hex
    return render(request, "wayfare/chat.html", {"visible_messages": [], "chat_id": chat_id})

@login_required
def chat_send(request):
    chat_cache = caches["chat"]

    chat_id = request.POST.get("chat_id") or uuid.uuid4().hex
    user_message = request.POST.get("message", "").strip()
    if not user_message:
        return HttpResponseBadRequest("Missing 'message' parameter")

    if chat_cache.get(f"chat_lock_{chat_id}"):
        return HttpResponseBadRequest("Still generating a reply to your last message — wait for it to finish.")
    chat_cache.set(f"chat_lock_{chat_id}", True, timeout=120)

    chat_messages = chat_cache.get(f"chat_messages_{chat_id}") or [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT}
    ]
    chat_messages.append({"role": "user", "content": user_message})
    chat_cache.set(f"chat_messages_{chat_id}", chat_messages)

    visible_messages = chat_cache.get(f"chat_visible_{chat_id}") or []
    visible_messages.append({"role": "user", "content": user_message})
    chat_cache.set(f"chat_visible_{chat_id}", visible_messages)

    return render(request, "wayfare/_chat_pending.html", {"user_message": user_message, "chat_id": chat_id})

@login_required
def chat_reply(request):
    chat_cache = caches["chat"]
    chat_id = request.GET.get("chat_id")
    chat_messages = chat_cache.get(f"chat_messages_{chat_id}") if chat_id else None
    if not chat_messages:
        return HttpResponseBadRequest("No chat in progress")

    try:
        try:
            reply_text = _run_chat_loop(chat_messages, request.user)
        except (ValueError, RuntimeError) as exc:
            reply_text = f"Sorry, something went wrong: {exc}"

        chat_cache.set(f"chat_messages_{chat_id}", chat_messages)

        visible_messages = chat_cache.get(f"chat_visible_{chat_id}") or []
        visible_messages.append({"role": "assistant", "content": reply_text})
        chat_cache.set(f"chat_visible_{chat_id}", visible_messages)
    finally:
        chat_cache.delete(f"chat_lock_{chat_id}")

    return render(request, "wayfare/_chat_reply.html", {"content": reply_text})