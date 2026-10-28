"""Geography reference data: ISO 3166-1 alpha-2 countries with UN M49
regions and sub-regions, a small set of economic groupings, and common
alternative names used when resolving extracted text to a country.

This is the single source for the `countries`, `regions` and
`region_countries` seed in migrations/sql/wfc_0002_directive.sql
(tests/domain/test_geography.py checks the two agree). Country codes are
ISO 3166-1 alpha-2. Sub-regions follow the UN M49 standard, with the
intermediate regions of Sub-Saharan Africa and Latin America used as the
sub-region. Taiwan (TW) is placed in Eastern Asia for reporting purposes.
"""
from __future__ import annotations

import re
import unicodedata

# code | name | M49 region | M49 sub-region
_RAW = """
DZ|Algeria|Africa|Northern Africa
EG|Egypt|Africa|Northern Africa
LY|Libya|Africa|Northern Africa
MA|Morocco|Africa|Northern Africa
SD|Sudan|Africa|Northern Africa
TN|Tunisia|Africa|Northern Africa
EH|Western Sahara|Africa|Northern Africa
IO|British Indian Ocean Territory|Africa|Eastern Africa
BI|Burundi|Africa|Eastern Africa
KM|Comoros|Africa|Eastern Africa
DJ|Djibouti|Africa|Eastern Africa
ER|Eritrea|Africa|Eastern Africa
ET|Ethiopia|Africa|Eastern Africa
TF|French Southern Territories|Africa|Eastern Africa
KE|Kenya|Africa|Eastern Africa
MG|Madagascar|Africa|Eastern Africa
MW|Malawi|Africa|Eastern Africa
MU|Mauritius|Africa|Eastern Africa
YT|Mayotte|Africa|Eastern Africa
MZ|Mozambique|Africa|Eastern Africa
RE|Réunion|Africa|Eastern Africa
RW|Rwanda|Africa|Eastern Africa
SC|Seychelles|Africa|Eastern Africa
SO|Somalia|Africa|Eastern Africa
SS|South Sudan|Africa|Eastern Africa
UG|Uganda|Africa|Eastern Africa
TZ|Tanzania|Africa|Eastern Africa
ZM|Zambia|Africa|Eastern Africa
ZW|Zimbabwe|Africa|Eastern Africa
AO|Angola|Africa|Middle Africa
CM|Cameroon|Africa|Middle Africa
CF|Central African Republic|Africa|Middle Africa
TD|Chad|Africa|Middle Africa
CG|Congo|Africa|Middle Africa
CD|Congo, Democratic Republic of the|Africa|Middle Africa
GQ|Equatorial Guinea|Africa|Middle Africa
GA|Gabon|Africa|Middle Africa
ST|Sao Tome and Principe|Africa|Middle Africa
BW|Botswana|Africa|Southern Africa
SZ|Eswatini|Africa|Southern Africa
LS|Lesotho|Africa|Southern Africa
NA|Namibia|Africa|Southern Africa
ZA|South Africa|Africa|Southern Africa
BJ|Benin|Africa|Western Africa
BF|Burkina Faso|Africa|Western Africa
CV|Cabo Verde|Africa|Western Africa
CI|Côte d'Ivoire|Africa|Western Africa
GM|Gambia|Africa|Western Africa
GH|Ghana|Africa|Western Africa
GN|Guinea|Africa|Western Africa
GW|Guinea-Bissau|Africa|Western Africa
LR|Liberia|Africa|Western Africa
ML|Mali|Africa|Western Africa
MR|Mauritania|Africa|Western Africa
NE|Niger|Africa|Western Africa
NG|Nigeria|Africa|Western Africa
SH|Saint Helena, Ascension and Tristan da Cunha|Africa|Western Africa
SN|Senegal|Africa|Western Africa
SL|Sierra Leone|Africa|Western Africa
TG|Togo|Africa|Western Africa
AI|Anguilla|Americas|Caribbean
AG|Antigua and Barbuda|Americas|Caribbean
AW|Aruba|Americas|Caribbean
BS|Bahamas|Americas|Caribbean
BB|Barbados|Americas|Caribbean
BQ|Bonaire, Sint Eustatius and Saba|Americas|Caribbean
VG|Virgin Islands (British)|Americas|Caribbean
KY|Cayman Islands|Americas|Caribbean
CU|Cuba|Americas|Caribbean
CW|Curaçao|Americas|Caribbean
DM|Dominica|Americas|Caribbean
DO|Dominican Republic|Americas|Caribbean
GD|Grenada|Americas|Caribbean
GP|Guadeloupe|Americas|Caribbean
HT|Haiti|Americas|Caribbean
JM|Jamaica|Americas|Caribbean
MQ|Martinique|Americas|Caribbean
MS|Montserrat|Americas|Caribbean
PR|Puerto Rico|Americas|Caribbean
BL|Saint Barthélemy|Americas|Caribbean
KN|Saint Kitts and Nevis|Americas|Caribbean
LC|Saint Lucia|Americas|Caribbean
MF|Saint Martin (French part)|Americas|Caribbean
VC|Saint Vincent and the Grenadines|Americas|Caribbean
SX|Sint Maarten (Dutch part)|Americas|Caribbean
TT|Trinidad and Tobago|Americas|Caribbean
TC|Turks and Caicos Islands|Americas|Caribbean
VI|Virgin Islands (U.S.)|Americas|Caribbean
BZ|Belize|Americas|Central America
CR|Costa Rica|Americas|Central America
SV|El Salvador|Americas|Central America
GT|Guatemala|Americas|Central America
HN|Honduras|Americas|Central America
MX|Mexico|Americas|Central America
NI|Nicaragua|Americas|Central America
PA|Panama|Americas|Central America
AR|Argentina|Americas|South America
BO|Bolivia|Americas|South America
BV|Bouvet Island|Americas|South America
BR|Brazil|Americas|South America
CL|Chile|Americas|South America
CO|Colombia|Americas|South America
EC|Ecuador|Americas|South America
FK|Falkland Islands (Malvinas)|Americas|South America
GF|French Guiana|Americas|South America
GY|Guyana|Americas|South America
PY|Paraguay|Americas|South America
PE|Peru|Americas|South America
GS|South Georgia and the South Sandwich Islands|Americas|South America
SR|Suriname|Americas|South America
UY|Uruguay|Americas|South America
VE|Venezuela|Americas|South America
BM|Bermuda|Americas|Northern America
CA|Canada|Americas|Northern America
GL|Greenland|Americas|Northern America
PM|Saint Pierre and Miquelon|Americas|Northern America
US|United States|Americas|Northern America
AQ|Antarctica|Antarctica|Antarctica
KZ|Kazakhstan|Asia|Central Asia
KG|Kyrgyzstan|Asia|Central Asia
TJ|Tajikistan|Asia|Central Asia
TM|Turkmenistan|Asia|Central Asia
UZ|Uzbekistan|Asia|Central Asia
CN|China|Asia|Eastern Asia
HK|Hong Kong|Asia|Eastern Asia
MO|Macao|Asia|Eastern Asia
KP|Korea, Democratic People's Republic of|Asia|Eastern Asia
JP|Japan|Asia|Eastern Asia
MN|Mongolia|Asia|Eastern Asia
KR|Korea, Republic of|Asia|Eastern Asia
TW|Taiwan|Asia|Eastern Asia
BN|Brunei Darussalam|Asia|South-eastern Asia
KH|Cambodia|Asia|South-eastern Asia
ID|Indonesia|Asia|South-eastern Asia
LA|Lao People's Democratic Republic|Asia|South-eastern Asia
MY|Malaysia|Asia|South-eastern Asia
MM|Myanmar|Asia|South-eastern Asia
PH|Philippines|Asia|South-eastern Asia
SG|Singapore|Asia|South-eastern Asia
TH|Thailand|Asia|South-eastern Asia
TL|Timor-Leste|Asia|South-eastern Asia
VN|Viet Nam|Asia|South-eastern Asia
AF|Afghanistan|Asia|Southern Asia
BD|Bangladesh|Asia|Southern Asia
BT|Bhutan|Asia|Southern Asia
IN|India|Asia|Southern Asia
IR|Iran|Asia|Southern Asia
MV|Maldives|Asia|Southern Asia
NP|Nepal|Asia|Southern Asia
PK|Pakistan|Asia|Southern Asia
LK|Sri Lanka|Asia|Southern Asia
AM|Armenia|Asia|Western Asia
AZ|Azerbaijan|Asia|Western Asia
BH|Bahrain|Asia|Western Asia
CY|Cyprus|Asia|Western Asia
GE|Georgia|Asia|Western Asia
IQ|Iraq|Asia|Western Asia
IL|Israel|Asia|Western Asia
JO|Jordan|Asia|Western Asia
KW|Kuwait|Asia|Western Asia
LB|Lebanon|Asia|Western Asia
OM|Oman|Asia|Western Asia
QA|Qatar|Asia|Western Asia
SA|Saudi Arabia|Asia|Western Asia
PS|Palestine, State of|Asia|Western Asia
SY|Syrian Arab Republic|Asia|Western Asia
TR|Türkiye|Asia|Western Asia
AE|United Arab Emirates|Asia|Western Asia
YE|Yemen|Asia|Western Asia
BY|Belarus|Europe|Eastern Europe
BG|Bulgaria|Europe|Eastern Europe
CZ|Czechia|Europe|Eastern Europe
HU|Hungary|Europe|Eastern Europe
PL|Poland|Europe|Eastern Europe
MD|Moldova|Europe|Eastern Europe
RO|Romania|Europe|Eastern Europe
RU|Russian Federation|Europe|Eastern Europe
SK|Slovakia|Europe|Eastern Europe
UA|Ukraine|Europe|Eastern Europe
AX|Åland Islands|Europe|Northern Europe
DK|Denmark|Europe|Northern Europe
EE|Estonia|Europe|Northern Europe
FO|Faroe Islands|Europe|Northern Europe
FI|Finland|Europe|Northern Europe
GG|Guernsey|Europe|Northern Europe
IS|Iceland|Europe|Northern Europe
IE|Ireland|Europe|Northern Europe
IM|Isle of Man|Europe|Northern Europe
JE|Jersey|Europe|Northern Europe
LV|Latvia|Europe|Northern Europe
LT|Lithuania|Europe|Northern Europe
NO|Norway|Europe|Northern Europe
SJ|Svalbard and Jan Mayen|Europe|Northern Europe
SE|Sweden|Europe|Northern Europe
GB|United Kingdom|Europe|Northern Europe
AL|Albania|Europe|Southern Europe
AD|Andorra|Europe|Southern Europe
BA|Bosnia and Herzegovina|Europe|Southern Europe
HR|Croatia|Europe|Southern Europe
GI|Gibraltar|Europe|Southern Europe
GR|Greece|Europe|Southern Europe
VA|Holy See|Europe|Southern Europe
IT|Italy|Europe|Southern Europe
MT|Malta|Europe|Southern Europe
ME|Montenegro|Europe|Southern Europe
MK|North Macedonia|Europe|Southern Europe
PT|Portugal|Europe|Southern Europe
SM|San Marino|Europe|Southern Europe
RS|Serbia|Europe|Southern Europe
SI|Slovenia|Europe|Southern Europe
ES|Spain|Europe|Southern Europe
AT|Austria|Europe|Western Europe
BE|Belgium|Europe|Western Europe
FR|France|Europe|Western Europe
DE|Germany|Europe|Western Europe
LI|Liechtenstein|Europe|Western Europe
LU|Luxembourg|Europe|Western Europe
MC|Monaco|Europe|Western Europe
NL|Netherlands|Europe|Western Europe
CH|Switzerland|Europe|Western Europe
AU|Australia|Oceania|Australia and New Zealand
CX|Christmas Island|Oceania|Australia and New Zealand
CC|Cocos (Keeling) Islands|Oceania|Australia and New Zealand
HM|Heard Island and McDonald Islands|Oceania|Australia and New Zealand
NZ|New Zealand|Oceania|Australia and New Zealand
NF|Norfolk Island|Oceania|Australia and New Zealand
FJ|Fiji|Oceania|Melanesia
NC|New Caledonia|Oceania|Melanesia
PG|Papua New Guinea|Oceania|Melanesia
SB|Solomon Islands|Oceania|Melanesia
VU|Vanuatu|Oceania|Melanesia
GU|Guam|Oceania|Micronesia
KI|Kiribati|Oceania|Micronesia
MH|Marshall Islands|Oceania|Micronesia
FM|Micronesia, Federated States of|Oceania|Micronesia
NR|Nauru|Oceania|Micronesia
MP|Northern Mariana Islands|Oceania|Micronesia
PW|Palau|Oceania|Micronesia
UM|United States Minor Outlying Islands|Oceania|Micronesia
AS|American Samoa|Oceania|Polynesia
CK|Cook Islands|Oceania|Polynesia
PF|French Polynesia|Oceania|Polynesia
NU|Niue|Oceania|Polynesia
PN|Pitcairn|Oceania|Polynesia
WS|Samoa|Oceania|Polynesia
TK|Tokelau|Oceania|Polynesia
TO|Tonga|Oceania|Polynesia
TV|Tuvalu|Oceania|Polynesia
WF|Wallis and Futuna|Oceania|Polynesia
"""

COUNTRIES: dict[str, tuple[str, str, str]] = {}
for _line in _RAW.strip().splitlines():
    _code, _name, _region, _sub = _line.split("|")
    COUNTRIES[_code] = (_name, _region, _sub)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()).strip("_")


# Regions: the five M49 regions, the M49 sub-regions, and economic groupings
# whose membership is fixed by treaty. Users may add custom regions.
REGIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {}
for _code, (_name, _region, _sub) in COUNTRIES.items():
    if _region == "Antarctica":
        continue
    for _rname, _kind in ((_region, "un_region"), (_sub, "un_subregion")):
        _rcode = _slug(_rname)
        name, kind, members = REGIONS.get(_rcode, (_rname, _kind, ()))
        REGIONS[_rcode] = (name, kind, members + (_code,))

REGIONS["GCC"] = ("Gulf Cooperation Council", "economic", ("AE", "BH", "KW", "OM", "QA", "SA"))
REGIONS["EU"] = ("European Union", "economic", (
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE"))
REGIONS["ASEAN"] = ("Association of Southeast Asian Nations", "economic",
                    ("BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"))
REGIONS["EAC"] = ("East African Community", "economic", ("BI", "CD", "KE", "RW", "SO", "SS", "TZ", "UG"))

# Alternative names seen in trade press and tender notices. Only unambiguous
# names: "Congo" alone is NOT mapped (two countries), nor is "Guinea".
ALIASES: dict[str, str] = {
    "UAE": "AE", "U.A.E.": "AE", "UNITED ARAB EMIRATES": "AE",
    "UK": "GB", "U.K.": "GB", "GREAT BRITAIN": "GB", "BRITAIN": "GB",
    "USA": "US", "U.S.A.": "US", "U.S.": "US", "UNITED STATES OF AMERICA": "US",
    "KSA": "SA", "KINGDOM OF SAUDI ARABIA": "SA",
    "RUSSIA": "RU", "SOUTH KOREA": "KR", "NORTH KOREA": "KP", "VIETNAM": "VN", "LAOS": "LA", "IRAN": "IR",
    "SYRIA": "SY", "TANZANIA": "TZ", "UNITED REPUBLIC OF TANZANIA": "TZ", "BOLIVIA": "BO", "VENEZUELA": "VE",
    "MOLDOVA": "MD", "CZECH REPUBLIC": "CZ", "TURKEY": "TR", "TURKIYE": "TR", "IVORY COAST": "CI", "COTE D'IVOIRE": "CI",
    "CAPE VERDE": "CV", "SWAZILAND": "SZ", "MACEDONIA": "MK", "BURMA": "MM", "DRC": "CD", "DR CONGO": "CD",
    "DEMOCRATIC REPUBLIC OF THE CONGO": "CD", "REPUBLIC OF THE CONGO": "CG", "CONGO-BRAZZAVILLE": "CG", "BRUNEI": "BN",
    "PALESTINE": "PS", "HONG KONG SAR": "HK", "MACAU": "MO", "HOLLAND": "NL", "THE NETHERLANDS": "NL",
    "THE GAMBIA": "GM", "THE BAHAMAS": "BS", "EAST TIMOR": "TL", "REUNION": "RE", "CURACAO": "CW",
    "SAO TOME": "ST", "ESWATINI": "SZ", "KIRGHIZIA": "KG", "KYRGYZ REPUBLIC": "KG",
    # Local-language names met in French, Spanish, Portuguese and German notices (accents are stripped by norm()).
    "OSTERREICH": "AT", "DEUTSCHLAND": "DE", "SCHWEIZ": "CH", "FRANKREICH": "FR", "ITALIEN": "IT", "SPANIEN": "ES", "BELGIEN": "BE",
    "NIEDERLANDE": "NL", "POLEN": "PL", "TSCHECHIEN": "CZ", "UNGARN": "HU", "DANEMARK": "DK", "SCHWEDEN": "SE", "NORWEGEN": "NO",
    "VEREINIGTE ARABISCHE EMIRATE": "AE", "VEREINIGTES KONIGREICH": "GB", "AGYPTEN": "EG", "SUDAFRIKA": "ZA", "KENIA": "KE",
    "ALLEMAGNE": "DE", "AUTRICHE": "AT", "SUISSE": "CH", "ESPAGNE": "ES", "ITALIE": "IT", "BELGIQUE": "BE", "PAYS-BAS": "NL", "ROYAUME-UNI": "GB",
    "EMIRATS ARABES UNIS": "AE", "ARABIE SAOUDITE": "SA", "EGYPTE": "EG", "AFRIQUE DU SUD": "ZA", "MAROC": "MA", "ALGERIE": "DZ", "TUNISIE": "TN",
    "SENEGAL": "SN", "CAMEROUN": "CM", "ETHIOPIE": "ET", "MAURICE": "MU", "ILE MAURICE": "MU", "GUINEE": "GN", "TCHAD": "TD", "NIGER": "NE",
    "ALEMANIA": "DE", "ESPANA": "ES", "ITALIA": "IT", "FRANCIA": "FR", "REINO UNIDO": "GB", "PAISES BAJOS": "NL", "BELGICA": "BE", "SUIZA": "CH",
    "EMIRATOS ARABES UNIDOS": "AE", "ARABIA SAUDITA": "SA", "ESTADOS UNIDOS": "US", "MEXICO": "MX", "BRASIL": "BR", "PERU": "PE",
    "MARRUECOS": "MA", "SUDAFRICA": "ZA", "EGIPTO": "EG", "ANGOLA": "AO", "MOCAMBIQUE": "MZ", "MOZAMBIQUE": "MZ", "CABO VERDE": "CV",
    "GUINE-BISSAU": "GW", "SAO TOME E PRINCIPE": "ST", "INGLATERRA": "GB", "ALEMANHA": "DE", "FRANCA": "FR", "ESPANHA": "ES", "SUICA": "CH",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9.' -]", " ", s)).strip()


_NAME_INDEX: dict[str, str] = {}
for _code, (_name, _r, _s) in COUNTRIES.items():
    _NAME_INDEX[norm(_name)] = _code
    if "," in _name:  # "Korea, Republic of" -> also "Republic of Korea"
        a, b = _name.split(",", 1)
        _NAME_INDEX[norm(f"{b.strip()} {a.strip()}")] = _code
for _alias, _code in ALIASES.items():
    _NAME_INDEX[norm(_alias)] = _code


def resolve_country(text: str | None) -> str | None:
    """ISO alpha-2 code for a country name, alias or code; None if not a
    recognised country. Codes must be given in upper case to avoid matching
    ordinary words ('in', 'it', 'no')."""
    if not text:
        return None
    raw = text.strip()
    if len(raw) == 2 and raw.isalpha() and raw.isupper() and raw in COUNTRIES:
        return raw
    return _NAME_INDEX.get(norm(raw))


def country_names(code: str) -> list[str]:
    """Every name this module recognises for a country, for text matching."""
    out = [n for n, c in _NAME_INDEX.items() if c == code and len(n) > 3]
    return sorted(set(out), key=len, reverse=True)


def countries_mentioned(text: str) -> set[str]:
    """Countries named in free text (full names and unambiguous aliases only;
    two-letter codes are not matched in prose)."""
    t = f" {norm(text)} "
    found: set[str] = set()
    for n, c in _NAME_INDEX.items():
        if len(n) <= 3 and "." not in n and n not in ("UAE", "KSA", "USA", "DRC", "UK"):
            continue
        if re.search(rf"(?<![A-Z0-9]){re.escape(n)}(?![A-Z0-9])", t):
            found.add(c)
    return found


def expand_geography(mode: str, countries: list[str], regions: list[str],
                     custom_regions: dict[str, tuple[str, ...]] | None = None) -> set[str] | None:
    """Country set for a search. None means worldwide (no restriction)."""
    if mode == "worldwide":
        return None
    out = {c.upper() for c in countries if c.upper() in COUNTRIES}
    for r in regions:
        if r in REGIONS:
            out |= set(REGIONS[r][2])
        elif custom_regions and r in custom_regions:
            out |= set(custom_regions[r])
    return out
