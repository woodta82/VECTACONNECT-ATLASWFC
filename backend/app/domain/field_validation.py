"""Per-field validation of extracted claims (directive §7).

A quotation appearing in the document is NOT enough. Every material field
of a claim is validated on its own:

1. the field's quote must appear verbatim in the document; and
2. the quote must itself state the field's value (the airline's name or
   code, the country, the tender reference, the status wording, the date,
   the eligibility wording, the amount and currency ...).

A field that fails either test is `unsupported`: it is kept for review but
never becomes a fact, never sets identity, deadline, status or geography,
and never feeds qualification. Fields that a claim type cannot establish
(a route announcement cannot establish a tender reference, an open
appointment, eligibility or a payable value) are `not_applicable`.

The claim's TYPE is validated the same way: a quote that does not describe
a tender cannot make a claim a tender, whatever the extractor said.

Meaning, not keyword presence (review of 26 Oct 2026): every keyword and
country match is read in its clause (`domain.meaning`). Negated wording
("is not inviting bids"), past processes ("invited bids in 2019") and plans
("plans to invite") do not establish a current tender or an open status;
conflicting status wording is not resolved by guessing; a country supports
a delivery field only when the sentence makes it the place of delivery, not
where the issuer is based; an eligibility value is supported only when the
quote states that requirement. Ambiguity is reported as unsupported so a
person reviews it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Literal

from ..reference.cities import cities_in_text, city_countries
from ..reference.geography import COUNTRIES, countries_mentioned, resolve_country
from . import deadlines as dl
from . import eligibility, meaning, relevance

Support = Literal["supported", "unsupported", "not_applicable", "review_required"]


def eligibility_sentences(value: str, quote: str) -> str:
    """The sentence(s) of the quote that state the requirement the value claims (shared numbers or most content words),
    so an unrelated "or" or condition elsewhere in the quote does not change the verdict."""
    want, want_n = meaning._content(value)
    picked = []
    for sent in re.split(r"(?<=[.;!?])\s+|\n+", quote):
        have, have_n = meaning._content(sent)
        if (want_n & have_n) or (want and len(want & have) * 2 >= len(want)):
            picked.append(sent)
    return " ".join(picked) or quote

FIELDS = ("organisation", "airline", "opportunity_type", "country", "issuer_country", "contract_territory", "origin", "destination",
          "tender_ref", "procurement_cycle", "status", "deadline", "eligibility", "published_value", "service", "freight_scope")
GEO_FIELDS = ("country", "issuer_country", "contract_territory", "origin", "destination")
TENDER_TYPES = {"gssa_tender", "tender_deadline", "tender_scope", "tender_status", "eligibility", "service_tender", "tender_context"}
ROUTE_TYPES = {"route_launch", "route_suspension", "capacity_statement"}
TENDER_ANCHOR_TYPES = {"gssa_tender", "service_tender", "tcm_signal"}
TERMINAL_STATUSES = ("cancelled", "awarded", "closed")
# Which stated roles support each geography field (domain.meaning.country_roles).
GEO_ACCEPTS: dict[str, set[str]] = {"country": {"scope"}, "contract_territory": {"scope"}, "issuer_country": {"issuer"},
                                    "origin": {"origin"}, "destination": {"destination", "scope"}}
ROUTE_SCOPE_ROLES = {"origin", "destination"}
GEO_LABEL = {"scope": "the place of delivery", "issuer": "where the issuer is based", "origin": "the route origin",
             "destination": "the route destination"}
GEO_LABEL_FIELD = {"country": "the delivery country", "contract_territory": "the contract territory", "issuer_country": "the issuer's location",
                   "origin": "the route origin", "destination": "the route destination"}
# What a route/capacity announcement cannot establish.
ROUTE_NOT_APPLICABLE = {"tender_ref", "procurement_cycle", "status", "eligibility", "published_value", "deadline"}

TYPE_LEXICON: dict[str, tuple[str, ...]] = {
    "gssa_tender": (r"\bgssas?\b", r"\bgsas?\b", r"general sales (?:and service )?agen", r"cargo sales agen", r"sales (?:and service )?representation",
                    r"\bagents? g[ée]n[ée]ra(?:l|ux) de vente", r"\bagentes? generales? de ventas?\b"),
    "tcm_signal": (r"total cargo management", r"\btcm\b"),
    "service_tender": (r"\btender\b", r"\brfp\b", r"\brfq\b", r"request for (proposal|quotation|information)", r"\binvit",
                       r"requests? (?:for )?(?:proposals?|quotations?|bids?|offers?)", r"\bseeks? (?:a |an )?(?:provider|supplier|contractor|proposals?|bids?|quotations?)",
                       r"\b(?:is |are )?seeking\b[^.;]{0,60}\b(?:agents?|gsas?|gssas?|providers?|suppliers?|contractors?|partners?|proposals?|bids?|quotations?|operators?)\b",
                       r"\bbids?\b", r"procurement", r"expressions? of interest", r"\beoi\b", r"\bpre-?qualification\b", r"\brfi\b",
                       r"\bplans? to (?:contract|engage|appoint|procure)\b", r"\bcall for (?:tenders?|bids?|proposals?|applications?|candidates?)\b",
                       # French: appel d'offres, appel public à la concurrence, consultation, procédure de sélection, sélection d'un opérateur/prestataire
                       r"appel d'offres?", r"appel public a la concurrence", r"appel a (?:candidatures?|concurrence|manifestation)", r"\bconsultation\b",
                       r"proc[ée]dure de s[ée]lection", r"s[ée]lection d(?:'un|'une|e|es) (?:op[ée]rateur|prestataire|fournisseur|candidat)",
                       r"\brecherche (?:un|une|des) (?:prestataire|fournisseur|op[ée]rateur|partenaire|agent)", r"\bmarch[ée] public\b", r"\bavis de march[ée]\b",
                       # Spanish
                       r"\blicitaci", r"\bconcurso\b", r"\bconvoca", r"\bsolicita (?:ofertas|propuestas)\b", r"\bproceso de selecci[oó]n\b",
                       r"\bpropostas?\b", r"\bausschreib", r"\bschreibt\b", r"\bangebote\b"),
    "route_launch": (r"\blaunch", r"new (freighter )?(route|service|flight)", r"\bcommenc", r"\binaugur",
                     r"\b(?:has|have) (?:introduced|added|opened|started)\b", r"\bintroduc(?:es|ed|ing)\b[^.;]{0,60}\b(?:service|route|flights?|rotation|connection)",
                     r"\b(?:daily|weekly|new|twice-weekly|thrice-weekly)\s+(?:road feeder|rfs|trucking|truck|freighter|cargo)\s+(?:service|connection|link|route)\b",
                     r"\bstart(s|ing)? (operating|flights|service)", r"\bwill (operate|fly|begin|start|serve)\b"),
    "route_suspension": (r"\bsuspen", r"\bcease", r"\bdiscontinu", r"\bterminat"),
    "representation_change": (r"\bappoint", r"\bgssa\b", r"\bgsa\b", r"representation", r"general sales"),
    "partnership": (r"\bpartner", r"\bagreement\b", r"\balliance\b", r"\bcooperat", r"memorandum", r"\bmou\b", r"joint venture"),
    "capacity_statement": (r"\bcapacity\b", r"\bfreighters?\b", r"\btonnes?\b", r"\btons?\b", r"frequenc", r"\bweekly\b"),
    "tender_deadline": (r"deadline", r"\bdue\b", r"no later than", r"\bby\b.*\d", r"closing date", r"submi"),
    "tender_scope": (r"\bscope\b", r"services? (required|include)", r"responsib", r"\bcover", r"\blots?\s*(?:no\.?\s*)?[a-z0-9]{1,3}\b", r"\bschedule\s+[a-z0-9]{1,3}\b",
                     r"\bterritor", r"\bpackage\s*\d", r"\bp[ée]rim[èe]tre\b", r"\balcance\b"),
    "tender_status": (r"\bopen\b", r"\bcancel", r"\bextend", r"\bamend", r"\baward", r"\bclosed\b", r"\bpostpon", r"\bwithdr", r"\bannul",
                      r"\bsuspend", r"\bterminat", r"\bresciss", r"\babandon", r"\bno longer\b",
                      # French / Spanish status wording
                      r"\badjudic", r"\basignad", r"\battribu", r"\bprorrog", r"\breport[ée]", r"\bprolong", r"\bretir", r"\bdesiert", r"\bsuspendid",
                      r"\bfinaliza el proceso\b", r"\bcl[ôo]tur", r"\bcerrad",
                      # an amendment that changes the closing date or a requirement without the words "extended"/"amended"
                      r"\bis now\b", r"\bare now\b", r"\bnow due\b", r"\b(?:has|have) been (?:moved|changed|brought forward|put back|rescheduled)\b",
                      r"\b(?:moved|changed|rescheduled|brought forward|put back) (?:from|to)\b", r"\b(?:increased|raised|reduced|lowered|decreased) from\b",
                      r"\bcorrigendum\b", r"\baddendum\b"),
    "eligibility": (r"eligib", r"\bmust\b", r"\brequire", r"\bminimum\b", r"criteria", r"qualif",
                    r"\bshould (?:have|hold|possess|be|provide|submit|demonstrate)\b", r"\b(?:tender|bid) (?:security|bond|guarantee)\b", r"\bbank guarantee\b",
                    r"\bearnest money\b", r"\bcaution(?:nement)?\b", r"\bgarant[ií]a\b", r"\bfianza\b",
                    r"\bonly\b[^.;]{0,80}\bmay (?:apply|bid|tender|participate|submit|respond)\b", r"\b(?:open|restricted|limited) (?:only )?to\b",
                    r"\bare (?:not )?eligible\b", r"\bshall (?:hold|have|possess|demonstrate)\b",
                    # French
                    r"\bdoivent\b", r"\bdevront\b", r"\bexig", r"\badmissib", r"\b[ée]ligib", r"\bcrit[èe]res?\b", r"\bau moins\b", r"\bau minimum\b",
                    r"\bseuls?\b[^.;]{0,80}\bpeuvent\b", r"\br[ée]serv[ée]e? aux?\b", r"\bjustifier d",
                    # Spanish
                    r"\bdeben\b", r"\bdeber[áa]n\b", r"\brequisit", r"\bal menos\b", r"\bcomo m[íi]nimo\b", r"\bs[óo]lo\b[^.;]{0,80}\bpodr[áa]n\b",
                    r"\bpodr[áa]n participar\b", r"\bcontar con\b", r"\bacreditar\b", r"\bhabilitad"),
    "other": (),
}
# A tender for representation must also say it is a procurement.
_PROCUREMENT = TYPE_LEXICON["service_tender"] + (r"\bappoint", r"\bselect", r"\blots?\s*(?:no\.?\s*)?(?:\d|[a-z]\b)")
_EOI = (r"expressions? of interest", r"\beoi\b", r"\bpre-?qualification\b", r"request for information", r"\brfi\b", r"\bmanifestation d'int[ée]r[êe]t\b",
        r"\bmanifestaci[oó]n de inter[ée]s\b")

STATUS_LEXICON: dict[str, tuple[str, ...]] = {
    # OPEN: wording that states applications are being accepted now (an active invitation, a submission instruction, a closing
    # date, "now open"). A heading or title that only names the procurement ("Request for proposal ...", "RFP", "appel d'offres",
    # "licitación") is ANNOUNCED wording (below): it establishes that the notice exists, not that it is still open.
    "open": (r"\binvit(?:es|ing|e|ed)\b", r"\b(?:are|is) (?:hereby )?invited\b", r"\bnow open\b", r"\bopen for\b", r"\bis open\b", r"\bremains? open\b",
             r"\bopen (?:requests?|tenders?|rfps?|calls?|opportunities|procurements?)\b",
             r"submissions? (are )?(due|by|before|must)", r"proposals? (are )?(due|must)", r"\b(?:must|shall|should|are to) be (?:submitted|received|lodged)\b",
             r"\bseeks?\b", r"\bseeking\b", r"bids? (are )?due", r"\bclosing date\b", r"\blast date (?:for|of) submission\b",
             r"\b(?:deadline|due date|closing)\s*[:\-]\s*\d", r"\bsubmission deadline\b",
             r"\bdeadline for (?:\w+ ){0,2}(?:submissions?|proposals?|bids?|offers?|applications?|responses?)\b",
             r"\binterested (?:parties|agents|bidders|providers|companies) (?:should|must|are invited|may)\b", r"\bnow accepting\b",
             # French
             r"\blance\b", r"doivent etre soumises", r"\bdoivent parvenir\b", r"date limite de (?:r[ée]ception|d[ée]p[oô]t|remise|soumission)",
             r"\brecherche (?:un|une|des)\b", r"\bsont invit[ée]s\b",
             # Spanish / Portuguese
             r"\bpropostas? devem\b", r"\bdevem ser entregues\b", r"\bdeben presentarse\b", r"\bse recib(?:en|ir[áa]n)\b",
             r"plazo de (?:recepci[oó]n|presentaci[oó]n)", r"\bsolicita (?:ofertas|propuestas)\b", r"\bsolicita propostas\b", r"\bfecha l[ií]mite\b",
             # "convoca" is the present-tense verb ("X convoca una licitación" = "X calls a tender", like "invites");
             # the noun "convocatoria" is a heading and stays in "announced"
             r"\bconvoca\b",
             r"\bangebote sind\b", r"\beinzureichen\b", r"\bbis sp[äa]testens\b"),
    "announced": (r"request for (?:proposals?|quotations?|information)", r"requests? (?:for )?(?:proposals?|quotations?|bids?|offers?)", r"\brfp\b", r"\brfq\b",
                  r"\brfi\b", r"expressions? of interest", r"\beoi\b", r"\bpre-?qualification\b", r"\bcall for (?:tenders?|bids?|proposals?)\b",
                  r"\binvitation to (?:bid|tender)\b", r"\btender notice\b", r"\bprocurement notice\b",
                  r"appel d'offres?", r"appel public a la concurrence", r"appel a candidatures?", r"\bconsultation\b", r"proc[ée]dure de s[ée]lection",
                  r"\bavis de march[ée]\b", r"\bconvocat[oó]ria\b", r"\blicitaci", r"\bconcurso\b", r"\bausschreib", r"\bschreibt\b"),
    "revised": (r"\bamend", r"\brevis", r"\bextend", r"\bextension\b", r"\bpostpon", r"corrigendum", r"addendum", r"\bnew (?:deadline|closing date|due date)\b",
                r"\b(?:has|have) been (?:moved|changed|brought forward|put back|rescheduled)\b", r"\b(?:moved|changed|rescheduled) from\b",
                r"\bnow due\b", r"\bis now\b[^.;]{0,30}\b\d{4}\b", r"\bupdate(?:d)? of\b", r"\bprorrog", r"\breport[ée]e?\b", r"\bprolong"),
    "cancelled": (r"\bcancel", r"\bwithdrawn?\b", r"\bannul", r"\bno longer (proceed|be awarded)", r"\babandoned\b", r"\brescinded\b",
                  r"\bwill not (?:proceed|be awarded)\b", r"\bterminated\b"),
    "awarded": (r"\bawarded\b", r"\baward of\b", r"\bhas appointed\b", r"\bselected\b", r"\bcontract (was |has been )?signed\b",
                # French / Spanish award wording
                r"\battribu[ée]e?\b", r"\battribution\b", r"\badjudicad[oa]s?\b", r"\badjudicaci[oó]n\b", r"\badjudicatari", r"\basignad[oa]s?\b",
                r"\bempresas? (?:asignad|seleccionad|adjudicatari)", r"\bfinaliza el proceso de asignaci[oó]n\b"),
    "closed": (r"\bclosed\b", r"\bno longer accept"),
}
ELIGIBILITY_LEXICON = (r"eligib", r"\bmust\b", r"\brequired?\b", r"\brequirements?\b", r"\bminimum\b", r"criteria", r"qualif", r"licen[cs]e",
                       r"\bat least \w+ (?:\(\w+\) )?years?\b", r"\byears?(?:'|’)? (?:of )?(?:relevant |proven |demonstrable )?experience\b",
                       r"\bshould (?:have|hold|possess|be|provide|submit|demonstrate)\b", r"\b(?:tender|bid) (?:security|bond|guarantee)\b", r"\bbank guarantee\b",
                       r"\bearnest money\b", r"\bsecurity deposit\b", r"\bcaution(?:nement)?\b", r"\bgarant[ií]a\b", r"\bfianza\b", r"\bpreferably\b", r"\bdesirable\b",
                       r"\bonly\b[^.;]{0,80}\bmay (?:apply|bid|tender|participate|submit|respond)\b", r"\b(?:open|restricted|limited) (?:only )?to\b",
                       r"\bare (?:not )?eligible\b", r"\bshall (?:hold|have|possess|demonstrate)\b",
                       r"\bdoivent\b", r"\bdevront\b", r"\bexig", r"\badmissib", r"\b[ée]ligib", r"\bcrit[èe]res?\b", r"\bau moins\b", r"\bau minimum\b",
                       r"\bseuls?\b[^.;]{0,80}\bpeuvent\b", r"\br[ée]serv[ée]e? aux?\b", r"\bjustifier d",
                       r"\bdeben\b", r"\bdeber[áa]n\b", r"\brequisit", r"\bal menos\b", r"\bcomo m[íi]nimo\b", r"\bs[óo]lo\b[^.;]{0,80}\bpodr[áa]n\b",
                       r"\bpodr[áa]n participar\b", r"\bcontar con\b", r"\bacreditar\b", r"\bhabilitad",
                       r"\bdevem\b", r"\bmüssen\b")
SERVICE_LEXICON: dict[str, tuple[str, ...]] = {
    "GSSA": (r"\bgssa\b", r"\bgsa\b", r"general sales"),
    "TCM": (r"total cargo management", r"\btcm\b"),
    "HANDLING": (r"\bhandling\b", r"\bassistance en escale\b", r"\bmanutention\b", r"\bservices? d'escale\b", r"\basistencia en tierra\b",
                 r"\bchargement et d[ée]chargement\b", r"\bassistance (?:bagages|piste|avion)\b",
                 r"\bmanipulaci[oó]n de carga\b", r"\bservicios de rampa\b", r"\bbodenabfertigung\b"),
    "TRUCKING": (r"\btruck", r"road feeder", r"\brfs\b", r"road transport", r"\bhaulage\b", r"\bcamionaje\b", r"\btransporte (?:por carretera|terrestre)\b",
                 r"\btransport routier\b", r"\bcamionnage\b"),
    "DATA_PROCESSING": (r"data (entry|processing|capture)", r"documentation processing", r"back[- ]office"),
    "ACCOUNTING": (r"\baccounting\b", r"\bbookkeeping\b"),
    "INVOICING": (r"\binvoic", r"\bbilling\b"),
    "COLLECTIONS": (r"\bcollections?\b", r"debt recovery"),
    "TRAINING": (r"\btraining\b", r"\bcourses?\b", r"\bcertification\b", r"\binstruct", r"\bformation\b", r"\bcapacitaci"),
    "TECHNOLOGY": (r"\bsoftware\b", r"\bplatform\b", r"\bdigital\b", r"\btechnology\b", r"\bit services\b", r"\bsystem\b"),
}

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9
# French and Spanish month names, for local-language notices (original text is kept; dates are read from it).
_MONTHS.update({"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8,
                "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
                "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
                # Portuguese and German
                "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "maio": 5, "junho": 6, "julho": 7, "setembro": 9, "outubro": 10, "dezembro": 12,
                "januar": 1, "februar": 2, "märz": 3, "marz": 3, "juni": 6, "juli": 7, "oktober": 10, "dezember": 12})
_MON = r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")"
# Unambiguous zone abbreviations -> fixed offset (minutes). Ambiguous ones are listed separately and never used as a fact.
_TZ_ABBR = {"UTC": 0, "GMT": 0, "Z": 0, "MEZ": 60, "MESZ": 120, "GST": 240, "EAT": 180, "CAT": 120, "WAT": 60, "SAST": 120, "SGT": 480, "HKT": 480, "CET": 60,
            "CEST": 120, "PKT": 300, "JST": 540, "KST": 540, "EST": -300, "EDT": -240, "CDT": -300, "PDT": -420, "AEST": 600,
            "AEDT": 660, "MSK": 180, "TRT": 180, "ICT": 420, "WIB": 420, "NPT": 345, "BDT": 360}
# Abbreviations whose meaning is established only by context: the quote or document must name the country (or give the
# offset explicitly); otherwise the time stays a local time and the uncertainty is shown.
_TZ_CONTEXT: dict[str, tuple[int, frozenset[str], str]] = {
    "SCT": (240, frozenset({"SC"}), "Seychelles Time"), "MUT": (240, frozenset({"MU"}), "Mauritius Time"), "CVT": (-60, frozenset({"CV"}), "Cape Verde Time"),
    "RET": (240, frozenset({"RE"}), "Réunion Time"), "EET": (120, frozenset({"EG", "GR", "RO", "BG", "FI", "UA", "CY", "LB", "JO", "LY"}), "Eastern European Time"),
    "EEST": (180, frozenset({"GR", "RO", "BG", "FI", "UA", "CY", "LB"}), "Eastern European Summer Time"),
    "WET": (0, frozenset({"PT", "MA", "IS", "FO", "CI", "GH", "SN", "ML", "BF", "GM", "GN", "SL", "LR", "TG"}), "Western European Time"),
    "WEST": (60, frozenset({"PT", "MA"}), "Western European Summer Time"), "MMT": (390, frozenset({"MM"}), "Myanmar Time"),
    "IRST": (210, frozenset({"IR"}), "Iran Standard Time"), "AFT": (270, frozenset({"AF"}), "Afghanistan Time"),
    "UZT": (300, frozenset({"UZ"}), "Uzbekistan Time"), "ALMT": (300, frozenset({"KZ"}), "Almaty Time"), "MVT": (300, frozenset({"MV"}), "Maldives Time"),
    "SLST": (330, frozenset({"LK"}), "Sri Lanka Standard Time"), "PHT": (480, frozenset({"PH"}), "Philippine Time"), "MYT": (480, frozenset({"MY"}), "Malaysia Time"),
    "WITA": (480, frozenset({"ID"}), "Central Indonesia Time"), "WIT": (540, frozenset({"ID"}), "Eastern Indonesia Time"),
    "AWST": (480, frozenset({"AU"}), "Australian Western Standard Time"), "ACST": (570, frozenset({"AU"}), "Australian Central Standard Time"),
    "NZST": (720, frozenset({"NZ"}), "New Zealand Standard Time"), "NZDT": (780, frozenset({"NZ"}), "New Zealand Daylight Time"),
    "FJT": (720, frozenset({"FJ"}), "Fiji Time"), "ART": (-180, frozenset({"AR"}), "Argentina Time"), "BRT": (-180, frozenset({"BR"}), "Brasília Time"),
    "CLT": (-240, frozenset({"CL"}), "Chile Standard Time"), "CLST": (-180, frozenset({"CL"}), "Chile Summer Time"), "PET": (-300, frozenset({"PE"}), "Peru Time"),
    "COT": (-300, frozenset({"CO"}), "Colombia Time"), "ECT": (-300, frozenset({"EC"}), "Ecuador Time"), "VET": (-240, frozenset({"VE"}), "Venezuela Time"),
    "BOT": (-240, frozenset({"BO"}), "Bolivia Time"), "UYT": (-180, frozenset({"UY"}), "Uruguay Time"), "GYT": (-240, frozenset({"GY"}), "Guyana Time"),
    "AKST": (-540, frozenset({"US"}), "Alaska Standard Time"), "HST": (-600, frozenset({"US"}), "Hawaii Standard Time"), "NST": (-210, frozenset({"CA"}), "Newfoundland Standard Time"),
    "AST": (180, frozenset({"SA", "KW", "BH", "QA", "YE", "IQ"}), "Arabia Standard Time"),
    "CST": (480, frozenset({"CN"}), "China Standard Time"), "IST": (330, frozenset({"IN"}), "India Standard Time"),
    "PST": (480, frozenset({"PH"}), "Philippine Standard Time"), "SST": (480, frozenset({"SG"}), "Singapore Standard Time"),
}
_TZ_AMBIGUOUS = {"CST": "US Central or China Standard Time", "IST": "India, Israel or Irish Standard Time",
                 "BST": "British Summer Time or Bangladesh Standard Time", "AST": "Arabia or Atlantic Standard Time",
                 "PST": "US Pacific or Philippine Standard Time", "MST": "US Mountain or Malaysia Standard Time",
                 "SST": "Samoa or Singapore Standard Time"}
_TZ_LONG = {"east africa time": 180, "gulf standard time": 240, "arabia standard time": 180, "west africa time": 60,
            "central africa time": 120, "south africa standard time": 120, "greenwich mean time": 0, "coordinated universal time": 0,
            "central european time": 60, "central european summer time": 120, "india standard time": 330,
            "pakistan standard time": 300, "singapore time": 480, "hong kong time": 480}
# Named places whose clocks change: resolved through IANA on the stated date, so daylight saving is applied.
_TZ_CITY = {"london time": "Europe/London", "uk time": "Europe/London", "british time": "Europe/London", "paris time": "Europe/Paris",
            "frankfurt time": "Europe/Berlin", "brussels time": "Europe/Brussels", "amsterdam time": "Europe/Amsterdam",
            "new york time": "America/New_York", "chicago time": "America/Chicago", "dubai time": "Asia/Dubai", "uae time": "Asia/Dubai",
            "nairobi time": "Africa/Nairobi", "kenya time": "Africa/Nairobi", "doha time": "Asia/Qatar", "riyadh time": "Asia/Riyadh",
            "istanbul time": "Europe/Istanbul", "cairo time": "Africa/Cairo", "johannesburg time": "Africa/Johannesburg",
            "lagos time": "Africa/Lagos", "mumbai time": "Asia/Kolkata", "delhi time": "Asia/Kolkata", "sydney time": "Australia/Sydney"}


@dataclass(frozen=True)
class FieldClaim:
    value: str
    quote: str | None


@dataclass
class FieldAssessment:
    field: str
    value: str
    normalised: str
    quote: str | None
    support: Support
    reason: str
    extra: dict = dc_field(default_factory=dict)


@dataclass
class ClaimValidation:
    claim_type: str
    type_supported: bool
    type_reason: str
    fields: list[FieldAssessment]
    contradiction: str | None = None     # the document both announces the opportunity and says the process has ended
    geography_conflict: str | None = None  # the document's title/territory definition and another passage name different territories

    def supported(self, name: str) -> list[FieldAssessment]:
        return [f for f in self.fields if f.field == name and f.support == "supported"]

    def first(self, name: str) -> FieldAssessment | None:
        s = self.supported(name)
        return s[0] if s else None


# --------------------------------------------------------------------- text helpers


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in_document(quote: str | None, document_text: str) -> bool:
    if not quote or len(quote.strip()) < 8:
        return False
    return _fold(quote) in _fold(document_text)


def _any(patterns: tuple[str, ...], text: str) -> str | None:
    t = _fold(text)
    for p in patterns:
        if re.search(p, t):
            return p
    return None


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()))


_ORG_STOP = {"the", "ltd", "limited", "llc", "plc", "inc", "co", "company", "pjsc", "psc", "sa", "ag", "gmbh", "group", "of", "and", "fze", "fzco"}


def _name_stated(value: str, quote: str) -> bool:
    if re.fullmatch(r"[A-Z0-9]{2}", value.strip()):  # IATA airline designator: exact token, case-sensitive
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(value.strip())}(?![A-Za-z0-9])", quote) is not None
    want = [t for t in _tokens(value) if t not in _ORG_STOP]
    have = set(_tokens(quote))
    return bool(want) and all(t in have for t in want)


# --------------------------------------------------------------------- dates


@dataclass(frozen=True)
class StatedDate:
    day: date
    hm: tuple[int, int] | None          # may be (24, 0): end of the day
    offset_minutes: int | None
    raw: str
    zone_label: str | None = None
    iana_zone: str | None = None
    ambiguous_zone: str | None = None


@dataclass(frozen=True)
class _Zone:
    offset: int | None = None
    label: str | None = None
    iana: str | None = None
    ambiguous: str | None = None


def _hm_after(text: str, start: int) -> tuple[tuple[int, int] | None, _Zone]:
    """Time and zone stated within ~48 characters after a date."""
    window = text[start:start + 48]
    hm = None
    m = re.search(r"(\d{1,2})[:.](\d{2})\s*(a\.?m\.?|p\.?m\.?|hrs|h)?", window, re.I)
    if m and int(m.group(1)) <= 24 and int(m.group(2)) < 60 and not (int(m.group(1)) == 24 and int(m.group(2)) != 0):
        h = int(m.group(1))
        suffix = (m.group(3) or "").lower().replace(".", "")
        if suffix == "pm" and h < 12:
            h += 12
        if suffix == "am" and h == 12:
            h = 0
        hm = (h, int(m.group(2)))                    # 24:00 kept as such; deadlines.build rolls it to the next day
    else:
        m = re.search(r"\b(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)", window, re.I)
        if m and 1 <= int(m.group(1)) <= 12:
            h = int(m.group(1)) % 12 + (12 if m.group(2).lower().startswith("p") else 0)
            hm = (h, 0)
        elif re.search(r"\bnoon\b|\bmidday\b", window, re.I):
            hm = (12, 0)
        elif re.search(r"\bmidnight\b", window, re.I):
            hm = (24, 0)
    z = re.search(r"\b(UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", window)
    if z:
        off = (1 if z.group(2) == "+" else -1) * (int(z.group(3)) * 60 + int(z.group(4) or 0))
        return hm, _Zone(off, f"UTC{z.group(2)}{int(z.group(3)):02d}:{int(z.group(4) or 0):02d}")
    z = re.search(r"(?<![A-Za-z])([+-])(\d{2}):?(\d{2})\b", window)
    if z and hm is not None:
        return hm, _Zone((1 if z.group(1) == "+" else -1) * (int(z.group(2)) * 60 + int(z.group(3))), f"UTC{z.group(1)}{z.group(2)}:{z.group(3)}")
    lw = window.lower()
    for name in sorted(_TZ_CITY, key=len, reverse=True):
        if name in lw:
            return hm, _Zone(None, name.title(), _TZ_CITY[name])
    lz = re.search(r"(" + "|".join(sorted(_TZ_LONG, key=len, reverse=True)) + r")", window, re.I)
    if lz:
        return hm, _Zone(_TZ_LONG[lz.group(1).lower()], lz.group(1).title())
    z = re.search(r"\b(" + "|".join(sorted(list(_TZ_ABBR) + list(_TZ_AMBIGUOUS), key=len, reverse=True)) + r")\b", window)
    if z and z.group(1) != "Z":
        if z.group(1) in _TZ_AMBIGUOUS:
            return hm, _Zone(None, None, None, f"{z.group(1)} ({_TZ_AMBIGUOUS[z.group(1)]})")
        return hm, _Zone(_TZ_ABBR[z.group(1)], z.group(1))
    if re.search(r"\blocal time\b|\bheure locale\b|\bhora local\b", window, re.I):
        return hm, _Zone(None, None, None, "'local time' (the place it refers to is not stated)")
    return hm, _Zone()


def _zone_by_context(z: _Zone, window: str, context_countries: frozenset[str]) -> _Zone:
    """An abbreviation whose meaning depends on context becomes a fact only when the source establishes it: an explicit
    offset next to it, or a country from the abbreviation's set named in the quote or document."""
    m = re.search(r"\b(" + "|".join(sorted(_TZ_CONTEXT, key=len, reverse=True)) + r")\b", window)
    if not m:
        return z
    abbr = m.group(1)
    offset, countries, name = _TZ_CONTEXT[abbr]
    if z.offset is not None and z.label and z.label.startswith("UTC"):
        return z                                   # explicit offset given next to it: that is the fact
    if countries & context_countries:
        return _Zone(offset, abbr)
    return _Zone(None, None, None, f"{abbr} (read as {name} only if the notice concerns {', '.join(sorted(countries))}; not established by the source)")


_NUMERIC_DATE = re.compile(r"\b(\d{1,2})([/.-])(\d{1,2})\2(\d{4})\b")


def date_convention(text: str | None) -> str | None:
    """The day/month order the document itself establishes for numeric dates: 'dmy' when it contains a numeric date whose
    first number exceeds 12 ("15-10-2026"), 'mdy' when the second does, None when neither or both (inconsistent)."""
    if not text:
        return None
    dmy = mdy = False
    for m in _NUMERIC_DATE.finditer(text):
        a, b = int(m.group(1)), int(m.group(3))
        if a > 12 and b <= 12:
            dmy = True
        elif b > 12 and a <= 12:
            mdy = True
    if dmy and not mdy:
        return "dmy"
    if mdy and not dmy:
        return "mdy"
    return None


def ambiguous_numeric_dates(text: str) -> list[tuple[str, date, date]]:
    """Numeric dates that read validly both day-first and month-first: (raw, day-first reading, month-first reading)."""
    out = []
    for m in _NUMERIC_DATE.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if a <= 12 and b <= 12:
            try:
                out.append((m.group(0), date(y, b, a), date(y, a, b)))
            except ValueError:
                continue
    return out


def dates_in_text(text: str, context_countries: frozenset[str] = frozenset(), convention: str | None = None) -> list[StatedDate]:
    """Calendar dates stated in text. Numeric dates are accepted only when
    unambiguous (ISO, or a day above 12) or when the document's own dating `convention` ('dmy' / 'mdy', see
    `date_convention`) establishes the reading; otherwise 03/04/2026 is not a fact. `context_countries`: countries the
    quote or document names, which decide context-dependent zone abbreviations (SCT, CVT, AST, CST, IST ...)."""
    out: list[StatedDate] = []

    def add(d: date, hm: tuple[int, int] | None, raw: str, end: int) -> None:
        hm2, z = _hm_after(text, end)
        z = _zone_by_context(z, text[end:end + 48], context_countries)
        out.append(StatedDate(d, hm or hm2, z.offset, raw, z.label, z.iana, z.ambiguous))

    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", text):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        add(d, (int(m.group(4)), int(m.group(5))) if m.group(4) else None, m.group(0), m.end())
    # "15 January 2027", "15th of January 2027", "15 de enero de 2027", "20 de dezembro de 2026", "9. Januar 2027", "1er janvier 2027"
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th|er|\.)?(?:\s+(?:of\s+|de\s+)?|-)" + _MON + r"\.?,?(?:\s+(?:de\s+)?|-)(\d{4})", text, re.I):
        try:
            d = date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        except (ValueError, KeyError):
            continue
        add(d, None, m.group(0), m.end())
    for m in re.finditer(_MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", text, re.I):
        try:
            d = date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        except (ValueError, KeyError):
            continue
        add(d, None, m.group(0), m.end())
    for m in _NUMERIC_DATE.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if a > 12 and b <= 12:
            dd, mm = a, b
        elif b > 12 and a <= 12:
            dd, mm = b, a
        elif convention == "dmy":
            dd, mm = a, b
        elif convention == "mdy":
            dd, mm = b, a
        else:
            continue  # ambiguous day/month order and nothing in the document establishes it
        try:
            d = date(y, mm, dd)
        except ValueError:
            continue
        add(d, None, m.group(0), m.end())
    return out


def _value_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


_SUPERSEDED_BEFORE = re.compile(r"\b(?:extended|postponed|moved|changed|revised|deferred|shifted|prolong\w*|report\w*|prorrog\w*)\s+(?:from|du|del|de)\s*(?:the\s+)?$"
                                r"|\b(?:instead of|previously|formerly|originally|initially|rather than|in place of|replacing|au lieu du|en lugar del|"
                                r"anstelle des|anstatt)\s*(?:the\s+)?$|\bfrom\s*$", re.I)
_SUBMISSION_CUE = re.compile(r"\b(?:deadline|due|closing|clos(?:e|es|ing)|submi\w*|received|receipt|no later than|not later than|by|before|until|"
                             r"bids?|proposals?|offers?|quotations?|responses?|expressions?|date limite|soumis\w*|dépôt|depot|"
                             r"plazo|propuestas?|ofertas?|presentar\w*|reciben|prazo|propostas?|entregues|einzureichen|angebote|frist|abgabe)\b", re.I)
_OTHER_DATE_CUE = re.compile(r"\b(?:expir\w*|valid (?:until|through|to)|validity|awarded|award date|signed|commenc\w*|start\w*|effective|"
                             r"contract (?:period|term|start|begins)|term of|runs? (?:from|until)|delivery|published|issued|dated|opening|"
                             r"site visit|clarification|pre-bid|briefing|kick-?off|go-?live)\b", re.I)


_QUERY_SUBMISSION = re.compile(r"\bsubmi\w*\s+(?:of|for)\s+(?:queries|questions|clarifications?|enquiries|inquiries|requests? for clarification|pre-?bid)\b"
                               r"|\b(?:queries|questions|clarifications?|enquiries)\s+(?:must|should|shall|are to|to)\s+be\s+(?:submitted|sent|raised)\b", re.I)


def _deadline_date_role(quote: str, raw: str) -> str:
    """What the quote ties this date to: 'submission' (or unstated), 'superseded' (an earlier deadline that was replaced)
    or 'other' (expiry, award, contract or event date in a clause that states a submission date elsewhere)."""
    idx = quote.find(raw)
    if idx < 0:
        return "submission"
    sent_start = max((quote.rfind(ch, 0, idx) for ch in ".;!?\n"), default=-1) + 1
    sent_end_candidates = [i for i in (quote.find(ch, idx) for ch in ".;!?\n") if i >= 0]
    sent_end = min(sent_end_candidates) if sent_end_candidates else len(quote)
    before = quote[max(sent_start, idx - 60):idx]
    sentence = quote[sent_start:sent_end]
    if _SUPERSEDED_BEFORE.search(before) and re.search(r"\b(?:to|until|au|al|bis)\b", quote[idx + len(raw):idx + len(raw) + 40], re.I):
        return "superseded"
    if _SUPERSEDED_BEFORE.search(before) and len([d for d in dates_in_text(quote) if d.raw != raw]) >= 1 and \
            re.search(r"\b(?:instead of|previously|formerly|originally|initially|rather than|in place of|replacing)", before, re.I):
        return "superseded"
    if _QUERY_SUBMISSION.search(sentence):
        return "other"              # the deadline for QUESTIONS about the tender, not for the proposal
    tail = before[-45:]
    if _OTHER_DATE_CUE.search(tail) and not _SUBMISSION_CUE.search(_OTHER_DATE_CUE.sub(" ", tail)):
        others = [d for d in dates_in_text(quote) if d.raw != raw]
        if others and any(_SUBMISSION_CUE.search(quote[max(0, quote.find(o.raw) - 60):quote.find(o.raw)]) for o in others):
            return "other"
        if not _SUBMISSION_CUE.search(sentence):
            return "other"
    return "submission"


def _validate_deadline(fc: FieldClaim, quote_ok: bool, tz_hint: str | None, document_text: str | None = None) -> FieldAssessment:
    """The deadline is exactly as precise as the quote states it (domain.deadlines). The extractor's time or
    zone is never adopted: a zone hint is kept only as a labelled assumption. A zone abbreviation whose meaning depends
    on context (SCT, CVT, AST, CST, IST ...) counts only when the quote or document names a country it belongs to."""
    base: dict[str, Any] = dict(field="deadline", value=fc.value, quote=fc.quote)
    day = _value_day(fc.value)
    if day is None:
        return FieldAssessment(**base, normalised=fc.value, support="unsupported", reason="deadline value is not a date")
    if not quote_ok:
        return FieldAssessment(**base, normalised=fc.value, support="unsupported", reason="quote not found verbatim in the document")
    context = frozenset(countries_mentioned(fc.quote or "")) | frozenset(countries_mentioned(document_text or "") if document_text else ())
    convention = date_convention(document_text)
    stated = [d for d in dates_in_text(fc.quote or "", context, convention) if d.day == day]
    if not stated:
        amb = [(raw, d1, d2) for raw, d1, d2 in ambiguous_numeric_dates(fc.quote or "") if day in (d1, d2)]
        if amb and convention:
            raw, d1, d2 = amb[0]
            read = d1 if convention == "dmy" else d2
            return FieldAssessment(**base, normalised=fc.value, support="unsupported",
                                   reason=f"the notice's other dates are {'day-first' if convention == 'dmy' else 'month-first'}, so '{raw}' is "
                                          f"{read.strftime('%-d %B %Y')}, not {day.strftime('%-d %B %Y')}")
        if amb:
            raw, d1, d2 = amb[0]
            # Preserved for a person, never a fact: neither reading is established by the document.
            return FieldAssessment(**base, normalised=fc.value, support="review_required",
                                   reason=f"the quote's '{raw}' can be read as {d1.strftime('%-d %B %Y')} or {d2.strftime('%-d %B %Y')} and the notice gives no "
                                          "day/month convention; a reviewer must confirm the date", extra={"ambiguous_date": raw})
        return FieldAssessment(**base, normalised=fc.value, support="unsupported", reason=f"the quote does not state {day.isoformat()} unambiguously")
    s = stated[0]
    role = _deadline_date_role(fc.quote or "", s.raw)
    if role == "superseded":
        return FieldAssessment(**base, normalised=fc.value, support="unsupported",
                               reason=f"the quote gives {day.isoformat()} as the earlier deadline that was replaced; the current deadline is the later date")
    if role == "other":
        return FieldAssessment(**base, normalised=fc.value, support="unsupported",
                               reason=f"the quote ties {day.isoformat()} to something other than the proposal submission deadline (a query deadline, expiry, "
                                      "award, contract or start date)")
    sd = dl.build(s.day, s.hm, offset_minutes=s.offset_minutes, zone_label=s.zone_label, iana_zone=s.iana_zone,
                  ambiguous_zone=s.ambiguous_zone, assumed_zone=tz_hint)
    proposed_time = fc.value.strip()[11:16] if len(fc.value.strip()) >= 16 else None
    notes = list(sd.notes)
    if proposed_time and sd.local_time and proposed_time != sd.local_time and s.hm != (24, 0):
        notes.append(f"time taken from the source ({sd.local_time}), not the extractor ({proposed_time})")
    if proposed_time and sd.local_time is None:
        notes.append(f"the extractor's time {proposed_time} is not stated in the source and is not used")
    normalised = sd.exact_utc.isoformat() if sd.exact_utc else (f"{sd.day.isoformat()}T{sd.local_time}" if sd.local_time else sd.day.isoformat())
    reason = ("date stated in the quote; " + ("time and zone stated" if sd.precision == "instant" else "; ".join(notes))) if notes or sd.precision == "instant" \
        else "date stated in the quote"
    if convention and _NUMERIC_DATE.fullmatch(s.raw) and all(int(x) <= 12 for x in re.split(r"[/.-]", s.raw)[:2]):
        reason += f"; numeric date read {'day-first' if convention == 'dmy' else 'month-first'} as the notice's other dates establish"
    if sd.precision == "instant" and notes:
        reason += "; " + "; ".join(notes)
    extra = {"deadline": sd.to_json(), "precision": sd.precision, "time_stated": sd.local_time is not None,
             "zone_stated": sd.precision == "instant", "source_tz": sd.zone}
    if sd.assumed_zone:
        extra["zone_assumed"] = sd.assumed_zone
    return FieldAssessment(**base, normalised=normalised, support="supported", reason=reason, extra=extra)


# --------------------------------------------------------------------- money

_CCY = r"(USD|EUR|GBP|AED|SAR|QAR|KWD|OMR|BHD|INR|KES|NGN|ZAR|EGP|CNY|HKD|SGD|JPY|CHF|AUD|CAD|TRY|PKR|BDT|LKR|MYR|THB|US\$|\$|€|£)"
_SYMBOL = {"US$": "USD", "$": "USD", "€": "EUR", "£": "GBP"}


def _amounts(text: str) -> list[tuple[str, Decimal]]:
    out = []
    pat = re.compile(_CCY + r"\s?([\d,]+(?:\.\d+)?)\s*(million|m|bn|billion|k|thousand)?\b|([\d,]+(?:\.\d+)?)\s*(million|m|bn|billion)?\s*" + _CCY,
                     re.I)
    for m in pat.finditer(text):
        if m.group(1):
            ccy, num, mult = m.group(1), m.group(2), m.group(3)
        else:
            num, mult, ccy = m.group(4), m.group(5), m.group(6)
        try:
            amt = Decimal(num.replace(",", ""))
        except InvalidOperation:
            continue
        factor = {"million": 10**6, "m": 10**6, "bn": 10**9, "billion": 10**9, "k": 10**3, "thousand": 10**3}.get((mult or "").lower(), 1)
        out.append((_SYMBOL.get(ccy, ccy.upper()), amt * factor))
    return out


# --------------------------------------------------------------------- main entry


_LOT_LINE = re.compile(r"^\s*(?:lot|schedule|lote|los)\s*(?:no\.?\s*)?(?:\d{1,3}|[a-z]{1,2})\b", re.I)
_LOT_INTRO = re.compile(r"(?P<org>[^.;:\n]{2,120}?)\s+(?:invites?|invite|publishes|publish|issues|issue|requests|request|seeks|seek|launches|launch|"
                        r"lance|convoca|publica)\b[^.;\n]{0,120}?\blots?\b", re.I)
_SEVERAL = re.compile(r"\s(?:and|&|et|y|e|und)\s|,|\bjointly\b|\bjoint\b|\btogether with\b|\bon behalf of\b", re.I)


def issuer_from_lot_introduction(value: str, quote: str, document_text: str) -> tuple[Literal["supported", "review_required"], str] | None:
    """The issuer of a LOT line that does not name it (fifth instruction of 27 Oct 2026, item 5): read from the document's
    introduction when it states the relationship explicitly ("Sample Airways invites proposals for the following lots").
    Returns (support, reason), or None when the quote is not a lot line or no introduction states an issuer.
    - the introduction names exactly this organisation as the one publishing the lots: 'supported';
    - it names several organisations (joint, on behalf of, "A and B"): 'review_required', never chosen by the system."""
    if not quote or not _LOT_LINE.search(quote):
        return None
    pos = document_text.find(quote.strip()[:40])
    head = document_text[:pos] if pos > 0 else ""
    intro = None
    for m in _LOT_INTRO.finditer(head):
        intro = m
    if intro is None:
        return None
    org = intro.group("org").strip()
    if _SEVERAL.search(org):
        return ("review_required", f"the introduction names more than one possible issuer of the lots (\"{org}\"); a reviewer must confirm "
                                   f"which one issues this lot")
    if _name_stated(value, org):
        return ("supported", f"issuer of the lot stated in the document's introduction (\"{intro.group(0).strip()}\"); "
                             f"the lot line itself does not repeat it")
    return None


def validate_claim(
    claim_type: str,
    fields: dict[str, FieldClaim],
    document_text: str,
    *,
    claim_quote: str | None,
    deadline_timezone: str | None = None,
    airport_country: Callable[[str], str | None] = lambda _c: None,
    reference_date: date | None = None,
    stance: str = "supports",
    document_title: str | None = None,
    reviewer: bool = False,
) -> ClaimValidation:
    """`reference_date`: when the document was published (else today); a year before it in a clause marks
    that clause as describing the past. `stance`: a claim that CONTRADICTS a tender ("Example Air is not
    running a GSSA tender") is established by negated wording, so for it negation is the expected meaning.
    `document_title`: the notice's title (its territory counts as a stated territory). `reviewer`: the fields were
    entered by a person, so a `freight_scope` value is their own reading rather than derived from wording."""
    denial = stance == "contradicts"
    out: list[FieldAssessment] = []
    terr: meaning.DocumentTerritories | None = None
    geo_conflict: meaning.GeographyConflict | None = None
    if any(n in GEO_FIELDS for n in fields):
        def _countries_in(text: str) -> list[str]:
            codes = list(countries_mentioned(text))
            for _a, _b, _city, cc in cities_in_text(meaning.ascii_text(text)):
                if len(cc) == 1 and cc[0] not in codes:
                    codes.append(cc[0])
            return codes
        terr = meaning.document_territories(document_text, document_title, countries_in=_countries_in, airport_country=airport_country)
        geo_conflict = meaning.geography_conflict(terr)

    # Claim type: stated by its own quote (or the claim's main quote).
    type_field = fields.get("opportunity_type")
    tq = type_field.quote if type_field is not None else claim_quote
    tq_ok = quote_in_document(tq, document_text)
    ref_year = (reference_date or date.today()).year
    lex = TYPE_LEXICON.get(claim_type, ())
    hit = meaning.first_match(lex, tq or "") if tq_ok and lex else None
    if hit is None and tq_ok and lex and claim_type in TENDER_ANCHOR_TYPES | {"tender_deadline"} and type_field is None:
        # A row of a tabular tender listing ("REF | subject | place | date") carries no procurement wording of its own; the
        # status field's quote (the listing's heading sentence, found verbatim in the same document) may state it instead.
        st_field = fields.get("status")
        if st_field is not None and st_field.quote and quote_in_document(st_field.quote, document_text) and meaning.first_match(lex, st_field.quote):
            tq, hit = st_field.quote, meaning.first_match(lex, st_field.quote)
    if claim_type == "gssa_tender" and hit and not meaning.first_match(_PROCUREMENT, tq or ""):
        hit = None  # mentions a GSSA but not a tender/appointment process
    type_extra: dict[str, Any] = {}
    if claim_type == "tender_context":
        # Supporting information about an established tender: the quote must cite the tender's reference. It states no status,
        # deadline or award and never refreshes one (those fields are not read from it).
        tr = fields.get("tender_ref")
        ref_v = str(tr.value).strip() if tr is not None and tr.value else ""
        cites = bool(ref_v) and tq_ok and re.sub(r"[\s\-_/]", "", ref_v).lower() in re.sub(r"[\s\-_/]", "", tq or "").lower()
        type_supported = cites
        type_reason = ("supporting information citing the tender reference; it announces nothing and never refreshes the status"
                       if cites else "supporting information must cite the tender's reference verbatim")
        type_extra["context"] = True
        fields = {k: v for k, v in fields.items() if k not in ("status", "deadline")}
    elif claim_type == "other":
        type_supported, type_reason = False, "claim type 'other' establishes nothing"
    elif not tq_ok:
        type_supported, type_reason = False, "type quote not found verbatim in the document"
    elif not hit and claim_type == "eligibility":
        # Held for a person rather than dropped: an eligibility criterion that cannot be interpreted must stay visible.
        type_supported, type_reason = True, "eligibility wording not recognised: the criterion is held for review, never treated as a fact"
        type_extra["uninterpreted"] = True
    elif not hit and claim_type in TENDER_ANCHOR_TYPES and meaning.first_match(_PROCUREMENT, tq or "") is not None \
            and relevance.freight_scope(claim_type, None, tq or "", document_title, document=document_text,
                                        service_supported=False, reference_year=ref_year).scope in relevance.EXCLUDED_SCOPES:
        # A procurement (a lot, a request for proposals) for work outside the freight scope, such as a passenger sales and
        # ticketing agent: kept as a tender record so it stays inspectable as EXCLUDED evidence with its reason (fourth
        # instruction of 27 Oct, item 4), never dropped before validation and never a freight opportunity.
        type_supported = True
        type_reason = "a procurement outside the freight scope: kept as excluded evidence, never a freight opportunity"
        type_extra["outside_freight_scope"] = True
    elif not hit:
        type_supported, type_reason = False, f"the quote does not describe a {claim_type.replace('_', ' ')}"
    else:
        # The process the type names must be affirmed in its clause. For a tender, the procurement wording counts too:
        # "Example Air is not inviting GSSA bids" mentions a GSSA and bids, and states that there is no tender.
        anchors = [hit] + ([meaning.first_match(_PROCUREMENT, tq or "")] if claim_type in TENDER_ANCHOR_TYPES else [])
        pols = {meaning.polarity_in_context(tq or "", m.start(), document_text, reference_year=ref_year) for m in anchors if m is not None}
        eoi = meaning.first_match(_EOI, tq or "")
        if "planned" in pols and eoi is not None and \
                meaning.polarity_in_context(tq or "", eoi.start(), document_text, reference_year=ref_year) not in ("negated", "historical"):
            # An expression of interest / pre-qualification for a contract the issuer "plans to" award: the EOI itself is the
            # current process, the plan describes the later contract.
            pols.discard("planned")
            type_extra["eoi"] = True
        type_extra["modality"] = sorted(pols)
        if denial:
            type_supported = "negated" in pols or "historical" in pols
            type_reason = "the quote denies it (contradicting evidence)" if type_supported else "a contradicting claim needs a quote that denies it"
        elif "negated" in pols and not (claim_type == "tender_status" and fields.get("status") is not None
                                        and fields["status"].value.lower() in TERMINAL_STATUSES
                                        and meaning.first_match(STATUS_LEXICON[fields["status"].value.lower()], tq or "")):
            type_supported, type_reason = False, "the quote says this is not happening (negated wording)"
        elif "historical" in pols and claim_type not in ROUTE_TYPES:
            type_supported, type_reason = False, "the quote describes a past process, not a current one"
        elif "planned" in pols and claim_type in TENDER_ANCHOR_TYPES:
            type_supported, type_reason = True, "a planned tender is stated; it is not open until a source says so"
        else:
            type_supported, type_reason = True, "type stated in the quote"
    out.append(FieldAssessment("opportunity_type", claim_type, claim_type, tq, "supported" if type_supported else "unsupported", type_reason,
                               extra=type_extra))
    # Item 4: the WHOLE document is checked. If one passage announces the opportunity and another says the process is
    # closed, cancelled or awarded, the opportunity is not shown as open until a person reviews it.
    contradiction = None
    if not denial and (claim_type in TENDER_ANCHOR_TYPES or claim_type == "tender_status") and (type_supported or claim_type == "tender_status"):
        found = meaning.status_contradiction(document_text, reference_year=ref_year)
        contradiction = found.describe() if found else None

    for name, fc in fields.items():
        if name == "opportunity_type" or name not in FIELDS or not fc.value or not str(fc.value).strip():
            continue
        value = str(fc.value).strip()
        quote = fc.quote
        q_ok = quote_in_document(quote, document_text)
        base: dict[str, Any] = dict(field=name, value=value, quote=quote)
        if claim_type in ROUTE_TYPES and name in ROUTE_NOT_APPLICABLE:
            out.append(FieldAssessment(**base, normalised=value, support="not_applicable",
                                       reason="a route or capacity announcement cannot establish this field"))
            continue
        if name == "deadline":
            out.append(_validate_deadline(FieldClaim(value, quote), q_ok, deadline_timezone, document_text))
            continue
        if not q_ok:
            out.append(FieldAssessment(**base, normalised=value, support="unsupported", reason="quote not found verbatim in the document"))
            continue
        q = quote or ""
        if name in ("organisation", "airline"):
            ok = _name_stated(value, q)
            norm = value.upper() if re.fullmatch(r"[A-Z0-9]{2}", value) else " ".join(_tokens(value))
            if not ok:
                lot_issuer = issuer_from_lot_introduction(value, q, document_text)
                if lot_issuer is not None:
                    out.append(FieldAssessment(**base, normalised=norm, support=lot_issuer[0], reason=lot_issuer[1]))
                    continue
            out.append(FieldAssessment(**base, normalised=norm, support="supported" if ok else "unsupported",
                                       reason="name stated in the quote" if ok else "the quote does not name this organisation"))
        elif name in GEO_FIELDS:
            code = resolve_country(value)
            airport = value.upper() if re.fullmatch(r"[A-Za-z]{3}", value) else None
            if code is None and airport:
                code = airport_country(airport)
            if code is None:
                # The value may be a city: resolved through the maintained register, ambiguous names go to a person.
                cc = city_countries(value)
                if len(cc) > 1:
                    out.append(FieldAssessment(**base, normalised=value, support="review_required",
                                               reason=f"'{value}' is a city listed for several countries ({', '.join(COUNTRIES[c][0] for c in cc)}); "
                                                      "a reviewer must say which", extra={"ambiguous_city": list(cc)}))
                    continue
                if len(cc) == 1:
                    code = cc[0]
            if code is None:
                ambiguous = [(c, codes) for _a, _b, c, codes in cities_in_text(q) if len(codes) > 1]
                if ambiguous:
                    c, codes = ambiguous[0]
                    out.append(FieldAssessment(**base, normalised=value, support="review_required",
                                               reason=f"the quote names {c}, a city listed for several countries ({', '.join(COUNTRIES[x][0] for x in codes)}); "
                                                      "a reviewer must say which", extra={"ambiguous_city": list(codes)}))
                    continue
                out.append(FieldAssessment(**base, normalised=value, support="unsupported", reason="not a recognised country, registered airport or listed city"))
                continue
            cname = COUNTRIES[code][0]
            mentions = meaning.country_roles(q, code, airport_country=airport_country)
            norm = airport if (airport and name in ("origin", "destination") and airport_country(airport) == code) else code
            # A route's two ends are its scope; so are the ends of a transport service a tender asks for ("between Dakar and Bamako").
            wanted = GEO_ACCEPTS[name] | (ROUTE_SCOPE_ROLES if claim_type in ROUTE_TYPES | TENDER_ANCHOR_TYPES and name in ("country", "contract_territory") else set())
            fits = [m for m in mentions if m.role in wanted
                    and (denial or meaning.polarity_in_context(q, m.start, document_text, reference_year=ref_year) != "negated")]
            roles = sorted({m.role for m in mentions})
            extra = {"country": code, "stated_roles": roles}
            rotation = meaning.rotation_in(q) if name in ("origin", "destination") else None
            if rotation and not denial:
                # A multi-stop rotation names several stops; reducing it to one origin-destination pair is not stated by the source.
                out.append(FieldAssessment(**base, normalised=norm, support="review_required",
                                           reason=f"the quote describes a multi-stop rotation ({' - '.join(rotation)}); a single {name} is not established "
                                                  "by it; the stops are kept for review", extra={"country": code, "rotation": rotation}))
                continue
            if fits and name in ("country", "contract_territory") and terr is not None and terr.stated and code not in terr.stated and not denial:
                # The passage names this country as a place of delivery, but the notice's own title / territory definition / lots
                # name a different territory: a conflict for a person, never the easiest sentence to match.
                names = ", ".join(COUNTRIES[c][0] for c in sorted(terr.stated))
                out.append(FieldAssessment(**base, normalised=code, support="review_required",
                                           reason=f"geography conflict: the notice's title or territory definition names {names} as the territory, "
                                                  f"but this passage names {cname} ({fits[0].why}); a reviewer must say which is the delivery territory",
                                           extra=extra | {"geography_conflict": True, "stated_territories": sorted(terr.stated)}))
                continue
            if fits and name in ("country", "contract_territory") and terr is not None and not terr.stated and terr.unread_definition \
                    and not denial and not meaning.defines_territory(q):
                # The notice DEFINES its territory, but the definition names no country the check can read: a country found in
                # another passage is not taken as the territory without a person.
                out.append(FieldAssessment(**base, normalised=code, support="review_required",
                                           reason=f"the notice defines its territory (\"{terr.unread_definition}\") but no country could be read from that "
                                                  f"definition; {cname} is named elsewhere ({fits[0].why}); a reviewer must confirm the territory",
                                           extra=extra | {"unread_territory_definition": True}))
                continue
            if fits:
                reason = f"{cname} stated as {GEO_LABEL[fits[0].role]} ({fits[0].why})"
                if terr is not None and code in terr.stated:
                    reason += "; consistent with the notice's stated territory"
            elif not mentions:
                amb = [(c, codes) for _a, _b, c, codes in cities_in_text(q) if len(codes) > 1 and code in codes]
                if amb:
                    c, codes = amb[0]
                    out.append(FieldAssessment(**base, normalised=code, support="review_required",
                                               reason=f"the quote names {c}, a city listed for several countries ({', '.join(COUNTRIES[x][0] for x in codes)}); "
                                                      f"a reviewer must confirm {cname}", extra={"country": code, "ambiguous_city": list(codes)}))
                    continue
                reason = f"the quote does not state {cname}"
            elif any(m.role in wanted for m in mentions):
                reason = f"the quote excludes {cname}"
            elif "issuer" in roles:
                reason = f"{cname} is where the issuer is based, not {GEO_LABEL_FIELD[name]}"
            elif "name" in roles:
                reason = f"{cname} appears only as part of an organisation's name"
            else:
                reason = f"{cname} is named, but the quote does not establish it as {GEO_LABEL_FIELD[name]}: {mentions[0].why}"
            out.append(FieldAssessment(**base, normalised=norm, support="supported" if fits else "unsupported", reason=reason, extra=extra))
        elif name in ("tender_ref", "procurement_cycle"):
            norm = re.sub(r"\s+", "", value).upper()
            # Whole-token match: "EXA-CGO-2026-01" is NOT stated by "EXA-CGO-2026-014" (directive §6/§7).
            pattern = r"\s*".join(re.escape(ch) for ch in norm)        # "EXA CGO 2026 014" still matches EXACGO2026014
            ok = len(norm) >= 3 and re.search(r"(?<![A-Z0-9])" + pattern + r"(?![A-Z0-9])", q.upper()) is not None
            out.append(FieldAssessment(**base, normalised=norm, support="supported" if ok else "unsupported",
                                       reason="reference stated in the quote" if ok else "the quote does not contain this reference"))
        elif name == "status" and contradiction and value.lower() in ("open", "revised"):
            out.append(FieldAssessment(**base, normalised=value.lower(), support="review_required",
                                       reason=f"contradictory: {contradiction}; review before treating it as {value.lower()}"))
        elif name == "status":
            st = value.lower()
            pats = STATUS_LEXICON.get(st)
            if not pats:
                out.append(FieldAssessment(**base, normalised=st, support="unsupported", reason=f"'{st}' is not a recognised tender status"))
                continue
            affirmed = {s_: bool(meaning.affirmed_matches(p_, q, reference_year=ref_year, document=document_text)) for s_, p_ in STATUS_LEXICON.items()}
            mentioned = meaning.first_match(pats, q)
            conflicts = sorted(s_ for s_ in TERMINAL_STATUSES if affirmed[s_] and s_ != st)
            status_extra: dict[str, Any] = {}
            if st in ("open", "revised") and conflicts:
                ok, reason = False, f"conflicting status wording in the quote ({st} and {', '.join(conflicts)}); review the notice"
            elif affirmed[st]:
                ok, reason = True, f"'{st}' status stated in the quote"
            elif st == "open" and affirmed["announced"]:
                ann = meaning.first_match(STATUS_LEXICON["announced"], q)
                ok, reason = False, (f"announced — current status unverified: the quote shows that a procurement notice exists "
                                     f"(\"{ann.group(0) if ann else 'notice'}\") but does not state that applications are still being accepted")
                status_extra = {"announced": True}
            elif mentioned is not None:
                pol = meaning.polarity_in_context(q, mentioned.start(), document_text, reference_year=ref_year)
                ok, reason = False, {"negated": f"the quote says the tender is not {st}",
                                     "historical": f"the quote describes a past {st} status, not the current one",
                                     "planned": f"the quote describes a plan; the tender is not yet {st}"}.get(pol, f"'{st}' is not affirmed")
            else:
                ok, reason = False, f"the quote does not state that the tender is {st}"
            out.append(FieldAssessment(**base, normalised=st, support="supported" if ok else "unsupported", reason=reason, extra=status_extra))
        elif name == "eligibility":
            # The exact requirement must be stated; eligibility vocabulary alone proves nothing. The source's own words
            # are kept as the normalised value, so a brief quotes the criterion rather than the extractor's paraphrase.
            # Then its STRUCTURE must match (domain.eligibility): minimum/maximum, numbers and units, dates, AND/OR and
            # conditions. A reading that may be fair but reshapes the requirement goes to review, never to "supported".
            support: str
            if _any(ELIGIBILITY_LEXICON, q) is None:
                stated_ok, _why = meaning.requirement_stated(eligibility.strip_comparators(value), eligibility.strip_comparators(q))
                if stated_ok:
                    support, reason = "review_required", ("the quote could not be interpreted as a requirement (no eligibility wording recognised); "
                                                          "a reviewer must confirm or reject the criterion")
                else:
                    support, reason = "unsupported", "the quote states no eligibility criteria and does not state the value"
            else:
                src = eligibility_sentences(value, q)
                structural = eligibility.compare(value, src) if eligibility.has_structure(value) else None
                if structural is not None and structural[0] == "unsupported":
                    support, reason = structural          # min/max reversed, other number, unit or date: say exactly that
                else:
                    ok, reason = meaning.requirement_stated(eligibility.strip_comparators(value), eligibility.strip_comparators(q))
                    support = "supported" if ok else "unsupported"
                    if ok:
                        support, reason = structural or eligibility.compare(value, src)
            modality = _modality(src if _any(ELIGIBILITY_LEXICON, q) is not None else q)
            if support == "supported" and modality:
                reason += f" ({modality} wording preserved)"
            out.append(FieldAssessment(**base, normalised=re.sub(r"\s+", " ", q).strip()[:2000] if support == "supported" else _fold(value)[:500],
                                       support=support, reason=reason, extra={"modality": modality} if modality else {}))  # type: ignore[arg-type]
        elif name == "published_value":
            want = _amounts(value)
            have = _amounts(q)
            ok = bool(want) and want[0] in have
            norm = f"{want[0][0]} {want[0][1].normalize():f}" if want else value
            out.append(FieldAssessment(**base, normalised=norm, support="supported" if ok else "unsupported",
                                       reason="amount and currency stated in the quote" if ok else "the quote does not state this amount and currency"))
        elif name == "service":
            code = value.strip().upper().replace(" ", "_")
            pats = SERVICE_LEXICON.get(code)
            # The service must be stated as wanted (now or planned), not negated ("handling is not included") or historical.
            hits = [m for p_ in (pats or ()) for m in [meaning.first_match((p_,), q)] if m is not None]
            ok = any(meaning.polarity_in_context(q, m.start(), document_text, reference_year=ref_year) in ("affirmed", "planned") for m in hits)
            out.append(FieldAssessment(**base, normalised=code, support="supported" if ok else "unsupported",
                                       reason="service stated in the quote" if ok else "the quote does not state this service as required"))
    # Freight relevance (item 1 of the second 27 Oct instruction): derived from the mandate's own wording and the title, never
    # from the extractor's label; a reviewer's reading (a corrected `freight_scope` field) stands in its place.
    if claim_type in relevance.SCOPED_TYPES and type_supported and not denial:
        svc = next((f.normalised for f in out if f.field == "service" and f.support == "supported"), None)
        given = fields.get("freight_scope")
        if reviewer and given is not None and given.value.strip().lower() in ("cargo", "passenger", "mixed", "unclear", "not_freight", "conflicting"):
            sc = given.value.strip().lower()
            fs = relevance.FreightScope(sc, f"freight scope set by a reviewer: {sc}")  # type: ignore[arg-type]
        else:
            svc_quote = next((f.quote for f in out if f.field == "service" and f.support == "supported" and f.quote), None)
            evidence_text = " ".join(x for x in (tq or claim_quote or "", svc_quote or "") if x)
            fs = relevance.freight_scope(claim_type, svc, evidence_text, document_title, document=document_text,
                                         service_supported=svc is not None, reference_year=ref_year)
        out.append(FieldAssessment("freight_scope", fs.scope, fs.scope, tq or claim_quote, fs.support, fs.reason,  # type: ignore[arg-type]
                                   extra={"scope": fs.scope, "cargo_cues": list(fs.cargo_cues), "passenger_cues": list(fs.passenger_cues),
                                          "cues": [{"word": c.word, "kind": c.kind, "where": c.where} for c in fs.cues][:20]}))
    conflict_text = geo_conflict.describe(lambda c: COUNTRIES[c][0]) if geo_conflict else None
    return ClaimValidation(claim_type, type_supported, type_reason, out, contradiction, conflict_text)


_MANDATORY = re.compile(r"\b(?:must|shall|required?|requirements?|mandatory|obligatoire|doivent|devront|deben|deber[áa]n|m[üu]ssen|only\b[^.;]{0,80}\bmay)\b", re.I)
_ADVISORY = re.compile(r"\b(?:should|preferably|preferred|desirable|ideally|encouraged|recommended|devraient|deber[ií]an|sollten)\b", re.I)


def _modality(text: str) -> str | None:
    """'mandatory' (must / shall / required), 'advisory' (should / preferably / desirable) or None, read from the requirement's
    own sentence so the meaning the source gave it is preserved rather than flattened into a requirement."""
    t = meaning.ascii_text(text)
    if _MANDATORY.search(t):
        return "mandatory"
    if _ADVISORY.search(t):
        return "advisory"
    return None
