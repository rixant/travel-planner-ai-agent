import os
import re
import sys
import unicodedata
from pathlib import Path

import certifi
import airportsdata
import pycountry
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.travel_data import COUNTRY_ALIASES, COUNTRY_MAIN_AIRPORT, CITY_MAIN_AIRPORT

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
DEFAULT_ORIGIN_IATA = (os.getenv("DEFAULT_ORIGIN_IATA") or "").strip().upper() or None
# The free AviationStack plan may only accept http://. Override here if needed:
# AVIATIONSTACK_BASE_URL=http://api.aviationstack.com/v1/flights
BASE_URL = os.getenv("AVIATIONSTACK_BASE_URL", "https://api.aviationstack.com/v1/flights")
AIRPORTS_DATA = airportsdata.load("IATA")

# Words removed from a place name before it is looked up
STOP_WORDS = {
    "flight", "flights", "ticket", "tickets", "trip", "travel",
    "plan", "complete", "days", "day", "including", "hotel",
    "hotels", "sightseeing", "under", "budget", "info", "information",
    "a", "an", "the", "my", "our", "visit", "visiting", "holiday",
    "vacation", "week", "weeks", "night", "nights",
}

# Words that end a place name in "from X ..." / "to Y ..."
_STOP = r"(?:on|for|under|including|with|in|at|and|by|via|next|during|starting|leaving|departing)"
_END = rf"(?:\s+{_STOP}\b|[.,!?;]|$)"

GLOBAL_KEYWORDS = [
    "all country",
    "all countries",
    "global flight",
    "global flights",
    "all flight",
    "all flights",
    "worldwide flight",
    "worldwide flights",
]


def _contains_word(haystack: str, needle: str) -> bool:
    """Whole-word match, so 'oman' does not match inside 'romania'."""
    return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None


def clean_text(text):
    # Remove accents: "São Paulo" -> "sao paulo"
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    words = [w for w in text.split() if w not in STOP_WORDS and not w.isdigit()]
    return " ".join(words).strip()


def get_country_code(text):
    text = clean_text(text)

    if not text:
        return None

    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    try:
        return pycountry.countries.lookup(text).alpha_2
    except LookupError:
        pass

    # Whole-word matches only, longest names first ("south korea" before "korea")
    for country in sorted(pycountry.countries, key=lambda c: len(c.name), reverse=True):
        if _contains_word(text, country.name.lower()):
            return country.alpha_2

    for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
        if len(alias) >= 3 and _contains_word(text, alias):
            return COUNTRY_ALIASES[alias]

    return None


def airport_country_matches(airport, country_code):
    airport_country = str(airport.get("country", "")).upper().strip()

    if airport_country == country_code:
        return True

    try:
        country = pycountry.countries.get(alpha_2=country_code)
        if country and airport_country.lower() == country.name.lower():
            return True
    except Exception:
        pass

    return False


def get_best_airport_for_country(country_code):
    preferred = COUNTRY_MAIN_AIRPORT.get(country_code)

    if preferred and preferred in AIRPORTS_DATA:
        return preferred

    candidates = []

    for iata, airport in AIRPORTS_DATA.items():
        if not iata:
            continue

        if airport_country_matches(airport, country_code):
            name = str(airport.get("name", "")).lower()
            city = str(airport.get("city", "")).lower()

            score = 0

            if "international" in name:
                score += 50
            if "intl" in name:
                score += 40
            if "capital" in name:
                score += 20
            if city:
                score += 5

            candidates.append((score, iata))

    if not candidates:
        return None

    # Highest score first; ties go to the alphabetically first code
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][1]


def resolve_location_to_iata(location):
    if not location:
        return None

    raw_location = location.strip()
    location_clean = clean_text(raw_location)

    if not location_clean:
        return None

    # Preferred cities and country names come first, so "usa" is the
    # United States and not the airport that happens to have the code USA.
    if location_clean in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[location_clean]

    if location_clean in COUNTRY_ALIASES:
        airport = get_best_airport_for_country(COUNTRY_ALIASES[location_clean])
        if airport:
            return airport

    # A plain 3-letter airport code, e.g. "DAC" or "nrt"
    if re.fullmatch(r"[A-Za-z]{3}", raw_location):
        code = raw_location.upper()
        if code in AIRPORTS_DATA:
            return code

    country_code = get_country_code(location_clean)
    if country_code:
        airport = get_best_airport_for_country(country_code)
        if airport:
            return airport

    city_matches = []

    for iata, airport in AIRPORTS_DATA.items():
        city = str(airport.get("city", "")).lower().strip()
        name = str(airport.get("name", "")).lower().strip()

        score = 0

        if city == location_clean:
            score += 100
        elif len(location_clean) >= 4 and _contains_word(city, location_clean):
            score += 70

        if len(location_clean) >= 4 and _contains_word(name, location_clean):
            score += 50

        if score > 0 and "international" in name:
            score += 10

        if score > 0:
            city_matches.append((score, iata))

    if city_matches:
        city_matches.sort(key=lambda c: (-c[0], c[1]))
        return city_matches[0][1]

    return None


def find_location_mentions(query: str):
    """
    Finds country or city names inside a natural language query.
    Returns a list of (start, end, name) in the order they appear.
    """

    q = query.lower()

    names = set(COUNTRY_ALIASES) | set(CITY_MAIN_AIRPORT)
    names |= {c.name.lower() for c in pycountry.countries if len(c.name) >= 4}

    candidates = []

    for name in names:
        if len(name) <= 3:
            # Very short names (UK, US, UAE) only count when written in capitals,
            # otherwise words like "us" would be read as the United States.
            pattern = rf"\b{re.escape(name.upper())}\b"
            haystack = query
        else:
            pattern = rf"\b{re.escape(name)}\b"
            haystack = q

        for m in re.finditer(pattern, haystack):
            candidates.append((m.start(), m.end(), name))

    # Longest match first, so "south korea" wins over "korea"
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))

    taken = []
    for start, end, name in candidates:
        if any(start < t_end and end > t_start for t_start, t_end, _ in taken):
            continue
        taken.append((start, end, name))

    taken.sort()
    return taken


def is_global_query(query: str) -> bool:
    q_lower = query.lower()
    return any(keyword in q_lower for keyword in GLOBAL_KEYWORDS)


def parse_route(query: str):
    """
    Returns (dep_iata, arr_iata). Either can be None when it was not found.

    DAC, NRT    -> route
    DAC, None   -> flights from DAC
    None, NRT   -> flights to NRT (caller adds the default origin)
    None, None  -> route could not be worked out
    """

    q = query.strip()
    q_lower = q.lower()

    # Two real airport codes: "DAC to NRT" (ignores words like THE or USD)
    codes = [c for c in re.findall(r"\b[A-Z]{3}\b", q) if c in AIRPORTS_DATA]
    if len(codes) >= 2:
        return codes[0], codes[1]

    # Pattern: from X to Y
    match = re.search(rf"\bfrom\s+(.+?)\s+to\s+(.+?){_END}", q_lower)
    if match:
        return (
            resolve_location_to_iata(match.group(1)),
            resolve_location_to_iata(match.group(2)),
        )

    # Pattern: to Y from X
    match = re.search(rf"\bto\s+(.+?)\s+from\s+(.+?){_END}", q_lower)
    if match:
        return (
            resolve_location_to_iata(match.group(2)),
            resolve_location_to_iata(match.group(1)),
        )

    # Known countries / cities anywhere in the sentence,
    # e.g. "7 days Japan trip from Bangladesh"
    mentions = find_location_mentions(q)
    if mentions:
        names = [name for _, _, name in mentions]

        origin = next(
            (
                name
                for start, _, name in mentions
                if re.search(r"\bfrom(?:\s+the)?$", q_lower[:start].rstrip())
            ),
            None,
        )

        if origin is None and len(names) >= 2:
            origin, dest = names[0], names[1]
        else:
            others = [n for n in names if n != origin]
            dest = others[0] if others else None

        return (
            resolve_location_to_iata(origin) if origin else None,
            resolve_location_to_iata(dest) if dest else None,
        )

    # Unknown place names: "from X" / "to Y"
    match = re.search(rf"\bfrom\s+(.+?){_END}", q_lower)
    if match:
        return resolve_location_to_iata(match.group(1)), None

    match = re.search(rf"\bto\s+(.+?){_END}", q_lower)
    if match:
        return None, resolve_location_to_iata(match.group(1))

    return None, None


def format_flight(flight: dict):
    airline = (flight.get("airline") or {}).get("name") or "Unknown airline"
    flight_number = (flight.get("flight") or {}).get("iata") or "Unknown flight number"
    status = flight.get("flight_status") or "Unknown"

    dep = flight.get("departure") or {}
    arr = flight.get("arrival") or {}

    dep_airport = dep.get("airport") or "Unknown departure airport"
    dep_iata = dep.get("iata") or "Unknown"
    dep_terminal = dep.get("terminal") or "N/A"
    dep_gate = dep.get("gate") or "N/A"
    dep_scheduled = dep.get("scheduled") or "Unknown"
    dep_delay = dep.get("delay")
    dep_delay_text = f"{dep_delay} minutes" if dep_delay is not None else "N/A"

    arr_airport = arr.get("airport") or "Unknown arrival airport"
    arr_iata = arr.get("iata") or "Unknown"
    arr_terminal = arr.get("terminal") or "N/A"
    arr_gate = arr.get("gate") or "N/A"
    arr_scheduled = arr.get("scheduled") or "Unknown"
    arr_delay = arr.get("delay")
    arr_delay_text = f"{arr_delay} minutes" if arr_delay is not None else "N/A"

    return f"""
Airline: {airline}
Flight: {flight_number}
Status: {status}

Departure:
- Airport: {dep_airport}
- IATA: {dep_iata}
- Terminal: {dep_terminal}
- Gate: {dep_gate}
- Scheduled: {dep_scheduled}
- Delay: {dep_delay_text}

Arrival:
- Airport: {arr_airport}
- IATA: {arr_iata}
- Terminal: {arr_terminal}
- Gate: {arr_gate}
- Scheduled: {arr_scheduled}
- Delay: {arr_delay_text}
""".strip()


DATA_NOTE = (
    "Note: this is live/scheduled flight status data from AviationStack. "
    "It has no ticket prices and cannot be searched by travel date, and the "
    "times may not be in local airport time. Do not invent prices or dates."
)


def search_flights(query: str, limit: int = 10):
    if not AVIATIONSTACK_API_KEY:
        return (
            "Flight API error: AVIATIONSTACK_API_KEY is missing.\n"
            "Please add this in your .env file:\n"
            "AVIATIONSTACK_API_KEY=your_api_key_here"
        )

    if is_global_query(query):
        dep_iata, arr_iata = None, None
    else:
        dep_iata, arr_iata = parse_route(query)

        # "Trip to India" with no origin: use the default origin
        if arr_iata and not dep_iata:
            if DEFAULT_ORIGIN_IATA:
                dep_iata = DEFAULT_ORIGIN_IATA
            else:
                return (
                    "No departure city was given and DEFAULT_ORIGIN_IATA is not set, "
                    "so flights were not searched. Ask the user where they are "
                    "flying from. Do not invent flight details."
                )

        if not dep_iata and not arr_iata:
            return (
                "Could not work out where to search flights from or to, so no "
                "flights were searched. Ask the user for a departure city and a "
                "destination (for example 'Dhaka to Tokyo'). "
                "Do not invent flight details."
            )

    # Ask for extra results because codeshare duplicates are filtered out below
    params = {
        "access_key": AVIATIONSTACK_API_KEY,
        "limit": min(max(limit, 1) * 3, 100),
    }

    if dep_iata:
        params["dep_iata"] = dep_iata

    if arr_iata:
        params["arr_iata"] = arr_iata

    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
    except requests.exceptions.RequestException as e:
        return f"Flight API request failed: {e}"

    try:
        data = response.json()
    except ValueError:
        return f"Flight API returned invalid JSON (HTTP {response.status_code})."

    if "error" in data:
        error = data["error"]
        return (
            "Flight API error:\n"
            f"Code: {error.get('code', 'Unknown')}\n"
            f"Message: {error.get('message', 'Unknown error')}"
        )

    if not response.ok:
        return f"Flight API error: HTTP {response.status_code}."

    # Codeshare listings repeat another airline's flight; keep the operating flight
    flight_data = [
        f for f in data.get("data", [])
        if not (f.get("flight") or {}).get("codeshared")
    ]

    if dep_iata and arr_iata:
        route_info = f"Live flights from {dep_iata} to {arr_iata}"
        route_text = f" for route {dep_iata} to {arr_iata}"
    elif dep_iata:
        route_info = f"Live flights from {dep_iata}"
        route_text = f" from {dep_iata}"
    elif arr_iata:
        route_info = f"Live flights to {arr_iata}"
        route_text = f" to {arr_iata}"
    else:
        route_info = "Global live flights"
        route_text = ""

    if not flight_data:
        return f"No live flight data found{route_text}.\n\n{DATA_NOTE}"

    formatted_flights = [format_flight(flight) for flight in flight_data[:limit]]

    return (
        f"{route_info}\n\n"
        + "\n\n---\n\n".join(formatted_flights)
        + f"\n\n{DATA_NOTE}"
    )


if __name__ == "__main__":
    test_queries = [
        "Plan a 7 days Japan trip from Bangladesh",
        "Plan a 5 day trip to India",
        "flights from Dhaka to Tokyo in March",
        "DAC to NRT",
        "Trip to South Korea from Canada under $2000",
        "tell us about the weather",
        "all country flight info",
    ]

    for q in test_queries:
        print(f"{q!r} -> global={is_global_query(q)} route={parse_route(q)}")

    print("\n" + "=" * 80 + "\n")
    print(search_flights("Plan a 7 days Japan trip from Bangladesh"))
    print("\n" + "=" * 80 + "\n")
    print(search_flights("all country flight info"))
