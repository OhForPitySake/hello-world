"""
Comprehensive UK Commercial & Residential EPC Address Matcher.

Designed for matching messy property/lease records of the form:
    [Unit Name, Street Address, Tenant Name]
against postcode-subsetted EPC candidate records of the form:
    {candidate_id: [addr1, addr2, ...], ...}

Key capabilities:
- Cross-field bleed handling (e.g. street address, building, post-town, postcode, or
  tenant name appearing inside Unit Name or Candidate addr1).
- UK commercial & residential sub-unit parsing with smart synonym grouping:
  Flat == Apartment == Maisonette; Suite == Office == Room; Shop == Retail Unit;
  soft commercial compatibility (Unit 3 <-> Suite 3 / Plot 3; Shop <-> Ground Floor),
  while strictly separating Floor levels from Unit numbers (3rd Floor != Unit 3) and
  rejecting incompatible types (Flat vs Shop).
- UK range expansion & containment:
  - Contiguous unit ranges ('Units 1-4', 'Units A-C', 'Units 1, 2 & 3')
  - Same-parity UK street ranges ('12-16 High St' -> 12, 14, 16) vs consecutive ranges
    ('12-15 High St' or parades/squares)
  - Whole-building / parent fallback at capped Medium confidence when one side omits
    sub-units/floors.
- Strict conflict vetoes on conflicting street numbers, letter suffixes ('12' vs '12A'),
  unit IDs ('Unit 2' vs 'Unit 3'), floor levels ('Ground' vs '1st'), or streets.
- Second-sweep Tenant Name matching (stripping UK legal suffixes like Ltd/PLC/LLP/UK/t/a
  and subtracting street/building tokens so 'Station Road Dental' never false-matches
  every property on Station Road). Old/different tenant names on historical EPCs never
  penalize strong structural matches.
- Auto-uses `rapidfuzz` when installed with a zero-dependency pure-Python fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

try:
    from rapidfuzz import distance as _rf_distance
    from rapidfuzz import fuzz as _rf_fuzz

    USING_RAPIDFUZZ = True
except ImportError:  # pragma: no cover - exercised explicitly via fallback helpers
    _rf_distance = None
    _rf_fuzz = None
    USING_RAPIDFUZZ = False


# ============================================================================
# String Similarity Primitives (rapidfuzz with Pure-Python Fallback)
# ============================================================================


def _pure_levenshtein_distance(s1: str, s2: str) -> int:
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, start=1):
        current_row = [i]
        for j, c2 in enumerate(s2, start=1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _pure_indel_ratio(s1: str, s2: str) -> float:
    """Normalized indel similarity (0.0-1.0), matching rapidfuzz.fuzz.ratio."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    # LCS length via DP for exact parity with rapidfuzz.fuzz.ratio (2*LCS / (len1+len2))
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    dp = [0] * (len(s2) + 1)
    for c1 in s1:
        prev = 0
        for j, c2 in enumerate(s2, start=1):
            temp = dp[j]
            if c1 == c2:
                dp[j] = prev + 1
            elif dp[j - 1] > dp[j]:
                dp[j] = dp[j - 1]
            prev = temp
    return (2.0 * dp[-1]) / (len(s1) + len(s2))


def _pure_jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        matches / len1
        + matches / len2
        + (matches - transpositions / 2.0) / matches
    ) / 3.0

    prefix = 0
    for c1, c2 in zip(s1[:4], s2[:4]):
        if c1 == c2:
            prefix += 1
        else:
            break

    return jaro + prefix * prefix_weight * (1.0 - jaro)


def string_ratio(s1: str, s2: str, *, force_pure: bool = False) -> float:
    """Return normalized string similarity in [0.0, 1.0]."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    if USING_RAPIDFUZZ and not force_pure:
        return float(_rf_fuzz.ratio(s1, s2)) / 100.0
    return _pure_indel_ratio(s1, s2)


def jaro_winkler_sim(s1: str, s2: str, *, force_pure: bool = False) -> float:
    """Return Jaro-Winkler similarity in [0.0, 1.0]."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    if USING_RAPIDFUZZ and not force_pure:
        return float(_rf_distance.JaroWinkler.similarity(s1, s2))
    return _pure_jaro_winkler(s1, s2)


def token_set_sim(s1: str, s2: str, *, force_pure: bool = False) -> float:
    """Return token-set similarity in [0.0, 1.0]."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    if USING_RAPIDFUZZ and not force_pure:
        return float(_rf_fuzz.token_set_ratio(s1, s2)) / 100.0

    t1 = set(s1.split())
    t2 = set(s2.split())
    if not t1 or not t2:
        return 0.0
    common = sorted(t1 & t2)
    diff1 = sorted(t1 - t2)
    diff2 = sorted(t2 - t1)
    sect = " ".join(common)
    comb1 = (sect + " " + " ".join(diff1)).strip()
    comb2 = (sect + " " + " ".join(diff2)).strip()
    candidates = [_pure_indel_ratio(comb1, comb2)]
    if sect:
        candidates.append(_pure_indel_ratio(sect, comb1))
        candidates.append(_pure_indel_ratio(sect, comb2))
    return max(candidates)


def token_sort_sim(s1: str, s2: str, *, force_pure: bool = False) -> float:
    """Return token-sort similarity in [0.0, 1.0]."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if USING_RAPIDFUZZ and not force_pure:
        return float(_rf_fuzz.token_sort_ratio(s1, s2)) / 100.0
    a = " ".join(sorted(s1.split()))
    b = " ".join(sorted(s2.split()))
    return _pure_indel_ratio(a, b)


# ============================================================================
# UK Domain Vocabularies & Normalization Constants
# ============================================================================

NULL_STRINGS = frozenset(
    {
        "",
        "nan",
        "none",
        "null",
        "n/a",
        "na",
        "nil",
        "tbc",
        "tba",
        "unknown",
        "not known",
        "-",
        "--",
        ".",
    }
)

# UK Postcode pattern (handles standard formats + GIR 0AA)
UK_POSTCODE_RE = re.compile(
    r"\b(?:GIR\s*0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)

# UK Route numbers (A4, A406, B4100, M25) - NOT unit numbers
UK_ROUTE_RE = re.compile(r"^[abm]\d{1,4}(?:\([m]\))?$", re.IGNORECASE)

SAINT_NAMES = frozenset(
    {
        "albans",
        "andrew",
        "andrews",
        "ann",
        "anne",
        "annes",
        "anns",
        "asaph",
        "augustine",
        "augustines",
        "austell",
        "barnabas",
        "bartholomew",
        "bartholomews",
        "bees",
        "benet",
        "blazey",
        "botolph",
        "botolphs",
        "bride",
        "brides",
        "catherine",
        "catherines",
        "chad",
        "chads",
        "christopher",
        "christophers",
        "clair",
        "claire",
        "cleer",
        "clement",
        "clements",
        "columb",
        "cross",
        "cuthbert",
        "cuthberts",
        "david",
        "davids",
        "denys",
        "dunstan",
        "dunstans",
        "edmund",
        "edmunds",
        "edward",
        "edwards",
        "enos",
        "erth",
        "fagan",
        "fagans",
        "faith",
        "francis",
        "george",
        "georges",
        "german",
        "germans",
        "giles",
        "helen",
        "helens",
        "hilary",
        "ives",
        "james",
        "jamess",
        "john",
        "johns",
        "joseph",
        "josephs",
        "jude",
        "judes",
        "just",
        "katherine",
        "katherines",
        "keverne",
        "keyne",
        "lawrence",
        "leonard",
        "leonards",
        "luke",
        "lukes",
        "margaret",
        "margarets",
        "mark",
        "marks",
        "martin",
        "martins",
        "mary",
        "marys",
        "matthew",
        "matthews",
        "mawes",
        "mellons",
        "michael",
        "michaels",
        "mirren",
        "neot",
        "neots",
        "nicholas",
        "olave",
        "olaves",
        "oswald",
        "oswalds",
        "osyth",
        "pancras",
        "patrick",
        "patricks",
        "paul",
        "pauls",
        "peter",
        "peters",
        "philip",
        "philips",
        "piran",
        "rokeby",
        "saviour",
        "saviours",
        "sepulchre",
        "stephen",
        "stephens",
        "swithin",
        "swithins",
        "thomas",
        "thomass",
        "vincent",
        "vincents",
        "werburgh",
        "werburghs",
    }
)

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}

ORDINAL_TO_INT = {
    "ground": 0,
    "gnd": 0,
    "grd": 0,
    "gf": 0,
    "g": 0,
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
    "sixth": 6,
    "6th": 6,
    "seventh": 7,
    "7th": 7,
    "eighth": 8,
    "8th": 8,
    "ninth": 9,
    "9th": 9,
    "tenth": 10,
    "10th": 10,
    "eleventh": 11,
    "11th": 11,
    "twelfth": 12,
    "12th": 12,
    "thirteenth": 13,
    "13th": 13,
    "fourteenth": 14,
    "14th": 14,
    "fifteenth": 15,
    "15th": 15,
}

SPECIAL_FLOOR_MAP = {
    "sub basement": "sub_basement",
    "sub-basement": "sub_basement",
    "basement": "basement",
    "bsmt": "basement",
    "bst": "basement",
    "cellar": "basement",
    "lower ground": "lower_ground",
    "lower gnd": "lower_ground",
    "lower grd": "lower_ground",
    "lgf": "lower_ground",
    "lg": "lower_ground",
    "upper ground": "upper_ground",
    "ugf": "upper_ground",
    "mezzanine": "mezzanine",
    "mezz": "mezzanine",
    "penthouse": "penthouse",
    "top": "top",
    "attic": "attic",
    "roof": "roof",
}

# Token-level abbreviation expansion (applied prudently after saint/street disambiguation)
TOKEN_ABBREVS = {
    "rd": "road",
    "ave": "avenue",
    "av": "avenue",
    "ln": "lane",
    "dr": "drive",
    "drv": "drive",
    "cl": "close",
    "ct": "court",
    "crt": "court",
    "cres": "crescent",
    "cr": "crescent",
    "sq": "square",
    "ter": "terrace",
    "terr": "terrace",
    "pl": "place",
    "gdns": "gardens",
    "gdn": "gardens",
    "pk": "park",
    "prk": "park",
    "wy": "way",
    "gro": "grove",
    "grv": "grove",
    "hl": "hill",
    "vw": "view",
    "wk": "walk",
    "wlk": "walk",
    "ch": "chase",
    "rw": "row",
    "yd": "yard",
    "yrd": "yard",
    "mws": "mews",
    "pde": "parade",
    "prd": "parade",
    "arc": "arcade",
    "bvd": "boulevard",
    "blvd": "boulevard",
    "hwy": "highway",
    "gn": "green",
    "grn": "green",
    "gt": "gate",
    "bdge": "bridge",
    "brg": "bridge",
    "jct": "junction",
    "est": "estate",
    "ind": "industrial",
    "trad": "trading",
    "comm": "commercial",
    "bus": "business",
    "ret": "retail",
    "sci": "science",
    "tech": "technology",
    "ctr": "centre",
    "cntr": "centre",
    "center": "centre",
    "bldg": "building",
    "bldgs": "buildings",
    "chbrs": "chambers",
    "hse": "house",
    "ho": "house",
    "mans": "mansions",
    "cott": "cottage",
    "cotts": "cottages",
    "flr": "floor",
    "flrs": "floors",
    "fl": "floor",
    "gnd": "ground",
    "grd": "ground",
    "bsmt": "basement",
    "bst": "basement",
    "mezz": "mezzanine",
    "apt": "apartment",
    "apts": "apartments",
    "flt": "flat",
    "flts": "flats",
    "ste": "suite",
    "stes": "suites",
    "rm": "room",
    "rms": "rooms",
    "blk": "block",
    "wks": "works",
    "whse": "warehouse",
    "nth": "north",
    "sth": "south",
    "pt": "part",
    "adj": "adjacent",
}

THOROUGHFARE_WORDS = frozenset(
    {
        "street",
        "road",
        "avenue",
        "lane",
        "drive",
        "close",
        "crescent",
        "way",
        "grove",
        "hill",
        "view",
        "walk",
        "chase",
        "rise",
        "row",
        "mews",
        "parade",
        "arcade",
        "boulevard",
        "highway",
        "terrace",
        "place",
        "square",
        "gardens",
        "green",
        "alley",
        "approach",
        "bank",
        "brae",
        "bridge",
        "broadway",
        "brow",
        "bypass",
        "buildings",  # only secondary; checked after building suffixes
        "causeway",
        "cheapside",
        "circus",
        "common",
        "concourse",
        "copse",
        "cornhill",
        "corner",
        "croft",
        "cross",
        "crossing",
        "cul-de-sac",
        "dale",
        "dene",
        "downs",
        "drapery",
        "embankment",
        "end",
        "esplanade",
        "fairway",
        "fenchurch",
        "field",
        "fields",
        "fold",
        "friargate",
        "front",
        "furlong",
        "garth",
        "gate",
        "glade",
        "glen",
        "gracechurch",
        "grange",
        "haymarket",
        "headrow",
        "heath",
        "highroad",
        "holborn",
        "hollow",
        "knightsbridge",
        "lawn",
        "leas",
        "link",
        "loan",
        "loop",
        "mall",
        "market",
        "marketplace",
        "mead",
        "meadow",
        "meadows",
        "millbank",
        "minories",
        "mount",
        "orchard",
        "paddock",
        "pall",
        "parkway",
        "passage",
        "path",
        "pathway",
        "pavement",
        "piccadilly",
        "piazza",
        "plain",
        "plaza",
        "precinct",
        "promenade",
        "quadrant",
        "quay",
        "quays",
        "quayside",
        "reach",
        "ridge",
        "ringway",
        "roundabout",
        "shambles",
        "side",
        "slope",
        "strand",
        "strip",
        "thoroughfare",
        "track",
        "trail",
        "turnpike",
        "vale",
        "viaduct",
        "villas",
        "walkway",
        "wharf",
        "whitehall",
        "wynd",
        "yard",
    }
)

# Streets where consecutive (mixed-parity) numbering is normal even when start/end share parity
CONSECUTIVE_THOROUGHFARE_WORDS = frozenset(
    {
        "parade",
        "arcade",
        "square",
        "market",
        "marketplace",
        "precinct",
        "concourse",
        "mall",
        "row",
        "mews",
        "court",
        "yard",
        "quay",
        "wharf",
        "circus",
        "quadrant",
        "terrace",
    }
)

ESTATE_PARK_PHRASES = (
    "industrial estate",
    "trading estate",
    "business park",
    "retail park",
    "science park",
    "technology park",
    "enterprise park",
    "commercial park",
    "office park",
    "distribution park",
    "logistics park",
    "leisure park",
    "shopping centre",
    "shopping park",
    "business centre",
    "enterprise centre",
    "innovation centre",
    "trade park",
    "industrial park",
    "retail centre",
    "outlet centre",
    "workshopping centre",
)

BUILDING_SUFFIX_WORDS = frozenset(
    {
        "house",
        "buildings",
        "building",
        "chambers",
        "tower",
        "towers",
        "court",
        "mansions",
        "hall",
        "lodge",
        "manor",
        "palace",
        "point",
        "heights",
        "exchange",
        "works",
        "mill",
        "mills",
        "wharf",
        "granary",
        "foundry",
        "brewery",
        "barn",
        "cottage",
        "cottages",
        "villa",
        "villas",
        "priory",
        "abbey",
        "rectory",
        "vicarage",
        "castle",
        "keep",
        "pavilion",
        "forum",
        "atrium",
        "plaza",
        "apex",
        "central",
    }
)

# Unit designator groups (per Q6 smart UK synonym grouping)
UNIT_CATEGORY_BY_DESIGNATOR = {
    # Residential group (strictly incompatible with commercial)
    "flat": ("residential", "flat"),
    "flats": ("residential", "flat"),
    "apartment": ("residential", "flat"),
    "apartments": ("residential", "flat"),
    "maisonette": ("residential", "flat"),
    "studio": ("residential", "flat"),
    "bedsit": ("residential", "flat"),
    # Commercial / Industrial general units
    "unit": ("commercial", "unit"),
    "units": ("commercial", "unit"),
    "workshop": ("commercial", "unit"),
    "warehouse": ("commercial", "unit"),
    "shed": ("commercial", "unit"),
    "bay": ("commercial", "unit"),
    "bays": ("commercial", "unit"),
    "arch": ("commercial", "unit"),
    "arches": ("commercial", "unit"),
    "hangar": ("commercial", "unit"),
    "berth": ("commercial", "unit"),
    # Office / Suite group
    "suite": ("commercial", "suite"),
    "suites": ("commercial", "suite"),
    "office": ("commercial", "suite"),
    "offices": ("commercial", "suite"),
    "room": ("commercial", "suite"),
    "rooms": ("commercial", "suite"),
    "pod": ("commercial", "suite"),
    # Retail group
    "shop": ("commercial", "shop"),
    "shops": ("commercial", "shop"),
    "store": ("commercial", "shop"),
    "kiosk": ("commercial", "shop"),
    "stall": ("commercial", "shop"),
    "stand": ("commercial", "shop"),
    # Plot / Site group
    "plot": ("commercial", "plot"),
    "plots": ("commercial", "plot"),
    # Structural Block / Wing / Phase (tracked separately so 'Block A, Unit 2' keeps both!)
    "block": ("structure", "block"),
    "wing": ("structure", "wing"),
    "core": ("structure", "core"),
    "phase": ("structure", "phase"),
    # Ancillary
    "annex": ("ancillary", "annex"),
    "annexe": ("ancillary", "annex"),
    "garage": ("ancillary", "garage"),
    "atm": ("ancillary", "atm"),
    "substation": ("ancillary", "substation"),
}

# Corporate & legal boilerplate tokens stripped when normalizing tenant names
TENANT_STOPWORDS = frozenset(
    {
        "ltd",
        "limited",
        "plc",
        "llp",
        "lp",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "uk",
        "gb",
        "britain",
        "british",
        "international",
        "holdings",
        "holding",
        "group",
        "services",
        "service",
        "enterprises",
        "enterprise",
        "properties",
        "property",
        "investments",
        "investment",
        "management",
        "commercial",
        "retail",
        "stores",
        "store",
        "supermarkets",
        "supermarket",
        "express",
        "local",
        "extra",
        "superstore",
        "trading",
        "as",
        "ta",
        "care",
        "of",
        "formerly",
        "ex",
        "the",
        "and",
        "at",
        "in",
        "for",
    }
)

CORPORATE_INDICATOR_WORDS = frozenset(
    {
        "ltd",
        "limited",
        "plc",
        "llp",
        "inc",
        "holdings",
        "group",
        "t/a",
        "trading as",
        "formerly",
    }
)

# Common UK Brand normalizations
BRAND_ALIASES = {
    "co-operative": "coop",
    "co operative": "coop",
    "cooperative": "coop",
    "co-op": "coop",
    "co op": "coop",
    "marks and spencer": "marks spencer",
    "m and s": "marks spencer",
    "m&s": "marks spencer",
    "b and q": "bq",
    "b&q": "bq",
    "h and m": "hm",
    "h&m": "hm",
    "w h smith": "whsmith",
    "wh smith": "whsmith",
    "t k maxx": "tkmaxx",
    "tk maxx": "tkmaxx",
    "j d wetherspoon": "wetherspoon",
    "jd wetherspoon": "wetherspoon",
    "j sainsbury": "sainsburys",
    "sainsbury": "sainsburys",
}

# Major UK Cities, Post-Towns, London Boroughs & Counties (only stripped from standalone
# trailing locality segments, NEVER from 'London Road' or 'York House')
UK_LOCALITIES = frozenset(
    {
        # Countries & Regions
        "uk",
        "united kingdom",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "east anglia",
        "west midlands",
        "east midlands",
        "greater london",
        "greater manchester",
        "merseyside",
        "south yorkshire",
        "west yorkshire",
        "north yorkshire",
        "east yorkshire",
        "tyne and wear",
        # Counties & Historic Counties
        "avon",
        "bedfordshire",
        "beds",
        "berkshire",
        "berks",
        "buckinghamshire",
        "bucks",
        "cambridgeshire",
        "cambs",
        "cheshire",
        "cleveland",
        "cornwall",
        "cumbria",
        "derbyshire",
        "derbys",
        "devon",
        "dorset",
        "durham",
        "county durham",
        "essex",
        "gloucestershire",
        "glos",
        "hampshire",
        "hants",
        "herefordshire",
        "hertfordshire",
        "herts",
        "humberside",
        "huntingdonshire",
        "isle of wight",
        "kent",
        "lancashire",
        "lancs",
        "leicestershire",
        "leics",
        "lincolnshire",
        "lincs",
        "middlesex",
        "midx",
        "norfolk",
        "northamptonshire",
        "northants",
        "northumberland",
        "nottinghamshire",
        "notts",
        "oxfordshire",
        "oxon",
        "rutland",
        "shropshire",
        "salop",
        "somerset",
        "staffordshire",
        "staffs",
        "suffolk",
        "surrey",
        "sussex",
        "east sussex",
        "west sussex",
        "warwickshire",
        "warks",
        "wilts",
        "wiltshire",
        "worcestershire",
        "worcs",
        "yorkshire",
        "aberdeenshire",
        "angus",
        "argyll",
        "ayrshire",
        "clackmannanshire",
        "dumfriesshire",
        "dunbartonshire",
        "east lothian",
        "fife",
        "inverness-shire",
        "lanarkshire",
        "midlothian",
        "moray",
        "perthshire",
        "renfrewshire",
        "stirlingshire",
        "west lothian",
        "anglesey",
        "brecknockshire",
        "caernarfonshire",
        "cardiganshire",
        "carmarthenshire",
        "clwyd",
        "conwy",
        "denbighshire",
        "dyfed",
        "flintshire",
        "glamorgan",
        "mid glamorgan",
        "south glamorgan",
        "west glamorgan",
        "gwent",
        "gwynedd",
        "monmouthshire",
        "pembrokeshire",
        "powys",
        "torfaen",
        "antrim",
        "armagh",
        "down",
        "fermanagh",
        "londonderry",
        "tyrone",
        # Major Cities & Post-Towns
        "aberdeen",
        "abingdon",
        "accrington",
        "airdrie",
        "aldershot",
        "altrincham",
        "andover",
        "ashford",
        "ashton-under-lyne",
        "aylesbury",
        "ayr",
        "banbury",
        "bangor",
        "barking",
        "barnet",
        "barnsley",
        "barnstaple",
        "barrow-in-furness",
        "barry",
        "basildon",
        "basingstoke",
        "bath",
        "bedford",
        "belfast",
        "bexley",
        "bexleyheath",
        "bicester",
        "birkenhead",
        "birmingham",
        "bishops stortford",
        "blackburn",
        "blackpool",
        "bognor regis",
        "bolton",
        "bootle",
        "boston",
        "bournemouth",
        "bracknell",
        "bradford",
        "braintree",
        "brentford",
        "brentwood",
        "bridgend",
        "bridgwater",
        "bridlington",
        "brighton",
        "bristol",
        "bromley",
        "bromsgrove",
        "burnley",
        "burton-on-trent",
        "burton upon trent",
        "bury",
        "bury saint edmunds",
        "bury st edmunds",
        "buxton",
        "caerphilly",
        "camberley",
        "cambridge",
        "cannock",
        "canterbury",
        "cardiff",
        "carlisle",
        "carmarthen",
        "castleford",
        "chatham",
        "chelmsford",
        "cheltenham",
        "chester",
        "chesterfield",
        "chichester",
        "chippenham",
        "chorley",
        "christchurch",
        "circencester",
        "cirencester",
        "clacton-on-sea",
        "coatbridge",
        "colchester",
        "colwyn bay",
        "corby",
        "coventry",
        "crawley",
        "crewe",
        "croydon",
        "cumbernauld",
        "cwmbran",
        "dagenham",
        "darlington",
        "dartford",
        "daventry",
        "derby",
        "dewsbury",
        "didcot",
        "doncaster",
        "dorchester",
        "dover",
        "dudley",
        "dumfries",
        "dundee",
        "dunfermline",
        "dunstable",
        "ealing",
        "east kilbride",
        "eastbourne",
        "eastleigh",
        "edgware",
        "edinburgh",
        "ely",
        "enfield",
        "epsom",
        "erith",
        "esher",
        "evesham",
        "exeter",
        "exmouth",
        "falkirk",
        "falmouth",
        "fareham",
        "farnborough",
        "farnham",
        "felixstowe",
        "fleet",
        "folkestone",
        "frome",
        "gainsborough",
        "gateshead",
        "gillingham",
        "glasgow",
        "glastonbury",
        "glenrothes",
        "glossop",
        "gloucester",
        "godalming",
        "gosport",
        "grantham",
        "gravesend",
        "grays",
        "great yarmouth",
        "greenock",
        "greenwich",
        "grimsby",
        "guildford",
        "hackney",
        "halesowen",
        "halifax",
        "hamilton",
        "hammersmith",
        "harlow",
        "harrogate",
        "harrow",
        "hartlepool",
        "hastings",
        "hatfield",
        "havant",
        "haverhill",
        "hayes",
        "haywards heath",
        "hemel hempstead",
        "henley-on-thames",
        "hereford",
        "hertford",
        "high wycombe",
        "hinckley",
        "hitchin",
        "hoddesdon",
        "hornchurch",
        "horsham",
        "hounslow",
        "hove",
        "huddersfield",
        "hull",
        "kingston upon hull",
        "huntingdon",
        "hyde",
        "ilford",
        "ilkeston",
        "inverness",
        "ipswich",
        "irvine",
        "islington",
        "keighley",
        "kendal",
        "kettering",
        "kidderminster",
        "kilmarnock",
        "kings lynn",
        "kingston upon thames",
        "kirkcaldy",
        "lambeth",
        "lancaster",
        "leamington spa",
        "royal leamington spa",
        "leatherhead",
        "leeds",
        "leicester",
        "leigh",
        "leighton buzzard",
        "letchworth",
        "lewes",
        "lewisham",
        "lichfield",
        "lincoln",
        "lisburn",
        "littlehampton",
        "liverpool",
        "livingston",
        "llandudno",
        "llanelli",
        "london",
        "londonderry",
        "loughborough",
        "loughton",
        "lowestoft",
        "luton",
        "lymington",
        "macclesfield",
        "maidenhead",
        "maidstone",
        "maldon",
        "malvern",
        "manchester",
        "mansfield",
        "margate",
        "market harborough",
        "marlow",
        "melton mowbray",
        "merthyr tydfil",
        "middlesbrough",
        "middleton",
        "milton keynes",
        "mitcham",
        "morecambe",
        "motherwell",
        "neath",
        "newark",
        "newbury",
        "newcastle",
        "newcastle upon tyne",
        "newcastle-under-lyme",
        "newmarket",
        "newport",
        "newquay",
        "newry",
        "newton abbot",
        "newton aycliffe",
        "northallerton",
        "northampton",
        "northwich",
        "norwich",
        "nottingham",
        "nuneaton",
        "oldbury",
        "oldham",
        "ormskirk",
        "orpington",
        "oswestry",
        "oxford",
        "paignton",
        "paisley",
        "penarth",
        "penzance",
        "perth",
        "peterborough",
        "peterlee",
        "plymouth",
        "pontefract",
        "pontypridd",
        "poole",
        "port talbot",
        "portsmouth",
        "potters bar",
        "preston",
        "pudsey",
        "radlett",
        "ramsgate",
        "reading",
        "redditch",
        "redhill",
        "redruth",
        "reigate",
        "rhyl",
        "richmond",
        "rickmansworth",
        "ripon",
        "rochdale",
        "rochester",
        "romford",
        "romsey",
        "rotherham",
        "royal tunbridge wells",
        "tunbridge wells",
        "rugby",
        "rugeley",
        "ruislip",
        "runcorn",
        "rushden",
        "saint albans",
        "st albans",
        "saint austell",
        "st austell",
        "saint helens",
        "st helens",
        "saint ives",
        "st ives",
        "saint neots",
        "st neots",
        "sale",
        "salford",
        "salisbury",
        "scarborough",
        "scunthorpe",
        "sevenoaks",
        "sheffield",
        "shipley",
        "shrewsbury",
        "sidcup",
        "sittingbourne",
        "skegness",
        "skelmersdale",
        "skipton",
        "sleaford",
        "slough",
        "smethwick",
        "solihull",
        "south shields",
        "southall",
        "southampton",
        "southend-on-sea",
        "southend",
        "southport",
        "southwark",
        "spalding",
        "spennymoor",
        "stafford",
        "staines",
        "staines-upon-thames",
        "stalybridge",
        "stamford",
        "stevenage",
        "stirling",
        "stockport",
        "stockton-on-tees",
        "stoke-on-trent",
        "stoke on trent",
        "stone",
        "stourbridge",
        "stowmarket",
        "stratford",
        "stratford-upon-avon",
        "streatham",
        "stroud",
        "sudbury",
        "sunderland",
        "surbiton",
        "sutton",
        "sutton coldfield",
        "swadlincote",
        "swanley",
        "swansea",
        "swindon",
        "tamworth",
        "taunton",
        "telford",
        "tewkesbury",
        "thatcham",
        "thetford",
        "thirsk",
        "thornton heath",
        "tilbury",
        "tiverton",
        "tonbridge",
        "torquay",
        "totnes",
        "tottenham",
        "trowbridge",
        "truro",
        "twickenham",
        "uckfield",
        "ulverston",
        "upminster",
        "uxbridge",
        "wakefield",
        "wallasey",
        "wallingford",
        "wallington",
        "walsall",
        "waltham cross",
        "walthamstow",
        "walton-on-thames",
        "wandsworth",
        "wantage",
        "ware",
        "warminster",
        "warrington",
        "warwick",
        "washington",
        "waterlooville",
        "watford",
        "wednesbury",
        "welling",
        "wellingborough",
        "wells",
        "welwyn garden city",
        "wembley",
        "west bromwich",
        "westcliff-on-sea",
        "westminster",
        "weston-super-mare",
        "weybridge",
        "weymouth",
        "whitby",
        "whitchurch",
        "whitehaven",
        "whitstable",
        "wickford",
        "widnes",
        "wigan",
        "wilmslow",
        "wimbledon",
        "wimborne",
        "winchester",
        "windsor",
        "winsford",
        "wisbech",
        "wishaw",
        "witham",
        "witney",
        "woking",
        "wokingham",
        "wolverhampton",
        "woodbridge",
        "woodford green",
        "woolwich",
        "worcester",
        "workington",
        "worksop",
        "worthing",
        "wrexham",
        "yeovil",
        "york",
    }
)


# ============================================================================
# Structured Data Representations
# ============================================================================


@dataclass
class UnitSpec:
    """Represents an extracted sub-unit or structural block designator."""

    broad_category: str  # 'residential' | 'commercial' | 'structure' | 'ancillary'
    synonym_group: str  # 'flat' | 'unit' | 'suite' | 'shop' | 'plot' | 'block' | ...
    raw_designator: str  # original normalized designator word (e.g. 'apartment', 'unit')
    ids: tuple[str, ...]  # canonical unit IDs (e.g. ('4b',) or ('1', '2', '3', '4'))
    is_range: bool = False
    is_bare_inferred: bool = False  # True when inferred from bare Unit Name slot


@dataclass
class NumberSpec:
    """Represents a street/building number or range (e.g. '12', '12a', '12-16')."""

    raw: str
    members: tuple[str, ...]  # expanded canonical IDs, e.g. ('12', '14', '16') or ('12a',)
    is_range: bool = False
    has_suffix: bool = False


@dataclass
class ParsedAddress:
    """Canonical structured representation of a UK property address + occupier."""

    raw_parts: tuple[str, ...]
    postcode: str | None = None
    floors: set[str] = field(default_factory=set)  # e.g. {'0'}, {'1'}, {'basement'}
    floor_modifiers: set[str] = field(default_factory=set)  # e.g. {'part', 'north'}
    units: list[UnitSpec] = field(default_factory=list)  # primary units (flat/unit/suite/shop)
    structures: list[UnitSpec] = field(default_factory=list)  # block/wing/phase
    street_numbers: list[NumberSpec] = field(default_factory=list)
    thoroughfares: list[str] = field(default_factory=list)  # e.g. ['high street']
    estates: list[str] = field(default_factory=list)  # e.g. ['acorn industrial estate']
    buildings: list[str] = field(default_factory=list)  # e.g. ['apex house']
    localities: list[str] = field(default_factory=list)  # stripped towns/counties
    explicit_tenant: str = ""  # from query[2] or 't/a ...'
    inferred_occupiers: list[str] = field(default_factory=list)  # leading company/brand segments
    unclassified_segments: list[str] = field(default_factory=list)
    core_structural_tokens: set[str] = field(default_factory=set)
    all_address_tokens: set[str] = field(default_factory=set)
    normalized_full: str = ""
    is_epc_exempt: bool = False
    exempt_category: str | None = None
    exempt_trigger: str | None = None


# ============================================================================
# Low-Level Cleaners & Range Expanders
# ============================================================================


def _clean_input_value(val: Any) -> str:
    """Convert raw input element (str, int, None, float('nan'), pd.NA) to clean str."""
    if val is None:
        return ""
    if isinstance(val, float):
        if math.isnan(val):
            return ""
        if val.is_integer():
            return str(int(val))
    s = str(val).strip()
    if s.lower() in NULL_STRINGS or s.lower() == "<na>":
        return ""
    # Normalize unicode accents & dash/quote variants
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    s = re.sub(r"[\r\n\t]+", ", ", s)
    return s.strip(" ,;")


def _normalize_apostrophes_and_symbols(text: str) -> str:
    text = re.sub(r"['`’]s\b", "s", text)
    text = re.sub(r"['`’]", "", text)
    # Protect 'c/o', 't/a', 'r/o' before generic punctuation splitting
    text = re.sub(r"\bc\s*/\s*o\b", " care_of ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bt\s*/\s*a\b", " trading_as ", text, flags=re.IGNORECASE)
    text = re.sub(r"\br\s*/\s*o\b", " rear_of ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bg\s*/\s*f\b", " ground floor ", text, flags=re.IGNORECASE)
    # Expand '1st/2nd' or '12/14' or '1/2' cautiously later; keep slash between alphanumerics
    text = text.replace("&", " and ").replace("+", " and ")
    return text


def _disambiguate_st_and_abbrevs(clause: str) -> str:
    """Expand UK abbreviations while distinguishing 'St' (Saint) from 'St' (Street)."""
    raw_tokens = clause.lower().split()
    if not raw_tokens:
        return ""

    out: list[str] = []
    n = len(raw_tokens)
    for i, tok in enumerate(raw_tokens):
        clean_tok = tok.strip(".,;:")
        if not clean_tok:
            continue

        if clean_tok in ("st", "st."):
            next_tok = raw_tokens[i + 1].strip(".,;:") if i + 1 < n else ""
            if next_tok in SAINT_NAMES:
                out.append("saint")
            elif i == 0 and n >= 2 and next_tok not in ("and", "or"):
                # Leading 'St ...' at start of clause is virtually always Saint in UK addresses
                out.append("saint")
            else:
                out.append("street")
            continue

        # Avoid turning single letter unit IDs ('Unit E', 'Block N', 'Flat A') into directions/abbrevs
        if len(clean_tok) == 1:
            out.append(clean_tok)
            continue

        # Context-sensitive 'ho' -> 'house' (avoid 'soho' - already full word, but avoid 'ho' in brand names if needed)
        mapped = TOKEN_ABBREVS.get(clean_tok, clean_tok)
        out.append(mapped)

    return " ".join(out)


def _is_thoroughfare_word(word: str) -> bool:
    if word in THOROUGHFARE_WORDS:
        return True
    # UK historic '-gate' thoroughfares (Deansgate, Bishopsgate, Briggate, Kirkgate, etc.)
    if len(word) >= 6 and word.endswith("gate") and word not in ("surrogate", "delegate", "colgate"):
        return True
    return False


def _expand_unit_id_expr(expr: str) -> tuple[tuple[str, ...], bool]:
    """
    Expand unit identifier expressions like:
      '4b' -> (('4b',), False)
      '1-4' -> (('1', '2', '3', '4'), True)
      'a-d' -> (('a', 'b', 'c', 'd'), True)
      '1a-1c' -> (('1a', '1b', '1c'), True)
      '1, 2 and 3' -> (('1', '2', '3'), True)
      '1/2' -> (('1', '2'), True)
    """
    s = expr.lower().strip(" ,.;:-")
    s = NUMBER_WORDS.get(s, s)
    if not s:
        return ((), False)

    # Normalize 'to' -> '-'
    s_norm = re.sub(r"\bto\b", "-", s)

    # Pure numeric range: 1-4
    m_num_range = re.fullmatch(r"(\d{1,4})\s*-\s*(\d{1,4})", s_norm)
    if m_num_range:
        start, end = int(m_num_range.group(1)), int(m_num_range.group(2))
        if 0 <= start < end and (end - start) <= 50:
            return (tuple(str(x) for x in range(start, end + 1)), True)

    # Pure single-letter range: a-d
    m_let_range = re.fullmatch(r"([a-z])\s*-\s*([a-z])", s_norm)
    if m_let_range:
        c1, c2 = ord(m_let_range.group(1)), ord(m_let_range.group(2))
        if c1 < c2 and (c2 - c1) <= 15:
            return (tuple(chr(c) for c in range(c1, c2 + 1)), True)

    # Number + letter suffix range: 1a-1c or 1a-c
    m_alnum_range = re.fullmatch(r"(\d{1,4})([a-z])\s*-\s*(?:\1)?([a-z])", s_norm)
    if m_alnum_range:
        base = m_alnum_range.group(1)
        c1, c2 = ord(m_alnum_range.group(2)), ord(m_alnum_range.group(3))
        if c1 < c2 and (c2 - c1) <= 15:
            return (tuple(f"{base}{chr(c)}" for c in range(c1, c2 + 1)), True)

    # Slash or 'and' list: '1/2', '1 and 2', '1a and 1b', '1, 2 and 3'
    if "/" in s_norm or " and " in s_norm or "," in s_norm:
        parts = [p.strip() for p in re.split(r"(?:/|,|\band\b)", s_norm) if p.strip()]
        valid_parts = [NUMBER_WORDS.get(p, p) for p in parts if re.fullmatch(r"\d{1,4}[a-z]?|[a-z]\d{0,3}", NUMBER_WORDS.get(p, p))]
        if len(valid_parts) >= 2 and len(valid_parts) == len(parts):
            return (tuple(dict.fromkeys(valid_parts)), True)

    # Single unit ID (e.g. '4', '4b', 'b', 'g1', '102')
    s_compact = re.sub(r"\s+", "", s_norm)
    if re.fullmatch(r"\d{1,4}[a-z]?|[a-z]\d{0,3}", s_compact):
        return ((s_compact,), False)

    return ((), False)


def _expand_street_number_expr(expr: str, consecutive_street: bool = False) -> NumberSpec | None:
    """
    Parse UK street number / range expressions:
      '12' -> ('12',)
      '12a' -> ('12a',), has_suffix=True
      '12-16' -> ('12', '14', '16') on standard UK streets (same parity), or consecutive on parades
      '12-15' -> ('12', '13', '14', '15') (mixed parity implies consecutive numbering)
      '12 and 12a' / '12-12a' -> ('12', '12a')
      '12/14' -> ('12', '14')
    """
    s = expr.lower().strip(" ,.;:")
    s = NUMBER_WORDS.get(s, s)
    if not s or UK_ROUTE_RE.fullmatch(s):
        return None

    s_norm = re.sub(r"\bto\b", "-", s)

    # Case 1: '12-12a' or '12 and 12a' or '12/12a'
    m_sub_pair = re.fullmatch(r"(\d{1,4})\s*(?:-|/|\band\b)\s*(\1[a-z])", s_norm)
    if m_sub_pair:
        return NumberSpec(
            raw=s,
            members=(m_sub_pair.group(1), m_sub_pair.group(2)),
            is_range=True,
            has_suffix=True,
        )

    # Case 2: Numeric range '12-16' or '12/14'
    m_range = re.fullmatch(r"(\d{1,4})\s*(-|/)\s*(\d{1,4})", s_norm)
    if m_range:
        n1, sep, n2 = int(m_range.group(1)), m_range.group(2), int(m_range.group(3))
        if sep == "/" and n1 < n2 and (n2 - n1) in (1, 2):
            # '12/14 High St' or '1/2 Market Sq' -> pair
            return NumberSpec(raw=s, members=(str(n1), str(n2)), is_range=True)
        if sep == "-" and 0 < n1 < n2 and (n2 - n1) <= 40:
            if not consecutive_street and (n1 % 2 == n2 % 2) and (n2 - n1) >= 2:
                members = tuple(str(x) for x in range(n1, n2 + 1, 2))
            else:
                members = tuple(str(x) for x in range(n1, n2 + 1))
            return NumberSpec(raw=s, members=members, is_range=True)

    # Case 3: '12 and 14'
    if " and " in s_norm:
        parts = [p.strip() for p in s_norm.split(" and ") if p.strip()]
        if len(parts) == 2 and all(re.fullmatch(r"\d{1,4}[a-z]?", p) for p in parts):
            has_suf = any(p[-1].isalpha() for p in parts)
            return NumberSpec(raw=s, members=tuple(parts), is_range=True, has_suffix=has_suf)

    # Case 4: Single number '12' or '12a'
    s_compact = re.sub(r"\s+", "", s_norm)
    m_single = re.fullmatch(r"(\d{1,4})([a-z]?)", s_compact)
    if m_single:
        has_suf = bool(m_single.group(2))
        return NumberSpec(raw=s_compact, members=(s_compact,), is_range=False, has_suffix=has_suf)

    return None


def normalize_tenant_name(name: str, subtract_tokens: set[str] | None = None) -> tuple[str, set[str]]:
    """
    Normalize a UK company / tenant / brand name:
    - Extracts 't/a <Brand>' as primary brand if present alongside legal name
    - Normalizes common UK retail brands (Co-op, M&S, B&Q, WHSmith, etc.)
    - Strips corporate suffixes (Ltd, Limited, PLC, LLP, UK, Holdings, Group, etc.)
    - Subtracts street/building/locality tokens so 'Station Road Dental' only keeps {'dental'}
    """
    cleaned = _clean_input_value(name)
    if not cleaned:
        return ("", set())

    low = _normalize_apostrophes_and_symbols(cleaned.lower())
    low = re.sub(r"[^\w\s-]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()

    # Check brand aliases before splitting hyphens
    for alias, canon in BRAND_ALIASES.items():
        low = re.sub(rf"\b{re.escape(alias)}\b", canon, low)

    low = low.replace("-", " ")

    # If 'trading_as' is present, keep ALL distinctive tokens from both parts, prioritizing trading name
    low = low.replace("trading_as", " ").replace("care_of", " ")

    raw_toks = [NUMBER_WORDS.get(t, t) for t in low.split() if t]
    filtered = [t for t in raw_toks if t not in TENANT_STOPWORDS and len(t) > 1]

    # If stripping stopwords removed everything (e.g. 'Next' is not in stopwords, 'Co-op' -> 'coop',
    # what if tenant is literally 'The Group' or 'Express Ltd'?), fall back cautiously
    if not filtered:
        filtered = [t for t in raw_toks if t not in {"ltd", "limited", "plc", "llp", "the", "and", "uk"}]

    distinctive = set(filtered)
    if subtract_tokens:
        rem = distinctive - subtract_tokens
        # Keep subtracted only if removing them leaves >=1 distinctive token, OR if ALL tokens were
        # street tokens (e.g. candidate '14 Station Road' has ZERO real tenant tokens -> empty set!)
        distinctive = rem

    norm_str = " ".join(t for t in filtered if not subtract_tokens or t in distinctive)
    return (norm_str, distinctive)


# ============================================================================
# Non-EPC / Statutory Exempt Structure Detection ('No Cert')
# ============================================================================

# Words that prove a phrase is actually naming a street or multi-let building rather than an exempt structure
# (e.g. '10 Monument Street', '12 Church Road', 'Church House', 'Temple Chambers', 'Chapel Court')
_STREET_OR_BLDG_FOLLOW_WORDS = (
    r"(?:street|road|lane|avenue|way|drive|close|walk|hill|grove|place|square|terrace|row|"
    r"mews|crescent|gardens|gate|court|house|buildings?|chambers|mansions|towers?|estate|"
    r"centre|plaza|point|heights|wharf|quays?|parade|arcade|approach|bridge|circus|parkway|"
    r"boulevard|highway|rise|chase|view|green|hall)\b"
)

# Tier 1: Point infrastructure, utilities, telecoms masts, street furniture, hoardings & bare-land prefixes.
# When one of these is the primary subject of the query (not tacked on after '&'/'including' to an office/shop),
# the asset NEVER requires an EPC, even if hosted at a building ('ATM, Unit 1, High St' or 'Substation, Units 1-4').
_EXEMPT_INFRASTRUCTURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Utility & Energy Infrastructure",
        (
            "electricity substation",
            "electric substation",
            "primary substation",
            "secondary substation",
            "distribution substation",
            "grid substation",
            "package substation",
            "kiosk substation",
            "electricity kiosk",
            "substation",
            "sub station",
            "transformer chamber",
            "transformer compound",
            "transformer station",
            "transformer",
            "switchgear",
            "hv compound",
            "lv compound",
            "battery energy storage",
            "battery storage",
            "bess compound",
            "solar farm",
            "solar park",
            "solar array",
            "pv array",
            "wind turbine",
            "wind farm",
            "generator compound",
            "standby generator",
            "electric vehicle charging",
            "ev charging",
            "ev charger",
            "charging station",
            "charging point",
            "charging bays",
            "charging bay",
            "gas governor",
            "pressure reduction station",
            "gas compound",
            "gas kiosk",
            "gas holder",
            "gasholder",
            "gas valve compound",
            "offtake station",
            "sewage pumping station",
            "water pumping station",
            "pumping station",
            "pump station",
            "sewage treatment",
            "sewage works",
            "wastewater treatment",
            "water tower",
            "service reservoir",
            "borehole",
            "attenuation pond",
            "balancing pond",
            "outfall",
            "weir",
            "sluice",
        ),
    ),
    (
        "Telecoms & Broadcast Infrastructure",
        (
            "telephone mast",
            "telecoms mast",
            "telecom mast",
            "telecommunications mast",
            "communications mast",
            "radio mast",
            "mobile mast",
            "phone mast",
            "lattice mast",
            "monopole",
            "mast site",
            "aerial mast",
            "transmitter mast",
            "broadcast mast",
            "telecoms site",
            "telecom site",
            "telecommunications site",
            "telecoms compound",
            "telecom compound",
            "telecoms apparatus",
            "telecoms equipment",
            "telecoms cabin",
            "telecoms cabinet",
            "equipment cabin",
            "cell site",
            "base station",
            "macrocell",
            "small cell",
            "rooftop telecoms",
            "rooftop mast",
            "rooftop aerial",
            "rooftop antenna",
            "antenna site",
            "aerial site",
            "repeater station",
            "fibre cabinet",
            "broadband cabinet",
            "street cabinet",
            "pcp cabinet",
            "telephone kiosk",
            "telephone box",
            "public phone box",
            "phone box",
            "payphone",
        ),
    ),
    (
        "Street Furniture, Shelters & ATMs",
        (
            "bus shelter",
            "bus stop",
            "tram shelter",
            "tram stop",
            "waiting shelter",
            "passenger shelter",
            "smoking shelter",
            "atm site",
            "automated teller",
            "cash machine",
            "hole in the wall",
            "atm",
            "inpost locker",
            "amazon locker",
            "parcel locker",
            "locker bank",
            "vending machine",
            "pillar box",
            "post box",
            "pay and display",
            "ticket machine",
            "parking meter",
            "public weighbridge",
            "weighbridge",
        ),
    ),
    (
        "Advertising Hoarding & Signage",
        (
            "advertising hoarding",
            "ad hoarding",
            "hoarding site",
            "hoarding at",
            "hoardings",
            "hoarding",
            "digital billboard",
            "billboard",
            "advertising station",
            "advertising rights",
            "advertising right",
            "advertising panel",
            "advertising screen",
            "led screen",
            "digital screen",
            "poster panel",
            "poster station",
            "totem sign",
            "gantry sign",
        ),
    ),
    (
        "Land, Open Space & Easements",
        (
            "land adjacent",
            "land adj",
            "land at",
            "land rear",
            "land rear_of",
            "land on",
            "land off",
            "land north",
            "land south",
            "land east",
            "land west",
            "land fronting",
            "land opposite",
            "land forming",
            "plot of land",
            "strip of land",
            "piece of land",
            "parcel of land",
            "area of land",
            "grazing land",
            "agricultural land",
            "arable land",
            "pasture land",
            "amenity land",
            "public open space",
            "open storage land",
            "open storage yard",
            "open storage",
            "storage land",
            "hardstanding",
            "grass verge",
            "highway verge",
            "allotments",
            "allotment",
            "woodland",
            "forestry",
            "paddock",
            "playing field",
            "recreation ground",
            "wayleave",
            "easement",
            "right of way",
            "bridleway",
            "airspace",
            "subsoil",
            "moorings",
            "mooring",
            "pontoon",
            "jetty",
            "slipway",
            "fishing rights",
            "shooting rights",
            "mineral rights",
        ),
    ),
)

# Tier 2: Parking, Garages & Ancillary Compounds (exempt when NOT bundled as an accessory to an
# explicit conditioned building demise like '2nd Floor Offices & 4 Car Spaces').
_EXEMPT_PARKING_AND_ANCILLARY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Parking & Vehicular Space",
        (
            "multi storey car park",
            "mscp",
            "surface car park",
            "underground car park",
            "basement car park",
            "decked car park",
            "car parking spaces",
            "car parking space",
            "car parking",
            "car park",
            "carpark",
            "park and ride",
            "lorry park",
            "hgv park",
            "coach park",
            "parking spaces",
            "parking space",
            "parking bays",
            "parking bay",
            "car spaces",
            "car space",
            "parking lot",
            "parking area",
            "parking compound",
            "parking deck",
            "lock up garages",
            "lock up garage",
            "lockup garage",
            "garage block",
            "battery of garages",
            "domestic garage",
            "single garage",
            "double garage",
            "en bloc garage",
            "cycle shelter",
            "cycle store",
            "cycle parking",
            "bike store",
            "bike shed",
            "trolley bay",
            "electric vehicle charging",
            "ev charging",
            "ev charger",
            "charging station",
            "charging point",
            "charging bays",
            "charging bay",
        ),
    ),
    (
        "Ancillary Unconditioned Compound / Store",
        (
            "bin store",
            "refuse store",
            "skip compound",
            "plant compound",
            "storage compound",
        ),
    ),
)

# Tier 3: Statutory Exempt Buildings under EPB Regulations 2012 (Places of Worship, Temporary/Portable,
# Low-Energy Agricultural Barns, Derelict/Demolished, Monuments) — only exempt when there is NO residential
# or commercial conversion indicator ('Flat 2, The Old Chapel' or 'Suite 1, Church House' ARE conditioned!).
_EXEMPT_STATUTORY_BUILDING_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Statutory Exempt — Place of Worship / Cemetery",
        (
            "place of worship",
            "parish church",
            "methodist church",
            "baptist church",
            "catholic church",
            "united reformed church",
            "evangelical church",
            "kingdom hall",
            "chapel of rest",
            "mosque",
            "masjid",
            "synagogue",
            "gurdwara",
            "mandir",
            "hindu temple",
            "buddhist temple",
            "crematorium",
            "cemetery",
            "burial ground",
            "graveyard",
            "church",
            "chapel",
            "temple",
        ),
    ),
    (
        "Statutory Exempt — Temporary, Portable or Container Structure",
        (
            "portakabin",
            "porta cabin",
            "portable cabin",
            "site cabin",
            "site hut",
            "welfare cabin",
            "welfare unit",
            "jackleg cabin",
            "shipping container",
            "storage container",
            "sea container",
            "iso container",
            "container store",
            "polytunnel",
            "marquee",
        ),
    ),
    (
        "Statutory Exempt — Agricultural / Low-Energy / Unconditioned Structure",
        (
            "agricultural barn",
            "hay barn",
            "dutch barn",
            "straw barn",
            "grain store",
            "silage clamp",
            "slurry store",
            "livestock shed",
            "cattle shed",
            "sheep shed",
            "poultry shed",
            "tractor shed",
            "beach hut",
            "bandstand",
            "war memorial",
            "monument",
            "derelict building",
            "derelict land",
            "demolished",
            "cleared site",
            "site of former",
        ),
    ),
)

_CONDITIONED_PRIMARY_WORDS = frozenset(
    {
        "office",
        "offices",
        "suite",
        "suites",
        "flat",
        "flats",
        "apartment",
        "apartments",
        "maisonette",
        "studio",
        "shop",
        "shops",
        "retail",
        "supermarket",
        "store",  # handled carefully (not 'bin store' / 'grain store' / 'cycle store')
        "warehouse",
        "workshop",
        "factory",
        "restaurant",
        "cafe",
        "pub",
        "public house",
        "hotel",
        "clinic",
        "surgery",
        "dental",
        "pharmacy",
        "nursery",
        "school",
        "college",
        "gym",
        "leisure centre",
        "cinema",
        "showroom",
    }
)

_MOTOR_TRADE_WORDS = frozenset(
    {
        "motor",
        "motors",
        "mot",
        "tyre",
        "tyres",
        "exhaust",
        "exhausts",
        "kwik fit",
        "halfords",
        "ats euromaster",
        "national tyres",
        "service station",
        "petrol",
        "filling station",
        "forecourt",
        "bodyshop",
        "body shop",
        "coachworks",
        "accident repair",
        "vehicle repair",
        "car sales",
        "dealership",
        "showroom",
    }
)

# Dedicated non-EPC operators (used ONLY when the address itself describes a generic non-building
# site/rooftop/compound/apparatus rather than a conditioned shop/office unit)
_NON_EPC_INFRA_TENANT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Utility & Energy Infrastructure", r"\b(?:uk power networks|ukpn|western power distribution|national grid electricity distribution|northern powergrid|sp energy networks|ssen|scottish and southern electricity|electricity north west|cadent gas|northern gas networks|wales and west utilities|sgn|southern gas networks)\b"),
    ("Telecoms & Broadcast Infrastructure", r"\b(?:cornerstone telecommunications|ctil|mobile broadband network|mbnl|cellnex|arqiva|wireless infrastructure group|freshwave)\b"),
    ("Advertising Hoarding & Signage", r"\b(?:jcdecaux|clear channel|ocean outdoor|global outdoor|primesight)\b"),
    ("Street Furniture, Shelters & ATMs", r"\b(?:inpost|notemachine|cardtronics|yourcash)\b"),
)


def detect_epc_exemption(
    address_lines: Sequence[Any],
    explicit_tenant: Any = None,
) -> tuple[bool, str | None, str | None]:
    """
    Identify UK portfolio structures/demises that do not require an EPC certificate
    (car parks, substations, telephone masts, bus shelters, ATMs, advertising hoardings,
    bare land/easements, places of worship, temporary cabins, agricultural barns, etc.).

    Includes strict false-positive guards so street names ('12 Church Street', '10 Monument St'),
    office/flat conversions ('Flat 2, The Old Chapel', 'Suite 1, Church House'), retail phone
    shops ('Unit 4, High St' + 'Vodafone'), motor-trade workshops ('Kwik Fit Garage'), and
    leases with ancillary parking ('2nd Floor Office & 4 Car Spaces') are NEVER misclassified.

    Returns
    -------
    tuple[bool, str | None, str | None]
        `(is_exempt, exempt_category, matched_trigger)`
    """
    clean_lines = [_clean_input_value(x) for x in address_lines]
    non_empty = [x for x in clean_lines if x]
    tenant_clean = _clean_input_value(explicit_tenant)

    if not non_empty:
        return (False, None, None)

    raw_joined = ", ".join(non_empty)
    # Strip UK postcodes before checking patterns
    no_pc = UK_POSTCODE_RE.sub(" ", raw_joined)

    # 1. Remove explicit ancillary inclusions ('inc 4 car spaces', 'including parking & yard',
    #    'together with 2 parking bays', 'with car parking') so primary building leases stay intact!
    ancillary_inc_re = re.compile(
        r"\((?:inc\.?|including|with|together\s+with|plus)\b[^)]*\)"
        r"|\b(?:inc\.?|including|together\s+with)\s+[^,;]+",
        re.IGNORECASE,
    )
    stripped_inc = ancillary_inc_re.sub(" ", no_pc)

    # Split into ordered clauses across lines and commas/semicolons
    raw_clauses = [c.strip() for c in re.split(r"[,;]+", stripped_inc) if c.strip()]
    norm_clauses: list[str] = []
    for rc in raw_clauses:
        s = _normalize_apostrophes_and_symbols(rc.lower())
        s = s.replace("-", " ")
        s = re.sub(r"[^\w\s]", " ", s)
        s = _disambiguate_st_and_abbrevs(s)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            norm_clauses.append(s)

    if not norm_clauses:
        return (False, None, None)

    full_norm = " , ".join(norm_clauses)
    tenant_norm = re.sub(r"[^\w\s]", " ", _normalize_apostrophes_and_symbols(tenant_clean.lower()).replace("-", " "))
    tenant_norm = re.sub(r"\s+", " ", tenant_norm).strip()

    # Helper: check if the FIRST / primary demise before 'and' is already a conditioned building
    # (e.g. '2nd floor offices and 6 car parking spaces', 'shop and atm', 'unit 4 and yard')
    first_clause = norm_clauses[0]
    lead_before_and = first_clause.split(" and ")[0].strip()

    def _has_conditioned_demise(text_seg: str) -> bool:
        # Strip estate/park phrases ('retail park', 'office park', 'shopping centre', 'business park')
        # so location names never masquerade as conditioned unit demises!
        cleaned_seg = text_seg
        for ep in ESTATE_PARK_PHRASES:
            cleaned_seg = cleaned_seg.replace(ep, " ")
        # Remove non-conditioned compound '* store' phrases before checking 'store'
        cleaned_seg = re.sub(
            r"\b(?:bin|refuse|cycle|bike|grain|slurry|container|cold)\s+store\b",
            " ",
            cleaned_seg,
        )
        for cw in _CONDITIONED_PRIMARY_WORDS:
            if cw in {"store", "retail"}:
                continue
            if re.search(rf"\b{re.escape(cw)}\b", cleaned_seg):
                return True
        if re.search(r"\bretail\s+(?:units?|shops?|stores?|warehouses?|premises)\b", cleaned_seg):
            return True
        return False

    lead_is_conditioned = _has_conditioned_demise(lead_before_and) or bool(
        re.match(r"^(?:units?|plots?)\s+\d", lead_before_and)
        and " and " in first_clause
        and not any(
            k in lead_before_and
            for k in ("substation", "mast", "car park", "parking", "atm", "hoarding", "shelter", "transformer")
        )
    )

    def _match_phrase_safely(clause_text: str, phrase: str) -> bool:
        # Match whole words, and ensure the matched phrase is NOT immediately followed by a
        # street thoroughfare or multi-let building suffix (protects '10 Monument Street',
        # '12 Church Road', 'Church House', 'Temple Chambers', '4 Mooring Way', 'Car Park Road')!
        pat = rf"\b{re.escape(phrase)}\b(?!\s+{_STREET_OR_BLDG_FOLLOW_WORDS})"
        return bool(re.search(pat, clause_text))

    # ------------------------------------------------------------------
    # Check Tier 1: Point Infrastructure, Utilities, Telecoms, Shelters, Hoardings & Land
    # ------------------------------------------------------------------
    # Evaluate on primary clauses (not trailing 'and <exempt>' attached to a conditioned office/shop)
    clauses_for_tier1 = [lead_before_and] + norm_clauses[1:] if lead_is_conditioned else norm_clauses
    for idx_c, cl in enumerate(clauses_for_tier1):
        if lead_is_conditioned and idx_c == 0:
            continue
        for category, phrases in _EXEMPT_INFRASTRUCTURE_RULES:
            for ph in phrases:
                # Extra guard for 'land ...': only trigger if 'land ...' is at the start of the clause
                if ph.startswith("land ") and not cl.startswith(ph):
                    continue
                if _match_phrase_safely(cl, ph):
                    # Guard against 'Substation Road' or 'Station' false hits (already handled by phrase + lookahead)
                    return (True, category, ph)

    # ------------------------------------------------------------------
    # Check Tier 2: Parking, Lock-Up Garages & Unconditioned Compounds
    # ------------------------------------------------------------------
    any_conditioned_anywhere = any(_has_conditioned_demise(c.split(" and ")[0]) for c in norm_clauses)
    if not lead_is_conditioned and not any_conditioned_anywhere:
        for cl in norm_clauses:
            for category, phrases in _EXEMPT_PARKING_AND_ANCILLARY_RULES:
                for ph in phrases:
                    if _match_phrase_safely(cl, ph):
                        return (True, category, ph)

            # Standalone 'garage' / 'garages' (e.g. 'Garage 4', 'Garages 1-6', 'Garage rear of 10 High St')
            # Guard against commercial motor-trade workshops/showrooms/petrol stations!
            if re.search(rf"\bgarages?\b(?!\s+{_STREET_OR_BLDG_FOLLOW_WORDS})", cl):
                combined_check = f"{full_norm} {tenant_norm}"
                if not any(mw in combined_check for mw in _MOTOR_TRADE_WORDS):
                    return (True, "Parking & Vehicular Space", "garage")

    # ------------------------------------------------------------------
    # Check Tier 3: Statutory Exempt Buildings (Worship, Cabins, Containers, Agricultural, Derelict)
    # ------------------------------------------------------------------
    has_conversion_clue = bool(
        re.search(r"\b(?:old|former|converted|conversion|apartments?|flats?|suites?|offices?|shops?|studios?)\b", full_norm)
    )
    if not lead_is_conditioned and not any_conditioned_anywhere and not has_conversion_clue:
        for cl in norm_clauses:
            for category, phrases in _EXEMPT_STATUTORY_BUILDING_RULES:
                for ph in phrases:
                    if _match_phrase_safely(cl, ph):
                        return (True, category, ph)

    # ------------------------------------------------------------------
    # Check Tier 4: Generic Non-Building Site/Rooftop/Compound + Dedicated Infra Operator Tenant
    # (e.g. ['Rooftop Site', 'Apex House', 'Cornerstone Telecommunications Infrastructure Ltd']
    #  or ['Site 04', 'High Street', 'JCDecaux UK Ltd'] — while NEVER flagging ['Unit 4', 'High St', 'Vodafone'])
    # ------------------------------------------------------------------
    if tenant_norm and not lead_is_conditioned and not any_conditioned_anywhere:
        has_generic_infra_locus = bool(
            re.search(
                r"\b(?:rooftop|roof\s+space|roof\s+site|compound|apparatus|installation|cabinet|kiosk|site|panel|shelter|locker|chamber|governor)\b",
                first_clause,
            )
        ) and not re.search(r"\b(?:units?|shops?|offices?|suites?|flats?|apartments?|floors?)\b", first_clause)
        if has_generic_infra_locus:
            for category, ten_pat in _NON_EPC_INFRA_TENANT_PATTERNS:
                m_ten = re.search(ten_pat, tenant_norm)
                if m_ten:
                    return (True, category, f"{first_clause} ({m_ten.group(0)})")

    return (False, None, None)


# ============================================================================
# Floor & Sub-Unit Clause Parsers
# ============================================================================

_FLOOR_RANGE_RE = re.compile(
    r"\b(?:floors?|flrs?|levels?)\s+(\d{1,2})\s*(?:-|to|and)\s*(\d{1,2})\b"
)
_ORD_TOKEN_PATTERN = "|".join(sorted(ORDINAL_TO_INT.keys(), key=len, reverse=True))
_MULTI_ORD_FLOOR_RE = re.compile(
    rf"\b({_ORD_TOKEN_PATTERN})\s*(?:,|and|&|-|to)\s*({_ORD_TOKEN_PATTERN})\s+(?:floors?|flrs?|levels?)\b"
)
_SINGLE_ORD_FLOOR_RE = re.compile(
    rf"\b(?:(part|pt)\s+)?({_ORD_TOKEN_PATTERN})\s+(?:floors?|flrs?|levels?)\b"
)
_PREFIX_FLOOR_RE = re.compile(
    r"\b(?:floor|flr|level)\s+(\d{1,2}|ground|gnd|grd|first|second|third|fourth|fifth)\b"
)


def _extract_floors_from_clause(clause: str, parsed: ParsedAddress) -> str:
    """Extract floor specifications into `parsed.floors` and strip floor phrases from clause."""
    work = f" {clause} "

    # 1. Special multi-word floors FIRST ('lower ground floor', 'sub basement', 'upper ground')
    for phrase in sorted(SPECIAL_FLOOR_MAP.keys(), key=len, reverse=True):
        canon = SPECIAL_FLOOR_MAP[phrase]
        # Match '<phrase> floor(s)' or standalone 'basement'/'mezzanine'/'lgf'/'penthouse'
        if phrase in ("basement", "bsmt", "bst", "cellar", "mezzanine", "mezz", "penthouse", "lgf", "ugf", "sub basement", "sub-basement", "lower ground", "upper ground"):
            pat = rf"\b(?:(part|pt)\s+)?{re.escape(phrase)}(?:\s+(?:floors?|flrs?|levels?))?\b"
        else:
            pat = rf"\b(?:(part|pt)\s+)?{re.escape(phrase)}\s+(?:floors?|flrs?|levels?)\b"
        m = re.search(pat, work)
        if m:
            parsed.floors.add(canon)
            if m.group(1):
                parsed.floor_modifiers.add("part")
            work = re.sub(pat, " ", work)

    # Check compound 'ground and basement' / 'ground and first floor'
    m_gb = re.search(r"\b(ground|gnd|grd)\s+and\s+(basement|bsmt|lower_ground)\b", work)
    if m_gb:
        parsed.floors.add("0")
        parsed.floors.add("basement")
        work = re.sub(r"\b(ground|gnd|grd)\s+and\s+(basement|bsmt|lower_ground)\b", " ", work)

    # 2. Numeric floor range: 'floors 1-3'
    for m in _FLOOR_RANGE_RE.finditer(work):
        f1, f2 = int(m.group(1)), int(m.group(2))
        if 0 <= f1 <= f2 and (f2 - f1) <= 20:
            for f in range(f1, f2 + 1):
                parsed.floors.add(str(f))
    work = _FLOOR_RANGE_RE.sub(" ", work)

    # 3. Multi-ordinal floors: 'ground and first floor', '1st & 2nd floors'
    for m in _MULTI_ORD_FLOOR_RE.finditer(work):
        o1 = ORDINAL_TO_INT[m.group(1)]
        o2 = ORDINAL_TO_INT[m.group(2)]
        sep_slice = work[m.start() : m.end()]
        if ("-" in sep_slice or " to " in sep_slice) and o1 < o2 and (o2 - o1) <= 15:
            for f in range(o1, o2 + 1):
                parsed.floors.add(str(f))
        else:
            parsed.floors.add(str(o1))
            parsed.floors.add(str(o2))
    work = _MULTI_ORD_FLOOR_RE.sub(" ", work)

    # 4. Single ordinal floor: 'ground floor', 'part 3rd floor', '1st floor'
    for m in _SINGLE_ORD_FLOOR_RE.finditer(work):
        if m.group(1):
            parsed.floor_modifiers.add("part")
        parsed.floors.add(str(ORDINAL_TO_INT[m.group(2)]))
    work = _SINGLE_ORD_FLOOR_RE.sub(" ", work)

    # 5. Prefix floor: 'floor 3', 'level 2'
    for m in _PREFIX_FLOOR_RE.finditer(work):
        tok = m.group(1)
        val = ORDINAL_TO_INT.get(tok, int(tok) if tok.isdigit() else None)
        if val is not None:
            parsed.floors.add(str(val))
    work = _PREFIX_FLOOR_RE.sub(" ", work)

    # 6. Standalone 'gf' token
    if re.search(r"\bgf\b", work):
        parsed.floors.add("0")
        work = re.sub(r"\bgf\b", " ", work)

    # Capture directional wing modifiers left adjacent to removed floor ('north', 'south', 'east', 'west', 'rear', 'front')
    for mod in ("north", "south", "east", "west", "rear", "front", "part"):
        if parsed.floors and re.fullmatch(rf"\s*{mod}(?:\s+wing|\s+suite)?\s*", work):
            parsed.floor_modifiers.add(mod)

    return re.sub(r"\s+", " ", work).strip()


_DESIGNATOR_KEYS = "|".join(sorted(UNIT_CATEGORY_BY_DESIGNATOR.keys(), key=len, reverse=True))

# Designator + ID (e.g., 'Units 1-4', 'Unit 4B', 'Flat 2', 'Suite A', 'Units 1, 2 and 3', 'Block C')
_UNIT_WITH_ID_RE = re.compile(
    rf"\b({_DESIGNATOR_KEYS})(?:\s+(?:no\.?|number|#)\s*|\s*#\s*|\s+)"
    r"((?:\d{1,4}[a-z]?|[a-z]\d{0,3}|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"(?:\s*(?:-|to|/|and|,)\s*(?:\d{1,4}[a-z]?|[a-z]\d{0,3}))*)\b"
)

# Suffix designator (e.g., '2A Flat' is rare, but '3B Studio' or 'G1 Unit') -> handled carefully
# Standalone designator WITHOUT ID (e.g. 'First Floor Flat', 'Ground Floor Shop', 'The Studio', 'The Barn')
_BARE_DESIGNATOR_RE = re.compile(rf"^(?:the\s+)?({_DESIGNATOR_KEYS})$")


def _extract_units_from_clause(clause: str, parsed: ParsedAddress) -> str:
    """Extract sub-units & structural blocks from a single comma-delimited clause."""
    work = clause.strip()
    if not work:
        return ""

    # Guard: do NOT treat 'Unit' or 'Court' or 'Park' inside a thoroughfare/building name improperly.
    # For example, 'Flat 2, 12 High Street' has comma split so clause 1 is 'flat 2' and clause 2 is '12 high street'.
    # What if there was NO comma: 'Flat 2 12 High Street' or 'Unit 4 Acorn Industrial Estate'?
    # Notice in 'Unit 4 Acorn Industrial Estate', _UNIT_WITH_ID_RE would match 'unit 4', leaving 'acorn industrial estate'!
    # Wait: what if clause is 'Shop at 12 High Street' or 'Flat above 12 High Street'?
    m_prep = re.match(
        rf"^({_DESIGNATOR_KEYS})\s+(?:at|above|over|under|rear\s+of|rear_of)\s+(.+)$",
        work,
    )
    if m_prep:
        desig = m_prep.group(1)
        cat, grp = UNIT_CATEGORY_BY_DESIGNATOR[desig]
        target_list = parsed.structures if cat == "structure" else parsed.units
        target_list.append(UnitSpec(cat, grp, desig, (), is_range=False))
        work = m_prep.group(2).strip()

    # Handle compact 'U4' / 'U4B' at start of clause
    m_u_compact = re.match(r"^u(\d{1,3}[a-z]?)\b(.*)$", work)
    if m_u_compact:
        uid = m_u_compact.group(1)
        parsed.units.append(UnitSpec("commercial", "unit", "unit", (uid,), is_range=False))
        work = m_u_compact.group(2).strip(" ,-")

    # Iteratively extract '<designator> <id_expr>' matches, being careful NOT to consume
    # a street number when the designator has NO unit ID!
    # E.g. 'flat 12 high street' -> here '12' IS immediately followed by 'high street'!
    # Wait: is 'Flat 12 High Street' (no comma) Flat #12 on High Street, or a flat at #12 High Street?
    # Let's check: 'Flat 2 12 High Street' has TWO numbers ('2' and '12') -> '2' is flat, '12' is street!
    # What if 'Shop 12 High Street' vs 'Unit 4 Station Road'?
    # On High Streets, '12 High Street' is the street number, whereas 'Unit 4 Station Road' -> 'Unit 4' on Station Road!
    matches_to_cut: list[tuple[int, int]] = []
    for m in _UNIT_WITH_ID_RE.finditer(work):
        desig = m.group(1)
        id_expr = m.group(2).strip()
        tail = work[m.end() :].strip()

        # Guard 1: If id_expr is a common word ('and', 'at', 'in', 'on', 'of', 'the', 'to') that matched single-letter rule, skip!
        if id_expr in {"a", "i"} and tail and not re.match(r"^(?:,|$)", tail):
            #Wait: 'Unit A Acorn Park' -> 'a' IS a real unit ID! When is 'a' an article?
            # 'Shop a ...' nobody writes 'Shop a' as an article, EXCEPT 'Flat a ...' = Flat A!
            # Only skip if id_expr is >1 char word, which regex already prevents unless 'one'..'ten'.
            pass

        # Guard 2: 'Block Court' or 'Office Park' or 'Retail Park' or 'Business Suite' ->
        # Check if id_expr is actually the start of a thoroughfare/estate word (impossible since id_expr is digits or 1 letter + digits)
        # UNLESS id_expr is a single letter followed immediately by no space (prevented by \b)!
        # What if tail starts with a thoroughfare word AND desig is 'shop'/'flat' with a single number, e.g. 'Shop 12 High Street'?
        #Wait: in UK addresses without commas, 'Unit 4 Station Road' means Unit 4 on Station Road,
        # and 'Flat 2 High Street' means Flat 2 on High Street ( whereas 'Flat, 12 High Street' had a comma!).
        ids, is_rng = _expand_unit_id_expr(id_expr)
        if not ids:
            continue

        cat, grp = UNIT_CATEGORY_BY_DESIGNATOR[desig]
        target_list = parsed.structures if cat == "structure" else parsed.units
        target_list.append(UnitSpec(cat, grp, desig, ids, is_range=is_rng))
        matches_to_cut.append((m.start(), m.end()))

    if matches_to_cut:
        pieces = []
        last = 0
        for s_idx, e_idx in matches_to_cut:
            pieces.append(work[last:s_idx])
            last = e_idx
        pieces.append(work[last:])
        work = re.sub(r"\s+", " ", " ".join(pieces)).strip(" ,;-")

    # Check if remaining clause is a bare unit designator ('flat', 'shop', 'studio', 'maisonette', 'kiosk', 'workshop')
    m_bare = _BARE_DESIGNATOR_RE.fullmatch(work)
    if m_bare:
        desig = m_bare.group(1)
        cat, grp = UNIT_CATEGORY_BY_DESIGNATOR[desig]
        target_list = parsed.structures if cat == "structure" else parsed.units
        target_list.append(UnitSpec(cat, grp, desig, (), is_range=False))
        return ""

    return work


# ============================================================================
# Full UK Address & Occupier Decomposition Pipeline
# ============================================================================


def parse_address_record(
    address_lines: Sequence[Any],
    *,
    explicit_tenant: Any = None,
    is_query: bool = False,
    town_hint: str | None = None,
) -> ParsedAddress:
    """
    Decompose messy UK address lines (and optional explicit tenant) into a canonical
    `ParsedAddress` object.
    """
    clean_lines = [_clean_input_value(x) for x in address_lines]
    non_empty_lines = [x for x in clean_lines if x]
    parsed = ParsedAddress(raw_parts=tuple(non_empty_lines))

    raw_joined = ", ".join(non_empty_lines)
    if not raw_joined and not _clean_input_value(explicit_tenant):
        return parsed

    # 1. Extract and strip any UK Postcodes embedded in the address lines
    pc_matches = UK_POSTCODE_RE.findall(raw_joined)
    if pc_matches:
        parsed.postcode = re.sub(r"\s+", " ", pc_matches[-1].upper()).strip()

    # Prepare town hint set if provided
    extra_localities: set[str] = set()
    if town_hint:
        th = _clean_input_value(town_hint).lower()
        if th:
            extra_localities.add(th)

    # Track slot-0 ('Unit Name') separately on queries to detect bare unit IDs safely
    slot0_raw = clean_lines[0] if (is_query and len(clean_lines) >= 1) else ""
    slot1_raw = clean_lines[1] if (is_query and len(clean_lines) >= 2) else ""

    # Pre-extract parenthetical '(formerly ...)' or '(t/a ...)' or '(Unit 4)'
    expanded_clauses: list[tuple[int, str]] = []  # (line_idx, clause_text)
    for line_idx, line in enumerate(clean_lines):
        if not line:
            continue
        # Remove UK postcodes and ancillary '(including ...)' / '(inc ...)' clauses
        line_wo_pc = UK_POSTCODE_RE.sub(" ", line)
        line_wo_pc = re.sub(
            r"\((?:inc\.?|including|together\s+with)\b[^)]*\)",
            " ",
            line_wo_pc,
            flags=re.IGNORECASE,
        )

        # Extract parenthetical remarks into separate sub-clauses rather than losing or merging them
        paren_items = re.findall(r"\(([^)]+)\)", line_wo_pc)
        line_wo_parens = re.sub(r"\([^)]*\)", ", ", line_wo_pc)

        sub_parts = [p.strip() for p in re.split(r"[,;]+", line_wo_parens) if p.strip()]
        for sp in sub_parts:
            expanded_clauses.append((line_idx, sp))
        for pi in paren_items:
            for sp in [p.strip() for p in re.split(r"[,;]+", pi) if p.strip()]:
                expanded_clauses.append((line_idx, sp))

    residual_clauses: list[tuple[int, str]] = []

    for line_idx, raw_clause in expanded_clauses:
        c = _normalize_apostrophes_and_symbols(raw_clause)
        c = re.sub(r"[^\w\s/-]", " ", c)
        c = re.sub(r"\s+", " ", c).strip(" -/")
        if not c:
            continue

        c_norm = _disambiguate_st_and_abbrevs(c)

        # Handle 'formerly ...' or 'trading_as ...' or 'care_of ...'
        if "formerly " in c_norm or c_norm.startswith("ex "):
            parts = re.split(r"\b(?:formerly|ex)\b", c_norm, maxsplit=1)
            before, after = parts[0].strip(), parts[1].strip()
            if after:
                parsed.inferred_occupiers.append(after)
            c_norm = before
            if not c_norm:
                continue

        if "trading_as" in c_norm:
            parts = c_norm.split("trading_as", 1)
            for p in parts:
                if p.strip():
                    parsed.inferred_occupiers.append(p.strip())
            continue

        if "care_of" in c_norm:
            parts = c_norm.split("care_of", 1)
            c_norm = parts[0].strip()
            if not c_norm:
                continue

        # Split ' - ' separator often used in EPCs: 'Co-op Food - 14-16 High Street'
        # (Note: 'co-op' has no spaces around '-', whereas ' - ' has spaces!)
        if " - " in c_norm:
            hyphen_parts = [hp.strip() for hp in c_norm.split(" - ") if hp.strip()]
        else:
            hyphen_parts = [c_norm]

        for hp in hyphen_parts:
            # Extract floors
            after_floors = _extract_floors_from_clause(hp, parsed)
            if not after_floors:
                continue
            # Extract explicit units/blocks
            after_units = _extract_units_from_clause(after_floors, parsed)
            if not after_units:
                continue
            residual_clauses.append((line_idx, after_units))

    # Now classify residual clauses into: localities, estates/parks, thoroughfares (+ street numbers),
    # buildings, bare numbers/units, or inferred occupiers!
    bare_number_clauses: list[tuple[int, str]] = []

    for idx_pos, (line_idx, clause) in enumerate(residual_clauses):
        tokens = clause.split()
        if not tokens:
            continue

        # 1. Check if standalone UK Town / County / Locality (ONLY when whole clause is a locality,
        # never stripping 'London Road' or 'York House'!)
        if clause in UK_LOCALITIES or clause in extra_localities:
            parsed.localities.append(clause)
            continue

        # 2. Check if clause is a bare number / unit code (e.g. '12', '4b', '12-14', 'a')
        if re.fullmatch(
            r"(?:\d{1,4}[a-z]?|[a-z])(?:\s*(?:-|to|/|and)\s*\d{1,4}[a-z]?)?",
            clause,
        ):
            bare_number_clauses.append((line_idx, clause))
            continue

        # 3. Check if clause contains an Estate / Park / Shopping Centre phrase
        is_estate = any(ep in clause for ep in ESTATE_PARK_PHRASES) or (
            tokens[-1] in {"estate", "park", "centre", "industrial"}
            and not any(_is_thoroughfare_word(t) for t in tokens[:-1])
        )
        # Wait: 'Hyde Park' or 'Regents Park' vs 'Acorn Park' -> classifying 'park'/'estate'/'centre'
        # as estate/complex works cleanly, and what if it starts with a number: '4 Acorn Park'?
        m_lead_num = re.match(
            r"^((?:\d{1,4}[a-z]?|one|two|three|four|five|six|seven|eight|nine|ten)"
            r"(?:\s*(?:-|to|/|and)\s*\d{1,4}[a-z]?)?)\s+(.+)$",
            clause,
        )

        if is_estate:
            if m_lead_num:
                num_part, rest_estate = m_lead_num.group(1), m_lead_num.group(2).strip()
                if not UK_ROUTE_RE.fullmatch(num_part):
                    ns = _expand_street_number_expr(num_part, consecutive_street=True)
                    if ns:
                        parsed.street_numbers.append(ns)
                    parsed.estates.append(rest_estate)
                    continue
            parsed.estates.append(clause)
            continue

        # 4. Check if clause ends with or contains a UK Thoroughfare
        has_thoroughfare = any(_is_thoroughfare_word(t) for t in tokens)
        # Exclude false thoroughfare when last word is 'court'/'yard'/'buildings'/'place' ONLY if
        # there's ANOTHER explicit thoroughfare in another clause (e.g. 'Apex Court, 12 High Street' ->
        # 'Apex Court' is a building, 'High Street' is the thoroughfare!).
        other_has_strong_street = any(
            j != idx_pos
            and any(
                t in {"street", "road", "lane", "avenue", "drive", "way", "close", "crescent", "boulevard", "highway", "walk", "hill", "grove"}
                or (len(t) >= 6 and t.endswith("gate"))
                for t in rc.split()
            )
            for j, (_, rc) in enumerate(residual_clauses)
        )

        ambiguous_building_or_street = tokens[-1] in {"court", "buildings", "wharf", "mansions", "villas", "chambers"}
        if has_thoroughfare and not (ambiguous_building_or_street and other_has_strong_street and not m_lead_num):
            # Strip leading 'off ' / 'rear_of ' / 'adjacent ' / UK route number ('a4 bath road')
            work_st = re.sub(r"^(?:off|rear_of|adjacent(?:\s+to)?|near|corner\s+of)\s+", "", clause).strip()
            st_tokens = work_st.split()
            if st_tokens and UK_ROUTE_RE.fullmatch(st_tokens[0]) and len(st_tokens) >= 2:
                work_st = " ".join(st_tokens[1:])

            consecutive_flag = any(t in CONSECUTIVE_THOROUGHFARE_WORDS for t in work_st.split())
            m_num = re.match(
                r"^((?:\d{1,4}[a-z]?|one|two|three|four|five|six|seven|eight|nine|ten)"
                r"(?:\s*(?:-|to|/|and)\s*\d{1,4}[a-z]?)?)\s+(.+)$",
                work_st,
            )
            if m_num and not UK_ROUTE_RE.fullmatch(m_num.group(1)):
                ns = _expand_street_number_expr(m_num.group(1), consecutive_street=consecutive_flag)
                street_body = m_num.group(2).strip()
                # Check if street_body has a trailing town glued without comma (e.g. '12 high street london')
                sb_toks = street_body.split()
                if (
                    len(sb_toks) >= 3
                    and sb_toks[-1] in (UK_LOCALITIES | extra_localities)
                    and _is_thoroughfare_word(sb_toks[-2])
                ):
                    parsed.localities.append(sb_toks[-1])
                    street_body = " ".join(sb_toks[:-1])
                if ns:
                    parsed.street_numbers.append(ns)
                parsed.thoroughfares.append(street_body)
            else:
                sb_toks = work_st.split()
                if (
                    len(sb_toks) >= 3
                    and sb_toks[-1] in (UK_LOCALITIES | extra_localities)
                    and _is_thoroughfare_word(sb_toks[-2])
                ):
                    parsed.localities.append(sb_toks[-1])
                    work_st = " ".join(sb_toks[:-1])
                parsed.thoroughfares.append(work_st)
            continue

        # 5. Check if clause is a Building Name (e.g. 'Apex House', 'Victoria Chambers', 'Two Snowhill')
        if tokens[-1] in BUILDING_SUFFIX_WORDS or (
            len(tokens) >= 2 and tokens[0] == "the" and tokens[-1] in BUILDING_SUFFIX_WORDS
        ):
            # Convert leading number word in building names like 'Two Snowhill' -> normalized via token compare
            parsed.buildings.append(clause)
            continue

        # 6. Check if clause has a leading number + obscure/rural street/place name (e.g. '14 Meadowbank', '2 Snowhill')
        if m_lead_num and not UK_ROUTE_RE.fullmatch(m_lead_num.group(1)):
            ns = _expand_street_number_expr(m_lead_num.group(1), consecutive_street=False)
            place_body = m_lead_num.group(2).strip()
            # Ensure place_body isn't corporate boilerplate (e.g. '365 Retail Ltd')
            if ns and not any(w in CORPORATE_INDICATOR_WORDS for w in place_body.split()):
                parsed.street_numbers.append(ns)
                parsed.thoroughfares.append(place_body)
                continue

        # 7. Check if clause looks like an Occupier / Company / Brand in addr1
        has_corp_word = any(w in CORPORATE_INDICATOR_WORDS for w in tokens)
        if has_corp_word:
            parsed.inferred_occupiers.append(clause)
            continue

        # If this is the FIRST clause of a candidate (or query) and later clauses already provide
        # a street/estate/building, a leading proper name ('Greggs', 'Costa Coffee', 'Boots The Chemist',
        # 'The Red Lion') may be EITHER a building/venue name OR an occupier name!
        # Recording it in unclassified_segments AND inferred_occupiers lets it match either a
        # building name OR a tenant name without falsely penalizing structural matches!
        parsed.unclassified_segments.append(clause)
        if line_idx == 0:
            parsed.inferred_occupiers.append(clause)

    # Resolve bare_number_clauses (e.g. query = ['12', 'High Street', ''] vs ['4B', '12 High Street', '']
    # vs ['4', 'Acorn Industrial Estate', ''])
    for line_idx, b_clause in bare_number_clauses:
        if parsed.street_numbers:
            # Street ALREADY has its own street number (e.g. '12 High Street'), so a bare '4' or '4b'
            # in another clause is unambiguously a sub-unit identifier!
            ids, is_rng = _expand_unit_id_expr(b_clause)
            if ids:
                parsed.units.append(
                    UnitSpec("commercial", "unit", "unit", ids, is_range=is_rng, is_bare_inferred=True)
                )
        elif parsed.thoroughfares and not parsed.estates and not re.fullmatch(r"[a-z]", b_clause):
            # e.g. ['12', 'High Street'] or '12, High Street' -> street number 12 on High Street!
            consecutive_flag = any(
                t in CONSECUTIVE_THOROUGHFARE_WORDS
                for st in parsed.thoroughfares
                for t in st.split()
            )
            ns = _expand_street_number_expr(b_clause, consecutive_street=consecutive_flag)
            if ns:
                parsed.street_numbers.append(ns)
        else:
            # e.g. ['4B', 'Acorn Industrial Estate'] or ['A', 'High Street'] -> unit ID!
            ids, is_rng = _expand_unit_id_expr(b_clause)
            if ids:
                parsed.units.append(
                    UnitSpec("commercial", "unit", "unit", ids, is_range=is_rng, is_bare_inferred=True)
                )

    # Handle explicit tenant if provided
    clean_tenant = _clean_input_value(explicit_tenant)
    if clean_tenant:
        parsed.explicit_tenant = clean_tenant

    # Detect non-EPC / statutory exempt structures on query records
    if is_query:
        is_ex, ex_cat, ex_trig = detect_epc_exemption(address_lines, explicit_tenant=explicit_tenant)
        parsed.is_epc_exempt = is_ex
        parsed.exempt_category = ex_cat
        parsed.exempt_trigger = ex_trig

    # Build canonical token sets (normalizing number words like 'two' -> '2' for token equivalence)
    struct_parts: list[str] = []
    for f in sorted(parsed.floors):
        struct_parts.append(f"floor_{f}")
    for u in parsed.units:
        struct_parts.append(u.synonym_group)
        struct_parts.extend(u.ids)
    for st_blk in parsed.structures:
        struct_parts.append(st_blk.synonym_group)
        struct_parts.extend(st_blk.ids)
    for ns in parsed.street_numbers:
        struct_parts.append(ns.raw)
    struct_parts.extend(parsed.thoroughfares)
    struct_parts.extend(parsed.estates)
    struct_parts.extend(parsed.buildings)

    def _canon_toks(items: Iterable[str]) -> set[str]:
        out: set[str] = set()
        for item in items:
            for tok in item.split():
                t = NUMBER_WORDS.get(tok, tok).strip(".,;:-")
                if t and t not in {"the", "and", "of", "at"}:
                    out.add(t)
        return out

    parsed.core_structural_tokens = _canon_toks(struct_parts)
    parsed.all_address_tokens = _canon_toks(struct_parts + parsed.unclassified_segments)

    norm_pieces = [
        *(f"floor {f}" for f in sorted(parsed.floors)),
        *(f"{u.synonym_group} {'-'.join(u.ids)}".strip() for u in parsed.units),
        *(f"{s.synonym_group} {'-'.join(s.ids)}".strip() for s in parsed.structures),
        *(ns.raw for ns in parsed.street_numbers),
        *parsed.buildings,
        *parsed.estates,
        *parsed.thoroughfares,
        *parsed.unclassified_segments,
    ]
    parsed.normalized_full = " ".join(p for p in norm_pieces if p).strip()

    return parsed


# ============================================================================
# Component Comparison & Scoring Helpers
# ============================================================================


def _best_phrase_similarity(
    list_a: list[str], list_b: list[str], *, force_pure: bool = False
) -> tuple[float, str, str]:
    """Compare two lists of normalized phrases (thoroughfares, estates, buildings)."""
    if not list_a or not list_b:
        return (0.0, "", "")

    def _norm_num_words(s: str) -> str:
        return " ".join(NUMBER_WORDS.get(t, t) for t in s.split())

    best = 0.0
    best_a, best_b = list_a[0], list_b[0]
    for a in list_a:
        na = _norm_num_words(a)
        for b in list_b:
            nb = _norm_num_words(b)
            if na == nb:
                return (1.0, a, b)
            # Combine ratio, Jaro-Winkler, and token-sort for typo resilience
            r = string_ratio(na, nb, force_pure=force_pure)
            ts = token_sort_sim(na, nb, force_pure=force_pure)
            jw = jaro_winkler_sim(na, nb, force_pure=force_pure)
            tset = token_set_sim(na, nb, force_pure=force_pure)
            sim = max(
                r,
                ts,
                0.88 * tset if len(na.split()) != len(nb.split()) else 0.0,
                0.92 * jw if r > 0.7 else 0.0,
            )
            if sim > best:
                best = sim
                best_a, best_b = a, b
    return (best, best_a, best_b)


def _compare_street_numbers(
    q_nums: list[NumberSpec], c_nums: list[NumberSpec]
) -> tuple[str, float, str]:
    """
    Compare street number specs.
    Returns (status, score_0_to_1, explanation):
      status in {'exact', 'range_contained', 'conflict_suffix', 'conflict_number', 'missing_both', 'missing_one'}
    """
    if not q_nums and not c_nums:
        return ("missing_both", 0.0, "")
    if not q_nums or not c_nums:
        return ("missing_one", 0.0, "")

    q_raws = [n.raw for n in q_nums]
    c_raws = [n.raw for n in c_nums]
    if set(q_raws) == set(c_raws):
        return ("exact", 1.0, f"Exact street number match ('{', '.join(q_raws)}')")

    q_members = {m for n in q_nums for m in n.members}
    c_members = {m for n in c_nums for m in c_nums[0].members}
    c_members = {m for n in c_nums for m in n.members}

    overlap = q_members & c_members
    if overlap:
        if q_members == c_members:
            return ("exact", 1.0, f"Exact street number match ('{', '.join(q_raws)}')")
        if q_members.issubset(c_members):
            return (
                "range_contained",
                0.86,
                f"Queried street number '{', '.join(q_raws)}' is contained within candidate range '{', '.join(c_raws)}'",
            )
        if c_members.issubset(q_members):
            return (
                "range_contained",
                0.84,
                f"Candidate street number '{', '.join(c_raws)}' is contained within queried range '{', '.join(q_raws)}'",
            )
        return (
            "range_contained",
            0.80,
            f"Overlapping street number ranges ('{', '.join(q_raws)}' vs '{', '.join(c_raws)}')",
        )

    # Check if base integer matches but suffix differs (e.g. '12' vs '12a', or '12a' vs '12b')
    q_bases = {re.match(r"^\d+", m).group(0) for m in q_members if re.match(r"^\d+", m)}
    c_bases = {re.match(r"^\d+", m).group(0) for m in c_members if re.match(r"^\d+", m)}
    if q_bases & c_bases:
        return (
            "conflict_suffix",
            0.0,
            f"Conflicting street number suffix ('{', '.join(q_raws)}' vs '{', '.join(c_raws)}')",
        )

    return (
        "conflict_number",
        0.0,
        f"Conflicting street numbers ('{', '.join(q_raws)}' vs '{', '.join(c_raws)}')",
    )


def _floor_label(f: str) -> str:
    if f == "0":
        return "Ground Floor"
    if f == "1":
        return "1st Floor"
    if f == "2":
        return "2nd Floor"
    if f == "3":
        return "3rd Floor"
    if f.isdigit():
        return f"{f}th Floor"
    return f.replace("_", " ").title()


def _compare_floors(q_floors: set[str], c_floors: set[str]) -> tuple[str, float, str]:
    """
    Compare floor sets.
    Returns (status, score_0_to_1, reason):
      status in {'exact', 'subset', 'soft_basement_lg', 'conflict', 'missing_both', 'missing_one'}
    """
    if not q_floors and not c_floors:
        return ("missing_both", 0.0, "")
    if not q_floors or not c_floors:
        return ("missing_one", 0.0, "")

    if q_floors == c_floors:
        lbl = ", ".join(_floor_label(f) for f in sorted(q_floors))
        return ("exact", 1.0, f"Exact floor match ({lbl})")

    overlap = q_floors & c_floors
    if overlap:
        q_lbl = ", ".join(_floor_label(f) for f in sorted(q_floors))
        c_lbl = ", ".join(_floor_label(f) for f in sorted(c_floors))
        return (
            "subset",
            0.85,
            f"Overlapping floor demise ({q_lbl} vs {c_lbl})",
        )

    # Check UK 'Basement' <-> 'Lower Ground' soft nuance vs true conflict:
    # Actually Basement and Lower Ground in UK Georgian/Victorian properties are VERY often used
    # interchangeably by assessors vs leases! Give soft match (0.82) rather than hard veto!
    if q_floors <= {"basement", "lower_ground"} and c_floors <= {"basement", "lower_ground"}:
        return (
            "soft_basement_lg",
            0.85,
            "Compatible sub-ground floor designation ('Basement' vs 'Lower Ground Floor')",
        )

    q_lbl = ", ".join(_floor_label(f) for f in sorted(q_floors))
    c_lbl = ", ".join(_floor_label(f) for f in sorted(c_floors))
    return ("conflict", 0.0, f"Conflicting floor levels ({q_lbl} vs {c_lbl})")


def _format_unit_spec(units: list[UnitSpec]) -> str:
    parts = []
    for u in units:
        if u.ids:
            parts.append(f"{u.raw_designator.title()} {', '.join(x.upper() for x in u.ids)}")
        else:
            parts.append(u.raw_designator.title())
    return "; ".join(parts)


def _compare_unit_lists(
    q_units: list[UnitSpec], c_units: list[UnitSpec]
) -> tuple[str, float, str]:
    """
    Compare extracted sub-units (per Q2 & Q6 rules).
    Returns (status, score_0_to_1, reason):
      status in {
        'exact', 'exact_synonym', 'soft_commercial', 'range_contained',
        'conflict_category', 'conflict_id', 'missing_both', 'missing_one'
      }
    """
    if not q_units and not c_units:
        return ("missing_both", 0.0, "")
    if not q_units or not c_units:
        return ("missing_one", 0.0, "")

    q_cats = {u.broad_category for u in q_units}
    c_cats = {u.broad_category for u in c_units}

    # Hard category incompatibility: Residential ('Flat'/'Apartment') vs Commercial ('Shop'/'Unit'/'Suite')
    if ("residential" in q_cats and "commercial" in c_cats) or (
        "commercial" in q_cats and "residential" in c_cats
    ):
        return (
            "conflict_category",
            0.0,
            f"Incompatible unit categories ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}')",
        )

    q_ids = {uid for u in q_units for uid in u.ids}
    c_ids = {uid for u in c_units for uid in c_units} if False else {uid for u in c_units for uid in u.ids}
    q_grps = {u.synonym_group for u in q_units}
    c_grps = {u.synonym_group for u in c_units}

    # Both have bare designators without unit IDs (e.g. 'First Floor Flat' vs '1st Floor Apartment', or 'Shop' vs 'Retail Unit')
    if not q_ids and not c_ids:
        if q_grps & c_grps:
            q_raw = {u.raw_designator for u in q_units}
            c_raw = {u.raw_designator for u in c_units}
            if q_raw == c_raw:
                return ("exact", 1.0, f"Exact unit type match ('{_format_unit_spec(q_units)}')")
            return (
                "exact_synonym",
                0.98,
                f"Equivalent UK unit designators ('{_format_unit_spec(q_units)}' == '{_format_unit_spec(c_units)}')",
            )
        return (
            "soft_commercial",
            0.88,
            f"Compatible commercial unit types ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}')",
        )

    # One side has a unit ID ('Flat 2') and the other only has a bare type ('Flat')
    if bool(q_ids) != bool(c_ids):
        if q_grps & c_grps:
            return (
                "range_contained",
                0.76,
                f"Partial unit match ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}' lacking unit number)",
            )
        return (
            "range_contained",
            0.68,
            f"Partial commercial unit match ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}')",
        )

    # Both sides have explicit unit IDs!
    overlap = q_ids & c_ids
    if not overlap:
        return (
            "conflict_id",
            0.0,
            f"Conflicting unit identifiers ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}')",
        )

    # IDs match exactly vs range containment
    same_syn_group = bool(q_grps & c_grps)
    any_bare_inferred = any(u.is_bare_inferred for u in q_units + c_units)

    if q_ids == c_ids:
        q_raw = {u.raw_designator for u in q_units}
        c_raw = {u.raw_designator for u in c_units}
        if same_syn_group and not any_bare_inferred:
            if q_raw == c_raw:
                return ("exact", 1.0, f"Exact unit match ('{_format_unit_spec(q_units)}')")
            return (
                "exact_synonym",
                0.98,
                f"Equivalent UK unit match ('{_format_unit_spec(q_units)}' == '{_format_unit_spec(c_units)}')",
            )
        if any_bare_inferred and same_syn_group:
            return (
                "exact_synonym",
                0.95,
                f"Matched unit identifier '{', '.join(sorted(q_ids)).upper()}' to '{_format_unit_spec(c_units if any(u.is_bare_inferred for u in q_units) else q_units)}'",
            )
        # Soft cross-commercial designator match (e.g. 'Unit 3' <-> 'Suite 3' / 'Office 3' / 'Plot 3')
        return (
            "soft_commercial",
            0.90,
            f"Matching unit identifier '{', '.join(sorted(q_ids)).upper()}' across compatible commercial designators ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}')",
        )

    # Range / multi-unit containment (e.g. 'Unit 2' inside 'Units 1-4')
    if q_ids.issubset(c_ids):
        return (
            "range_contained",
            0.86 if same_syn_group else 0.82,
            f"Queried '{_format_unit_spec(q_units)}' is contained within multi-unit EPC '{_format_unit_spec(c_units)}'",
        )
    if c_ids.issubset(q_ids):
        return (
            "range_contained",
            0.84 if same_syn_group else 0.80,
            f"Candidate '{_format_unit_spec(c_units)}' is part of queried multi-unit range '{_format_unit_spec(q_units)}'",
        )
    return (
        "range_contained",
        0.78,
        f"Overlapping multi-unit ranges ('{_format_unit_spec(q_units)}' vs '{_format_unit_spec(c_units)}')",
    )


# ============================================================================
# Pairwise Candidate Scorer
# ============================================================================


def score_candidate(
    query: ParsedAddress,
    cand: ParsedAddress,
    *,
    force_pure_sim: bool = False,
) -> dict[str, Any]:
    """
    Evaluate a single `ParsedAddress` candidate against `query`.
    Returns a detailed scoring dict with `score` (0-100), `reasons`, `component_scores`,
    and `has_hard_conflict`.
    """
    reasons: list[str] = []
    comp_scores: dict[str, float] = {
        "unit": 0.0,
        "floor": 0.0,
        "street_number": 0.0,
        "thoroughfare": 0.0,
        "estate_or_building": 0.0,
        "tenant": 0.0,
    }

    # Empty guard
    if not cand.raw_parts or (not query.raw_parts and not query.explicit_tenant):
        return {
            "score": 0.0,
            "reasons": ["Empty query or candidate address"],
            "component_scores": comp_scores,
            "has_hard_conflict": False,
        }

    hard_conflict = False
    hard_conflict_cap = 100.0
    max_tier_cap = 100.0

    # ------------------------------------------------------------------
    # 0. Special Cross-Slot Commercial Equivalence:
    #    'Unit 4, Acorn Way' (unit=4, street_num=[]) <-> '4 Acorn Way' (unit=[], street_num=[4])
    #    ONLY for commercial 'unit'/'plot' (NEVER residential 'Flat 4' vs '4 High St'!).
    # ------------------------------------------------------------------
    cross_unit_streetnum_match = False
    effective_q_units = query.units
    effective_c_units = cand.units
    effective_q_snums = query.street_numbers
    effective_c_snums = cand.street_numbers

    if (
        query.units
        and not query.street_numbers
        and not cand.units
        and cand.street_numbers
        and all(u.broad_category == "commercial" and u.synonym_group in {"unit", "plot"} and u.ids for u in query.units)
    ):
        # Convert query commercial unit IDs into synthetic NumberSpecs to test equivalence OR conflict!
        q_u_ids = tuple(uid for u in query.units for uid in u.ids)
        c_s_ids = tuple(m for n in cand.street_numbers for m in n.members)
        if set(q_u_ids) & set(c_s_ids):
            cross_unit_streetnum_match = True
            effective_q_units = []
            effective_q_snums = [NumberSpec(raw=",".join(q_u_ids), members=q_u_ids, is_range=len(q_u_ids) > 1)]
            max_tier_cap = min(max_tier_cap, 92.0)
            reasons.append(
                f"Matched commercial '{_format_unit_spec(query.units)}' to street/estate number '{', '.join(n.raw for n in cand.street_numbers)}'"
            )
        else:
            hard_conflict = True
            hard_conflict_cap = min(hard_conflict_cap, 22.0)
            reasons.append(
                f"Conflicting identifier ('{_format_unit_spec(query.units)}' vs number '{', '.join(n.raw for n in cand.street_numbers)}')"
            )
    elif (
        cand.units
        and not cand.street_numbers
        and not query.units
        and query.street_numbers
        and all(u.broad_category == "commercial" and u.synonym_group in {"unit", "plot"} and u.ids for u in cand.units)
    ):
        c_u_ids = tuple(uid for u in cand.units for uid in u.ids)
        q_s_ids = tuple(m for n in query.street_numbers for m in n.members)
        if set(c_u_ids) & set(q_s_ids):
            cross_unit_streetnum_match = True
            effective_c_units = []
            effective_c_snums = [NumberSpec(raw=",".join(c_u_ids), members=c_u_ids, is_range=len(c_u_ids) > 1)]
            max_tier_cap = min(max_tier_cap, 92.0)
            reasons.append(
                f"Matched queried number '{', '.join(n.raw for n in query.street_numbers)}' to candidate '{_format_unit_spec(cand.units)}'"
            )
        else:
            hard_conflict = True
            hard_conflict_cap = min(hard_conflict_cap, 22.0)
            reasons.append(
                f"Conflicting identifier (number '{', '.join(n.raw for n in query.street_numbers)}' vs '{_format_unit_spec(cand.units)}')"
            )

    # ------------------------------------------------------------------
    # 1. Structural Block / Wing Conflict ('Block A' vs 'Block B')
    # ------------------------------------------------------------------
    if query.structures and cand.structures:
        st_status, st_sim, st_reason = _compare_unit_lists(query.structures, cand.structures)
        if st_status.startswith("conflict"):
            hard_conflict = True
            hard_conflict_cap = min(hard_conflict_cap, 24.0)
            reasons.append(st_reason.replace("unit", "block/wing"))
        elif st_sim > 0:
            reasons.append(st_reason)

    # ------------------------------------------------------------------
    # 2. Thoroughfare, Estate/Park & Building Name Alignment
    # ------------------------------------------------------------------
    st_sim, q_st_best, c_st_best = _best_phrase_similarity(
        query.thoroughfares, cand.thoroughfares, force_pure=force_pure_sim
    )
    comp_scores["thoroughfare"] = round(st_sim * 100.0, 1)

    q_places = query.estates + query.buildings + query.unclassified_segments
    c_places = cand.estates + cand.buildings + cand.unclassified_segments
    q_strict_places = query.estates + query.buildings
    c_strict_places = cand.estates + cand.buildings

    strict_place_sim, q_pl_best, c_pl_best = _best_phrase_similarity(
        q_strict_places, c_strict_places, force_pure=force_pure_sim
    )
    broad_place_sim, q_bpl_best, c_bpl_best = _best_phrase_similarity(
        q_places, c_places, force_pure=force_pure_sim
    )

    # Cross-layer check: e.g. Query has building='saint marys court' + street='station road',
    # while Candidate omitted 'station road' so 'saint marys court' landed in cand.thoroughfares!
    cross_q_bldg_c_st, qb_cs_q, qb_cs_c = _best_phrase_similarity(
        q_strict_places, cand.thoroughfares, force_pure=force_pure_sim
    )
    cross_c_bldg_q_st, cb_qs_c, cb_qs_q = _best_phrase_similarity(
        c_strict_places, query.thoroughfares, force_pure=force_pure_sim
    )
    cross_layer_sim = max(cross_q_bldg_c_st, cross_c_bldg_q_st)
    cross_layer_matched = False
    if st_sim < 0.80 and cross_layer_sim >= 0.90:
        cross_layer_matched = True
        strict_place_sim = max(strict_place_sim, cross_layer_sim)
        if cross_q_bldg_c_st >= cross_c_bldg_q_st:
            q_pl_best, c_pl_best = qb_cs_q, qb_cs_c
        else:
            q_pl_best, c_pl_best = cb_qs_q, cb_qs_c

    place_sim = max(strict_place_sim, broad_place_sim)
    best_q_place = q_pl_best if strict_place_sim >= broad_place_sim else q_bpl_best
    best_c_place = c_pl_best if strict_place_sim >= broad_place_sim else c_bpl_best
    comp_scores["estate_or_building"] = round(place_sim * 100.0, 1)

    if query.thoroughfares and cand.thoroughfares:
        if st_sim >= 0.96:
            reasons.append(f"Exact street match ('{c_st_best.title()}')")
        elif st_sim >= 0.80:
            reasons.append(f"Fuzzy street match ('{q_st_best.title()}' ~ '{c_st_best.title()}', {st_sim:.0%})")
            max_tier_cap = min(max_tier_cap, 93.0)
        elif cross_layer_matched:
            max_tier_cap = min(max_tier_cap, 93.0)
            reasons.append(
                f"Matched court/building '{q_pl_best.title()}' (parent street omitted on one record)"
            )
        else:
            # Both specify thoroughfares and they differ!
            # Exception: Same named industrial estate/building + same unit, where one lists access road
            if strict_place_sim >= 0.90:
                max_tier_cap = min(max_tier_cap, 78.0)
                reasons.append(
                    f"Matched estate/building ('{best_c_place.title()}'), but secondary street differs ('{q_st_best.title()}' vs '{c_st_best.title()}')"
                )
            else:
                hard_conflict = True
                hard_conflict_cap = min(hard_conflict_cap, 20.0)
                reasons.append(
                    f"Conflicting street names ('{q_st_best.title()}' vs '{c_st_best.title()}')"
                )

    if strict_place_sim >= 0.95 and not cross_layer_matched:
        reasons.append(f"Exact building/estate match ('{q_pl_best.title()}')")
    elif strict_place_sim >= 0.80 and not cross_layer_matched:
        reasons.append(f"Fuzzy building/estate match ('{q_pl_best.title()}' ~ '{c_pl_best.title()}', {strict_place_sim:.0%})")
        max_tier_cap = min(max_tier_cap, 93.0)
    elif broad_place_sim >= 0.92 and best_q_place and not cross_layer_matched:
        reasons.append(f"Matched property/venue name ('{best_c_place.title()}')")

    # Detect conflicting distinct Estates/Buildings when NO street number/unit overrides
    if query.estates and cand.estates:
        est_sim, qe, ce = _best_phrase_similarity(
            query.estates, cand.estates, force_pure=force_pure_sim
        )
        if est_sim < 0.65:
            hard_conflict = True
            hard_conflict_cap = min(hard_conflict_cap, 25.0)
            reasons.append(f"Conflicting estates/parks ('{qe.title()}' vs '{ce.title()}')")

    # ------------------------------------------------------------------
    # 3. Street Number Comparison (Strict Suffix & Number Conflict Checks)
    # ------------------------------------------------------------------
    snum_status, snum_val, snum_reason = _compare_street_numbers(effective_q_snums, effective_c_snums)
    comp_scores["street_number"] = round(snum_val * 100.0, 1)

    if snum_status in {"conflict_suffix", "conflict_number"}:
        hard_conflict = True
        hard_conflict_cap = min(hard_conflict_cap, 22.0)
        reasons.append(snum_reason)
    elif snum_status == "exact":
        if not cross_unit_streetnum_match:
            reasons.append(snum_reason)
    elif snum_status == "range_contained":
        max_tier_cap = min(max_tier_cap, 89.0)
        reasons.append(snum_reason)

    # ------------------------------------------------------------------
    # 4. Floor & Shop<->Ground Floor Comparison (Q2 & Q6)
    # ------------------------------------------------------------------
    # Check Q6 special rule: 'Shop, 12 High St' <-> 'Ground Floor, 12 High St'
    shop_ground_soft_equiv = False
    q_has_bare_shop = (
        len(effective_q_units) == 1
        and effective_q_units[0].synonym_group == "shop"
        and not effective_q_units[0].ids
        and not query.floors
    )
    c_has_bare_shop = (
        len(effective_c_units) == 1
        and effective_c_units[0].synonym_group == "shop"
        and not effective_c_units[0].ids
        and not cand.floors
    )
    if q_has_bare_shop and cand.floors == {"0"} and not effective_c_units:
        shop_ground_soft_equiv = True
        max_tier_cap = min(max_tier_cap, 90.0)
        comp_scores["floor"] = 88.0
        comp_scores["unit"] = 88.0
        reasons.append("Matched retail 'Shop' to 'Ground Floor' at same address")
    elif c_has_bare_shop and query.floors == {"0"} and not effective_q_units:
        shop_ground_soft_equiv = True
        max_tier_cap = min(max_tier_cap, 90.0)
        comp_scores["floor"] = 88.0
        comp_scores["unit"] = 88.0
        reasons.append("Matched queried 'Ground Floor' to retail 'Shop' at same address")

    if not shop_ground_soft_equiv:
        fl_status, fl_val, fl_reason = _compare_floors(query.floors, cand.floors)
        comp_scores["floor"] = round(fl_val * 100.0, 1)
        if fl_status == "conflict":
            hard_conflict = True
            hard_conflict_cap = min(hard_conflict_cap, 22.0)
            reasons.append(fl_reason)
        elif fl_status == "exact":
            reasons.append(fl_reason)
        elif fl_status in {"subset", "soft_basement_lg"}:
            max_tier_cap = min(max_tier_cap, 89.0)
            reasons.append(fl_reason)
    else:
        fl_status = "soft_shop_ground"
        fl_val = 0.88

    # ------------------------------------------------------------------
    # 5. Sub-Unit Comparison (Q2 & Q6)
    # ------------------------------------------------------------------
    if not shop_ground_soft_equiv:
        u_status, u_val, u_reason = _compare_unit_lists(effective_q_units, effective_c_units)
        comp_scores["unit"] = round(u_val * 100.0, 1)
        if u_status in {"conflict_category", "conflict_id"}:
            hard_conflict = True
            hard_conflict_cap = min(hard_conflict_cap, 22.0)
            reasons.append(u_reason)
        elif u_status in {"exact", "exact_synonym"}:
            reasons.append(u_reason)
            if u_status == "exact_synonym" and any(u.is_bare_inferred for u in effective_q_units + effective_c_units):
                max_tier_cap = min(max_tier_cap, 96.0)
        elif u_status == "soft_commercial":
            max_tier_cap = min(max_tier_cap, 92.0)
            reasons.append(u_reason)
        elif u_status == "range_contained":
            max_tier_cap = min(max_tier_cap, 88.0)
            reasons.append(u_reason)
    else:
        u_status = "soft_shop_ground"
        u_val = 0.88

    # Guard Q6: Ensure '3rd Floor' (floor=3, no unit) vs 'Unit 3' (no floor, unit=3) NEVER gets bonus
    # from raw digit '3' overlapping in token similarity!
    floor_vs_unit_trap = (
        (bool(query.floors) and not effective_q_units and bool(effective_c_units) and not cand.floors)
        or (bool(cand.floors) and not effective_c_units and bool(effective_q_units) and not query.floors)
    ) and not shop_ground_soft_equiv

    # ------------------------------------------------------------------
    # 6. Second-Sweep Tenant / Occupier Evaluation (Q3)
    # ------------------------------------------------------------------
    # Subtract query & candidate structural street/estate/locality tokens so 'Station Road Dental'
    # only keeps {'dental'} and never false-matches '14 Station Road'!
    structural_vocab = (
        query.core_structural_tokens
        | cand.core_structural_tokens
        | {t for loc in query.localities + cand.localities for t in loc.split()}
    )
    # However, do NOT subtract tokens that came from unclassified venue names (like 'Red Lion')!
    pure_geo_vocab: set[str] = set()
    for item in (
        query.thoroughfares
        + query.estates
        + query.localities
        + cand.thoroughfares
        + cand.estates
        + cand.localities
    ):
        for tok in item.split():
            pure_geo_vocab.add(NUMBER_WORDS.get(tok, tok))

    q_tenant_sources = [query.explicit_tenant] if query.explicit_tenant else []
    q_tenant_sources.extend(query.inferred_occupiers)

    best_tenant_sim = 0.0
    matched_tenant_label = ""

    if q_tenant_sources:
        # Build candidate occupier strings: inferred occupiers + unclassified + named buildings + raw lines
        c_occ_candidates = (
            list(cand.inferred_occupiers)
            + list(cand.unclassified_segments)
            + list(cand.buildings)
        )
        c_full_raw = " ".join(cand.raw_parts)
        c_occ_candidates.append(c_full_raw)

        for qt_raw in q_tenant_sources:
            qt_norm, qt_toks = normalize_tenant_name(qt_raw, subtract_tokens=pure_geo_vocab)
            if not qt_toks:
                continue
            for ct_raw in c_occ_candidates:
                ct_norm, ct_toks = normalize_tenant_name(ct_raw, subtract_tokens=pure_geo_vocab)
                if not ct_toks:
                    continue
                # Compare distinctive tenant tokens
                overlap_toks = qt_toks & ct_toks
                if overlap_toks:
                    jacc = len(overlap_toks) / len(qt_toks | ct_toks)
                    contain = len(overlap_toks) / min(len(qt_toks), len(ct_toks))
                    sim = 0.35 * jacc + 0.65 * contain
                else:
                    # Typo tolerance on distinctive brand name (e.g. 'Sainsburys' vs 'Sainsburys', 'Greggs' vs 'Gregs')
                    if len(qt_toks) <= 3 and len(ct_toks) <= 4:
                        sim = max(
                            string_ratio(qt_norm, ct_norm, force_pure=force_pure_sim),
                            0.92 * jaro_winkler_sim(qt_norm, ct_norm, force_pure=force_pure_sim)
                            if string_ratio(qt_norm, ct_norm, force_pure=force_pure_sim) >= 0.78
                            else 0.0,
                        )
                        if sim < 0.84:
                            sim = 0.0
                    else:
                        sim = 0.0

                if sim > best_tenant_sim:
                    best_tenant_sim = sim
                    matched_tenant_label = qt_norm.title()

    comp_scores["tenant"] = round(best_tenant_sim * 100.0, 1)

    # ------------------------------------------------------------------
    # 7. Synthesize Structural Score + Hierarchy/Fallback + Tenant Rescue
    # ------------------------------------------------------------------
    if hard_conflict:
        if best_tenant_sim >= 0.80:
            reasons.append(
                f"Tenant name matched ('{matched_tenant_label}'), but cannot override hard structural address conflict"
            )
        # Differentiate slightly among rejected candidates so closest rejected still ranks cleanly below cutoff
        residual = (0.3 * st_sim + 0.3 * place_sim + 0.2 * best_tenant_sim) * 25.0
        final_score = round(min(hard_conflict_cap, max(2.0, residual)), 1)
        return {
            "score": final_score,
            "reasons": reasons,
            "component_scores": comp_scores,
            "has_hard_conflict": True,
        }

    # Evaluate anchor strength:
    has_street_match = st_sim >= 0.80
    has_strict_place_match = strict_place_sim >= 0.80
    has_broad_place_match = broad_place_sim >= 0.85

    has_exact_snum = snum_status == "exact" or cross_unit_streetnum_match
    has_range_snum = snum_status == "range_contained"
    has_any_snum_match = has_exact_snum or has_range_snum

    has_exact_unit = u_status in {"exact", "exact_synonym"}
    has_good_unit = has_exact_unit or u_status in {"soft_commercial", "range_contained", "soft_shop_ground"}

    has_exact_floor = fl_status == "exact"
    has_good_floor = has_exact_floor or fl_status in {"subset", "soft_basement_lg", "soft_shop_ground"}

    # Check if one side specifies a sub-demise (unit or floor) that the other side omits (Whole-building / Parent fallback)
    q_has_subdemise = bool(effective_q_units or query.floors) and not shop_ground_soft_equiv
    c_has_subdemise = bool(effective_c_units or cand.floors) and not shop_ground_soft_equiv

    missing_subdemise_on_cand = q_has_subdemise and not c_has_subdemise
    missing_subdemise_on_query = c_has_subdemise and not q_has_subdemise
    # Partial subdemise mismatch: e.g. '3rd Floor' vs 'Unit 3' (floor_vs_unit_trap)
    if floor_vs_unit_trap:
        q_desc = _format_unit_spec(effective_q_units) or ", ".join(_floor_label(f) for f in sorted(query.floors))
        c_desc = _format_unit_spec(effective_c_units) or ", ".join(_floor_label(f) for f in sorted(cand.floors))
        reasons.append(
            f"Unaligned sub-demise types ('{q_desc}' vs '{c_desc}'; floor levels are kept distinct from unit numbers)"
        )
        max_tier_cap = min(max_tier_cap, 58.0)

    # Check missing street number on one side when the other side has one
    snum_missing_one = snum_status == "missing_one" and not cross_unit_streetnum_match

    # Compute base structural score by archetype:
    base_score = 0.0

    # Archetype 1: Specific Property Identifier + Location Anchor Match!
    #   (e.g. Unit 4 + Acorn Ind Est [with or without street], OR 12 + High St, OR Flat 2 + 12 High St, OR Apex House + High St)
    if (has_any_snum_match or has_good_unit or strict_place_sim >= 0.90 or broad_place_sim >= 0.94) and (
        has_street_match or has_strict_place_match or has_broad_place_match
    ):
        # Start from anchor quality
        loc_quality = max(st_sim, strict_place_sim, 0.95 * broad_place_sim)
        # Bonus if BOTH street AND estate/building are present and match
        if has_street_match and has_strict_place_match:
            loc_quality = min(1.0, 0.55 * st_sim + 0.50 * strict_place_sim)

        id_quality = 1.0
        if has_range_snum:
            id_quality = min(id_quality, snum_val)
        if u_status in {"soft_commercial", "range_contained", "soft_shop_ground"}:
            id_quality = min(id_quality, u_val)
        if fl_status in {"subset", "soft_basement_lg"}:
            id_quality = min(id_quality, fl_val)

        base_score = 98.0 * (0.45 * loc_quality + 0.55 * id_quality)

        # Penalize gracefully if one side has an extra street/estate that the other omitted
        if (query.thoroughfares and not cand.thoroughfares) or (cand.thoroughfares and not query.thoroughfares):
            if has_strict_place_match and (has_good_unit or has_any_snum_match):
                # e.g. 'Unit 4, Acorn Industrial Estate, Station Rd' vs 'Unit 4, Acorn Industrial Estate'
                base_score = min(base_score, 93.0)
                omitted_st = (query.thoroughfares or cand.thoroughfares)[0].title()
                reasons.append(f"Matched on unit/building/estate ('{omitted_st}' omitted on one record)")
            else:
                base_score -= 12.0

        # Apply parent / whole-building fallback penalty when sub-demise (unit/floor) is missing on one side!
        if missing_subdemise_on_cand:
            sub_desc = _format_unit_spec(effective_q_units) or ", ".join(_floor_label(f) for f in sorted(query.floors))
            base_score = min(base_score, 74.0)
            max_tier_cap = min(max_tier_cap, 76.0)
            reasons.append(
                f"Matched parent building only; candidate has no sub-unit/floor specified for queried '{sub_desc}'"
            )
        elif missing_subdemise_on_query:
            sub_desc = _format_unit_spec(effective_c_units) or ", ".join(_floor_label(f) for f in sorted(cand.floors))
            base_score = min(base_score, 68.0)
            max_tier_cap = min(max_tier_cap, 78.0)
            reasons.append(
                f"Query specifies parent building only; candidate covers specific sub-demise '{sub_desc}'"
            )
        elif (bool(effective_q_units) != bool(effective_c_units)) and not shop_ground_soft_equiv:
            # e.g. both have '1st Floor', but one also says 'Suite 2'
            base_score = min(base_score, 75.0)
            max_tier_cap = min(max_tier_cap, 78.0)
            reasons.append("Matched floor and building, but sub-unit specificity differs")
        elif (bool(query.floors) != bool(cand.floors)) and not shop_ground_soft_equiv:
            # Both have 'Unit 2' / 'Flat 2', and only one mentions '1st Floor' -> very common in UK!
            # ('Flat 2, 1st Floor, 12 High St' vs 'Flat 2, 12 High St' IS the exact same flat!)
            if has_exact_unit:
                base_score = min(base_score, 96.0)
                fl_lbl = ", ".join(_floor_label(f) for f in sorted(query.floors or cand.floors))
                reasons.append(f"Unit matched explicitly ('{fl_lbl}' omitted on one record)")
            else:
                base_score -= 6.0

        # Apply missing street number penalty if neither unit nor named building pins down the exact plot
        if snum_missing_one:
            if has_good_unit and has_strict_place_match:
                # 'Unit 4, Apex House, 10 High St' vs 'Unit 4, Apex House, High St' -> still unmistakably same unit!
                base_score = min(base_score, 94.0)
            elif strict_place_sim >= 0.92 or broad_place_sim >= 0.94:
                # 'Apex House, 10 High St' vs 'Apex House, High St' -> named building on same street!
                base_score = min(base_score, 91.0)
                reasons.append("Matched named building on street (street number omitted on one record)")
            else:
                # e.g. '14 High Street' vs 'High Street' (no unit, no building name!)
                base_score = min(base_score, 50.0)
                reasons.append("Matched street only; street number missing on one record")

    # Archetype 2: Only Street / Estate Name Matches (No shared number, unit, or named building)
    elif has_street_match or has_strict_place_match:
        loc_sim = max(st_sim, strict_place_sim)
        if snum_missing_one or missing_subdemise_on_cand or missing_subdemise_on_query:
            base_score = 44.0 * loc_sim
            reasons.append("Partial location match only (missing distinguishing building/unit/street number)")
        else:
            # Neither query nor candidate has any number or unit (e.g. ['','High Street',''] vs ['High Street',''])
            base_score = 52.0 * loc_sim
            reasons.append("Street/estate name matched, but neither record contains a specific unit or number")

    # Archetype 3: Unit/Floor matched within postcode, when one side completely omitted street/estate!
    #   (e.g. EPC says ['Unit 4B', ''] and Query says ['Unit 4B', 'Acorn Ind Est', ''])
    elif has_exact_unit and not cand.thoroughfares and not cand.estates and not query.street_numbers:
        base_score = 66.0
        max_tier_cap = min(max_tier_cap, 75.0)
        reasons.append("Unit identifier matched within postcode, but candidate lacks street/estate details")

    else:
        # Fallback fuzzy token check for highly unconventional rural/house-name addresses
        tok_sim = token_set_sim(query.normalized_full, cand.normalized_full, force_pure=force_pure_sim)
        if tok_sim >= 0.85 and query.normalized_full and cand.normalized_full:
            base_score = 72.0 * tok_sim
            reasons.append(f"Fuzzy address token overlap ({tok_sim:.0%})")
        else:
            base_score = 25.0 * tok_sim

    # ------------------------------------------------------------------
    # Apply Tenant Booster / Second-Sweep Rescue (Q3)
    # ------------------------------------------------------------------
    if best_tenant_sim >= 0.75 and not floor_vs_unit_trap:
        if base_score >= 80.0:
            # Tie-breaker & confirmation boost on already strong structural match
            boost = 4.0 * best_tenant_sim
            base_score = min(100.0, base_score + boost)
            reasons.append(f"Confirmed by tenant/occupier match ('{matched_tenant_label}', {best_tenant_sim:.0%})")
        elif base_score >= 60.0:
            # Boost parent/sub-demise match when tenant confirms exact occupier!
            boost = 12.0 * best_tenant_sim
            base_score = min(88.0, base_score + boost)
            max_tier_cap = max(max_tier_cap, 86.0) if not hard_conflict else max_tier_cap
            reasons.append(
                f"Second-sweep tenant match ('{matched_tenant_label}', {best_tenant_sim:.0%}) strengthened partial structural match"
            )
        elif has_street_match or has_strict_place_match:
            # Classic EPC rescue: Query=['', '14 High Street', 'Costa Coffee Ltd'] vs Cand=['Costa Coffee', 'High Street']
            rescue_score = 74.0 + 12.0 * best_tenant_sim * max(st_sim, strict_place_sim)
            base_score = max(base_score, min(86.0, rescue_score))
            max_tier_cap = min(max_tier_cap, 88.0)
            reasons.append(
                f"Second-sweep tenant match ('{matched_tenant_label}', {best_tenant_sim:.0%}) resolved address lacking shared unit/street number"
            )
        elif not cand.thoroughfares and not cand.estates and not cand.street_numbers and not cand.units:
            # Tenant-only EPC record inside the same postcode (e.g. ['Tesco Express', ''])
            rescue_score = 60.0 + 10.0 * best_tenant_sim
            base_score = max(base_score, min(70.0, rescue_score))
            max_tier_cap = min(max_tier_cap, 72.0)
            reasons.append(
                f"Second-sweep tenant match ('{matched_tenant_label}', {best_tenant_sim:.0%}) against occupier-only EPC record in postcode"
            )

    # Exact canonical polish:
    # Distinguish 100.0 (clean canonical match) vs 96-99 (exact structural match with extra old-tenant tokens or town stripped)
    if (
        base_score >= 95.0
        and max_tier_cap >= 95.0
        and not missing_subdemise_on_cand
        and not missing_subdemise_on_query
        and not snum_missing_one
        and not cross_unit_streetnum_match
    ):
        # Check if candidate had leftover foreign occupier tokens that didn't match query
        extra_cand_occ = bool(cand.unclassified_segments or cand.inferred_occupiers) and best_tenant_sim < 0.75 and (
            query.normalized_full != cand.normalized_full
        )
        if query.normalized_full == cand.normalized_full and not extra_cand_occ:
            base_score = 100.0 if best_tenant_sim >= 0.8 or not query.explicit_tenant else 99.0
        elif extra_cand_occ:
            # Per Q3: never penalize out of High/Exact for former tenant name, just shave ~2 pts so
            # a clean or current-tenant EPC wins ties!
            base_score = min(base_score, 96.5)
            reasons.append("Note: candidate includes additional occupier/building text ignored as non-conflicting")
        else:
            base_score = max(base_score, 97.0)

    # Locality confirmation micro-bonus (never a penalty when absent!)
    if query.localities and cand.localities:
        if set(query.localities) & set(cand.localities):
            reasons.append(f"Locality confirmed ('{(set(query.localities) & set(cand.localities)).pop().title()}')")

    final_score = round(max(0.0, min(max_tier_cap, base_score)), 1)
    if not reasons:
        reasons.append("No matching address or occupier components found")

    return {
        "score": final_score,
        "reasons": reasons,
        "component_scores": comp_scores,
        "has_hard_conflict": False,
    }


# ============================================================================
# Confidence Tiering & Public API
# ============================================================================


def score_to_tier(score: float, min_score: float = 40.0) -> str:
    """Map a 0-100 score to human-readable match tier."""
    if score < min_score:
        return "No Match"
    if score >= 95.0:
        return "Exact"
    if score >= 80.0:
        return "High"
    if score >= 60.0:
        return "Medium"
    return "Low"


class AddressMatcher:
    """
    Pre-parsed candidate index for matching one or many queries against the same
    postcode candidate pool.
    """

    def __init__(
        self,
        candidates: Mapping[Any, Sequence[Any] | str],
        *,
        town_hint: str | None = None,
    ) -> None:
        self.town_hint = town_hint
        self._raw_candidates: dict[Any, tuple[str, ...]] = {}
        self._parsed_candidates: dict[Any, ParsedAddress] = {}

        if not isinstance(candidates, Mapping):
            raise TypeError("`candidates` must be a dict/mapping of {id: [addr1, addr2, ...]}")

        for cid, val in candidates.items():
            if isinstance(val, (str, bytes)) or val is None or isinstance(val, float):
                lines: Sequence[Any] = [val]
            else:
                lines = list(val)
            clean_tuple = tuple(_clean_input_value(x) for x in lines if _clean_input_value(x))
            self._raw_candidates[cid] = clean_tuple
            self._parsed_candidates[cid] = parse_address_record(
                lines,
                explicit_tenant=None,
                is_query=False,
                town_hint=town_hint,
            )

    def match(
        self,
        query: Sequence[Any],
        *,
        min_score: float = 40.0,
        top_k_alternatives: int = 3,
        check_exempt: bool = True,
        force_pure_sim: bool = False,
    ) -> dict[str, Any]:
        """Match `[Unit Name, Street Address, Tenant Name]` against the candidate pool."""
        if isinstance(query, (str, bytes)):
            raise TypeError(
                "`query` must be a sequence like [unit_name, street_address, tenant_name], not a bare string"
            )

        q_list = list(query)
        addr_inputs = q_list[:2] if len(q_list) >= 2 else q_list[:1]
        tenant_input = q_list[2] if len(q_list) >= 3 else None
        # If caller passed >3 items, treat items[:-1] as address lines and last as tenant
        if len(q_list) > 3:
            addr_inputs = q_list[:-1]
            tenant_input = q_list[-1]

        parsed_query = parse_address_record(
            addr_inputs,
            explicit_tenant=tenant_input,
            is_query=True,
            town_hint=self.town_hint,
        )

        parsed_query_dict = {
            "normalized": parsed_query.normalized_full,
            "units": [_format_unit_spec([u]) for u in parsed_query.units],
            "floors": sorted(_floor_label(f) for f in parsed_query.floors),
            "street_numbers": [n.raw for n in parsed_query.street_numbers],
            "thoroughfares": parsed_query.thoroughfares,
            "estates": parsed_query.estates,
            "buildings": parsed_query.buildings,
            "stripped_localities": parsed_query.localities,
            "stripped_postcode": parsed_query.postcode,
            "tenant": parsed_query.explicit_tenant,
            "is_epc_exempt": parsed_query.is_epc_exempt,
            "exempt_category": parsed_query.exempt_category,
        }

        if check_exempt and parsed_query.is_epc_exempt:
            return {
                "best_match_id": None,
                "best_match_address": None,
                "score": 0.0,
                "match_tier": "No Cert",
                "reasons": [
                    f"Non-EPC / exempt structure detected ({parsed_query.exempt_category}: matched '{parsed_query.exempt_trigger}') "
                    "— property type does not require an EPC certificate"
                ],
                "component_scores": {
                    "unit": 0.0,
                    "floor": 0.0,
                    "street_number": 0.0,
                    "thoroughfare": 0.0,
                    "estate_or_building": 0.0,
                    "tenant": 0.0,
                },
                "tied_ids": [],
                "alternatives": [],
                "parsed_query": parsed_query_dict,
            }

        if not self._parsed_candidates:
            return {
                "best_match_id": None,
                "best_match_address": None,
                "score": 0.0,
                "match_tier": "No Match",
                "reasons": ["Candidate dictionary is empty"],
                "component_scores": {
                    "unit": 0.0,
                    "floor": 0.0,
                    "street_number": 0.0,
                    "thoroughfare": 0.0,
                    "estate_or_building": 0.0,
                    "tenant": 0.0,
                },
                "tied_ids": [],
                "alternatives": [],
                "parsed_query": parsed_query_dict,
            }

        scored_items: list[dict[str, Any]] = []
        for cid, p_cand in self._parsed_candidates.items():
            res = score_candidate(parsed_query, p_cand, force_pure_sim=force_pure_sim)
            scored_items.append(
                {
                    "id": cid,
                    "address": list(self._raw_candidates[cid]),
                    "score": res["score"],
                    "match_tier": score_to_tier(res["score"], min_score=min_score),
                    "reasons": res["reasons"],
                    "component_scores": res["component_scores"],
                    "has_hard_conflict": res["has_hard_conflict"],
                }
            )

        # Sort descending by score; prefer non-conflicting on exact numeric tie
        scored_items.sort(key=lambda item: (item["score"], not item["has_hard_conflict"]), reverse=True)

        winner = scored_items[0]
        is_match = winner["score"] >= min_score

        if is_match:
            best_id = winner["id"]
            best_addr = winner["address"]
            tier = winner["match_tier"]
            reasons = list(winner["reasons"])
            # Collect duplicate/historical EPC IDs that achieved the identical top score (within 0.1 pt)
            tied_ids = [
                item["id"]
                for item in scored_items
                if abs(item["score"] - winner["score"]) <= 0.1 and item["score"] >= min_score
            ]
            if len(tied_ids) > 1:
                reasons.append(
                    f"Tie detected across {len(tied_ids)} EPC candidates with equal top score ({winner['score']})"
                )
            runner_ups = [
                {
                    "id": item["id"],
                    "address": item["address"],
                    "score": item["score"],
                    "match_tier": item["match_tier"],
                    "reasons": item["reasons"],
                }
                for item in scored_items[1 : 1 + max(0, top_k_alternatives)]
            ]
        else:
            best_id = None
            best_addr = None
            tier = "No Match"
            reasons = [
                f"Best candidate '{winner['id']}' ({', '.join(winner['address']) or 'empty'}) scored {winner['score']} "
                f"(below min_score={min_score}): {'; '.join(winner['reasons'])}"
            ]
            tied_ids = []
            runner_ups = [
                {
                    "id": item["id"],
                    "address": item["address"],
                    "score": item["score"],
                    "match_tier": item["match_tier"],
                    "reasons": item["reasons"],
                }
                for item in scored_items[: max(0, top_k_alternatives)]
            ]

        return {
            "best_match_id": best_id,
            "best_match_address": best_addr,
            "score": winner["score"],
            "match_tier": tier,
            "reasons": reasons,
            "component_scores": winner["component_scores"],
            "tied_ids": tied_ids,
            "alternatives": runner_ups,
            "parsed_query": parsed_query_dict,
        }


def match_address(
    query: Sequence[Any],
    candidates: Mapping[Any, Sequence[Any] | str],
    *,
    min_score: float = 40.0,
    top_k_alternatives: int = 3,
    town_hint: str | None = None,
    check_exempt: bool = True,
) -> dict[str, Any]:
    """
    Find the best matching EPC candidate (or No Match / No Cert) for a messy UK property query.

    Parameters
    ----------
    query : Sequence[Any]
        `[Unit Name, Street Address, Tenant Name]` (handles None/NaN and field bleed).
    candidates : Mapping[Any, Sequence[Any] | str]
        `{candidate_id: [addr1, addr2, ...], ...}` subsetted to the property's postcode.
    min_score : float, default 40.0
        Minimum 0-100 score required to return a `best_match_id` (40='Low'+, 60='Medium'+,
        80='High'+, 95='Exact'). Below `min_score`, `best_match_id` is `None`.
    top_k_alternatives : int, default 3
        Number of runner-up candidates (or closest rejected candidates on No Match) to include.
    town_hint : str | None, default None
        Optional post-town name (if not already in the built-in UK towns dictionary) to
        strip harmlessly if it bleeds into `Unit Name` or `Street Address`.
    check_exempt : bool, default True
        When True, automatically isolates structures that do not require an EPC certificate
        (car parks, substations, telephone masts, bus shelters, ATMs, hoardings, bare land,
        places of worship, temporary cabins, etc.) and returns `match_tier='No Cert'`, `score=0.0`.

    Returns
    -------
    dict[str, Any]
        Plain dictionary suitable for JSON or `pd.Series` / `pd.DataFrame` / Polars unpacking:
        - `best_match_id`: winning candidate key or `None`
        - `best_match_address`: winning candidate's cleaned address lines or `None`
        - `score`: float in `[0.0, 100.0]`
        - `match_tier`: `'Exact' | 'High' | 'Medium' | 'Low' | 'No Match' | 'No Cert'`
        - `reasons`: list of human-readable explanations for the match/rejection/exemption
        - `component_scores`: per-component breakdown (`unit`, `floor`, `street_number`,
          `thoroughfare`, `estate_or_building`, `tenant`)
        - `tied_ids`: list of all candidate IDs tied for the winning score
        - `alternatives`: top runner-up candidates with scores and reasons
        - `parsed_query`: structured diagnostic view of how the messy query was decomposed
    """
    matcher = AddressMatcher(candidates, town_hint=town_hint)
    return matcher.match(
        query,
        min_score=min_score,
        top_k_alternatives=top_k_alternatives,
        check_exempt=check_exempt,
    )
