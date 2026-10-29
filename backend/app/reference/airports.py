"""Reference: major air cargo airports (IATA code -> name, city, ISO country). Used to resolve an airport named in a brief or a
supplied dataset ("GSA list BRU") to its country, and to name airports in queries. Not exhaustive: an unknown code is kept as
written and labelled "airport not resolved". Values are public knowledge; no operational data.
"""
from __future__ import annotations

_RAW = """
AMS|Amsterdam Schiphol|Amsterdam|NL
BRU|Brussels Airport|Brussels|BE
LGG|Liège Airport|Liège|BE
CDG|Paris Charles de Gaulle|Paris|FR
ORY|Paris Orly|Paris|FR
FRA|Frankfurt Airport|Frankfurt|DE
MUC|Munich Airport|Munich|DE
HHN|Frankfurt-Hahn|Hahn|DE
LEJ|Leipzig/Halle|Leipzig|DE
CGN|Cologne Bonn|Cologne|DE
LHR|London Heathrow|London|GB
LGW|London Gatwick|London|GB
STN|London Stansted|London|GB
EMA|East Midlands|Nottingham|GB
MAN|Manchester|Manchester|GB
DUB|Dublin|Dublin|IE
LUX|Luxembourg Findel|Luxembourg|LU
MXP|Milan Malpensa|Milan|IT
FCO|Rome Fiumicino|Rome|IT
MAD|Madrid Barajas|Madrid|ES
BCN|Barcelona El Prat|Barcelona|ES
ZAZ|Zaragoza|Zaragoza|ES
LIS|Lisbon|Lisbon|PT
ZRH|Zurich|Zurich|CH
GVA|Geneva|Geneva|CH
VIE|Vienna|Vienna|AT
CPH|Copenhagen|Copenhagen|DK
ARN|Stockholm Arlanda|Stockholm|SE
OSL|Oslo Gardermoen|Oslo|NO
HEL|Helsinki-Vantaa|Helsinki|FI
WAW|Warsaw Chopin|Warsaw|PL
PRG|Prague|Prague|CZ
BUD|Budapest|Budapest|HU
OTP|Bucharest Otopeni|Bucharest|RO
ATH|Athens|Athens|GR
IST|Istanbul|Istanbul|TR
SAW|Istanbul Sabiha Gökçen|Istanbul|TR
DXB|Dubai International|Dubai|AE
DWC|Dubai World Central (Al Maktoum)|Dubai|AE
AUH|Abu Dhabi Zayed|Abu Dhabi|AE
SHJ|Sharjah|Sharjah|AE
DOH|Doha Hamad|Doha|QA
BAH|Bahrain|Manama|BH
KWI|Kuwait|Kuwait City|KW
MCT|Muscat|Muscat|OM
SLL|Salalah|Salalah|OM
RUH|Riyadh King Khalid|Riyadh|SA
JED|Jeddah King Abdulaziz|Jeddah|SA
DMM|Dammam King Fahd|Dammam|SA
AMM|Amman Queen Alia|Amman|JO
BEY|Beirut|Beirut|LB
TLV|Tel Aviv Ben Gurion|Tel Aviv|IL
CAI|Cairo|Cairo|EG
CMN|Casablanca Mohammed V|Casablanca|MA
ALG|Algiers|Algiers|DZ
TUN|Tunis Carthage|Tunis|TN
NBO|Nairobi Jomo Kenyatta|Nairobi|KE
MBA|Mombasa Moi|Mombasa|KE
EBB|Entebbe|Entebbe|UG
DAR|Dar es Salaam Julius Nyerere|Dar es Salaam|TZ
JRO|Kilimanjaro|Arusha|TZ
KGL|Kigali|Kigali|RW
ADD|Addis Ababa Bole|Addis Ababa|ET
JNB|Johannesburg O. R. Tambo|Johannesburg|ZA
CPT|Cape Town|Cape Town|ZA
DUR|Durban King Shaka|Durban|ZA
LOS|Lagos Murtala Muhammed|Lagos|NG
ABV|Abuja|Abuja|NG
ACC|Accra Kotoka|Accra|GH
ABJ|Abidjan Félix-Houphouët-Boigny|Abidjan|CI
DKR|Dakar Blaise Diagne|Dakar|SN
DSS|Dakar Blaise Diagne|Dakar|SN
LUN|Lusaka Kenneth Kaunda|Lusaka|ZM
HRE|Harare|Harare|ZW
LAD|Luanda|Luanda|AO
MPM|Maputo|Maputo|MZ
MRU|Mauritius Sir Seewoosagur Ramgoolam|Port Louis|MU
TNR|Antananarivo|Antananarivo|MG
FIH|Kinshasa N'djili|Kinshasa|CD
DLA|Douala|Douala|CM
BOM|Mumbai Chhatrapati Shivaji|Mumbai|IN
DEL|Delhi Indira Gandhi|Delhi|IN
BLR|Bengaluru Kempegowda|Bengaluru|IN
MAA|Chennai|Chennai|IN
HYD|Hyderabad|Hyderabad|IN
CCU|Kolkata|Kolkata|IN
CMB|Colombo Bandaranaike|Colombo|LK
DAC|Dhaka Hazrat Shahjalal|Dhaka|BD
KHI|Karachi Jinnah|Karachi|PK
LHE|Lahore|Lahore|PK
ISB|Islamabad|Islamabad|PK
KTM|Kathmandu Tribhuvan|Kathmandu|NP
SIN|Singapore Changi|Singapore|SG
KUL|Kuala Lumpur|Kuala Lumpur|MY
PEN|Penang|Penang|MY
BKK|Bangkok Suvarnabhumi|Bangkok|TH
HAN|Hanoi Noi Bai|Hanoi|VN
SGN|Ho Chi Minh City Tan Son Nhat|Ho Chi Minh City|VN
CGK|Jakarta Soekarno-Hatta|Jakarta|ID
MNL|Manila Ninoy Aquino|Manila|PH
PNH|Phnom Penh|Phnom Penh|KH
HKG|Hong Kong|Hong Kong|HK
PVG|Shanghai Pudong|Shanghai|CN
PEK|Beijing Capital|Beijing|CN
CAN|Guangzhou Baiyun|Guangzhou|CN
SZX|Shenzhen Bao'an|Shenzhen|CN
CTU|Chengdu|Chengdu|CN
TPE|Taipei Taoyuan|Taipei|TW
ICN|Seoul Incheon|Seoul|KR
NRT|Tokyo Narita|Tokyo|JP
HND|Tokyo Haneda|Tokyo|JP
KIX|Osaka Kansai|Osaka|JP
SYD|Sydney Kingsford Smith|Sydney|AU
MEL|Melbourne|Melbourne|AU
BNE|Brisbane|Brisbane|AU
PER|Perth|Perth|AU
AKL|Auckland|Auckland|NZ
JFK|New York JFK|New York|US
EWR|Newark Liberty|Newark|US
ORD|Chicago O'Hare|Chicago|US
LAX|Los Angeles|Los Angeles|US
MIA|Miami|Miami|US
ATL|Atlanta Hartsfield-Jackson|Atlanta|US
DFW|Dallas/Fort Worth|Dallas|US
IAH|Houston George Bush|Houston|US
SFO|San Francisco|San Francisco|US
ANC|Anchorage Ted Stevens|Anchorage|US
MEM|Memphis|Memphis|US
SDF|Louisville|Louisville|US
CVG|Cincinnati/Northern Kentucky|Cincinnati|US
YYZ|Toronto Pearson|Toronto|CA
YVR|Vancouver|Vancouver|CA
YUL|Montréal-Trudeau|Montreal|CA
MEX|Mexico City|Mexico City|MX
GRU|São Paulo Guarulhos|São Paulo|BR
VCP|Campinas Viracopos|Campinas|BR
GIG|Rio de Janeiro Galeão|Rio de Janeiro|BR
EZE|Buenos Aires Ezeiza|Buenos Aires|AR
SCL|Santiago|Santiago|CL
BOG|Bogotá El Dorado|Bogotá|CO
LIM|Lima Jorge Chávez|Lima|PE
UIO|Quito|Quito|EC
PTY|Panama City Tocumen|Panama City|PA
ALA|Almaty|Almaty|KZ
TAS|Tashkent|Tashkent|UZ
BKU|Baku Heydar Aliyev|Baku|AZ
GYD|Baku Heydar Aliyev|Baku|AZ
TBS|Tbilisi|Tbilisi|GE
"""

AIRPORTS: dict[str, tuple[str, str, str]] = {}
for _line in _RAW.strip().splitlines():
    _code, _name, _city, _country = _line.split("|")
    AIRPORTS[_code] = (_name, _city, _country)


def airport(code: str | None) -> tuple[str, str, str] | None:
    return AIRPORTS.get((code or "").strip().upper()) if code else None


def airports_in(country: str) -> list[str]:
    return [c for c, (_n, _ci, cc) in AIRPORTS.items() if cc == country.upper()]
