"""Reference: IATA two-character airline designators -> airline name, for reading supplied lists such as "LO | M6 | FO" and for
naming represented airlines in queries. Deliberately limited to well-known carriers; a code not listed is kept exactly as written
and labelled "airline not resolved" rather than guessed. Designators are reassigned over time, so a resolution is a reading aid,
never evidence: the represented-airline fact stays "supplied" or "sourced" according to where it came from.
"""
from __future__ import annotations

import re

_RAW = """
AA|American Airlines
AC|Air Canada
AF|Air France
AH|Air Algérie
AI|Air India
AM|Aeroméxico
AT|Royal Air Maroc
AV|Avianca
AY|Finnair
AZ|ITA Airways
A3|Aegean Airlines
BA|British Airways
BR|EVA Air
BT|airBaltic
BW|Caribbean Airlines
CA|Air China
CI|China Airlines
CK|China Cargo Airlines
CM|Copa Airlines
CV|Cargolux
CX|Cathay Pacific
CZ|China Southern Airlines
DE|Condor
DL|Delta Air Lines
DT|TAAG Angola Airlines
DY|Norwegian
EI|Aer Lingus
EK|Emirates
ET|Ethiopian Airlines
EY|Etihad Airways
FB|Bulgaria Air
FI|Icelandair
FX|FedEx Express
GA|Garuda Indonesia
GF|Gulf Air
GQ|Sky Express
HA|Hawaiian Airlines
HO|Juneyao Air
HU|Hainan Airlines
IB|Iberia
JD|Beijing Capital Airlines
JL|Japan Airlines
JU|Air Serbia
KE|Korean Air
KL|KLM Royal Dutch Airlines
KM|KM Malta Airlines (formerly Air Malta)
KN|China United Airlines
KQ|Kenya Airways
KU|Kuwait Airways
K4|Kalitta Air
LA|LATAM Airlines
LH|Lufthansa
LO|LOT Polish Airlines
LX|Swiss International Air Lines
LY|El Al
ME|Middle East Airlines
MH|Malaysia Airlines
MK|Air Mauritius
MP|Martinair
MS|EgyptAir
MU|China Eastern Airlines
M6|Amerijet International
NH|All Nippon Airways
NZ|Air New Zealand
OS|Austrian Airlines
OU|Croatia Airlines
OZ|Asiana Airlines
PK|Pakistan International Airlines
PR|Philippine Airlines
PS|Ukraine International Airlines
QF|Qantas
QR|Qatar Airways
QS|Smartwings
QT|Avianca Cargo
QY|European Air Transport (DHL)
RJ|Royal Jordanian
RU|AirBridgeCargo
SA|South African Airways
SK|SAS Scandinavian Airlines
SN|Brussels Airlines
SQ|Singapore Airlines
SS|Corsair
SU|Aeroflot
SV|Saudia
TB|TUI fly Belgium
TG|Thai Airways
TK|Turkish Airlines
TN|Air Tahiti Nui
TP|TAP Air Portugal
TS|Air Transat
TU|Tunisair
TX|Air Caraïbes
UA|United Airlines
UL|SriLankan Airlines
UU|Air Austral
UX|Air Europa
VN|Vietnam Airlines
VS|Virgin Atlantic
VY|Vueling
WB|RwandAir
WY|Oman Air
W8|Cargojet
XC|Corendon Airlines
XQ|SunExpress
Y8|Suparna Airlines
2C|CMA CGM Air Cargo
3O|Air Arabia Maroc
3U|Sichuan Airlines
5J|Cebu Pacific
5C|Challenge Airlines
5X|UPS Airlines
7C|Jeju Air
"""

AIRLINE_CODES: dict[str, str] = {}
for _line in _RAW.strip().splitlines():
    _code, _name = _line.split("|")
    AIRLINE_CODES[_code] = _name

_CODE = re.compile(r"^[A-Z0-9]{2,3}$")


def split_codes(text: str | None) -> list[str]:
    """'LO | M6 | FO | 3O' or 'IB/VY' or 'ALL' -> ['LO', 'M6', 'FO', '3O'] (codes as written, upper-cased, deduplicated)."""
    out: list[str] = []
    for part in re.split(r"[|/,;]+", text or ""):
        p = part.strip().upper()
        if p and _CODE.match(p) and p not in out:
            out.append(p)
    return out


def resolve(code: str) -> tuple[str | None, str]:
    """(name or None, label): the name when the designator is in the reference; otherwise the code as written."""
    name = AIRLINE_CODES.get(code.upper())
    return (name, f"{name} ({code})") if name else (None, f"{code} (airline not resolved)")
