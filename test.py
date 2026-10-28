import json
import sys

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"
MAX_HIDDEN_STEPS = 10

MOCK_USER_PREFERENCES = {"type": "COMFORT"}
MOCK_USER_INTRESTS = ["food", "nightlife"]

MOCK_CITIES = [
    {"id": 1, "name": "Barcelona", "known_for": ["food", "sight seeing"], "budget": "BUDGET"},
    {"id": 2, "name": "Monaco", "known_for": ["nightlife", "shopping"], "budget": "LUXURY"},
    {"id": 3, "name": "Lisbon", "known_for": ["food", "nightlife"], "budget": "COMFORT"},
]

MOCK_AIRPORTS = {
    1: [{"code": "BCN", "name": "Barcelona Airport", "flights": 500}],
    2: [{"code": "MCM", "name": "Monaco Heliport", "flights": 10}],
    3: [{"code": "LIS", "name": "Lisbon Airport", "flights": 300}],
}

SYSTEM_PROMPT = """While you are still reasoning or need more information, you must respond using only this structure — a strict two-element list [hidden, apis], nothing else, no extra text before or after it:
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


def call_api(api, values):
    if api == "user_preferences":
        return MOCK_USER_PREFERENCES
    elif api == "user_intrests":
        return MOCK_USER_INTRESTS
    elif api == "city_detail":
        name = values.get("name", "").lower()
        for city in MOCK_CITIES:
            if name in city["name"].lower():
                return city
        return {"error": "city not found"}
    elif api == "city_search":
        known_for = values.get("known_for")
        budget = values.get("budget")
        results = MOCK_CITIES
        if known_for:
            results = [c for c in results if known_for in c["known_for"]]
        if budget:
            results = [c for c in results if c["budget"] == budget]
        return results[:20]
    elif api == "city_airports":
        return MOCK_AIRPORTS.get(values.get("city_id"), [])
    else:
        return {"error": f"unknown api '{api}'"}


def parse_model_reply(content):
    try:
        parsed = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reply is not valid JSON: {content!r}") from exc

    if not (isinstance(parsed, list) and len(parsed) == 2
            and isinstance(parsed[0], bool) and isinstance(parsed[1], list)):
        raise ValueError(f"Reply is not a strict [hidden, apis] list: {content!r}")

    hidden, apis = parsed
    return hidden, apis


def ask_ollama(messages):
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": messages, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def run_turn(messages, user_message):
    messages.append({"role": "user", "content": user_message})

    empty_streak = 0

    for _ in range(MAX_HIDDEN_STEPS):
        reply = ask_ollama(messages)
        messages.append({"role": "assistant", "content": reply})
        print(f"  RAW REPLY -> {reply!r}", file=sys.stderr)

        hidden, apis = parse_model_reply(reply)

        if not hidden:
            messages.append({"role": "user", "content":
                "Give your answer now in plain, normal language. Do not use the [hidden, apis] list "
                "format for this response — no brackets, no JSON."})
            final_reply = ask_ollama(messages)
            messages.append({"role": "assistant", "content": final_reply})
            return final_reply

        if not apis:
            empty_streak += 1
        else:
            empty_streak = 0

        for api, values in apis:
            print(f"  [calling {api}({values})]", file=sys.stderr)

        results = [{"api": api, "values": values, "result": call_api(api, values)} for api, values in apis]
        print(f"  [result: {results}]", file=sys.stderr)

        if empty_streak >= 2:
            reminder = (
                "You have taken multiple steps in a row with no API calls and no progress. "
                "You must now either put a real API call in apis, or stop and send [false, []] "
                "based on whatever you already know."
            )
        else:
            reminder = "Respond with ONLY the [hidden, apis] list — no other text, no explanation of this data."
        messages.append({"role": "user", "content": json.dumps({"api_results": results, "reminder": reminder})})

    raise RuntimeError(f"Model did not reach a final answer within {MAX_HIDDEN_STEPS} hidden steps.")


def main():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("Connected. Type a message (or 'exit' to quit).")
    while True:
        user_message = input("> ").strip()
        if user_message.lower() in ("exit", "quit"):
            break
        if not user_message:
            continue

        try:
            reply = run_turn(messages, user_message)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            continue

        print(reply)


if __name__ == "__main__":
    main()
