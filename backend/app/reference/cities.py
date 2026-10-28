"""Maintained location register: city -> country, for geography stated as a city (27 Oct 2026, item 3).

A city resolves to a country only when the register lists it once. A name listed for several countries is AMBIGUOUS
and must be reviewed by a person, never guessed (Santiago, Valencia, Tripoli, Hyderabad ...). Airport codes and names
are resolved separately through the airports table (imports). Extend this table deliberately; every entry is a
maintained fact, not an inference.
"""
from __future__ import annotations

import re
import unicodedata

_RAW: dict[str, str] = {
    # Africa
    "Nairobi": "KE", "Mombasa": "KE", "Eldoret": "KE", "Kampala": "UG", "Entebbe": "UG", "Dar es Salaam": "TZ", "Zanzibar": "TZ",
    "Kilimanjaro": "TZ", "Addis Ababa": "ET", "Djibouti City": "DJ", "Kigali": "RW", "Bujumbura": "BI", "Mogadishu": "SO",
    "Khartoum": "SD", "Juba": "SS", "Lusaka": "ZM", "Ndola": "ZM", "Harare": "ZW", "Lilongwe": "MW", "Blantyre": "MW",
    "Maputo": "MZ", "Beira": "MZ", "Luanda": "AO", "Windhoek": "NA", "Gaborone": "BW", "Francistown": "BW", "Johannesburg": "ZA",
    "Cape Town": "ZA", "Durban": "ZA", "Port Elizabeth": "ZA", "Gqeberha": "ZA", "Antananarivo": "MG", "Port Louis": "MU",
    "Plaisance": "MU", "Mahe": "SC", "Victoria": "SC|CA|HK", "Praia": "CV", "Sal": "CV", "Lagos": "NG", "Abuja": "NG", "Kano": "NG",
    "Port Harcourt": "NG", "Accra": "GH", "Kumasi": "GH", "Abidjan": "CI", "Dakar": "SN", "Bamako": "ML", "Ouagadougou": "BF",
    "Niamey": "NE", "Lome": "TG", "Cotonou": "BJ", "Conakry": "GN", "Freetown": "SL", "Monrovia": "LR", "Douala": "CM", "Yaounde": "CM",
    "Libreville": "GA", "Brazzaville": "CG", "Kinshasa": "CD", "Lubumbashi": "CD", "Cairo": "EG", "Alexandria": "EG|US", "Casablanca": "MA",
    "Tangier": "MA", "Algiers": "DZ", "Alger": "DZ", "Oran": "DZ", "Constantine": "DZ", "Tunis": "TN", "Tripoli": "LY|LB", "Asmara": "ER",
    "Nanyuki": "KE", "Isiolo": "KE", "Walvis Bay": "NA", "Port-au-Prince": "HT", "Santo Domingo": "DO", "San Juan": "PR|AR",
    # Middle East
    "Dubai": "AE", "Abu Dhabi": "AE", "Sharjah": "AE", "Al Ain": "AE", "Doha": "QA", "Muscat": "OM", "Salalah": "OM", "Manama": "BH",
    "Kuwait City": "KW", "Riyadh": "SA", "Jeddah": "SA", "Dammam": "SA", "Amman": "JO", "Beirut": "LB", "Baghdad": "IQ", "Erbil": "IQ",
    "Tehran": "IR", "Tel Aviv": "IL", "Istanbul": "TR", "Ankara": "TR",
    # Europe
    "London": "GB", "Manchester": "GB", "Birmingham": "GB|US", "Frankfurt": "DE", "Munich": "DE", "Cologne": "DE", "Leipzig": "DE",
    "Hamburg": "DE", "Berlin": "DE", "Vienna": "AT", "Zurich": "CH", "Geneva": "CH", "Basel": "CH", "Paris": "FR", "Lyon": "FR",
    "Marseille": "FR", "Amsterdam": "NL", "Maastricht": "NL", "Brussels": "BE", "Liege": "BE", "Luxembourg": "LU", "Madrid": "ES",
    "Barcelona": "ES", "Valencia": "ES|VE", "Zaragoza": "ES", "Lisbon": "PT", "Porto": "PT", "Milan": "IT", "Rome": "IT", "Bologna": "IT",
    "Athens": "GR|US", "Copenhagen": "DK", "Stockholm": "SE", "Oslo": "NO", "Helsinki": "FI", "Warsaw": "PL", "Prague": "CZ", "Budapest": "HU",
    "Bucharest": "RO", "Sofia": "BG", "Dublin": "IE", "Moscow": "RU", "Kyiv": "UA",
    # Asia-Pacific
    "Singapore": "SG", "Hong Kong": "HK", "Shanghai": "CN", "Beijing": "CN", "Guangzhou": "CN", "Shenzhen": "CN", "Tokyo": "JP", "Osaka": "JP",
    "Seoul": "KR", "Incheon": "KR", "Taipei": "TW", "Bangkok": "TH", "Kuala Lumpur": "MY", "Penang": "MY", "Jakarta": "ID", "Manila": "PH",
    "Hanoi": "VN", "Ho Chi Minh City": "VN", "Delhi": "IN", "New Delhi": "IN", "Mumbai": "IN", "Chennai": "IN", "Bengaluru": "IN",
    "Bangalore": "IN", "Hyderabad": "IN|PK", "Karachi": "PK", "Lahore": "PK", "Dhaka": "BD", "Colombo": "LK", "Kathmandu": "NP",
    "Sydney": "AU", "Melbourne": "AU", "Perth": "AU", "Brisbane": "AU", "Auckland": "NZ",
    # Americas
    "New York": "US", "Los Angeles": "US", "Chicago": "US", "Miami": "US", "Houston": "US", "Atlanta": "US", "Memphis": "US",
    "Louisville": "US", "Portland": "US", "Richmond": "US|AU", "Toronto": "CA", "Montreal": "CA", "Vancouver": "CA", "Mexico City": "MX",
    "Guadalajara": "MX|ES", "Bogota": "CO", "Medellin": "CO", "Lima": "PE", "Quito": "EC", "Guayaquil": "EC", "Santiago": "CL|ES|DO|CU",
    "Buenos Aires": "AR", "Sao Paulo": "BR", "Rio de Janeiro": "BR", "Campinas": "BR", "Montevideo": "UY", "Panama City": "PA",
    "San Jose": "CR|US", "Kingston": "JM|CA", "Georgetown": "GY|KY", "Cordoba": "AR|ES", "Caracas": "VE", "La Paz": "BO",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s)).strip()


REGISTER: dict[str, tuple[str, ...]] = {_norm(k): tuple(v.split("|")) for k, v in _RAW.items()}
_PATTERN = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(k) for k in sorted(REGISTER, key=len, reverse=True)) + r")(?![A-Za-z])", re.I)


def city_countries(name: str) -> tuple[str, ...]:
    """Countries the register lists for a city name: () unknown, (code,) resolved, several = ambiguous."""
    return REGISTER.get(_norm(name), ())


def cities_in_text(text: str) -> list[tuple[int, int, str, tuple[str, ...]]]:
    """(start, end, city, countries) for every registered city named in the text (accents ignored)."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    out = []
    for m in _PATTERN.finditer(t):
        out.append((m.start(), m.end(), m.group(1), REGISTER[_norm(m.group(1))]))
    return out
