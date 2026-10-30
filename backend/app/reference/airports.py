"""Reference: the bundled airport seed and the lookups used by the rules (30 Oct 2026: the global airport directory).

The directory itself is the `airport_directory` table (migration wfc_0016), loaded with provenance from a maintained public dataset
by `tools/load_airports.py` (OurAirports: airports.csv, public domain) and searchable by name, IATA, ICAO, city and country,
including airports without an IATA code. This module holds the BUNDLED SEED that the migration loads first, so a fresh install can
select an airport before the full dataset is loaded; the seed is a curated starting set (major and secondary cargo, passenger and
regional airports), it is NOT the directory, and every row is replaced by the maintained dataset's row when that is loaded.
A code not in the directory is kept as written and labelled "airport not resolved". Presence in the directory never means the
airport handles cargo: freight relevance is assessed from evidence, separately from airport selection.

Line format: IATA|ICAO|name|city|ISO country|type   (type: large_airport, medium_airport, small_airport)
"""
from __future__ import annotations

SEED_PROVENANCE = {"key": "airport_seed", "name": "ATLAS bundled airport seed", "source": "curated by the ATLAS build (public knowledge; codes as published by ICAO/IATA)",
                   "version": "2026-10-30", "licence": "no restriction", "notes": "starting set only; load the maintained dataset for the full directory"}

_RAW = """
AMS|EHAM|Amsterdam Airport Schiphol|Amsterdam|NL|large_airport
RTM|EHRD|Rotterdam The Hague Airport|Rotterdam|NL|medium_airport
MST|EHBK|Maastricht Aachen Airport|Maastricht|NL|medium_airport
EIN|EHEH|Eindhoven Airport|Eindhoven|NL|medium_airport
BRU|EBBR|Brussels Airport|Brussels|BE|large_airport
LGG|EBLG|Liège Airport|Liège|BE|medium_airport
CRL|EBCI|Brussels South Charleroi Airport|Charleroi|BE|medium_airport
OST|EBOS|Ostend-Bruges International Airport|Ostend|BE|medium_airport
ANR|EBAW|Antwerp International Airport|Antwerp|BE|medium_airport
LUX|ELLX|Luxembourg Airport|Luxembourg|LU|large_airport
CDG|LFPG|Paris Charles de Gaulle Airport|Paris|FR|large_airport
ORY|LFPO|Paris Orly Airport|Paris|FR|large_airport
LYS|LFLL|Lyon Saint-Exupéry Airport|Lyon|FR|large_airport
MRS|LFML|Marseille Provence Airport|Marseille|FR|large_airport
TLS|LFBO|Toulouse-Blagnac Airport|Toulouse|FR|large_airport
NCE|LFMN|Nice Côte d'Azur Airport|Nice|FR|large_airport
BOD|LFBD|Bordeaux-Mérignac Airport|Bordeaux|FR|large_airport
NTE|LFRS|Nantes Atlantique Airport|Nantes|FR|large_airport
LIL|LFQQ|Lille Airport|Lille|FR|medium_airport
CFE|LFLC|Clermont-Ferrand Auvergne Airport|Clermont-Ferrand|FR|medium_airport
BVA|LFOB|Paris Beauvais-Tillé Airport|Beauvais|FR|medium_airport
FRA|EDDF|Frankfurt Airport|Frankfurt|DE|large_airport
MUC|EDDM|Munich Airport|Munich|DE|large_airport
HHN|EDFH|Frankfurt-Hahn Airport|Hahn|DE|medium_airport
LEJ|EDDP|Leipzig/Halle Airport|Leipzig|DE|large_airport
CGN|EDDK|Cologne Bonn Airport|Cologne|DE|large_airport
DUS|EDDL|Düsseldorf Airport|Düsseldorf|DE|large_airport
HAM|EDDH|Hamburg Airport|Hamburg|DE|large_airport
BER|EDDB|Berlin Brandenburg Airport|Berlin|DE|large_airport
STR|EDDS|Stuttgart Airport|Stuttgart|DE|large_airport
NUE|EDDN|Nuremberg Airport|Nuremberg|DE|medium_airport
HAJ|EDDV|Hannover Airport|Hannover|DE|large_airport
FMO|EDDG|Münster Osnabrück Airport|Münster|DE|medium_airport
LHR|EGLL|London Heathrow Airport|London|GB|large_airport
LGW|EGKK|London Gatwick Airport|London|GB|large_airport
STN|EGSS|London Stansted Airport|London|GB|large_airport
LTN|EGGW|London Luton Airport|London|GB|large_airport
EMA|EGNX|East Midlands Airport|Nottingham|GB|large_airport
MAN|EGCC|Manchester Airport|Manchester|GB|large_airport
BHX|EGBB|Birmingham Airport|Birmingham|GB|large_airport
EDI|EGPH|Edinburgh Airport|Edinburgh|GB|large_airport
GLA|EGPF|Glasgow Airport|Glasgow|GB|large_airport
PIK|EGPK|Glasgow Prestwick Airport|Prestwick|GB|medium_airport
BFS|EGAA|Belfast International Airport|Belfast|GB|large_airport
BRS|EGGD|Bristol Airport|Bristol|GB|large_airport
NCL|EGNT|Newcastle Airport|Newcastle|GB|large_airport
DUB|EIDW|Dublin Airport|Dublin|IE|large_airport
SNN|EINN|Shannon Airport|Shannon|IE|large_airport
ORK|EICK|Cork Airport|Cork|IE|medium_airport
MXP|LIMC|Milan Malpensa Airport|Milan|IT|large_airport
LIN|LIML|Milan Linate Airport|Milan|IT|large_airport
BGY|LIME|Milan Bergamo Airport|Bergamo|IT|large_airport
FCO|LIRF|Rome Fiumicino Airport|Rome|IT|large_airport
VCE|LIPZ|Venice Marco Polo Airport|Venice|IT|large_airport
BLQ|LIPE|Bologna Guglielmo Marconi Airport|Bologna|IT|large_airport
NAP|LIRN|Naples International Airport|Naples|IT|large_airport
BRI|LIBD|Bari Karol Wojtyła Airport|Bari|IT|medium_airport
CTA|LICC|Catania-Fontanarossa Airport|Catania|IT|large_airport
MAD|LEMD|Adolfo Suárez Madrid-Barajas Airport|Madrid|ES|large_airport
BCN|LEBL|Josep Tarradellas Barcelona-El Prat Airport|Barcelona|ES|large_airport
ZAZ|LEZG|Zaragoza Airport|Zaragoza|ES|medium_airport
VIT|LEVT|Vitoria Airport|Vitoria-Gasteiz|ES|medium_airport
VLC|LEVC|Valencia Airport|Valencia|ES|large_airport
AGP|LEMG|Málaga-Costa del Sol Airport|Málaga|ES|large_airport
PMI|LEPA|Palma de Mallorca Airport|Palma|ES|large_airport
SVQ|LEZL|Seville Airport|Seville|ES|large_airport
BIO|LEBB|Bilbao Airport|Bilbao|ES|medium_airport
LPA|GCLP|Gran Canaria Airport|Las Palmas|ES|large_airport
TFS|GCTS|Tenerife South Airport|Tenerife|ES|large_airport
LIS|LPPT|Lisbon Humberto Delgado Airport|Lisbon|PT|large_airport
OPO|LPPR|Porto Airport|Porto|PT|large_airport
FAO|LPFR|Faro Airport|Faro|PT|large_airport
ZRH|LSZH|Zurich Airport|Zurich|CH|large_airport
GVA|LSGG|Geneva Airport|Geneva|CH|large_airport
BSL|LFSB|EuroAirport Basel Mulhouse Freiburg|Basel|CH|large_airport
VIE|LOWW|Vienna International Airport|Vienna|AT|large_airport
LNZ|LOWL|Linz Airport|Linz|AT|medium_airport
CPH|EKCH|Copenhagen Airport|Copenhagen|DK|large_airport
BLL|EKBI|Billund Airport|Billund|DK|large_airport
ARN|ESSA|Stockholm Arlanda Airport|Stockholm|SE|large_airport
GOT|ESGG|Gothenburg Landvetter Airport|Gothenburg|SE|large_airport
MMX|ESMS|Malmö Airport|Malmö|SE|medium_airport
OSL|ENGM|Oslo Gardermoen Airport|Oslo|NO|large_airport
BGO|ENBR|Bergen Airport Flesland|Bergen|NO|large_airport
TRD|ENVA|Trondheim Airport Værnes|Trondheim|NO|large_airport
SVG|ENZV|Stavanger Airport Sola|Stavanger|NO|large_airport
HEL|EFHK|Helsinki-Vantaa Airport|Helsinki|FI|large_airport
KEF|BIKF|Keflavík International Airport|Reykjavík|IS|large_airport
WAW|EPWA|Warsaw Chopin Airport|Warsaw|PL|large_airport
KTW|EPKT|Katowice Airport|Katowice|PL|large_airport
KRK|EPKK|Kraków John Paul II International Airport|Kraków|PL|large_airport
GDN|EPGD|Gdańsk Lech Wałęsa Airport|Gdańsk|PL|large_airport
WRO|EPWR|Wrocław Copernicus Airport|Wrocław|PL|large_airport
POZ|EPPO|Poznań-Ławica Airport|Poznań|PL|medium_airport
RZE|EPRZ|Rzeszów-Jasionka Airport|Rzeszów|PL|medium_airport
PRG|LKPR|Václav Havel Airport Prague|Prague|CZ|large_airport
BRQ|LKTB|Brno-Tuřany Airport|Brno|CZ|medium_airport
OSR|LKMT|Ostrava Leoš Janáček Airport|Ostrava|CZ|medium_airport
BTS|LZIB|Bratislava Airport|Bratislava|SK|medium_airport
KSC|LZKZ|Košice International Airport|Košice|SK|medium_airport
BUD|LHBP|Budapest Ferenc Liszt International Airport|Budapest|HU|large_airport
DEB|LHDC|Debrecen International Airport|Debrecen|HU|medium_airport
OTP|LROP|Bucharest Henri Coandă International Airport|Bucharest|RO|large_airport
CLJ|LRCL|Cluj-Napoca International Airport|Cluj-Napoca|RO|medium_airport
TSR|LRTR|Timișoara Traian Vuia International Airport|Timișoara|RO|medium_airport
SOF|LBSF|Sofia Airport|Sofia|BG|large_airport
VAR|LBWN|Varna Airport|Varna|BG|medium_airport
BEG|LYBE|Belgrade Nikola Tesla Airport|Belgrade|RS|large_airport
ZAG|LDZA|Zagreb Franjo Tuđman Airport|Zagreb|HR|large_airport
LJU|LJLJ|Ljubljana Jože Pučnik Airport|Ljubljana|SI|medium_airport
SJJ|LQSA|Sarajevo International Airport|Sarajevo|BA|medium_airport
SKP|LWSK|Skopje International Airport|Skopje|MK|medium_airport
TIA|LATI|Tirana International Airport Nënë Tereza|Tirana|AL|medium_airport
ATH|LGAV|Athens International Airport Eleftherios Venizelos|Athens|GR|large_airport
SKG|LGTS|Thessaloniki Airport Makedonia|Thessaloniki|GR|large_airport
LCA|LCLK|Larnaca International Airport|Larnaca|CY|large_airport
MLA|LMML|Malta International Airport|Luqa|MT|large_airport
VNO|EYVI|Vilnius Airport|Vilnius|LT|large_airport
KUN|EYKA|Kaunas Airport|Kaunas|LT|medium_airport
PLQ|EYPA|Palanga International Airport|Palanga|LT|medium_airport
RIX|EVRA|Riga International Airport|Riga|LV|large_airport
TLL|EETN|Tallinn Lennart Meri Airport|Tallinn|EE|large_airport
KIV|LUKK|Chișinău International Airport|Chișinău|MD|medium_airport
KBP|UKBB|Boryspil International Airport|Kyiv|UA|large_airport
LWO|UKLL|Lviv Danylo Halytskyi International Airport|Lviv|UA|medium_airport
MSQ|UMMS|Minsk National Airport|Minsk|BY|large_airport
IST|LTFM|Istanbul Airport|Istanbul|TR|large_airport
SAW|LTFJ|Istanbul Sabiha Gökçen International Airport|Istanbul|TR|large_airport
ESB|LTAC|Ankara Esenboğa International Airport|Ankara|TR|large_airport
ADB|LTBJ|İzmir Adnan Menderes Airport|İzmir|TR|large_airport
AYT|LTAI|Antalya Airport|Antalya|TR|large_airport
DXB|OMDB|Dubai International Airport|Dubai|AE|large_airport
DWC|OMDW|Al Maktoum International Airport (Dubai World Central)|Dubai|AE|large_airport
AUH|OMAA|Zayed International Airport|Abu Dhabi|AE|large_airport
SHJ|OMSJ|Sharjah International Airport|Sharjah|AE|large_airport
RKT|OMRK|Ras Al Khaimah International Airport|Ras Al Khaimah|AE|medium_airport
FJR|OMFJ|Fujairah International Airport|Fujairah|AE|medium_airport
AAN|OMAL|Al Ain International Airport|Al Ain|AE|medium_airport
DOH|OTHH|Hamad International Airport|Doha|QA|large_airport
BAH|OBBI|Bahrain International Airport|Manama|BH|large_airport
KWI|OKKK|Kuwait International Airport|Kuwait City|KW|large_airport
MCT|OOMS|Muscat International Airport|Muscat|OM|large_airport
SLL|OOSA|Salalah Airport|Salalah|OM|medium_airport
DQM|OODQ|Duqm International Airport|Duqm|OM|medium_airport
OHS|OOSH|Sohar Airport|Sohar|OM|medium_airport
RUH|OERK|King Khalid International Airport|Riyadh|SA|large_airport
JED|OEJN|King Abdulaziz International Airport|Jeddah|SA|large_airport
DMM|OEDF|King Fahd International Airport|Dammam|SA|large_airport
MED|OEMA|Prince Mohammad bin Abdulaziz International Airport|Medina|SA|large_airport
AMM|OJAI|Queen Alia International Airport|Amman|JO|large_airport
AQJ|OJAQ|King Hussein International Airport|Aqaba|JO|medium_airport
BEY|OLBA|Beirut-Rafic Hariri International Airport|Beirut|LB|large_airport
TLV|LLBG|Ben Gurion Airport|Tel Aviv|IL|large_airport
BGW|ORBI|Baghdad International Airport|Baghdad|IQ|large_airport
EBL|ORER|Erbil International Airport|Erbil|IQ|large_airport
BSR|ORMM|Basra International Airport|Basra|IQ|medium_airport
IKA|OIIE|Tehran Imam Khomeini International Airport|Tehran|IR|large_airport
CAI|HECA|Cairo International Airport|Cairo|EG|large_airport
ALY|HEBA|Borg El Arab Airport|Alexandria|EG|medium_airport
HRG|HEGN|Hurghada International Airport|Hurghada|EG|large_airport
CMN|GMMN|Mohammed V International Airport|Casablanca|MA|large_airport
TNG|GMTT|Tangier Ibn Battouta Airport|Tangier|MA|medium_airport
RAK|GMMX|Marrakesh Menara Airport|Marrakesh|MA|large_airport
AGA|GMAD|Agadir-Al Massira Airport|Agadir|MA|medium_airport
ALG|DAAG|Houari Boumediene Airport|Algiers|DZ|large_airport
ORN|DAOO|Oran Ahmed Ben Bella Airport|Oran|DZ|medium_airport
TUN|DTTA|Tunis-Carthage International Airport|Tunis|TN|large_airport
TIP|HLLT|Tripoli International Airport|Tripoli|LY|medium_airport
MJI|HLLM|Mitiga International Airport|Tripoli|LY|medium_airport
KRT|HSSK|Khartoum International Airport|Khartoum|SD|large_airport
ADD|HAAB|Addis Ababa Bole International Airport|Addis Ababa|ET|large_airport
JIB|HDAM|Djibouti-Ambouli International Airport|Djibouti|DJ|medium_airport
NBO|HKJK|Jomo Kenyatta International Airport|Nairobi|KE|large_airport
MBA|HKMO|Moi International Airport|Mombasa|KE|large_airport
EDL|HKEL|Eldoret International Airport|Eldoret|KE|medium_airport
EBB|HUEN|Entebbe International Airport|Entebbe|UG|large_airport
DAR|HTDA|Julius Nyerere International Airport|Dar es Salaam|TZ|large_airport
JRO|HTKJ|Kilimanjaro International Airport|Arusha|TZ|medium_airport
ZNZ|HTZA|Abeid Amani Karume International Airport|Zanzibar|TZ|medium_airport
KGL|HRYR|Kigali International Airport|Kigali|RW|large_airport
BJM|HBBA|Bujumbura International Airport|Bujumbura|BI|medium_airport
JUB|HSSJ|Juba International Airport|Juba|SS|medium_airport
MGQ|HCMM|Aden Adde International Airport|Mogadishu|SO|medium_airport
JNB|FAOR|O. R. Tambo International Airport|Johannesburg|ZA|large_airport
CPT|FACT|Cape Town International Airport|Cape Town|ZA|large_airport
DUR|FALE|King Shaka International Airport|Durban|ZA|large_airport
PLZ|FAPE|Chief Dawid Stuurman International Airport|Gqeberha|ZA|medium_airport
HLA|FALA|Lanseria International Airport|Johannesburg|ZA|medium_airport
WDH|FYWH|Hosea Kutako International Airport|Windhoek|NA|medium_airport
GBE|FBSK|Sir Seretse Khama International Airport|Gaborone|BW|medium_airport
MPM|FQMA|Maputo International Airport|Maputo|MZ|medium_airport
BEW|FQBR|Beira Airport|Beira|MZ|medium_airport
LUN|FLKK|Kenneth Kaunda International Airport|Lusaka|ZM|medium_airport
NLA|FLSK|Simon Mwansa Kapwepwe International Airport|Ndola|ZM|medium_airport
HRE|FVRG|Robert Gabriel Mugabe International Airport|Harare|ZW|medium_airport
LLW|FWKI|Lilongwe International Airport|Lilongwe|MW|medium_airport
LAD|FNLU|Quatro de Fevereiro International Airport|Luanda|AO|large_airport
MRU|FIMP|Sir Seewoosagur Ramgoolam International Airport|Port Louis|MU|large_airport
RUN|FMEE|Roland Garros Airport|Saint-Denis|RE|medium_airport
TNR|FMMI|Ivato International Airport|Antananarivo|MG|medium_airport
SEZ|FSIA|Seychelles International Airport|Mahé|SC|medium_airport
FIH|FZAA|N'djili International Airport|Kinshasa|CD|large_airport
FBM|FZQA|Lubumbashi International Airport|Lubumbashi|CD|medium_airport
BZV|FCBB|Maya-Maya Airport|Brazzaville|CG|medium_airport
PNR|FCPP|Pointe-Noire Airport|Pointe-Noire|CG|medium_airport
DLA|FKKD|Douala International Airport|Douala|CM|medium_airport
NSI|FKYS|Yaoundé Nsimalen International Airport|Yaoundé|CM|medium_airport
LBV|FOOL|Léon-Mba International Airport|Libreville|GA|medium_airport
SSG|FGSL|Malabo International Airport|Malabo|GQ|medium_airport
NDJ|FTTJ|N'Djamena International Airport|N'Djamena|TD|medium_airport
LOS|DNMM|Murtala Muhammed International Airport|Lagos|NG|large_airport
ABV|DNAA|Nnamdi Azikiwe International Airport|Abuja|NG|large_airport
PHC|DNPO|Port Harcourt International Airport|Port Harcourt|NG|medium_airport
KAN|DNKN|Mallam Aminu Kano International Airport|Kano|NG|medium_airport
ACC|DGAA|Kotoka International Airport|Accra|GH|large_airport
ABJ|DIAP|Félix-Houphouët-Boigny International Airport|Abidjan|CI|large_airport
LFW|DXXX|Lomé-Tokoin International Airport|Lomé|TG|medium_airport
COO|DBBB|Cadjehoun Airport|Cotonou|BJ|medium_airport
OUA|DFFD|Ouagadougou Airport|Ouagadougou|BF|medium_airport
NIM|DRRN|Diori Hamani International Airport|Niamey|NE|medium_airport
BKO|GABS|Modibo Keita International Airport|Bamako|ML|medium_airport
DSS|GOBD|Blaise Diagne International Airport|Dakar|SN|large_airport
DKR|GOOY|Léopold Sédar Senghor International Airport|Dakar|SN|medium_airport
CKY|GUCY|Conakry International Airport|Conakry|GN|medium_airport
FNA|GFLL|Lungi International Airport|Freetown|SL|medium_airport
ROB|GLRB|Roberts International Airport|Monrovia|LR|medium_airport
BJL|GBYD|Banjul International Airport|Banjul|GM|medium_airport
NKC|GQNO|Nouakchott-Oumtounsy International Airport|Nouakchott|MR|medium_airport
RAI|GVNP|Nelson Mandela International Airport|Praia|CV|medium_airport
SID|GVAC|Amílcar Cabral International Airport|Sal|CV|medium_airport
BOM|VABB|Chhatrapati Shivaji Maharaj International Airport|Mumbai|IN|large_airport
DEL|VIDP|Indira Gandhi International Airport|Delhi|IN|large_airport
BLR|VOBL|Kempegowda International Airport|Bengaluru|IN|large_airport
MAA|VOMM|Chennai International Airport|Chennai|IN|large_airport
HYD|VOHS|Rajiv Gandhi International Airport|Hyderabad|IN|large_airport
CCU|VECC|Netaji Subhas Chandra Bose International Airport|Kolkata|IN|large_airport
AMD|VAAH|Sardar Vallabhbhai Patel International Airport|Ahmedabad|IN|large_airport
COK|VOCI|Cochin International Airport|Kochi|IN|large_airport
TRV|VOTV|Trivandrum International Airport|Thiruvananthapuram|IN|large_airport
PNQ|VAPO|Pune Airport|Pune|IN|medium_airport
NAG|VANP|Dr. Babasaheb Ambedkar International Airport|Nagpur|IN|medium_airport
CMB|VCBI|Bandaranaike International Airport|Colombo|LK|large_airport
MLE|VRMM|Velana International Airport|Malé|MV|large_airport
DAC|VGHS|Hazrat Shahjalal International Airport|Dhaka|BD|large_airport
CGP|VGEG|Shah Amanat International Airport|Chattogram|BD|medium_airport
KHI|OPKC|Jinnah International Airport|Karachi|PK|large_airport
LHE|OPLA|Allama Iqbal International Airport|Lahore|PK|large_airport
ISB|OPIS|Islamabad International Airport|Islamabad|PK|large_airport
KTM|VNKT|Tribhuvan International Airport|Kathmandu|NP|large_airport
KBL|OAKB|Kabul International Airport|Kabul|AF|medium_airport
SIN|WSSS|Singapore Changi Airport|Singapore|SG|large_airport
KUL|WMKK|Kuala Lumpur International Airport|Kuala Lumpur|MY|large_airport
PEN|WMKP|Penang International Airport|Penang|MY|large_airport
JHB|WMKJ|Senai International Airport|Johor Bahru|MY|medium_airport
BKI|WBKK|Kota Kinabalu International Airport|Kota Kinabalu|MY|large_airport
BKK|VTBS|Suvarnabhumi Airport|Bangkok|TH|large_airport
DMK|VTBD|Don Mueang International Airport|Bangkok|TH|large_airport
CNX|VTCC|Chiang Mai International Airport|Chiang Mai|TH|large_airport
HKT|VTSP|Phuket International Airport|Phuket|TH|large_airport
HAN|VVNB|Noi Bai International Airport|Hanoi|VN|large_airport
SGN|VVTS|Tan Son Nhat International Airport|Ho Chi Minh City|VN|large_airport
DAD|VVDN|Da Nang International Airport|Da Nang|VN|large_airport
CGK|WIII|Soekarno-Hatta International Airport|Jakarta|ID|large_airport
SUB|WARR|Juanda International Airport|Surabaya|ID|large_airport
DPS|WADD|I Gusti Ngurah Rai International Airport|Denpasar|ID|large_airport
KNO|WIMM|Kualanamu International Airport|Medan|ID|large_airport
MNL|RPLL|Ninoy Aquino International Airport|Manila|PH|large_airport
CRK|RPLC|Clark International Airport|Angeles City|PH|large_airport
CEB|RPVM|Mactan-Cebu International Airport|Cebu|PH|large_airport
PNH|VDPP|Phnom Penh International Airport|Phnom Penh|KH|large_airport
VTE|VLVT|Wattay International Airport|Vientiane|LA|medium_airport
RGN|VYYY|Yangon International Airport|Yangon|MM|large_airport
BWN|WBSB|Brunei International Airport|Bandar Seri Begawan|BN|medium_airport
HKG|VHHH|Hong Kong International Airport|Hong Kong|HK|large_airport
MFM|VMMC|Macau International Airport|Macau|MO|large_airport
PVG|ZSPD|Shanghai Pudong International Airport|Shanghai|CN|large_airport
SHA|ZSSS|Shanghai Hongqiao International Airport|Shanghai|CN|large_airport
PEK|ZBAA|Beijing Capital International Airport|Beijing|CN|large_airport
PKX|ZBAD|Beijing Daxing International Airport|Beijing|CN|large_airport
CAN|ZGGG|Guangzhou Baiyun International Airport|Guangzhou|CN|large_airport
SZX|ZGSZ|Shenzhen Bao'an International Airport|Shenzhen|CN|large_airport
CTU|ZUUU|Chengdu Shuangliu International Airport|Chengdu|CN|large_airport
TFU|ZUTF|Chengdu Tianfu International Airport|Chengdu|CN|large_airport
CKG|ZUCK|Chongqing Jiangbei International Airport|Chongqing|CN|large_airport
HGH|ZSHC|Hangzhou Xiaoshan International Airport|Hangzhou|CN|large_airport
NKG|ZSNJ|Nanjing Lukou International Airport|Nanjing|CN|large_airport
XIY|ZLXY|Xi'an Xianyang International Airport|Xi'an|CN|large_airport
WUH|ZHHH|Wuhan Tianhe International Airport|Wuhan|CN|large_airport
EHU|ZHEC|Ezhou Huahu Airport|Ezhou|CN|large_airport
CGO|ZHCC|Zhengzhou Xinzheng International Airport|Zhengzhou|CN|large_airport
TSN|ZBTJ|Tianjin Binhai International Airport|Tianjin|CN|large_airport
XMN|ZSAM|Xiamen Gaoqi International Airport|Xiamen|CN|large_airport
KMG|ZPPP|Kunming Changshui International Airport|Kunming|CN|large_airport
URC|ZWWW|Ürümqi Diwopu International Airport|Ürümqi|CN|large_airport
TPE|RCTP|Taiwan Taoyuan International Airport|Taipei|TW|large_airport
KHH|RCKH|Kaohsiung International Airport|Kaohsiung|TW|large_airport
ICN|RKSI|Incheon International Airport|Seoul|KR|large_airport
GMP|RKSS|Gimpo International Airport|Seoul|KR|large_airport
PUS|RKPK|Gimhae International Airport|Busan|KR|large_airport
NRT|RJAA|Narita International Airport|Tokyo|JP|large_airport
HND|RJTT|Tokyo Haneda Airport|Tokyo|JP|large_airport
KIX|RJBB|Kansai International Airport|Osaka|JP|large_airport
NGO|RJGG|Chubu Centrair International Airport|Nagoya|JP|large_airport
FUK|RJFF|Fukuoka Airport|Fukuoka|JP|large_airport
CTS|RJCC|New Chitose Airport|Sapporo|JP|large_airport
OKA|ROAH|Naha Airport|Okinawa|JP|large_airport
ULN|ZMCK|Chinggis Khaan International Airport|Ulaanbaatar|MN|medium_airport
ALA|UAAA|Almaty International Airport|Almaty|KZ|large_airport
NQZ|UACC|Nursultan Nazarbayev International Airport|Astana|KZ|large_airport
TAS|UTTT|Tashkent International Airport|Tashkent|UZ|large_airport
NVI|UTSA|Navoi International Airport|Navoi|UZ|medium_airport
FRU|UCFM|Manas International Airport|Bishkek|KG|medium_airport
DYU|UTDD|Dushanbe International Airport|Dushanbe|TJ|medium_airport
ASB|UTAA|Ashgabat International Airport|Ashgabat|TM|medium_airport
GYD|UBBB|Heydar Aliyev International Airport|Baku|AZ|large_airport
TBS|UGTB|Tbilisi International Airport|Tbilisi|GE|large_airport
EVN|UDYZ|Zvartnots International Airport|Yerevan|AM|large_airport
SVO|UUEE|Sheremetyevo International Airport|Moscow|RU|large_airport
DME|UUDD|Domodedovo International Airport|Moscow|RU|large_airport
VKO|UUWW|Vnukovo International Airport|Moscow|RU|large_airport
LED|ULLI|Pulkovo Airport|Saint Petersburg|RU|large_airport
SVX|USSS|Koltsovo International Airport|Yekaterinburg|RU|large_airport
OVB|UNNT|Tolmachevo Airport|Novosibirsk|RU|large_airport
KJA|UNKL|Krasnoyarsk International Airport|Krasnoyarsk|RU|large_airport
KHV|UHHH|Khabarovsk Novy Airport|Khabarovsk|RU|large_airport
VVO|UHWW|Vladivostok International Airport|Vladivostok|RU|large_airport
SYD|YSSY|Sydney Kingsford Smith Airport|Sydney|AU|large_airport
MEL|YMML|Melbourne Airport|Melbourne|AU|large_airport
BNE|YBBN|Brisbane Airport|Brisbane|AU|large_airport
PER|YPPH|Perth Airport|Perth|AU|large_airport
ADL|YPAD|Adelaide Airport|Adelaide|AU|large_airport
CNS|YBCS|Cairns Airport|Cairns|AU|large_airport
DRW|YPDN|Darwin International Airport|Darwin|AU|large_airport
TWB|YBWW|Toowoomba Wellcamp Airport|Toowoomba|AU|medium_airport
AKL|NZAA|Auckland Airport|Auckland|NZ|large_airport
CHC|NZCH|Christchurch Airport|Christchurch|NZ|large_airport
WLG|NZWN|Wellington International Airport|Wellington|NZ|large_airport
NAN|NFFN|Nadi International Airport|Nadi|FJ|large_airport
POM|AYPY|Port Moresby Jacksons International Airport|Port Moresby|PG|medium_airport
PPT|NTAA|Faa'a International Airport|Papeete|PF|large_airport
NOU|NWWW|La Tontouta International Airport|Nouméa|NC|medium_airport
JFK|KJFK|John F. Kennedy International Airport|New York|US|large_airport
EWR|KEWR|Newark Liberty International Airport|Newark|US|large_airport
ORD|KORD|Chicago O'Hare International Airport|Chicago|US|large_airport
RFD|KRFD|Chicago Rockford International Airport|Rockford|US|medium_airport
LAX|KLAX|Los Angeles International Airport|Los Angeles|US|large_airport
ONT|KONT|Ontario International Airport|Ontario|US|large_airport
MIA|KMIA|Miami International Airport|Miami|US|large_airport
ATL|KATL|Hartsfield-Jackson Atlanta International Airport|Atlanta|US|large_airport
DFW|KDFW|Dallas/Fort Worth International Airport|Dallas|US|large_airport
AFW|KAFW|Fort Worth Alliance Airport|Fort Worth|US|medium_airport
IAH|KIAH|George Bush Intercontinental Airport|Houston|US|large_airport
SFO|KSFO|San Francisco International Airport|San Francisco|US|large_airport
OAK|KOAK|Oakland International Airport|Oakland|US|large_airport
SEA|KSEA|Seattle-Tacoma International Airport|Seattle|US|large_airport
ANC|PANC|Ted Stevens Anchorage International Airport|Anchorage|US|large_airport
MEM|KMEM|Memphis International Airport|Memphis|US|large_airport
SDF|KSDF|Louisville Muhammad Ali International Airport|Louisville|US|large_airport
CVG|KCVG|Cincinnati/Northern Kentucky International Airport|Cincinnati|US|large_airport
IND|KIND|Indianapolis International Airport|Indianapolis|US|large_airport
BOS|KBOS|Boston Logan International Airport|Boston|US|large_airport
IAD|KIAD|Washington Dulles International Airport|Washington|US|large_airport
PHL|KPHL|Philadelphia International Airport|Philadelphia|US|large_airport
DEN|KDEN|Denver International Airport|Denver|US|large_airport
PHX|KPHX|Phoenix Sky Harbor International Airport|Phoenix|US|large_airport
MSP|KMSP|Minneapolis-Saint Paul International Airport|Minneapolis|US|large_airport
DTW|KDTW|Detroit Metropolitan Wayne County Airport|Detroit|US|large_airport
CLT|KCLT|Charlotte Douglas International Airport|Charlotte|US|large_airport
MCO|KMCO|Orlando International Airport|Orlando|US|large_airport
LCK|KLCK|Rickenbacker International Airport|Columbus|US|medium_airport
HNL|PHNL|Daniel K. Inouye International Airport|Honolulu|US|large_airport
YYZ|CYYZ|Toronto Pearson International Airport|Toronto|CA|large_airport
YHM|CYHM|John C. Munro Hamilton International Airport|Hamilton|CA|medium_airport
YVR|CYVR|Vancouver International Airport|Vancouver|CA|large_airport
YUL|CYUL|Montréal-Pierre Elliott Trudeau International Airport|Montreal|CA|large_airport
YMX|CYMX|Montréal-Mirabel International Airport|Montreal|CA|medium_airport
YYC|CYYC|Calgary International Airport|Calgary|CA|large_airport
YEG|CYEG|Edmonton International Airport|Edmonton|CA|large_airport
YWG|CYWG|Winnipeg James Armstrong Richardson International Airport|Winnipeg|CA|large_airport
YHZ|CYHZ|Halifax Stanfield International Airport|Halifax|CA|large_airport
MEX|MMMX|Mexico City International Airport|Mexico City|MX|large_airport
NLU|MMSM|Felipe Ángeles International Airport|Mexico City|MX|large_airport
GDL|MMGL|Guadalajara International Airport|Guadalajara|MX|large_airport
MTY|MMMY|Monterrey International Airport|Monterrey|MX|large_airport
QRO|MMQT|Querétaro Intercontinental Airport|Querétaro|MX|medium_airport
CUN|MMUN|Cancún International Airport|Cancún|MX|large_airport
GUA|MGGT|La Aurora International Airport|Guatemala City|GT|medium_airport
SAL|MSLP|El Salvador International Airport|San Salvador|SV|medium_airport
SJO|MROC|Juan Santamaría International Airport|San José|CR|large_airport
PTY|MPTO|Tocumen International Airport|Panama City|PA|large_airport
HAV|MUHA|José Martí International Airport|Havana|CU|large_airport
SDQ|MDSD|Las Américas International Airport|Santo Domingo|DO|large_airport
SJU|TJSJ|Luis Muñoz Marín International Airport|San Juan|PR|large_airport
KIN|MKJP|Norman Manley International Airport|Kingston|JM|medium_airport
POS|TTPP|Piarco International Airport|Port of Spain|TT|medium_airport
BGI|TBPB|Grantley Adams International Airport|Bridgetown|BB|medium_airport
CUR|TNCC|Curaçao International Airport|Willemstad|CW|medium_airport
BOG|SKBO|El Dorado International Airport|Bogotá|CO|large_airport
MDE|SKRG|José María Córdova International Airport|Medellín|CO|large_airport
CLO|SKCL|Alfonso Bonilla Aragón International Airport|Cali|CO|large_airport
UIO|SEQM|Mariscal Sucre International Airport|Quito|EC|large_airport
GYE|SEGU|José Joaquín de Olmedo International Airport|Guayaquil|EC|large_airport
LIM|SPJC|Jorge Chávez International Airport|Lima|PE|large_airport
LPB|SLLP|El Alto International Airport|La Paz|BO|medium_airport
VVI|SLVR|Viru Viru International Airport|Santa Cruz|BO|large_airport
SCL|SCEL|Arturo Merino Benítez International Airport|Santiago|CL|large_airport
EZE|SAEZ|Ministro Pistarini International Airport|Buenos Aires|AR|large_airport
AEP|SABE|Aeroparque Jorge Newbery|Buenos Aires|AR|large_airport
COR|SACO|Ingeniero Ambrosio Taravella International Airport|Córdoba|AR|medium_airport
MVD|SUMU|Carrasco International Airport|Montevideo|UY|large_airport
ASU|SGAS|Silvio Pettirossi International Airport|Asunción|PY|medium_airport
GRU|SBGR|São Paulo/Guarulhos International Airport|São Paulo|BR|large_airport
VCP|SBKP|Viracopos International Airport|Campinas|BR|large_airport
GIG|SBGL|Rio de Janeiro/Galeão International Airport|Rio de Janeiro|BR|large_airport
CNF|SBCF|Belo Horizonte/Confins International Airport|Belo Horizonte|BR|large_airport
BSB|SBBR|Brasília International Airport|Brasília|BR|large_airport
MAO|SBEG|Manaus/Eduardo Gomes International Airport|Manaus|BR|large_airport
REC|SBRF|Recife/Guararapes International Airport|Recife|BR|large_airport
FOR|SBFZ|Fortaleza Pinto Martins International Airport|Fortaleza|BR|large_airport
CWB|SBCT|Curitiba Afonso Pena International Airport|Curitiba|BR|large_airport
POA|SBPA|Porto Alegre Salgado Filho International Airport|Porto Alegre|BR|large_airport
CCS|SVMI|Simón Bolívar International Airport|Caracas|VE|large_airport
GEO|SYCJ|Cheddi Jagan International Airport|Georgetown|GY|medium_airport
PBM|SMJP|Johan Adolf Pengel International Airport|Paramaribo|SR|medium_airport
"""

AIRPORTS: dict[str, tuple[str, str, str]] = {}            # IATA -> (name, city, country), as before
SEED: list[dict[str, str]] = []
for _line in _RAW.strip().splitlines():
    _iata, _icao, _name, _city, _country, _type = _line.split("|")
    AIRPORTS.setdefault(_iata, (_name, _city, _country))
    SEED.append({"iata": _iata, "icao": _icao, "name": _name, "city": _city, "country": _country, "type": _type})


def airport(code: str | None) -> tuple[str, str, str] | None:
    """(name, city, country) for an IATA code in the bundled seed; the directory service answers for everything else."""
    return AIRPORTS.get((code or "").strip().upper()) if code else None


def airports_in(country: str) -> list[str]:
    return [c for c, (_n, _ci, cc) in AIRPORTS.items() if cc == country.upper()]
