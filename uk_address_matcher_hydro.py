def match_uk_address(target_address: list, candidates: dict) -> dict:
    """
    Comprehensive, self-contained UK Address Matcher (100% Python Standard Library).

    Parameters
    ----------
    target_address : list
        A 4-element list `[address1, address2, address3, postcode]` representing
        the input UK address to match. Elements may be strings, ints, or None/empty.
    candidates : dict
        A dictionary mapping `{uprn: [address1, address2, address3, postcode], ...}`.

    Returns
    -------
    dict
        A dictionary containing:
        - `target`: Raw and parsed representation of `target_address`.
        - `best_match`: The highest-scoring candidate with `uprn`, `address`,
          `overall_score` (0.0-1.0), `pre_penalty_score`, `confidence`,
          `is_ambiguous`, `ambiguity_note`, `penalties_applied`, and rich
          `component_scores` breakdown.
        - `candidates`: Full ranked list of evaluated candidates (best first).
        - `metadata`: Summary execution statistics.
    """
    import collections
    import math
    import re
    import unicodedata

    # =========================================================================
    # 1. COMPREHENSIVE UK DOMAIN LOOKUP TABLES & DICTIONARIES
    # =========================================================================

    # Saints and St-prefix place/street names where "ST" means "SAINT", not "STREET"
    SAINT_NAMES = {
        "ABBS", "ALBANS", "ALDATES", "ANDREW", "ANDREWS", "ANNE", "ANNES", "ANNS",
        "ANTHONY", "ASAPH", "AUGUSTINE", "AUGUSTINES", "AUSTELL", "BARNABAS",
        "BARTHOLOMEW", "BARTHOLOMEWS", "BEES", "BENETS", "BLAIZE", "BOTOLPH",
        "BOTOLPHS", "BRIDES", "BUDEAUX", "CATHERINE", "CATHERINES", "CHAD", "CHADS",
        "CLAIR", "CLAIRS", "CLARE", "CLARES", "CLEMENT", "CLEMENTS", "COLUMB",
        "CROSS", "CUTHBERT", "CUTHBERTS", "CYRES", "DAVID", "DAVIDS", "DENYS",
        "DOGMAELS", "DOMINICK", "DUNSTAN", "DUNSTANS", "EDMUND", "EDMUNDS",
        "EDWARD", "EDWARDS", "ENODER", "ERTH", "EVAL", "EWE", "FAGANS", "FAITHS",
        "FILLANS", "FINBARRS", "FRANCIS", "GALL", "GENNYS", "GEORGE", "GEORGES",
        "GERMANS", "GILES", "GOVANS", "GREGORY", "GREGORYS", "HELEN", "HELENS",
        "HELIER", "HILDA", "HILDAS", "HILARY", "ILLTYDS", "ISSEY", "IVES",
        "JAMES", "JOHN", "JOHNS", "JOSEPH", "JOSEPHS", "JUDE", "JUDES",
        "JULIANS", "JUST", "KATHERINE", "KATHERINES", "KEVERNE", "KEW", "KEYNE",
        "LAURENCE", "LAWRENCE", "LEONARD", "LEONARDS", "LEVAN", "LUKE", "LUKES",
        "MABYN", "MAGNUS", "MARGARET", "MARGARETS", "MARK", "MARKS", "MARTIN",
        "MARTINS", "MARY", "MARYS", "MATTHEW", "MATTHEWS", "MAWES", "MELLONS",
        "MERRYN", "MEWAN", "MICHAEL", "MICHAELS", "MINVER", "MONANS", "NEOT",
        "NEOTS", "NICHOLAS", "NINIANS", "OLAVES", "OSWALD", "OSWALDS", "OSYTH",
        "PANCRAS", "PATRICK", "PATRICKS", "PAUL", "PAULS", "PETER", "PETERS",
        "PHILIP", "PHILIPS", "PIRAN", "PIRANS", "QUINTIN", "SAVIOUR", "SAVIOURS",
        "SEPULCHRE", "STEPHEN", "STEPHENS", "SWITHUN", "SWITHUNS", "TEATH",
        "THOMAS", "TUDY", "VEEP", "VINCENT", "VINCENTS", "WENN", "WINNOW",
        "WOLSTANS",
    }

    SAINT_POSSESSIVE_BASES = {
        "ANDREW", "GEORGE", "JAMES", "JOHN", "JOSEPH", "LUKE", "MARK", "MARTIN",
        "MARY", "MATTHEW", "MICHAEL", "PAUL", "PETER", "PHILIP", "STEPHEN",
    }

    # Written numbers and ordinals
    CARDINAL_WORDS = {
        "ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
        "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10,
        "ELEVEN": 11, "TWELVE": 12, "THIRTEEN": 13, "FOURTEEN": 14,
        "FIFTEEN": 15, "SIXTEEN": 16, "SEVENTEEN": 17, "EIGHTEEN": 18,
        "NINETEEN": 19, "TWENTY": 20, "THIRTY": 30, "FORTY": 40,
        "FIFTY": 50, "SIXTY": 60, "SEVENTY": 70, "EIGHTY": 80, "NINETY": 90,
    }

    # Non-house-number nouns that commonly follow a written cardinal at start of a street/house name
    CARDINAL_NAME_FOLLOWERS = {
        "ACRES", "ARCHES", "ASHES", "BARN", "BEECHES", "BELLS", "BIRCHES",
        "BRIDGES", "CEDARS", "CHIMNEYS", "CORNERS", "COTTAGE", "COTTAGES",
        "CROSSES", "CROWNS", "CUPS", "ELMS", "FEATHERS", "FIELDS", "FIRS",
        "GABLES", "GATES", "HILLS", "HOLLIES", "HORSESHOES", "HOUSE", "HOUSES",
        "KEYS", "LANES", "LAURELS", "LIMES", "LIONS", "MAPLES", "MILE",
        "OAKS", "PINES", "ROADS", "SISTERS", "SPRINGS", "STONES", "STREETS",
        "SWANS", "TREES", "TUNNELS", "TUNS", "WAYS", "WELLS", "WILLOWS",
    }

    ORDINAL_WORDS = {
        "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH",
        "FIFTH": "5TH", "SIXTH": "6TH", "SEVENTH": "7TH", "EIGHTH": "8TH",
        "NINTH": "9TH", "TENTH": "10TH", "ELEVENTH": "11TH", "TWELFTH": "12TH",
        "THIRTEENTH": "13TH", "FOURTEENTH": "14TH", "FIFTEENTH": "15TH",
        "SIXTEENTH": "16TH", "SEVENTEENTH": "17TH", "EIGHTEENTH": "18TH",
        "NINETEENTH": "19TH", "TWENTIETH": "20TH",
    }

    ORDINAL_TO_INT = {
        "1ST": 1, "FIRST": 1, "2ND": 2, "SECOND": 2, "3RD": 3, "THIRD": 3,
        "4TH": 4, "FOURTH": 4, "5TH": 5, "FIFTH": 5, "6TH": 6, "SIXTH": 6,
        "7TH": 7, "SEVENTH": 7, "8TH": 8, "EIGHTH": 8, "9TH": 9, "NINTH": 9,
        "10TH": 10, "TENTH": 10, "11TH": 11, "ELEVENTH": 11, "12TH": 12,
        "TWELFTH": 12, "13TH": 13, "THIRTEENTH": 13, "14TH": 14,
        "FOURTEENTH": 14, "15TH": 15, "FIFTEENTH": 15, "16TH": 16,
        "SIXTEENTH": 16, "17TH": 17, "SEVENTEENTH": 17, "18TH": 18,
        "EIGHTEENTH": 18, "19TH": 19, "NINETEENTH": 19, "20TH": 20,
        "TWENTIETH": 20,
    }

    # UK Street / Thoroughfare Suffixes (Abbreviation -> Canonical)
    STREET_SUFFIX_MAP = {
        # Standard English suffixes
        "RD": "ROAD", "RAOD": "ROAD", "ROADS": "ROAD", "ROAD": "ROAD",
        "ST": "STREET", "STR": "STREET", "STRT": "STREET", "STREET": "STREET",
        "AVE": "AVENUE", "AV": "AVENUE", "AVEN": "AVENUE", "AVNUE": "AVENUE", "AVENUE": "AVENUE",
        "CL": "CLOSE", "CLS": "CLOSE", "CLSE": "CLOSE", "CLOSE": "CLOSE",
        "CRES": "CRESCENT", "CR": "CRESCENT", "CRS": "CRESCENT", "CRSCNT": "CRESCENT", "CRESCENT": "CRESCENT",
        "DR": "DRIVE", "DRV": "DRIVE", "DRI": "DRIVE", "DRIVE": "DRIVE",
        "GDNS": "GARDENS", "GDN": "GARDENS", "GRDNS": "GARDENS", "GARDN": "GARDENS", "GARDENS": "GARDENS", "GARDEN": "GARDENS",
        "GRV": "GROVE", "GR": "GROVE", "GROV": "GROVE", "GROVE": "GROVE",
        "LN": "LANE", "LNE": "LANE", "LANE": "LANE",
        "PL": "PLACE", "PLACE": "PLACE",
        "SQ": "SQUARE", "SQR": "SQUARE", "SQUARE": "SQUARE",
        "TER": "TERRACE", "TERR": "TERRACE", "TRC": "TERRACE", "TERRACE": "TERRACE",
        "CT": "COURT", "CRT": "COURT", "COURT": "COURT",
        "WY": "WAY", "WAY": "WAY",
        "WLK": "WALK", "WK": "WALK", "WALK": "WALK",
        "HL": "HILL", "HLL": "HILL", "HILL": "HILL",
        "VW": "VIEW", "VIEW": "VIEW",
        "GRN": "GREEN", "GN": "GREEN", "GREEN": "GREEN",
        "PK": "PARK", "PRK": "PARK", "PARK": "PARK",
        "PKWY": "PARKWAY", "PKY": "PARKWAY", "PARKWAY": "PARKWAY",
        "PRD": "PARADE", "PARADE": "PARADE",
        "BDWY": "BROADWAY", "BWY": "BROADWAY", "BROADWAY": "BROADWAY",
        "CIR": "CIRCUS", "CRCS": "CIRCUS", "CIRCUS": "CIRCUS",
        "ESP": "ESPLANADE", "ESPL": "ESPLANADE", "ESPLANADE": "ESPLANADE",
        "PROM": "PROMENADE", "PROMENADE": "PROMENADE",
        "QY": "QUAY", "QUAYS": "QUAY", "QUAY": "QUAY", "QUAYSIDE": "QUAYSIDE",
        "WHF": "WHARF", "WHARF": "WHARF",
        "BLVD": "BOULEVARD", "BVD": "BOULEVARD", "BOULEVARD": "BOULEVARD",
        "HWY": "HIGHWAY", "HIGHWAY": "HIGHWAY",
        "CSWY": "CAUSEWAY", "CAUSEWAY": "CAUSEWAY",
        "BYP": "BYPASS", "BYPASS": "BYPASS",
        "APPR": "APPROACH", "APP": "APPROACH", "APPROACH": "APPROACH",
        "ARC": "ARCADE", "ARCADE": "ARCADE",
        "CH": "CHASE", "CHS": "CHASE", "CHASE": "CHASE",
        "CPS": "COPSE", "COPSE": "COPSE", "COPPICE": "COPPICE",
        "CRFT": "CROFT", "CROFT": "CROFT",
        "DN": "DENE", "DENE": "DENE", "DEAN": "DENE",
        "DRFT": "DRIFT", "DRIFT": "DRIFT",
        "END": "END", "FURLONG": "FURLONG", "GARTH": "GARTH", "GATE": "GATE",
        "GLADE": "GLADE", "GLD": "GLADE", "GLEN": "GLEN", "GLEBE": "GLEBE",
        "HTH": "HEATH", "HEATH": "HEATH", "HEDGES": "HEDGES",
        "LEAZE": "LEAZE", "LEA": "LEA",
        "MEAD": "MEAD", "MDW": "MEADOW", "MEADOW": "MEADOW", "MEADOWS": "MEADOWS",
        "MWS": "MEWS", "MEWS": "MEWS",
        "MT": "MOUNT", "MOUNT": "MOUNT",
        "NOOK": "NOOK", "ORCHARD": "ORCHARD", "ORCHARDS": "ORCHARDS",
        "PTH": "PATH", "PATH": "PATH", "PATHWAY": "PATHWAY", "PATCH": "PATCH",
        "PADDOCK": "PADDOCK", "PADDOCKS": "PADDOCKS",
        "QUAD": "QUADRANT", "QUADRANT": "QUADRANT",
        "REACH": "REACH", "RDG": "RIDGE", "RIDGE": "RIDGE", "RIDGEWAY": "RIDGEWAY",
        "RISE": "RISE", "ROW": "ROW", "SIDE": "SIDE", "SPINNEY": "SPINNEY",
        "STRAND": "STRAND", "VLE": "VALE", "VALE": "VALE",
        "VLY": "VALLEY", "VALLEY": "VALLEY", "VILLAS": "VILLAS",
        "YD": "YARD", "YARD": "YARD",
        "COMMON": "COMMON", "LAWNS": "LAWNS", "LAWN": "LAWN",
        "EMBANKMENT": "EMBANKMENT",
        # Scottish street suffixes
        "BRAE": "BRAE", "BRAES": "BRAE", "WYND": "WYND", "LOAN": "LOAN",
        "LOANING": "LOANING", "GAIT": "GAIT", "VENNEL": "VENNEL", "PEND": "PEND",
        "RIGG": "RIGG", "KNOWE": "KNOWE", "MAINS": "MAINS", "BURN": "BURN",
        "HAUGH": "HAUGH", "LINKS": "LINKS", "BRIG": "BRIG",
        # Welsh street words (often prefix, sometimes suffix)
        "HEOL": "HEOL", "FFORDD": "FFORDD", "STRYD": "STRYD", "LON": "LON",
        "LLWYBR": "LLWYBR", "RHOS": "RHOS",
    }

    # Unambiguous thoroughfare suffixes (rarely used as standalone house names without another street)
    STRONG_STREET_SUFFIXES = {
        "ROAD", "STREET", "AVENUE", "CLOSE", "CRESCENT", "DRIVE", "LANE",
        "WAY", "WALK", "GROVE", "TERRACE", "PLACE", "SQUARE", "BOULEVARD",
        "HIGHWAY", "CAUSEWAY", "BYPASS", "APPROACH", "PARADE", "BROADWAY",
        "CIRCUS", "ESPLANADE", "PROMENADE", "PARKWAY", "MEWS", "RISE", "ROW",
        "VALE", "WYND", "BRAE", "LOAN", "LOANING", "VENNEL", "HEOL", "FFORDD",
        "STRYD", "PATH", "RIDGEWAY", "EMBANKMENT", "QUAYSIDE",
    }

    # Suffixes that can be EITHER a Building/Block Name OR a Street Name
    DUAL_PURPOSE_SUFFIXES = {
        "COURT", "GARDENS", "PARK", "HILL", "VIEW", "GREEN", "YARD", "CHASE",
        "CROFT", "GARTH", "GATE", "GLADE", "GLEN", "GLEBE", "HEATH", "MEAD",
        "MEADOW", "MEADOWS", "MOUNT", "ORCHARD", "PADDOCK", "PADDOCKS", "QUAY",
        "WHARF", "ARCADE", "COPSE", "COPPICE", "DENE", "SPINNEY", "VILLAS",
    }

    # Tokens that may follow a strong street suffix as part of the same street phrase
    STREET_CONTINUATION_TOKENS = {
        "NORTH", "SOUTH", "EAST", "WEST", "UPPER", "LOWER", "CENTRAL", "MIDDLE",
        "GATE", "END", "HILL", "PARK", "GREEN", "COMMON", "SIDE", "ESTATE",
        "MEWS", "CLOSE", "COURT", "ARCADE", "MALL", "PARADE", "APPROACH",
        "ROW", "RISE", "TERRACE", "PLACE", "SQUARE", "GARDENS", "YARD",
        "WALK", "WAY", "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    }

    # Building / Property / House Name Suffixes & Keywords
    BUILDING_NAME_SUFFIXES = {
        "HOUSE", "HSE", "COTTAGE", "COTTAGES", "CTGE", "CTG", "LODGE", "LDG",
        "MANOR", "MNR", "VICARAGE", "RECTORY", "PARSONAGE", "MANSE", "VILLA",
        "VILLAS", "BUNGALOW", "BUNGALOWS", "FARM", "FARMHOUSE", "BARN", "BARNS",
        "MILL", "WATERMILL", "WINDMILL", "HALL", "TOWER", "TOWERS", "HEIGHTS",
        "POINT", "MANSIONS", "MANSION", "CHAMBERS", "APARTMENTS", "RESIDENCE",
        "RESIDENCES", "PRIORY", "ABBEY", "CASTLE", "GRANGE", "GRANARY", "OAST",
        "STABLES", "STABLE", "SCHOOLHOUSE", "GATEHOUSE", "TOLLHOUSE",
        "ALMSHOUSES", "STEADING", "BOTHIE", "PLAS", "TY", "BWTHYN", "FFARM",
        "KEEP", "PAVILION", "CHALET", "GABLES", "CEDARS", "PINES", "OAKS",
        "ELMS", "WILLOWS", "BEECHES", "POPLARS", "LAURELS", "HOLLIES",
        "SYCAMORES", "CHESTNUTS", "BIRCHES", "LIMES", "ACRES",
    }

    BUILDING_NAME_CANONICAL = {
        "HSE": "HOUSE", "CTGE": "COTTAGE", "CTG": "COTTAGE", "COTTAGES": "COTTAGE",
        "LDG": "LODGE", "MNR": "MANOR", "MANSIONS": "MANSION", "VILLAS": "VILLA",
        "APT": "APARTMENTS", "APTS": "APARTMENTS", "BLDG": "BUILDING",
        "BLDGS": "BUILDINGS", "CTR": "CENTRE", "CENTER": "CENTRE",
        "EST": "ESTATE", "IND": "INDUSTRIAL", "TRAD": "TRADING",
        "CT": "COURT", "CRT": "COURT",
    }

    COMMERCIAL_KEYWORDS = {
        "LIMITED", "LTD", "PLC", "LLP", "INC", "CORP", "COMPANY", "CO",
        "SUPERMARKET", "EXPRESS", "STORE", "STORES", "SHOP", "PHARMACY",
        "CHEMIST", "SURGERY", "MEDICAL", "CLINIC", "HOSPITAL", "DENTAL",
        "SCHOOL", "ACADEMY", "COLLEGE", "UNIVERSITY", "NURSERY", "PRESCHOOL",
        "CHURCH", "CHAPEL", "CATHEDRAL", "MOSQUE", "TEMPLE", "SYNAGOGUE",
        "HOTEL", "INN", "TAVERN", "ARMS", "PUB", "CLUB", "INSTITUTE",
        "BANK", "SOCIETY", "POST OFFICE", "GARAGE", "MOTORS", "WORKSHOP",
        "WORKS", "DEPOT", "WAREHOUSE", "STUDIOS", "CENTRE", "CENTER",
        "PLAZA", "MALL", "EXCHANGE", "TERMINAL", "STATION", "ESTATE",
        "BUSINESS PARK", "INDUSTRIAL ESTATE", "TRADING ESTATE", "RETAIL PARK",
        "SCIENCE PARK", "ENTERPRISE PARK", "TECHNOLOGY PARK",
    }

    # Trailing generic tokens stripped from commercial/org names before core comparison
    BUILDING_GENERIC_SUFFIX_TOKENS = {
        "LIMITED", "LTD", "PLC", "LLP", "INC", "CORP", "COMPANY", "CO",
        "GROUP", "HOLDINGS", "SERVICES", "MOTORS", "PARK", "ESTATE",
        "BUSINESS", "INDUSTRIAL", "TRADING", "RETAIL", "SCIENCE",
        "TECHNOLOGY", "ENTERPRISE", "CENTRE", "CENTER", "BUILDING",
        "BUILDINGS", "COMPLEX",
    }

    # Directional & Modifier Canonicalization
    DIRECTIONAL_MAP = {
        "N": "NORTH", "NTH": "NORTH", "NRTH": "NORTH",
        "S": "SOUTH", "STH": "SOUTH",
        "E": "EAST", "EST": "EAST",
        "W": "WEST", "WST": "WEST",
        "NE": "NORTH EAST", "NW": "NORTH WEST",
        "SE": "SOUTH EAST", "SW": "SOUTH WEST",
        "UPR": "UPPER", "UP": "UPPER",
        "LWR": "LOWER", "LOWR": "LOWER",
        "GT": "GREAT", "GRT": "GREAT",
        "LT": "LITTLE", "LTL": "LITTLE",
        "MID": "MIDDLE", "MDL": "MIDDLE",
        "CEN": "CENTRAL", "CENT": "CENTRAL",
    }

    DIRECTIONAL_OPPOSITES = {
        "NORTH": "SOUTH", "SOUTH": "NORTH",
        "EAST": "WEST", "WEST": "EAST",
        "UPPER": "LOWER", "LOWER": "UPPER",
        "GREAT": "LITTLE", "LITTLE": "GREAT",
    }

    # Sub-building type canonicalization
    SUB_BUILDING_TYPES = {
        "FLAT": "FLAT", "FLT": "FLAT", "FLATS": "FLAT", "F": "FLAT",
        "APARTMENT": "FLAT", "APT": "FLAT", "APPT": "FLAT", "APTS": "FLAT",
        "UNIT": "UNIT", "UNT": "UNIT", "UNITS": "UNIT",
        "SUITE": "SUITE", "STE": "SUITE",
        "ROOM": "ROOM", "RM": "ROOM",
        "STUDIO": "STUDIO", "MAISONETTE": "MAISONETTE", "PENTHOUSE": "PENTHOUSE",
        "ANNEX": "ANNEX", "ANNEXE": "ANNEX",
        "WING": "WING", "WORKSHOP": "WORKSHOP", "STALL": "STALL",
        "KIOSK": "KIOSK", "PLOT": "PLOT", "BERTH": "BERTH",
        "CARAVAN": "CARAVAN", "CHALET": "CHALET", "CABIN": "CABIN",
        "BLOCK": "BLOCK", "BLK": "BLOCK",
    }

    DWELLING_SUB_TYPES = {
        "FLAT", "STUDIO", "MAISONETTE", "PENTHOUSE", "UNIT", "SUITE", "ROOM",
    }

    FLOOR_CANONICAL_MAP = {
        "SUB BASEMENT": -2, "LOWER GROUND": -1, "LWR GND": -1, "LWR GRD": -1,
        "LG": -1, "BASEMENT": -1, "BSMT": -1, "CELLAR": -1, "GARDEN": 0,
        "GROUND": 0, "GND": 0, "GRD": 0, "GF": 0, "G": 0,
        "FIRST": 1, "1ST": 1, "1F": 1,
        "SECOND": 2, "2ND": 2, "2F": 2,
        "THIRD": 3, "3RD": 3, "3F": 3,
        "FOURTH": 4, "4TH": 4, "4F": 4,
        "FIFTH": 5, "5TH": 5, "5F": 5,
        "SIXTH": 6, "6TH": 6, "6F": 6,
        "SEVENTH": 7, "7TH": 7, "7F": 7,
        "EIGHTH": 8, "8TH": 8, "8F": 8,
        "NINTH": 9, "9TH": 9, "9F": 9,
        "TENTH": 10, "10TH": 10, "10F": 10,
        "MEZZANINE": 0, "UPPER": 2, "TOP": 99, "ATTIC": 99, "PENTHOUSE": 99,
    }

    LETTER_TO_NUMBER_MAP = {
        "A": "1", "B": "2", "C": "3", "D": "4",
        "E": "5", "F": "6", "G": "7", "H": "8",
    }
    NUMBER_TO_LETTER_MAP = {v: k for k, v in LETTER_TO_NUMBER_MAP.items()}

    # UK Counties & Abbreviations -> Canonical County Name
    UK_COUNTY_MAP = {
        "HANTS": "HAMPSHIRE", "HAMPSHIRE": "HAMPSHIRE", "SOUTHAMPTONSHIRE": "HAMPSHIRE",
        "BERKS": "BERKSHIRE", "BERKSHIRE": "BERKSHIRE", "ROYAL BERKSHIRE": "BERKSHIRE",
        "BUCKS": "BUCKINGHAMSHIRE", "BUCKINGHAMSHIRE": "BUCKINGHAMSHIRE",
        "OXON": "OXFORDSHIRE", "OXFORDSHIRE": "OXFORDSHIRE",
        "WILTS": "WILTSHIRE", "WILTSHIRE": "WILTSHIRE",
        "GLOS": "GLOUCESTERSHIRE", "GLOUCS": "GLOUCESTERSHIRE", "GLOUCESTERSHIRE": "GLOUCESTERSHIRE",
        "WORCS": "WORCESTERSHIRE", "WORCESTERSHIRE": "WORCESTERSHIRE",
        "WARKS": "WARWICKSHIRE", "WARWICKS": "WARWICKSHIRE", "WARWICKSHIRE": "WARWICKSHIRE",
        "STAFFS": "STAFFORDSHIRE", "STAFFORDSHIRE": "STAFFORDSHIRE",
        "SALOP": "SHROPSHIRE", "SHROPS": "SHROPSHIRE", "SHROPSHIRE": "SHROPSHIRE",
        "CHES": "CHESHIRE", "CHESHIRE": "CHESHIRE",
        "LANCS": "LANCASHIRE", "LANCASHIRE": "LANCASHIRE",
        "YORKS": "YORKSHIRE", "YORKSHIRE": "YORKSHIRE",
        "N YORKS": "NORTH YORKSHIRE", "NORTH YORKSHIRE": "NORTH YORKSHIRE",
        "S YORKS": "SOUTH YORKSHIRE", "SOUTH YORKSHIRE": "SOUTH YORKSHIRE",
        "W YORKS": "WEST YORKSHIRE", "WEST YORKSHIRE": "WEST YORKSHIRE",
        "E YORKS": "EAST YORKSHIRE", "EAST YORKSHIRE": "EAST YORKSHIRE",
        "EAST RIDING OF YORKSHIRE": "EAST YORKSHIRE",
        "NOTTS": "NOTTINGHAMSHIRE", "NOTTINGHAMSHIRE": "NOTTINGHAMSHIRE",
        "LEICS": "LEICESTERSHIRE", "LEICESTERSHIRE": "LEICESTERSHIRE",
        "NORTHANTS": "NORTHAMPTONSHIRE", "NORTHAMPTONSHIRE": "NORTHAMPTONSHIRE",
        "CAMBS": "CAMBRIDGESHIRE", "CAMBRIDGESHIRE": "CAMBRIDGESHIRE",
        "BEDS": "BEDFORDSHIRE", "BEDFORDSHIRE": "BEDFORDSHIRE",
        "HERTS": "HERTFORDSHIRE", "HERTFORDSHIRE": "HERTFORDSHIRE",
        "MIDDX": "MIDDLESEX", "MIDDLESEX": "MIDDLESEX",
        "LINCS": "LINCOLNSHIRE", "LINCOLNSHIRE": "LINCOLNSHIRE",
        "DERBYS": "DERBYSHIRE", "DERBYSHIRE": "DERBYSHIRE",
        "CORNW": "CORNWALL", "CORNWALL": "CORNWALL",
        "DEVON": "DEVON", "DEVONSHIRE": "DEVON",
        "SOMERSET": "SOMERSET", "SOM": "SOMERSET",
        "DORSET": "DORSET", "SURREY": "SURREY", "KENT": "KENT", "ESSEX": "ESSEX",
        "SUSSEX": "SUSSEX", "WEST SUSSEX": "WEST SUSSEX", "W SUSSEX": "WEST SUSSEX",
        "EAST SUSSEX": "EAST SUSSEX", "E SUSSEX": "EAST SUSSEX",
        "NORFOLK": "NORFOLK", "SUFFOLK": "SUFFOLK", "CUMBRIA": "CUMBRIA",
        "NORTHUMBERLAND": "NORTHUMBERLAND", "NORTHD": "NORTHUMBERLAND",
        "CO DURHAM": "COUNTY DURHAM", "COUNTY DURHAM": "COUNTY DURHAM",
        "TYNE AND WEAR": "TYNE AND WEAR", "MERSEYSIDE": "MERSEYSIDE",
        "GREATER MANCHESTER": "GREATER MANCHESTER", "GT MANCHESTER": "GREATER MANCHESTER",
        "WEST MIDLANDS": "WEST MIDLANDS", "W MIDLANDS": "WEST MIDLANDS",
        "GREATER LONDON": "GREATER LONDON",
        "AVON": "AVON", "CLEVELAND": "CLEVELAND", "HUMBERSIDE": "HUMBERSIDE",
        "HEREFORDSHIRE": "HEREFORDSHIRE",
        "RUTLAND": "RUTLAND", "ISLE OF WIGHT": "ISLE OF WIGHT", "IOW": "ISLE OF WIGHT",
        # Wales & Scotland counties
        "PEMBS": "PEMBROKESHIRE", "PEMBROKESHIRE": "PEMBROKESHIRE",
        "CARMS": "CARMARTHENSHIRE", "CARMARTHENSHIRE": "CARMARTHENSHIRE",
        "GLAM": "GLAMORGAN", "MID GLAMORGAN": "GLAMORGAN", "SOUTH GLAMORGAN": "GLAMORGAN", "WEST GLAMORGAN": "GLAMORGAN",
        "MON": "MONMOUTHSHIRE", "MONMOUTHSHIRE": "MONMOUTHSHIRE",
        "GWENT": "GWENT", "GWYNEDD": "GWYNEDD", "POWYS": "POWYS", "CLWYD": "CLWYD", "DYFED": "DYFED",
        "CEREDIGION": "CEREDIGION", "ANGLESEY": "ANGLESEY", "ISLE OF ANGLESEY": "ANGLESEY",
        "GUERNSEY": "GUERNSEY", "JERSEY": "JERSEY", "ISLE OF MAN": "ISLE OF MAN",
        "FIFESHIRE": "FIFE", "FIFE": "FIFE", "AYRSHIRE": "AYRSHIRE", "LANARKSHIRE": "LANARKSHIRE",
        "RENFREWSHIRE": "RENFREWSHIRE", "DUMBARTONSHIRE": "DUMBARTONSHIRE",
        "STIRLINGSHIRE": "STIRLINGSHIRE", "PERTHSHIRE": "PERTHSHIRE", "ABERDEENSHIRE": "ABERDEENSHIRE",
        "MIDLOTHIAN": "MIDLOTHIAN", "EAST LOTHIAN": "EAST LOTHIAN", "WEST LOTHIAN": "WEST LOTHIAN",
        "INVERNESS SHIRE": "INVERNESS", "ROSS SHIRE": "ROSS", "ARGYLL": "ARGYLL",
        # Northern Ireland counties
        "ANTRIM": "COUNTY ANTRIM", "CO ANTRIM": "COUNTY ANTRIM", "COUNTY ANTRIM": "COUNTY ANTRIM",
        "ARMAGH": "COUNTY ARMAGH", "CO ARMAGH": "COUNTY ARMAGH", "COUNTY ARMAGH": "COUNTY ARMAGH",
        "DOWN": "COUNTY DOWN", "CO DOWN": "COUNTY DOWN", "COUNTY DOWN": "COUNTY DOWN",
        "FERMANAGH": "COUNTY FERMANAGH", "CO FERMANAGH": "COUNTY FERMANAGH", "COUNTY FERMANAGH": "COUNTY FERMANAGH",
        "LONDONDERRY": "COUNTY LONDONDERRY", "CO LONDONDERRY": "COUNTY LONDONDERRY", "DERRY": "COUNTY LONDONDERRY",
        "TYRONE": "COUNTY TYRONE", "CO TYRONE": "COUNTY TYRONE", "COUNTY TYRONE": "COUNTY TYRONE",
    }

    # Greater London Boroughs & Districts often used interchangeably with Post Town "LONDON"
    LONDON_BOROUGHS_AND_DISTRICTS = {
        "WESTMINSTER", "CITY OF WESTMINSTER", "CAMDEN", "ISLINGTON", "HACKNEY",
        "TOWER HAMLETS", "GREENWICH", "LEWISHAM", "SOUTHWARK", "LAMBETH",
        "WANDSWORTH", "HAMMERSMITH", "FULHAM", "HAMMERSMITH AND FULHAM",
        "KENSINGTON", "CHELSEA", "KENSINGTON AND CHELSEA", "CITY OF LONDON",
        "WALTHAM FOREST", "REDBRIDGE", "HAVERING", "BARKING", "DAGENHAM",
        "NEWHAM", "BEXLEY", "BROMLEY", "CROYDON", "SUTTON", "MERTON",
        "KINGSTON ON THAMES", "RICHMOND ON THAMES", "HOUNSLOW", "HILLINGDON",
        "EALING", "BRENT", "HARROW", "BARNET", "ENFIELD", "HARINGEY",
        # Inner/Outer London Districts within LONDON post town
        "ACTON", "BALHAM", "BATTERSEA", "BELGRAVIA", "BERMONDSEY", "BETHNAL GREEN",
        "BLACKHEATH", "BLOOMSBURY", "BOW", "BRIXTON", "BROCKLEY", "CAMBERWELL",
        "CANARY WHARF", "CATFORD", "CHARLTON", "CHISWICK", "CLAPHAM",
        "CLERKENWELL", "COVENT GARDEN", "CRYSTAL PALACE", "DALSTON", "DEPTFORD",
        "DULWICH", "EARLS COURT", "EAST DULWICH", "ELEPHANT AND CASTLE",
        "ELTHAM", "FARRINGDON", "FINCHLEY", "FINSBURY", "FITZROVIA",
        "FOREST HILL", "GOLDERS GREEN", "HAMPSTEAD", "HARLESDEN", "HENDON",
        "HERNE HILL", "HIGHBURY", "HIGHGATE", "HOLBORN", "HOLLOWAY", "HOMERTON",
        "HOXTON", "KENNINGTON", "KENSAL GREEN", "KENTISH TOWN", "KILBURN",
        "KINGS CROSS", "KNIGHTSBRIDGE", "LEYTON", "LEYTONSTONE",
        "LIMEHOUSE", "MAIDA VALE", "MANOR PARK", "MARYLEBONE", "MAYFAIR",
        "MILL HILL", "MILLWALL", "MORTLAKE", "MUSWELL HILL", "NEW CROSS",
        "NINE ELMS", "NORBURY", "NORTHOLT", "NOTTING HILL", "NUNHEAD",
        "PADDINGTON", "PALMERS GREEN", "PECKHAM", "PIMLICO", "PLAISTOW",
        "POPLAR", "PUTNEY", "QUEENS PARK", "ROEHAMPTON", "ROTHERHITHE",
        "SHEPHERDS BUSH", "SHOREDITCH", "SOHO", "SOUTH BANK", "SOUTH KENSINGTON",
        "SOUTHFIELDS", "SPITALFIELDS", "ST JOHNS WOOD", "SAINT JOHNS WOOD",
        "STAMFORD HILL", "STEPNEY", "STOCKWELL", "STOKE NEWINGTON", "STRATFORD",
        "STREATHAM", "SWISS COTTAGE", "SYDENHAM", "TOOTING", "TOTTENHAM",
        "TUFNELL PARK", "UPTON PARK", "VAUXHALL", "VICTORIA", "WALWORTH",
        "WANSTEAD", "WAPPING", "WEST HAM", "WEST HAMPSTEAD", "WEST NORWOOD",
        "WHITECHAPEL", "WILLESDEN", "WIMBLEDON", "WOOD GREEN", "WOOLWICH",
    }

    KNOWN_UK_LOCALITY_TOWNS = {
        "WALTHAM ABBEY", "BARNARD CASTLE", "CHURCH STRETTON", "CHAPEL EN LE FRITH",
        "HAYWARDS HEATH", "THORNTON HEATH", "HARROW ON THE HILL", "BISHOPS CASTLE",
        "SUTTON COLDFIELD", "KINGSTON ON HULL", "NEWCASTLE ON TYNE", "STOKE ON TRENT",
        "STRATFORD ON AVON", "SOUTHEND ON SEA", "CLACTON ON SEA", "FRINTON ON SEA",
        "LEIGH ON SEA", "BEXHILL ON SEA", "WESTON SUPER MARE", "BURTON ON TRENT",
        "BOURTON ON THE WATER", "MORETON IN MARSH", "STOW ON THE WOLD",
        "ASHBY DE LA ZOUCH", "ROSS ON WYE", "CHESTER LE STREET", "HOUGHTON LE SPRING",
        "HETTON LE HOLE", "POULTON LE FYLDE", "WELWYN GARDEN CITY", "MARKET HARBOROUGH",
        "BISHOP AUCKLAND", "BISHOPS STORTFORD", "HENLEY ON THAMES", "WALTON ON THAMES",
        "BERWICK ON TWEED", "BRIGHTON AND HOVE", "NEWTON ABBOT", "BURNHAM ON CROUCH",
    }

    COUNTRY_NOISE = {
        "UK", "U K", "UNITED KINGDOM", "GREAT BRITAIN", "GB", "GBR",
        "ENGLAND", "SCOTLAND", "WALES", "CYMRU", "NORTHERN IRELAND", "NI",
    }

    MULTIWORD_COUNTRY_RE = re.compile(
        r"(?:\b(?:UNITED\s+KINGDOM|GREAT\s+BRITAIN|NORTHERN\s+IRELAND|U\s+K)\b)$"
    )
    TRAILING_SHORT_COUNTRY_RE = re.compile(r"\s+\b(?:UK|GB|GBR)\b$")

    # =========================================================================
    # 2. PURE-PYTHON STRING & PHONETIC SIMILARITY ENGINE
    # =========================================================================

    def _jaro_winkler(s1: str, s2: str) -> float:
        """Compute Jaro-Winkler similarity in [0.0, 1.0]."""
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
        transpositions = 0

        for i in range(len1):
            start = max(0, i - match_distance)
            end = min(i + match_distance + 1, len2)
            ch = s1[i]
            for j in range(start, end):
                if s2_matches[j] or ch != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

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
            (matches / len1)
            + (matches / len2)
            + ((matches - transpositions / 2.0) / matches)
        ) / 3.0

        # Winkler common prefix boost (up to 4 chars, p = 0.1)
        prefix = 0
        for i in range(min(4, len1, len2)):
            if s1[i] == s2[i]:
                prefix += 1
            else:
                break
        return jaro + prefix * 0.1 * (1.0 - jaro)

    def _damerau_levenshtein_sim(s1: str, s2: str) -> float:
        """Compute Normalized Optimal String Alignment (Damerau-Levenshtein) similarity."""
        if s1 == s2:
            return 1.0
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        max_len = max(len1, len2)
        if abs(len1 - len2) >= max_len:
            return 0.0

        # Trim common prefix and suffix to accelerate DP without altering distance
        start = 0
        min_len = min(len1, len2)
        while start < min_len and s1[start] == s2[start]:
            start += 1
        end1, end2 = len1, len2
        while end1 > start and end2 > start and s1[end1 - 1] == s2[end2 - 1]:
            end1 -= 1
            end2 -= 1

        t1 = s1[start:end1]
        t2 = s2[start:end2]
        n1, n2 = len(t1), len(t2)
        if n1 == 0 or n2 == 0:
            return max(0.0, 1.0 - (max(n1, n2) / max_len))

        prev2 = list(range(n2 + 1))
        prev1 = list(range(n2 + 1))
        curr = [0] * (n2 + 1)

        for i in range(1, n1 + 1):
            curr[0] = i
            c1 = t1[i - 1]
            c1_prev = t1[i - 2] if i > 1 else ""
            for j in range(1, n2 + 1):
                c2 = t2[j - 1]
                cost = 0 if c1 == c2 else 1
                val = prev1[j] + 1
                ins = curr[j - 1] + 1
                sub = prev1[j - 1] + cost
                if ins < val:
                    val = ins
                if sub < val:
                    val = sub
                if i > 1 and j > 1 and c1 == t2[j - 2] and c1_prev == c2:
                    trans = prev2[j - 2] + 1
                    if trans < val:
                        val = trans
                curr[j] = val
            prev2, prev1, curr = prev1, curr, prev2

        dist = prev1[n2]
        return max(0.0, 1.0 - (dist / max_len))

    def _uk_phonetic_word(word: str) -> str:
        """
        Encode a single uppercase word using UK-toponym-aware phonetic rules.
        Handles British silent letters and place-name orthography (e.g.,
        Leicester->Lester, Beauchamp->Beecham, Chiswick->Chisick, Burgh->Bra,
        Quay->Key, Welsh LL/DD/FF/CWM).
        """
        w = re.sub(r"[^A-Z0-9]", "", word.upper())
        if not w or w.isdigit():
            return w

        uk_replacements = (
            ("ICESTER", "STER"),
            ("CESTER", "STER"),
            ("CHESTER", "CHSTER"),
            ("BEAUCHAMP", "BEECHAM"),
            ("MARYLEBONE", "MARLEBON"),
            ("SOUTHWARK", "SUTHARK"),
            ("GREENWICH", "GRENICH"),
            ("CHISWICK", "CHISICK"),
            ("ALNWICK", "ANICK"),
            ("WARWICK", "WARICK"),
            ("BERWICK", "BERICK"),
            ("KESWICK", "KESICK"),
            ("NORWICH", "NORICH"),
            ("WOOLWICH", "WOLICH"),
            ("HARWICH", "HARICH"),
            ("WYMONDHAM", "WINDAM"),
            ("HAPPISBURGH", "HAZEBR"),
            ("FARNBOROUGH", "FARNBRA"),
            ("MIDDLESBROUGH", "MIDLSBRA"),
            ("LOUGHBOROUGH", "LUFBRA"),
            ("SCARBOROUGH", "SCARBRA"),
            ("PETERBOROUGH", "PETERBRA"),
            ("EDINBURGH", "EDINBRA"),
            ("BOROUGH", "BRA"),
            ("BROUGH", "BRA"),
            ("BURGH", "BRA"),
            ("LEIGH", "LY"),
            ("QUAY", "KEY"),
            ("AUGH", "AF"),
            ("OUGH", "O"),
            ("EIGH", "AY"),
            ("IGHT", "IT"),
            ("KN", "N"),
            ("WR", "R"),
            ("WH", "W"),
            ("PH", "F"),
            ("GH", ""),
            ("CK", "K"),
            ("SCH", "SK"),
            ("TCH", "CH"),
            ("DG", "J"),
            ("CWM", "KUM"),
            ("LL", "L"),
            ("DD", "TH"),
            ("FF", "F"),
        )
        for src, dst in uk_replacements:
            if src in w:
                w = w.replace(src, dst)

        if not w:
            return word[:1]

        first = w[0]
        if first == "C":
            first = "S" if w[1:2] in ("E", "I", "Y") else "K"
        elif first == "Q":
            first = "K"
        elif first == "X":
            first = "S"

        rest = w[1:]
        rest = re.sub(r"C(?=[EIY])", "S", rest)
        rest = rest.replace("C", "K").replace("Q", "K").replace("X", "KS").replace("Z", "S")
        rest = re.sub(r"(?<=[ST])W(?=[IYO])", "", rest)
        rest = re.sub(r"(?<![SCT])H", "", rest)
        rest = re.sub(r"[AEIOUY]", "", rest)

        collapsed = [first]
        for ch in rest:
            if ch != collapsed[-1]:
                collapsed.append(ch)
        return "".join(collapsed)

    def _uk_phonetic_phrase(phrase: str) -> str:
        tokens = [t for t in phrase.split() if t not in ("THE", "AND", "OF", "AT", "IN")]
        return " ".join(_uk_phonetic_word(t) for t in tokens if t)

    def _string_similarity(s1: str, s2: str) -> float:
        """Combined character-level similarity using Damerau-Levenshtein and Jaro-Winkler."""
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        jw = _jaro_winkler(s1, s2)
        dl = _damerau_levenshtein_sim(s1, s2)
        return 0.55 * dl + 0.45 * jw

    def _phonetic_words_compatible(a: str, b: str) -> bool:
        """
        Guard phonetic skeleton equality so short English minimal pairs
        (e.g. HILL/HALL, MILL/MALL, WELL/WALL, ROSE/RISE) do not collide.
        """
        if max(len(a), len(b)) < 6 or min(len(a), len(b)) < 5:
            return False
        if _uk_phonetic_word(a) != _uk_phonetic_word(b):
            return False
        return _string_similarity(a, b) >= 0.62

    def _guard_short_core_sim(a: str, b: str, sim: float) -> float:
        """
        Cap short single-word minimal-pair collisions (e.g. MILL/HILL, HILL/HALL,
        WELL/WALL, ROSE/RISE) while preserving genuine transpositions or missing chars.
        """
        if not a or not b or a == b or " " in a or " " in b:
            return sim
        if max(len(a), len(b)) <= 5 and a[:1] != b[:1]:
            return min(sim, 0.40)
        if len(a) == len(b) <= 4 and sorted(a) != sorted(b):
            return min(sim, 0.40)
        return sim

    def _token_similarity(s1: str, s2: str, ignore_stopwords: bool = True) -> float:
        """
        Compute order-independent and fuzzy-token-aligned similarity between two phrases.
        Combines Token Sort, Token Set, and Greedy Bipartite Token Alignment.
        """
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0

        stops = {"THE", "AND", "OF", "AT", "BY", "IN", "NEAR", "OFF"} if ignore_stopwords else set()
        t1 = [t for t in s1.split() if t not in stops] or s1.split()
        t2 = [t for t in s2.split() if t not in stops] or s2.split()

        if t1 == t2:
            return 0.99

        if len(t1) == 1 and len(t2) == 1:
            sc = _string_similarity(t1[0], t2[0])
            if sc < 0.85 and _phonetic_words_compatible(t1[0], t2[0]):
                sc = max(sc, 0.88)
            return min(1.0, sc)

        # 1. Token Sort Similarity
        sorted1 = " ".join(sorted(t1))
        sorted2 = " ".join(sorted(t2))
        sort_sim = _string_similarity(sorted1, sorted2)

        # 2. Token Set (Intersection + Remainder) Similarity
        set1, set2 = set(t1), set(t2)
        inter = sorted(set1 & set2)
        rem1 = sorted(set1 - set2)
        rem2 = sorted(set2 - set1)
        inter_str = " ".join(inter)
        comb1 = (inter_str + " " + " ".join(rem1)).strip()
        comb2 = (inter_str + " " + " ".join(rem2)).strip()

        set_sim = _string_similarity(comb1, comb2)
        if inter and (not rem1 or not rem2):
            coverage = len(inter) / max(len(set1), len(set2))
            set_sim = max(set_sim, 0.82 + 0.18 * coverage)

        # 3. Greedy Bipartite Fuzzy Token Alignment
        short_t, long_t = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
        used = [False] * len(long_t)
        total_pair_score = 0.0
        for tok_a in short_t:
            best_j = -1
            best_sc = -1.0
            for j, tok_b in enumerate(long_t):
                if used[j]:
                    continue
                sc = 1.0 if tok_a == tok_b else _string_similarity(tok_a, tok_b)
                if sc < 0.85 and _phonetic_words_compatible(tok_a, tok_b):
                    sc = max(sc, 0.88)
                if sc > best_sc:
                    best_sc = sc
                    best_j = j
            if best_j >= 0:
                used[best_j] = True
                total_pair_score += best_sc

        len_ratio = len(short_t) / len(long_t)
        bipartite_sim = (total_pair_score / len(short_t)) * (0.80 + 0.20 * len_ratio)

        return min(1.0, max(sort_sim, set_sim, bipartite_sim))

    # =========================================================================
    # 3. UK POSTCODE PARSER, VALIDATOR & OCR REPAIR ENGINE
    # =========================================================================

    STRICT_POSTCODE_RE = re.compile(
        r"^(?:GIR\s*0AA|([A-Z]{1,2})([0-9][0-9A-Z]?)\s*([0-9])([A-Z]{2}))$"
    )
    BFPO_RE = re.compile(r"^BFPO\s*([0-9]{1,4})$")
    EMBEDDED_POSTCODE_RE = re.compile(
        r"\b(GIR\s*0AA|BFPO\s*[0-9]{1,4}|[A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b"
    )
    ORDINAL_UNIT_FOLLOWERS_RE = re.compile(
        r"^\s*(?:FLOOR|FLR|FL|AVE|AVENUE|STREET|ST|ROAD|RD|LANE|LN|CLOSE|CL|WAY|DRIVE|DR)\b"
    )
    PARTIAL_OUTWARD_SECTOR_RE = re.compile(
        r"^([A-Z]{1,2})([0-9][0-9A-Z]?)(?:\s+([0-9]))?$"
    )

    OCR_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
    OCR_TO_DIGIT = {"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6"}

    OUTWARD_TEMPLATES = {
        2: ["LD"],
        3: ["LLD", "LDD", "LDL"],
        4: ["LLDD", "LLDL"],
    }

    def _repair_ocr_postcode(raw_compact: str):
        """
        Attempt position-aware UK postcode OCR repair on a 5-7 char alphanumeric string.
        Returns `(canonical_postcode, outward, inward, area, district, sector, unit, repaired)` or `None`.
        """
        s = re.sub(r"[^A-Z0-9]", "", raw_compact.upper())
        if len(s) < 5 or len(s) > 7:
            return None

        out_raw = s[:-3]
        in_raw = s[-3:]
        in_template = "DLL"

        in_chars = []
        in_edits = 0
        for ch, exp in zip(in_raw, in_template):
            if exp == "D":
                if ch.isdigit():
                    in_chars.append(ch)
                elif ch in OCR_TO_DIGIT:
                    in_chars.append(OCR_TO_DIGIT[ch])
                    in_edits += 1
                else:
                    return None
            else:
                if ch.isalpha():
                    in_chars.append(ch)
                elif ch in OCR_TO_LETTER:
                    in_chars.append(OCR_TO_LETTER[ch])
                    in_edits += 1
                else:
                    return None
        in_fixed = "".join(in_chars)

        best_out = None
        best_out_edits = 99
        for tmpl in OUTWARD_TEMPLATES.get(len(out_raw), []):
            chars = []
            edits = 0
            valid = True
            for ch, exp in zip(out_raw, tmpl):
                if exp == "D":
                    if ch.isdigit():
                        chars.append(ch)
                    elif ch in OCR_TO_DIGIT:
                        chars.append(OCR_TO_DIGIT[ch])
                        edits += 1
                    else:
                        valid = False
                        break
                else:
                    if ch.isalpha():
                        chars.append(ch)
                    elif ch in OCR_TO_LETTER:
                        chars.append(OCR_TO_LETTER[ch])
                        edits += 1
                    else:
                        valid = False
                        break
            if valid and edits < best_out_edits:
                best_out = "".join(chars)
                best_out_edits = edits

        total_edits = best_out_edits + in_edits
        if best_out is not None and total_edits <= 2:
            full_pc = f"{best_out} {in_fixed}"
            m = STRICT_POSTCODE_RE.match(full_pc)
            if m:
                return (
                    full_pc,
                    f"{m.group(1)}{m.group(2)}",
                    f"{m.group(3)}{m.group(4)}",
                    m.group(1),
                    m.group(2),
                    m.group(3),
                    m.group(4),
                    total_edits > 0,
                )
        return None

    def _strip_postcode_noise(pc_raw: str) -> str:
        pc_str = (pc_raw or "").strip().upper()
        pc_str = re.sub(r"[^A-Z0-9\s]", " ", pc_str)
        pc_str = re.sub(r"\s+", " ", pc_str).strip()
        pc_str = MULTIWORD_COUNTRY_RE.sub("", pc_str).strip()
        pc_str = TRAILING_SHORT_COUNTRY_RE.sub("", pc_str).strip()
        return pc_str

    def _parse_postcode(pc_raw: str, lines_raw: list) -> tuple:
        """
        Extract and parse UK postcode from `pc_raw` (or embedded in `lines_raw`).
        Returns `(postcode_info_dict, cleaned_lines)`.
        """
        cleaned_lines = list(lines_raw)
        pc_str = _strip_postcode_noise(pc_raw)

        # If postcode slot is empty, check lines in reverse order for an embedded UK postcode
        if not pc_str:
            for idx in range(len(cleaned_lines) - 1, -1, -1):
                line_up = cleaned_lines[idx].upper()
                matches = list(EMBEDDED_POSTCODE_RE.finditer(line_up))
                chosen = None
                for m_emb in reversed(matches):
                    cand_pc = m_emb.group(1).strip()
                    tail_after = line_up[m_emb.end():]
                    compact_cand = re.sub(r"\s+", "", cand_pc)
                    # Guard against ordinal floor/street identifiers like "B1 2ND FLOOR"
                    if compact_cand[-3:] in ("1ST", "2ND", "3RD", "4TH", "5TH", "6TH", "7TH", "8TH", "9TH"):
                        if ORDINAL_UNIT_FOLLOWERS_RE.match(tail_after):
                            continue
                    chosen = m_emb
                    break
                if chosen:
                    pc_str = chosen.group(1).strip()
                    cleaned_lines[idx] = (
                        cleaned_lines[idx][: chosen.start()]
                        + " "
                        + cleaned_lines[idx][chosen.end() :]
                    ).strip(" ,;-")
                    break

        info = {
            "raw": pc_str,
            "canonical": "",
            "outward": "",
            "inward": "",
            "area": "",
            "district": "",
            "sector": "",
            "unit": "",
            "is_valid_full": False,
            "is_partial": False,
            "ocr_repaired": False,
        }

        if not pc_str:
            return info, cleaned_lines

        if pc_str.replace(" ", "") == "GIR0AA":
            info.update({
                "canonical": "GIR 0AA",
                "outward": "GIR",
                "inward": "0AA",
                "area": "GIR",
                "district": "0",
                "sector": "0",
                "unit": "AA",
                "is_valid_full": True,
            })
            return info, cleaned_lines

        m_bfpo = BFPO_RE.match(pc_str)
        if m_bfpo:
            bfpo_num = str(int(m_bfpo.group(1)))
            info.update({
                "canonical": f"BFPO {bfpo_num}",
                "outward": "BFPO",
                "inward": bfpo_num,
                "area": "BFPO",
                "district": bfpo_num,
                "is_valid_full": True,
            })
            return info, cleaned_lines

        # 1. Strict full postcode match
        m_strict = STRICT_POSTCODE_RE.match(pc_str)
        if m_strict:
            area, dist, sec, unit = m_strict.groups()
            outw = f"{area}{dist}"
            inw = f"{sec}{unit}"
            info.update({
                "canonical": f"{outw} {inw}",
                "outward": outw,
                "inward": inw,
                "area": area,
                "district": dist,
                "sector": sec,
                "unit": unit,
                "is_valid_full": True,
            })
            return info, cleaned_lines

        # 2. Try OCR repair on 5-7 char string
        repaired = _repair_ocr_postcode(pc_str)
        if repaired:
            full_pc, outw, inw, area, dist, sec, unit, was_repaired = repaired
            info.update({
                "canonical": full_pc,
                "outward": outw,
                "inward": inw,
                "area": area,
                "district": dist,
                "sector": sec,
                "unit": unit,
                "is_valid_full": True,
                "ocr_repaired": was_repaired,
            })
            return info, cleaned_lines

        # 3. Check partial outward or outward + sector postcode (e.g. "GU1", "SW1A 2")
        m_part = PARTIAL_OUTWARD_SECTOR_RE.match(pc_str)
        if m_part:
            area, dist, sec = m_part.groups()
            outw = f"{area}{dist}"
            info.update({
                "canonical": f"{outw} {sec}".strip() if sec else outw,
                "outward": outw,
                "area": area,
                "district": dist,
                "sector": sec or "",
                "is_partial": True,
            })
            return info, cleaned_lines

        info["canonical"] = pc_str
        return info, cleaned_lines

    # =========================================================================
    # 4. DEEP UK SEMANTIC ADDRESS COMPONENT PARSER
    # =========================================================================

    def _clean_text(text: str) -> str:
        """Normalize Unicode, strip accents, standardize punctuation and whitespace."""
        if text is None:
            return ""
        s = str(text).strip()
        if not s:
            return ""
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = s.upper()
        # Remove care-of prefixes
        s = re.sub(r"^\b(?:C/O|CARE OF|FAO|ATTN)\b[:.\s]*", "", s)
        # Collapse possessive apostrophes (St. John's -> ST JOHNS, King's -> KINGS)
        s = re.sub(r"['’`]", "", s)
        # Semicolons act as clause delimiters alongside commas
        s = s.replace(";", ",")
        # Separate sub-building identifier followed by spaced hyphen + number ("Flat 2 - 14 High St")
        s = re.sub(
            r"\b(FLAT|FLT|APARTMENT|APT|APPT|UNIT|UNT|SUITE|STE|ROOM|RM|STUDIO|MAISONETTE|"
            r"PENTHOUSE|ANNEX|ANNEXE|BLOCK|BLK)\s+([A-Z0-9]+)\s+-\s+(?=\d)",
            r"\1 \2, ",
            s,
        )
        # Standardize ranges/suffixes around digits before handling letter-hyphen-letter
        s = re.sub(r"(?<=\d[A-Z])\s*-\s*(?=\d)", "-", s)
        s = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", s)
        s = re.sub(r"(?<=\d)\s+TO\s+(?=\d)", "-", s)
        # Collapse hyphen between building number and single-letter suffix (14-A -> 14A)
        s = re.sub(r"(?<=\d)-(?=[A-Z]\b)", "", s)
        # Convert standalone spaced hyphen ("Flat 2 - 14 High Street") to clause boundary
        s = re.sub(r"\s+-\s+", ", ", s)
        # Convert Welsh/compound word hyphens ("Heol-y-Bont", "Stratford-upon-Avon") to spaces
        s = re.sub(r"(?<=[A-Z])-(?=[A-Z])", " ", s)
        # Convert standalone spaced slash to comma, preserving compact slashes (2/14, 1/2, A/B)
        s = re.sub(r"\s+/\s+", ", ", s)
        # Replace remaining punctuation (except commas, hyphens, slashes) with spaces
        s = re.sub(r"[^A-Z0-9,\-/&\s]", " ", s)
        s = s.replace("&", " AND ")
        # Strip stray standalone hyphens not anchored inside alphanumeric ranges
        s = re.sub(r"(?<![A-Z0-9])-|-(?![A-Z0-9])", " ", s)
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s+", " ", s).strip(" ,")
        return s

    def _strip_clause_country_noise(clause: str) -> str:
        c = clause.strip()
        if not c or c in COUNTRY_NOISE:
            return ""
        c = MULTIWORD_COUNTRY_RE.sub("", c).strip(" ,")
        if " " in c:
            c = TRAILING_SHORT_COUNTRY_RE.sub("", c).strip(" ,")
        return "" if c in COUNTRY_NOISE else c

    def _normalize_written_numbers_in_clause(clause: str) -> str:
        """Convert leading or sub-building written numbers (ONE..NINETY NINE, FIRST..TWENTIETH)."""
        tokens = clause.split()
        if not tokens:
            return clause

        out = []
        i = 0
        n = len(tokens)
        while i < n:
            tok = tokens[i]
            if (
                tok in ("TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY")
                and i + 1 < n
                and tokens[i + 1] in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE")
            ):
                val = CARDINAL_WORDS[tok] + CARDINAL_WORDS[tokens[i + 1]]
                out.append(str(val))
                i += 2
                continue
            if tok in CARDINAL_WORDS:
                prev_tok = out[-1] if out else ""
                next_tok = tokens[i + 1] if i + 1 < n else ""
                is_sub_prefix = prev_tok in SUB_BUILDING_TYPES or prev_tok in ("NO", "NUMBER")
                is_clause_start = (
                    i == 0
                    and n >= 2
                    and next_tok not in CARDINAL_NAME_FOLLOWERS
                )
                if is_sub_prefix or is_clause_start:
                    out.append(str(CARDINAL_WORDS[tok]))
                    i += 1
                    continue
            if tok in ORDINAL_WORDS:
                out.append(ORDINAL_WORDS[tok])
                i += 1
                continue
            out.append(tok)
            i += 1

        final_tokens = []
        for idx, t in enumerate(out):
            if t in ("NO", "NUMBER") and idx + 1 < len(out) and re.match(r"^\d+", out[idx + 1]):
                continue
            final_tokens.append(t)
        return " ".join(final_tokens)

    def _normalize_saint_and_tokens(tokens: list, normalize_possessive_suffix: bool = True) -> list:
        """Disambiguate ST (SAINT vs STREET) and normalize saint phrases."""
        res = []
        n = len(tokens)
        i = 0
        while i < n:
            t = tokens[i]
            if t in ("ST", "SAINT") and i + 1 < n:
                nxt = tokens[i + 1]
                if nxt in SAINT_NAMES:
                    res.append("SAINT")
                    if (
                        normalize_possessive_suffix
                        and nxt in SAINT_POSSESSIVE_BASES
                        and i + 2 < n
                        and (tokens[i + 2] in STREET_SUFFIX_MAP or tokens[i + 2] in BUILDING_NAME_SUFFIXES)
                    ):
                        res.append(nxt + "S")
                        i += 2
                        continue
                    i += 1
                    continue
            res.append(t)
            i += 1
        return res

    # Sub-building extraction patterns
    SUB_PREFIX_RE = re.compile(
        r"\b(?:(FLAT|FLT|APARTMENT|APT|APPT|UNIT|UNT|SUITE|STE|ROOM|RM|STUDIO|MAISONETTE|"
        r"PENTHOUSE|ANNEX|ANNEXE|WORKSHOP|STALL|KIOSK|PLOT|BERTH|CARAVAN|CHALET|CABIN|"
        r"BLOCK|BLK)\s*(?:NO\s*)?([0-9]+/[0-9]+|[0-9]+[A-Z]?|[A-Z][0-9]{1,3}|[A-Z](?=\b))|"
        r"(F)\s*(?:NO\s*)?([0-9]+[A-Z]?))\b"
    )
    FLOOR_RE = re.compile(
        r"\b(SUB\s+BASEMENT|LOWER\s+GROUND|LWR\s+GND|LWR\s+GRD|BASEMENT|BSMT|CELLAR|"
        r"GARDEN|GROUND|GND|GRD|FIRST|1ST|SECOND|2ND|THIRD|3RD|FOURTH|4TH|FIFTH|5TH|"
        r"SIXTH|6TH|SEVENTH|7TH|EIGHTH|8TH|NINTH|9TH|TENTH|10TH|MEZZANINE|TOP|UPPER|"
        r"LOWER|MIDDLE|ATTIC)\s+(?:FLOOR|FLR|FL)\b"
        r"(?:\s+(FLAT|FLT|APT|APARTMENT|UNIT|SUITE|ROOM|LEFT|RIGHT|FRONT|REAR))?"
        r"(?:\s+(LEFT|RIGHT|FRONT|REAR))?"
        r"(?:\s+([0-9]+[A-Z]?|[A-Z][0-9]{1,3}|[A-Z](?=\b)))?"
    )
    STANDALONE_FLOOR_CODE_RE = re.compile(r"\b(G|[1-9]|10)F\b")
    STANDALONE_FLAT_FLOOR_RE = re.compile(
        r"\b(BASEMENT|BSMT|LOWER\s+GROUND|GARDEN|GROUND|FIRST|1ST|SECOND|2ND|THIRD|3RD|"
        r"TOP|UPPER|LOWER|ATTIC|REAR|FRONT|STUDIO)\s+(FLAT|FLT|APARTMENT|APT|MAISONETTE)\b"
        r"(?:\s+([0-9]+[A-Z]?|[A-Z][0-9]{1,3}|[A-Z](?=\b)))?"
    )
    SCOTTISH_TENEMENT_RE = re.compile(
        r"\b(?:FLAT\s+)?([0-9]|G)F([0-9]|[LRM])\b|\b([0-9]|G)/([LR]|[1-9])\b"
    )

    def _format_sub_building_canonical(sub_info: dict) -> str:
        if not sub_info["has_sub"]:
            return ""
        parts = []
        if sub_info["block_id"]:
            parts.append(f"BLOCK:{sub_info['block_id']}")
        if sub_info["floor"] is not None and not sub_info["id"]:
            parts.append(f"FLOOR:{sub_info['floor']}")
        if sub_info["pos"]:
            parts.append(sub_info["pos"])
        stype = sub_info["type"]
        sid = sub_info["id"]
        if sid:
            if stype and stype not in ("FLOOR", "BLOCK"):
                parts.append(f"{stype}:{sid}")
            elif not parts:
                parts.append(f"FLAT:{sid}")
            else:
                parts.append(sid)
        elif stype and stype != "FLOOR" and not parts:
            parts.append(stype)
        elif stype and stype not in ("FLOOR", "BLOCK") and sub_info["floor"] is not None:
            parts.append(stype)
        return ":".join(parts)

    def _extract_sub_building(clauses: list) -> tuple:
        """
        Extract sub-building/flat/floor/block information across `(line_idx, clause)` items.
        Returns `(sub_info_dict, remaining_clauses)`.
        """
        sub_parts = []
        sub_id = ""
        sub_type = ""
        sub_floor = None
        sub_pos = ""
        block_id = ""
        new_clauses = []

        # Count standalone numeric tokens outside X/Y slash patterns to avoid misclassifying "2/4 High St"
        all_text_no_slash = re.sub(r"\b[A-Z0-9]+/[A-Z0-9]+\b", " ", " , ".join(c for _, c in clauses))
        other_numbers = re.findall(r"\b\d+[A-Z]?\b", all_text_no_slash)

        for line_idx, cl in clauses:
            working = cl

            # 1. Check explicit Floor expression (e.g. "FIRST FLOOR FLAT 2", "FIRST FLOOR FRONT")
            m_flr = FLOOR_RE.search(working)
            if m_flr:
                flr_word, sub_kind, sub_dir2, flr_id = m_flr.groups()
                sub_floor = FLOOR_CANONICAL_MAP.get(flr_word, sub_floor)
                if flr_id and not sub_id:
                    sub_id = flr_id
                if sub_kind in ("LEFT", "RIGHT", "FRONT", "REAR"):
                    sub_pos = sub_kind
                elif sub_dir2 in ("LEFT", "RIGHT", "FRONT", "REAR"):
                    sub_pos = sub_dir2
                if sub_kind and sub_kind not in ("LEFT", "RIGHT", "FRONT", "REAR") and not sub_type:
                    sub_type = SUB_BUILDING_TYPES.get(sub_kind, sub_kind)
                elif not sub_type:
                    sub_type = "FLOOR"
                sub_parts.append(m_flr.group(0).strip())
                working = (working[: m_flr.start()] + " " + working[m_flr.end() :]).strip()

            # 2. Check standalone floor+flat (e.g. "GROUND FLAT", "BASEMENT FLAT", "TOP FLAT")
            m_sff = STANDALONE_FLAT_FLOOR_RE.search(working)
            if m_sff:
                flr_word, kind_word, sff_id = m_sff.groups()
                if flr_word in FLOOR_CANONICAL_MAP and sub_floor is None:
                    sub_floor = FLOOR_CANONICAL_MAP[flr_word]
                if flr_word in ("FRONT", "REAR") and not sub_pos:
                    sub_pos = flr_word
                sub_type = SUB_BUILDING_TYPES.get(kind_word, "FLAT")
                if sff_id and not sub_id:
                    sub_id = sff_id
                sub_parts.append(m_sff.group(0).strip())
                working = (working[: m_sff.start()] + " " + working[m_sff.end() :]).strip()

            # 3. Check standard Sub-building prefix (e.g. "FLAT 2", "F2", "UNIT B4", "BLOCK 2")
            while True:
                m_sub = SUB_PREFIX_RE.search(working)
                if not m_sub:
                    break
                kw = m_sub.group(1) or m_sub.group(3)
                ident = m_sub.group(2) or m_sub.group(4)
                canon_kw = SUB_BUILDING_TYPES.get(kw, kw)
                if canon_kw == "BLOCK":
                    if not block_id:
                        block_id = ident
                    if not sub_type:
                        sub_type = "BLOCK"
                else:
                    # Check if ident is Scottish slash notation inside "FLAT 2/1"
                    m_sl_id = re.match(r"^([0-9]|G)/([1-9]|[LR])$", ident)
                    if m_sl_id and len(other_numbers) >= 1:
                        fl_c, pos_c = m_sl_id.groups()
                        sub_floor = 0 if fl_c == "G" else int(fl_c)
                        ident = f"{fl_c}F{pos_c}"
                    if not sub_type or sub_type in ("FLOOR", "BLOCK"):
                        sub_type = canon_kw
                    if not sub_id:
                        sub_id = ident
                sub_parts.append(f"{canon_kw} {ident}")
                working = (working[: m_sub.start()] + " " + working[m_sub.end() :]).strip()

            # 4. Check Scottish tenement notation (e.g., "2F1", or "1/2" when a separate building number exists)
            m_scot = SCOTTISH_TENEMENT_RE.search(working)
            if m_scot:
                g1, g2, g3, g4 = m_scot.groups()
                if g1 is not None or len(other_numbers) >= 1:
                    fl_c, pos_c = (g1, g2) if g1 is not None else (g3, g4)
                    sub_floor = 0 if fl_c == "G" else int(fl_c)
                    sub_id = f"{fl_c}F{pos_c}"
                    if pos_c in ("L", "R"):
                        sub_pos = "LEFT" if pos_c == "L" else "RIGHT"
                    sub_type = "FLAT"
                    sub_parts.append(m_scot.group(0).strip())
                    working = (working[: m_scot.start()] + " " + working[m_scot.end() :]).strip()

            # 5. Check standalone floor shorthand codes ("1F", "2F", "GF")
            m_fc = STANDALONE_FLOOR_CODE_RE.search(working)
            if m_fc and not working.endswith("HIGHWAY"):
                fc_tok = m_fc.group(0)
                if fc_tok in FLOOR_CANONICAL_MAP:
                    sub_floor = FLOOR_CANONICAL_MAP[fc_tok]
                    if not sub_type:
                        sub_type = "FLOOR"
                    sub_parts.append(fc_tok)
                    working = (working[: m_fc.start()] + " " + working[m_fc.end() :]).strip()

            # 6. Check standalone bare sub-building clause ("FLAT", "ANNEXE", "GROUND FLOOR", etc.)
            working_clean = re.sub(r"\s+", " ", working).strip()
            bare_check = working_clean[4:].strip() if working_clean.startswith("THE ") else working_clean
            if bare_check in (
                "FLAT", "APARTMENT", "STUDIO", "PENTHOUSE", "ANNEX", "ANNEXE",
                "MAISONETTE", "BASEMENT", "GROUND FLOOR", "FIRST FLOOR",
                "SECOND FLOOR", "THIRD FLOOR", "TOP FLOOR",
            ):
                if "BASEMENT" in bare_check:
                    sub_floor = -1
                elif "GROUND" in bare_check:
                    sub_floor = 0
                elif "FIRST" in bare_check:
                    sub_floor = 1
                elif "SECOND" in bare_check:
                    sub_floor = 2
                elif "THIRD" in bare_check:
                    sub_floor = 3
                elif "TOP" in bare_check or "PENTHOUSE" in bare_check:
                    sub_floor = 99
                canon_bare = SUB_BUILDING_TYPES.get(bare_check, bare_check)
                if not sub_type:
                    sub_type = canon_bare
                sub_parts.append(canon_bare)
                working_clean = ""

            if working_clean:
                new_clauses.append((line_idx, working_clean))

        # Bare flat ID clause strictly before a house-number + street clause: ["2", "14 HIGH STREET"]
        if (
            not sub_id
            and len(new_clauses) >= 2
            and re.match(r"^([0-9]{1,3}[A-Z]?|[A-H])$", new_clauses[0][1])
            and re.match(r"^\d+(?:-\d+)?[A-Z]?\s+[A-Z]", new_clauses[1][1])
        ):
            sub_id = new_clauses[0][1]
            if not sub_type:
                sub_type = "FLAT"
            sub_parts.append(f"FLAT {sub_id}")
            new_clauses = new_clauses[1:]

        if not sub_id and block_id:
            sub_id = block_id

        display = " ".join(sub_parts).strip()
        sub_info = {
            "display": display,
            "type": sub_type,
            "id": sub_id,
            "block_id": block_id,
            "floor": sub_floor,
            "pos": sub_pos,
            "has_sub": bool(display or sub_id or block_id or sub_floor is not None),
        }
        sub_info["canonical"] = _format_sub_building_canonical(sub_info)
        return sub_info, new_clauses

    def _canonicalize_street_tokens(tokens: list) -> tuple:
        """
        Canonicalize a street token list (expanding suffixes, directions, SAINT).
        Returns `(full_canonical_street, core_street_name, canonical_suffix)`.
        """
        if not tokens:
            return "", "", ""
        norm = _normalize_saint_and_tokens(tokens)
        out = []
        n = len(norm)
        suffix = ""
        for idx, tok in enumerate(norm):
            is_last = idx == n - 1
            is_second_last_before_dir = (
                idx == n - 2 and (norm[-1] in DIRECTIONAL_MAP or norm[-1] in ("NORTH", "SOUTH", "EAST", "WEST"))
            )
            if (is_last or is_second_last_before_dir) and tok in STREET_SUFFIX_MAP and n >= 2:
                canon_sfx = STREET_SUFFIX_MAP[tok]
                out.append(canon_sfx)
                suffix = canon_sfx
            elif idx == 0 and tok in ("HEOL", "FFORDD", "STRYD", "LON", "LLWYBR"):
                out.append(tok)
                suffix = tok
            elif tok in DIRECTIONAL_MAP and (idx == 0 or idx == n - 1):
                out.append(DIRECTIONAL_MAP[tok])
            else:
                out.append(tok)

        full_street = " ".join(out)
        core_tokens = [t for i, t in enumerate(out) if not (i == 0 and t == "THE")]
        if suffix and len(core_tokens) >= 2 and core_tokens[-1] == suffix:
            core_tokens = core_tokens[:-1]
        elif suffix and len(core_tokens) >= 2 and core_tokens[0] == suffix:
            core_tokens = core_tokens[1:]
        core_street = " ".join(core_tokens) if core_tokens else full_street
        return full_street, core_street, suffix

    def _parse_premise_number_token(tok: str):
        """
        Parse a house number token like `14`, `14A`, `12-14`, `12A-14`, `12-14A`.
        Returns `(display_str, start_num, end_num, suffix_letter)` or `None`.
        """
        m = re.match(r"^(\d{1,5})([A-Z])?(?:-(\d{1,5})([A-Z])?)?$", tok)
        if not m:
            return None
        s_num = int(m.group(1))
        s_sfx = m.group(2) or ""
        e_num = int(m.group(3)) if m.group(3) else s_num
        e_sfx = m.group(4) or ""
        sfx = e_sfx or s_sfx
        if m.group(3) and e_num < s_num:
            if s_num >= 10 and e_num < 10 and (s_num % 10) < e_num:
                e_num = (s_num // 10) * 10 + e_num
            else:
                s_num, e_num = e_num, s_num
        disp = f"{s_num}-{e_num}{sfx}" if s_num != e_num else f"{s_num}{sfx}"
        return disp, s_num, e_num, sfx

    def _split_street_and_locality_tokens(rest_toks: list) -> tuple:
        """Split a post-number token list into `(street_tokens, locality_tokens)` when a town trails a street."""
        split_idx = -1
        n_rest = len(rest_toks)
        for k in range(1, n_rest - 1):
            cand_sfx = STREET_SUFFIX_MAP.get(rest_toks[k], "")
            if cand_sfx in STRONG_STREET_SUFFIXES:
                after_tok = rest_toks[k + 1]
                if after_tok in DIRECTIONAL_MAP or after_tok in ("NORTH", "SOUTH", "EAST", "WEST"):
                    if k + 2 < n_rest:
                        split_idx = k + 2
                        break
                    continue
                if after_tok not in STREET_CONTINUATION_TOKENS:
                    split_idx = k + 1
                    break
        if split_idx > 0:
            return rest_toks[:split_idx], rest_toks[split_idx:]
        return rest_toks, []

    def _parse_address_record(raw_record: list) -> dict:
        """
        Parse a 4-element UK address list `[address1, address2, address3, postcode]`
        into canonical UK PAF / AddressBase semantic components and normalized lines.
        """
        rec = list(raw_record) if isinstance(raw_record, (list, tuple)) else [raw_record]
        while len(rec) < 4:
            rec.append("")
        if len(rec) > 4:
            rec = [rec[0], rec[1], ", ".join(str(x) for x in rec[2:-1] if x), rec[-1]]

        raw_lines = ["" if x is None else str(x).strip() for x in rec[:3]]
        raw_pc = "" if rec[3] is None else str(rec[3]).strip()

        # 1. Extract & validate postcode (including scanning lines if needed)
        pc_info, lines_no_pc = _parse_postcode(raw_pc, raw_lines)

        # 2. Clean each positional line and split into sub-clauses keeping line_idx
        cleaned_lines = [_clean_text(ln) for ln in lines_no_pc]
        clauses = []
        for line_idx, ln in enumerate(cleaned_lines):
            if not ln:
                continue
            for part in ln.split(","):
                p = _normalize_written_numbers_in_clause(part.strip())
                p = _strip_clause_country_noise(p)
                if p:
                    # Normalize ST -> SAINT at clause level so building names & localities benefit too
                    p_toks = _normalize_saint_and_tokens(p.split(), normalize_possessive_suffix=False)
                    clauses.append((line_idx, " ".join(p_toks)))

        # 3. Extract Sub-Building (Flat / Unit / Floor / Scottish tenement / Block)
        sub_info, rem_clauses = _extract_sub_building(clauses)

        # 4. Classify remaining clauses
        building_num_disp = ""
        building_num_range = None
        building_name_parts = []
        street_candidates = []     # (full_street, core_street, suffix, was_off_prefix)
        locality_parts = []

        def _is_pure_locality_clause(toks: list) -> bool:
            phrase = " ".join(toks)
            phrase_on = re.sub(r"\bUPON\b", "ON", phrase)
            if (
                phrase in UK_COUNTY_MAP
                or phrase_on in LONDON_BOROUGHS_AND_DISTRICTS
                or phrase_on in KNOWN_UK_LOCALITY_TOWNS
                or phrase == "LONDON"
            ):
                return True
            for c_len in (3, 2, 1):
                if len(toks) > c_len:
                    tail = " ".join(toks[-c_len:])
                    if tail in UK_COUNTY_MAP:
                        return True
            return False

        def _looks_like_building_clause(toks: list) -> bool:
            last_t = toks[-1]
            return (
                last_t in BUILDING_NAME_SUFFIXES
                or any(t in COMMERCIAL_KEYWORDS for t in toks)
                or (len(toks) >= 2 and " ".join(toks[-2:]) in COMMERCIAL_KEYWORDS)
                or (toks[0] in ("TY", "PLAS", "BWTHYN", "FFARM") and toks[0] not in ("HEOL", "FFORDD", "STRYD", "LON", "LLWYBR"))
            )

        for cl_idx, (line_idx, cl) in enumerate(rem_clauses):
            toks = cl.split()
            if not toks:
                continue

            # Check PO Box
            m_pobox = re.search(r"\b(?:P\s*O\s*BOX|POST\s+OFFICE\s+BOX)\s*(\d+[A-Z]?)\b", cl)
            if m_pobox:
                building_name_parts.append(f"PO BOX {m_pobox.group(1)}")
                continue

            # Check prefix slash notation ("2/14 High Street" or "14/2 High Street")
            if (
                not sub_info["has_sub"]
                and re.match(r"^(\d+[A-Z]?)/(\d+[A-Z]?)$", toks[0])
                and len(toks) >= 2
            ):
                m_sl = re.match(r"^(\d+[A-Z]?)/(\d+[A-Z]?)$", toks[0])
                left_v, right_v = m_sl.group(1), m_sl.group(2)
                left_digits = int(re.match(r"^\d+", left_v).group(0))
                right_digits = int(re.match(r"^\d+", right_v).group(0))
                # If left > right and right is small (e.g. 14/2 -> building 14, flat 2)
                if left_digits > right_digits and right_digits <= 12:
                    sub_id_val, bnum_val = right_v, left_v
                else:
                    sub_id_val, bnum_val = left_v, right_v
                sub_info["id"] = sub_id_val
                sub_info["type"] = "FLAT"
                sub_info["display"] = f"FLAT {sub_id_val}"
                sub_info["has_sub"] = True
                sub_info["canonical"] = _format_sub_building_canonical(sub_info)
                toks = [bnum_val] + toks[1:]

            # Clause starts with a premise number
            num_parsed = _parse_premise_number_token(toks[0])
            if num_parsed and (len(toks) == 1 or toks[1] not in ("FLOOR", "FLR", "FL", "MILE", "ACRES", "OAKS", "ELMS", "PINES")):
                disp_n, s_n, e_n, sfx_n = num_parsed
                rest_toks = toks[1:]
                # Handle "14 A High Street" (detached single-letter suffix excluding compass letters)
                if (
                    not sfx_n
                    and len(rest_toks) >= 2
                    and rest_toks[0] in ("A", "B", "C", "D", "F", "G", "H")
                ):
                    sfx_n = rest_toks[0]
                    disp_n = f"{disp_n}{sfx_n}"
                    rest_toks = rest_toks[1:]

                if not building_num_disp:
                    building_num_disp = disp_n
                    building_num_range = (s_n, e_n, sfx_n)
                if not rest_toks:
                    continue

                st_toks, loc_toks = _split_street_and_locality_tokens(rest_toks)
                if not loc_toks:
                    # Check if e.g. "14 Rose Cottage" (numbered named house before "High Street")
                    st_last_sfx = STREET_SUFFIX_MAP.get(st_toks[-1], "")
                    if (
                        st_last_sfx not in STRONG_STREET_SUFFIXES
                        and st_last_sfx not in DUAL_PURPOSE_SUFFIXES
                        and _looks_like_building_clause(st_toks)
                    ):
                        building_name_parts.append(" ".join(st_toks))
                        continue
                full_s, core_s, sfx_s = _canonicalize_street_tokens(st_toks)
                street_candidates.append((full_s, core_s, sfx_s, False))
                if loc_toks:
                    locality_parts.append(" ".join(loc_toks))
                continue

            # Check embedded number inside building+street or building+number clause
            # e.g. "ROSE COTTAGE 14 HIGH STREET" or "SOVEREIGN COURT 14 HIGH STREET GUILDFORD" or "OAK HOUSE 14"
            emb_num_idx = -1
            for k in range(1, len(toks)):
                if _parse_premise_number_token(toks[k]):
                    if k == len(toks) - 1 and _looks_like_building_clause(toks[:-1]):
                        emb_num_idx = k
                        break
                    if k < len(toks) - 1:
                        tail_after = toks[k + 1 :]
                        has_street_sfx = any(
                            STREET_SUFFIX_MAP.get(t, "") in STRONG_STREET_SUFFIXES
                            or STREET_SUFFIX_MAP.get(t, "") in DUAL_PURPOSE_SUFFIXES
                            for t in tail_after
                        )
                        if has_street_sfx:
                            emb_num_idx = k
                            break

            if emb_num_idx > 0:
                bname_toks = toks[:emb_num_idx]
                building_name_parts.append(" ".join(bname_toks))
                disp_n, s_n, e_n, sfx_n = _parse_premise_number_token(toks[emb_num_idx])
                if not building_num_disp:
                    building_num_disp = disp_n
                    building_num_range = (s_n, e_n, sfx_n)
                after_toks = toks[emb_num_idx + 1 :]
                if after_toks:
                    st_toks, loc_toks = _split_street_and_locality_tokens(after_toks)
                    full_s, core_s, sfx_s = _canonicalize_street_tokens(st_toks)
                    street_candidates.append((full_s, core_s, sfx_s, False))
                    if loc_toks:
                        locality_parts.append(" ".join(loc_toks))
                continue

            # Strip leading "OFF" for dependent thoroughfares (e.g. "OFF STATION ROAD")
            is_off_street = False
            if toks[0] == "OFF" and len(toks) >= 2:
                toks = toks[1:]
                is_off_street = True

            last_tok = toks[-1]
            second_last_tok = toks[-2] if len(toks) >= 2 else ""
            canon_last_sfx = STREET_SUFFIX_MAP.get(last_tok, "")
            if (
                not canon_last_sfx
                and (last_tok in DIRECTIONAL_MAP or last_tok in ("NORTH", "SOUTH", "EAST", "WEST"))
                and second_last_tok in STREET_SUFFIX_MAP
            ):
                canon_last_sfx = STREET_SUFFIX_MAP[second_last_tok]

            has_welsh_street_prefix = toks[0] in ("HEOL", "FFORDD", "STRYD", "LON", "LLWYBR")
            is_strong_street = (
                canon_last_sfx in STRONG_STREET_SUFFIXES
                or has_welsh_street_prefix
                or is_off_street
            )
            is_dual_purpose = canon_last_sfx in DUAL_PURPOSE_SUFFIXES
            is_building_name = _looks_like_building_clause(toks)
            is_locality_ctx = (
                line_idx >= 1
                and (bool(street_candidates) or bool(building_num_disp) or bool(building_name_parts) or cl_idx == len(rem_clauses) - 1)
            )

            if is_strong_street:
                full_s, core_s, sfx_s = _canonicalize_street_tokens(toks)
                street_candidates.append((full_s, core_s, sfx_s, is_off_street))
            elif is_locality_ctx and _is_pure_locality_clause(toks):
                locality_parts.append(" ".join(toks))
            elif is_building_name and not is_dual_purpose:
                # Protect final locality-line clauses (address3) when premise/street already seen
                if line_idx == 2 and cl_idx == len(rem_clauses) - 1 and (street_candidates or building_num_disp):
                    locality_parts.append(" ".join(toks))
                else:
                    building_name_parts.append(" ".join(toks))
            elif is_dual_purpose:
                full_s, core_s, sfx_s = _canonicalize_street_tokens(toks)
                street_candidates.append((full_s, core_s, sfx_s, is_off_street))
            elif _is_pure_locality_clause(toks):
                locality_parts.append(" ".join(toks))
            else:
                if not street_candidates and not building_num_disp and not building_name_parts and cl_idx < len(rem_clauses) - 1:
                    building_name_parts.append(" ".join(toks))
                else:
                    locality_parts.append(" ".join(toks))

        # 5. Resolve Dual-Purpose / Multiple Street Candidates
        primary_street = ""
        primary_street_core = ""
        primary_street_suffix = ""
        dependent_street = ""
        dependent_was_off = False

        if len(street_candidates) == 1:
            primary_street, primary_street_core, primary_street_suffix, _ = street_candidates[0]
        elif len(street_candidates) >= 2:
            first_st, first_core, first_sfx, first_off = street_candidates[0]
            second_st, second_core, second_sfx, second_off = street_candidates[1]
            if first_sfx in DUAL_PURPOSE_SUFFIXES and second_sfx in STRONG_STREET_SUFFIXES:
                building_name_parts.append(first_st)
                primary_street, primary_street_core, primary_street_suffix = second_st, second_core, second_sfx
                if len(street_candidates) >= 3:
                    dependent_street = street_candidates[2][0]
                    dependent_was_off = street_candidates[2][3]
            else:
                primary_street, primary_street_core, primary_street_suffix = first_st, first_core, first_sfx
                dependent_street = second_st
                dependent_was_off = second_off

        # 6. Canonicalize Building Name
        raw_bname = " ".join(building_name_parts).strip()
        bname_tokens = [BUILDING_NAME_CANONICAL.get(t, t) for t in raw_bname.split()]
        canonical_bname = " ".join(bname_tokens)

        # 7. Canonicalize Locality & separate Post Town vs County
        locality_clauses_clean = []
        all_loc_tokens = []
        for lp in locality_parts:
            lp_norm = re.sub(r"\bUPON\b", "ON", lp.replace("-", " "))
            lp_toks = [t for t in lp_norm.split() if t not in COUNTRY_NOISE]
            if lp_toks:
                locality_clauses_clean.append(" ".join(lp_toks))
                all_loc_tokens.extend(lp_toks)

        extracted_county = ""
        town_tokens = list(all_loc_tokens)
        for c_len in (3, 2, 1):
            if len(town_tokens) >= c_len:
                tail = " ".join(town_tokens[-c_len:])
                if tail in UK_COUNTY_MAP:
                    extracted_county = UK_COUNTY_MAP[tail]
                    town_tokens = town_tokens[:-c_len]
                    break
        canonical_town = " ".join(town_tokens).strip()
        canonical_locality = " ".join(filter(None, [canonical_town, extracted_county])).strip()

        # 8. Build normalized full token set for line/token alignment
        norm_lines = []
        for ln in cleaned_lines:
            ln_clean = _strip_clause_country_noise(ln)
            ln_toks = _normalize_saint_and_tokens(
                _normalize_written_numbers_in_clause(ln_clean.replace(",", " ")).split()
            )
            ln_canon = [
                STREET_SUFFIX_MAP.get(t, BUILDING_NAME_CANONICAL.get(t, t))
                for t in ln_toks
                if t not in COUNTRY_NOISE
            ]
            norm_lines.append(" ".join(ln_canon))
        full_tokens_str = " ".join(filter(None, norm_lines))

        return {
            "postcode": pc_info["canonical"],
            "postcode_info": pc_info,
            "sub_building": sub_info["display"],
            "sub_building_canonical": sub_info["canonical"],
            "sub_info": sub_info,
            "building_number": building_num_disp,
            "building_number_range": building_num_range,
            "building_name": canonical_bname,
            "street": primary_street,
            "street_core": primary_street_core,
            "street_suffix": primary_street_suffix,
            "dependent_street": dependent_street,
            "dependent_was_off": dependent_was_off,
            "locality": canonical_locality,
            "locality_clauses": locality_clauses_clean,
            "town": canonical_town,
            "county": extracted_county,
            "normalized_lines": norm_lines,
            "full_tokens_str": full_tokens_str,
        }

    # =========================================================================
    # 5. COMPONENT-BY-COMPONENT SCORING FUNCTIONS
    # =========================================================================

    def _score_postcode(t_pc: dict, c_pc: dict) -> dict:
        """Score UK Postcode component (outward, sector, unit, BFPO, OCR repairs, transpositions)."""
        t_val = t_pc["canonical"]
        c_val = c_pc["canonical"]

        if not t_val and not c_val:
            return {"score": 0.50, "target_value": "", "candidate_value": "", "match_type": "BOTH_MISSING"}
        if not t_val or not c_val:
            return {"score": 0.50, "target_value": t_val, "candidate_value": c_val, "match_type": "MISSING_ONE_SIDE"}

        if t_val == c_val:
            if t_pc["ocr_repaired"] or c_pc["ocr_repaired"]:
                return {"score": 0.95, "target_value": t_val, "candidate_value": c_val, "match_type": "OCR_REPAIRED_EXACT"}
            return {"score": 1.0, "target_value": t_val, "candidate_value": c_val, "match_type": "EXACT"}

        # Strict BFPO mismatch (different BFPO numbers do not fuzzy-match)
        if t_pc["area"] == "BFPO" or c_pc["area"] == "BFPO":
            return {"score": 0.0, "target_value": t_val, "candidate_value": c_val, "match_type": "CONFLICT"}

        if t_pc["outward"] and c_pc["outward"]:
            same_outward = t_pc["outward"] == c_pc["outward"]
            same_sector = same_outward and bool(t_pc["sector"]) and (t_pc["sector"] == c_pc["sector"])

            if same_sector:
                if t_pc["is_partial"] or c_pc["is_partial"]:
                    return {"score": 0.78, "target_value": t_val, "candidate_value": c_val, "match_type": "PARTIAL_SECTOR_MATCH"}
                unit_sim = _damerau_levenshtein_sim(t_pc["unit"], c_pc["unit"])
                if unit_sim >= 0.50:
                    return {"score": 0.85, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_SECTOR_UNIT_TYPO"}
                return {"score": 0.75, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_SECTOR"}

            if same_outward:
                if t_pc["is_partial"] or c_pc["is_partial"]:
                    return {"score": 0.65, "target_value": t_val, "candidate_value": c_val, "match_type": "PARTIAL_OUTWARD_MATCH"}
                if t_pc["unit"] and t_pc["unit"] == c_pc["unit"]:
                    return {"score": 0.72, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_OUTWARD_AND_UNIT_SECTOR_TYPO"}
                return {"score": 0.55, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_OUTWARD"}

            if t_pc["inward"] and t_pc["inward"] == c_pc["inward"]:
                out_sim = _damerau_levenshtein_sim(t_pc["outward"], c_pc["outward"])
                if out_sim >= 0.66:
                    return {"score": 0.65, "target_value": t_val, "candidate_value": c_val, "match_type": "OUTWARD_TYPO_INWARD_EXACT"}

            if t_pc["area"] and t_pc["area"] == c_pc["area"]:
                return {"score": 0.25, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_AREA_ONLY"}

            return {"score": 0.0, "target_value": t_val, "candidate_value": c_val, "match_type": "CONFLICT"}

        sim = _damerau_levenshtein_sim(t_val.replace(" ", ""), c_val.replace(" ", ""))
        return {
            "score": round(sim * 0.7, 4) if sim >= 0.7 else 0.0,
            "target_value": t_val,
            "candidate_value": c_val,
            "match_type": "FUZZY" if sim >= 0.7 else "CONFLICT",
        }

    def _check_flat_suffix_equivalence(t_parsed: dict, c_parsed: dict) -> tuple:
        """
        Check if one side encodes a flat as a building number suffix (`14A`) while the
        other side encodes it as a sub-building + base number (`Flat A, 14` or `Flat 1, 14` or `Ground Floor Flat, 14`).
        Returns `(is_equivalent, score_boost, match_label)`.
        """
        t_rng = t_parsed["building_number_range"]
        c_rng = c_parsed["building_number_range"]
        if not t_rng or not c_rng:
            return False, 0.0, ""

        t_s, t_e, t_sfx = t_rng
        c_s, c_e, c_sfx = c_rng
        if t_s != c_s or t_e != c_e:
            return False, 0.0, ""

        t_sub = t_parsed["sub_info"]
        c_sub = c_parsed["sub_info"]

        if t_sfx and not c_sfx and not t_sub["has_sub"] and c_sub["has_sub"]:
            sfx_letter = t_sfx
            c_id = c_sub["id"]
            if c_id == sfx_letter or NUMBER_TO_LETTER_MAP.get(c_id) == sfx_letter:
                sc = 0.96 if c_id == sfx_letter else 0.92
                return True, sc, "FLAT_SUFFIX_EQUIVALENT"
            if sfx_letter == "A" and c_sub["floor"] == 0 and not c_id:
                return True, 0.88, "GROUND_FLOOR_SUFFIX_EQUIVALENT"
            if sfx_letter == "B" and c_sub["floor"] == 1 and not c_id:
                return True, 0.86, "FIRST_FLOOR_SUFFIX_EQUIVALENT"

        if c_sfx and not t_sfx and not c_sub["has_sub"] and t_sub["has_sub"]:
            sfx_letter = c_sfx
            t_id = t_sub["id"]
            if t_id == sfx_letter or NUMBER_TO_LETTER_MAP.get(t_id) == sfx_letter:
                sc = 0.96 if t_id == sfx_letter else 0.92
                return True, sc, "FLAT_SUFFIX_EQUIVALENT"
            if sfx_letter == "A" and t_sub["floor"] == 0 and not t_id:
                return True, 0.88, "GROUND_FLOOR_SUFFIX_EQUIVALENT"
            if sfx_letter == "B" and t_sub["floor"] == 1 and not t_id:
                return True, 0.86, "FIRST_FLOOR_SUFFIX_EQUIVALENT"

        return False, 0.0, ""

    def _score_building_number(t_parsed: dict, c_parsed: dict, bn_res: dict, street_score: float) -> dict:
        """Score Building / Premise Number (including ranges, suffixes, flat-suffix equivalences, and cooperative name matching)."""
        t_val = t_parsed["building_number"]
        c_val = c_parsed["building_number"]
        t_rng = t_parsed["building_number_range"]
        c_rng = c_parsed["building_number_range"]

        if not t_rng and not c_rng:
            return {
                "score": 1.0,
                "target_value": "",
                "candidate_value": "",
                "match_type": "NOT_APPLICABLE",
            }

        if not t_rng or not c_rng:
            # Cooperative premise match ONLY when both sides actually share an explicit building name
            has_real_bname_match = (
                bool(t_parsed["building_name"])
                and bool(c_parsed["building_name"])
                and bn_res["match_type"] not in ("NOT_APPLICABLE", "MISSING_ONE_SIDE", "CONFLICT")
                and bn_res["score"] >= 0.88
            )
            if has_real_bname_match and street_score >= 0.80:
                return {
                    "score": 0.92,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "COOPERATIVE_NAME_MATCH",
                }
            return {
                "score": 0.10,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "MISSING_ONE_SIDE",
            }

        if t_val == c_val:
            return {
                "score": 1.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "EXACT",
            }

        is_eq, eq_sc, eq_label = _check_flat_suffix_equivalence(t_parsed, c_parsed)
        if is_eq:
            return {
                "score": eq_sc,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": eq_label,
            }

        t_s, t_e, t_sfx = t_rng
        c_s, c_e, c_sfx = c_rng

        if t_s == c_s and t_e == c_e:
            if not t_sfx or not c_sfx:
                return {
                    "score": 0.70,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "BASE_NUMBER_MATCH_SUFFIX_DIFF",
                }
            return {
                "score": 0.25,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "SUFFIX_CONFLICT",
            }

        overlap_start = max(t_s, c_s)
        overlap_end = min(t_e, c_e)
        if overlap_start <= overlap_end:
            if t_s == t_e or c_s == c_e:
                single_n = t_s if t_s == t_e else c_s
                rng_s, rng_e = (c_s, c_e) if t_s == t_e else (t_s, t_e)
                if single_n in (rng_s, rng_e) or (single_n % 2 == rng_s % 2):
                    return {
                        "score": 0.90,
                        "target_value": t_val,
                        "candidate_value": c_val,
                        "match_type": "RANGE_MATCH",
                    }
                if (rng_e - rng_s) <= 4:
                    return {
                        "score": 0.86,
                        "target_value": t_val,
                        "candidate_value": c_val,
                        "match_type": "RANGE_CONTIGUOUS_MATCH",
                    }
                return {
                    "score": 0.72,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "RANGE_OPPOSITE_PARITY",
                }
            return {
                "score": 0.85,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "RANGE_OVERLAP",
            }

        return {
            "score": 0.0,
            "target_value": t_val,
            "candidate_value": c_val,
            "match_type": "CONFLICT",
        }

    def _score_sub_building(t_parsed: dict, c_parsed: dict) -> dict:
        """Score Sub-building / Flat / Unit / Floor / Block component."""
        t_sub = t_parsed["sub_info"]
        c_sub = c_parsed["sub_info"]
        t_val = t_parsed["sub_building"]
        c_val = c_parsed["sub_building"]

        is_eq, eq_sc, eq_label = _check_flat_suffix_equivalence(t_parsed, c_parsed)
        if is_eq:
            return {
                "score": eq_sc,
                "target_value": t_val or t_parsed["building_number"],
                "candidate_value": c_val or c_parsed["building_number"],
                "match_type": eq_label,
            }

        if not t_sub["has_sub"] and not c_sub["has_sub"]:
            return {
                "score": 1.0,
                "target_value": "",
                "candidate_value": "",
                "match_type": "NOT_APPLICABLE",
            }

        if t_sub["has_sub"] != c_sub["has_sub"]:
            return {
                "score": 0.40,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "PARENT_CHILD_PARTIAL",
            }

        if t_val == c_val:
            return {
                "score": 1.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "EXACT",
            }

        # Check explicit block conflict first ("Block 1, Flat 2" vs "Block 2, Flat 2")
        if t_sub["block_id"] and c_sub["block_id"] and t_sub["block_id"] != c_sub["block_id"]:
            return {
                "score": 0.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "CONFLICT",
            }

        # Check explicit positional floor modifier conflict ("Front" vs "Rear", "Left" vs "Right")
        if t_sub["pos"] and c_sub["pos"] and t_sub["pos"] != c_sub["pos"]:
            return {
                "score": 0.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "CONFLICT",
            }

        t_id, c_id = t_sub["id"], c_sub["id"]
        t_fl, c_fl = t_sub["floor"], c_sub["floor"]
        t_tp, c_tp = t_sub["type"], c_sub["type"]

        # Do not equate "BLOCK 1" with "FLAT 1"
        types_compatible = (
            t_tp == c_tp
            or not t_tp
            or not c_tp
            or (t_tp in DWELLING_SUB_TYPES and c_tp in DWELLING_SUB_TYPES)
        )

        # Check Scottish tenement notation vs explicit Floor + Flat ("2F1" vs "2nd Floor Flat 1")
        m_sc_t = re.match(r"^([0-9]|G)F([0-9]+)$", t_id)
        m_sc_c = re.match(r"^([0-9]|G)F([0-9]+)$", c_id)
        if m_sc_t and not m_sc_c and c_fl is not None and c_id:
            fl_t = 0 if m_sc_t.group(1) == "G" else int(m_sc_t.group(1))
            if fl_t == c_fl and m_sc_t.group(2) == c_id:
                return {
                    "score": 0.94,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "CANONICAL_EXACT",
                }
        if m_sc_c and not m_sc_t and t_fl is not None and t_id:
            fl_c = 0 if m_sc_c.group(1) == "G" else int(m_sc_c.group(1))
            if fl_c == t_fl and m_sc_c.group(2) == t_id:
                return {
                    "score": 0.94,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "CANONICAL_EXACT",
                }

        if t_id and c_id:
            if t_id == c_id and types_compatible:
                return {
                    "score": 1.0,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "CANONICAL_EXACT",
                }
            if types_compatible and (LETTER_TO_NUMBER_MAP.get(t_id) == c_id or LETTER_TO_NUMBER_MAP.get(c_id) == t_id):
                return {
                    "score": 0.94,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "LETTER_NUMBER_EQUIVALENT",
                }
            # Different flat/unit identifiers even on the same floor ("2F1" vs "2F2", "1st Flr Flat 1" vs "Flat 2") -> CONFLICT
            return {
                "score": 0.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "CONFLICT",
            }

        if t_fl is not None and c_fl is not None and not t_id and not c_id:
            if t_fl == c_fl:
                return {
                    "score": 0.95,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "FLOOR_EXACT",
                }
            return {
                "score": 0.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "CONFLICT",
            }

        if (t_fl == 0 and c_id in ("1", "A", "G")) or (c_fl == 0 and t_id in ("1", "A", "G")):
            return {
                "score": 0.88,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "FLOOR_ID_EQUIVALENT",
            }
        if (t_fl == 1 and c_id in ("2", "B")) or (c_fl == 1 and t_id in ("2", "B")):
            return {
                "score": 0.84,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "FLOOR_ID_EQUIVALENT",
            }
        if (t_fl is not None and not t_id and c_id) or (c_fl is not None and not c_id and t_id):
            return {
                "score": 0.25,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "CONFLICT",
            }

        sim = _token_similarity(t_val, c_val)
        return {
            "score": round(sim, 4),
            "target_value": t_val,
            "candidate_value": c_val,
            "match_type": "FUZZY" if sim >= 0.70 else "CONFLICT",
        }

    def _score_street(t_parsed: dict, c_parsed: dict) -> dict:
        """Score Primary and Dependent Street / Thoroughfare."""
        t_st = t_parsed["street"]
        c_st = c_parsed["street"]
        t_dep = t_parsed["dependent_street"]
        c_dep = c_parsed["dependent_street"]

        if not t_st and not c_st:
            return {
                "score": 1.0,
                "target_value": "",
                "candidate_value": "",
                "match_type": "NOT_APPLICABLE",
            }

        if not t_st or not c_st:
            if t_st and c_parsed["building_name"] and _token_similarity(t_st, c_parsed["building_name"]) >= 0.90:
                return {
                    "score": 0.94,
                    "target_value": t_st,
                    "candidate_value": c_parsed["building_name"],
                    "match_type": "CROSS_FIELD_BUILDING_STREET_MATCH",
                }
            if c_st and t_parsed["building_name"] and _token_similarity(c_st, t_parsed["building_name"]) >= 0.90:
                return {
                    "score": 0.94,
                    "target_value": t_parsed["building_name"],
                    "candidate_value": c_st,
                    "match_type": "CROSS_FIELD_BUILDING_STREET_MATCH",
                }
            return {
                "score": 0.15,
                "target_value": t_st,
                "candidate_value": c_st,
                "match_type": "MISSING_ONE_SIDE",
            }

        if t_st == c_st:
            return {
                "score": 1.0,
                "target_value": t_st,
                "candidate_value": c_st,
                "match_type": "CANONICAL_EXACT",
            }

        # Dependent street cross-matching ONLY when not an "OFF <parent road>" reference
        if (t_dep and not t_parsed["dependent_was_off"] and t_dep == c_st) or (
            c_dep and not c_parsed["dependent_was_off"] and c_dep == t_st
        ):
            return {
                "score": 0.96,
                "target_value": f"{t_st} ({t_dep})".strip(" ()"),
                "candidate_value": f"{c_st} ({c_dep})".strip(" ()"),
                "match_type": "DEPENDENT_STREET_MATCH",
            }

        t_core = t_parsed["street_core"]
        c_core = c_parsed["street_core"]
        t_sfx = t_parsed["street_suffix"]
        c_sfx = c_parsed["street_suffix"]

        if t_core and c_core and t_core == c_core:
            if not t_sfx or not c_sfx:
                return {
                    "score": 0.90,
                    "target_value": t_st,
                    "candidate_value": c_st,
                    "match_type": "CORE_EXACT_SUFFIX_OMITTED",
                }
            return {
                "score": 0.78,
                "target_value": t_st,
                "candidate_value": c_st,
                "match_type": "CORE_EXACT_SUFFIX_DIFF",
            }

        # Check explicit directional opposition ("NORTH STREET" vs "SOUTH STREET")
        t_core_toks = t_core.split()
        c_core_toks = c_core.split()
        for tok in t_core_toks:
            opp = DIRECTIONAL_OPPOSITES.get(tok)
            if opp and opp in c_core_toks:
                return {
                    "score": 0.20,
                    "target_value": t_st,
                    "candidate_value": c_st,
                    "match_type": "CONFLICT",
                }

        # Score primarily on street core so sharing generic suffix ("STREET"/"ROAD") does not inflate unrelated streets
        core_sim = max(_string_similarity(t_core, c_core), _token_similarity(t_core, c_core)) if (t_core and c_core) else 0.0
        core_sim = _guard_short_core_sim(t_core, c_core, core_sim)

        sfx_bonus = 0.05 if (t_sfx and t_sfx == c_sfx and core_sim >= 0.75) else (-0.06 if (t_sfx and c_sfx and t_sfx != c_sfx) else 0.0)
        combined_sim = min(0.98, max(0.0, core_sim + sfx_bonus))

        # UK phonetic match on multi-syllable core street name (e.g., BEAUCHAMP <-> BEECHAM)
        if t_core and c_core and max(len(t_core), len(c_core)) >= 6 and min(len(t_core), len(c_core)) >= 5:
            if _uk_phonetic_phrase(t_core) == _uk_phonetic_phrase(c_core) and _string_similarity(t_core, c_core) >= 0.62:
                phon_score = 0.92 if (t_sfx == c_sfx) else 0.84
                if phon_score > combined_sim:
                    return {
                        "score": phon_score,
                        "target_value": t_st,
                        "candidate_value": c_st,
                        "match_type": "PHONETIC_MATCH",
                    }

        match_type = "FUZZY_TYPO" if combined_sim >= 0.78 else ("PARTIAL" if combined_sim >= 0.50 else "CONFLICT")
        return {
            "score": round(combined_sim, 4),
            "target_value": t_st,
            "candidate_value": c_st,
            "match_type": match_type,
        }

    def _score_building_name(t_parsed: dict, c_parsed: dict) -> dict:
        """Score Building Name / House Name / Block Name / Commercial Organization."""
        t_bn = t_parsed["building_name"]
        c_bn = c_parsed["building_name"]

        if not t_bn and not c_bn:
            return {
                "score": 1.0,
                "target_value": "",
                "candidate_value": "",
                "match_type": "NOT_APPLICABLE",
            }

        if not t_bn and c_bn and t_parsed["street"] and _token_similarity(c_bn, t_parsed["street"]) >= 0.90:
            return {
                "score": 0.94,
                "target_value": t_parsed["street"],
                "candidate_value": c_bn,
                "match_type": "CROSS_FIELD_MATCH",
            }
        if not c_bn and t_bn and c_parsed["street"] and _token_similarity(t_bn, c_parsed["street"]) >= 0.90:
            return {
                "score": 0.94,
                "target_value": t_bn,
                "candidate_value": c_parsed["street"],
                "match_type": "CROSS_FIELD_MATCH",
            }

        if not t_bn or not c_bn:
            return {
                "score": 0.15,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "MISSING_ONE_SIDE",
            }

        if t_bn == c_bn:
            return {
                "score": 1.0,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "EXACT",
            }

        t_clean = re.sub(r"^THE\s+", "", t_bn).strip()
        c_clean = re.sub(r"^THE\s+", "", c_bn).strip()
        if t_clean == c_clean:
            return {
                "score": 0.99,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "CANONICAL_EXACT",
            }

        m_po_t = re.search(r"\bPO BOX\s+(\d+[A-Z]?)\b", t_clean)
        m_po_c = re.search(r"\bPO BOX\s+(\d+[A-Z]?)\b", c_clean)
        if m_po_t or m_po_c:
            if m_po_t and m_po_c and m_po_t.group(1) == m_po_c.group(1):
                return {
                    "score": 1.0,
                    "target_value": t_bn,
                    "candidate_value": c_bn,
                    "match_type": "PO_BOX_EXACT",
                }
            return {
                "score": 0.0,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "CONFLICT",
            }

        def _strip_bname_suffixes(toks: list) -> tuple:
            stripped = list(toks)
            sfx_parts = []
            while len(stripped) >= 2 and (
                stripped[-1] in BUILDING_NAME_SUFFIXES
                or stripped[-1] in DUAL_PURPOSE_SUFFIXES
                or stripped[-1] in BUILDING_GENERIC_SUFFIX_TOKENS
            ):
                sfx_parts.insert(0, stripped.pop())
            return " ".join(stripped), " ".join(sfx_parts)

        t_core, t_sfx = _strip_bname_suffixes(t_clean.split())
        c_core, c_sfx = _strip_bname_suffixes(c_clean.split())

        if t_core == c_core and t_core:
            sc = 0.92 if (not t_sfx or not c_sfx) else 0.80
            return {
                "score": sc,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "CORE_BUILDING_NAME_MATCH",
            }

        core_sim = max(_string_similarity(t_core, c_core), _token_similarity(t_core, c_core))
        core_sim = _guard_short_core_sim(t_core, c_core, core_sim)

        sfx_adj = 0.03 if (t_sfx and t_sfx == c_sfx and core_sim >= 0.70) else (-0.05 if (t_sfx and c_sfx and t_sfx != c_sfx) else 0.0)
        sim = min(0.98, max(0.0, core_sim + sfx_adj))

        if (
            sim < 0.88
            and t_core
            and c_core
            and max(len(t_core), len(c_core)) >= 6
            and min(len(t_core), len(c_core)) >= 5
            and _uk_phonetic_phrase(t_core) == _uk_phonetic_phrase(c_core)
            and _string_similarity(t_core, c_core) >= 0.62
        ):
            sim = max(sim, 0.88 if t_sfx == c_sfx else 0.82)
            m_type = "PHONETIC_MATCH"
        else:
            m_type = "FUZZY_TYPO" if sim >= 0.75 else "CONFLICT"

        return {
            "score": round(sim, 4),
            "target_value": t_bn,
            "candidate_value": c_bn,
            "match_type": m_type,
        }

    def _score_locality(t_parsed: dict, c_parsed: dict) -> dict:
        """Score Locality / Post Town / County / Greater London Borough."""
        t_loc = t_parsed["locality"]
        c_loc = c_parsed["locality"]
        t_town = t_parsed["town"] or t_loc
        c_town = c_parsed["town"] or c_loc

        if not t_loc and not c_loc:
            return {
                "score": 0.80,
                "target_value": "",
                "candidate_value": "",
                "match_type": "BOTH_MISSING",
            }

        if not t_loc or not c_loc:
            return {
                "score": 0.65,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "MISSING_ONE_SIDE",
            }

        if t_loc == c_loc:
            return {
                "score": 1.0,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "EXACT",
            }

        if t_town and c_town and t_town == c_town:
            return {
                "score": 0.98,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "TOWN_EXACT_COUNTY_OPTIONAL",
            }

        t_set = set(t_town.split())
        c_set = set(c_town.split())
        if t_set and c_set and (t_set.issubset(c_set) or c_set.issubset(t_set)):
            return {
                "score": 0.95,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "SUBSET_MATCH",
            }

        # Check Greater London Borough / District <-> "LONDON" via exact clause/town match (not substring!)
        t_is_london = t_town == "LONDON" or t_loc == "GREATER LONDON"
        c_is_london = c_town == "LONDON" or c_loc == "GREATER LONDON"
        t_in_london = (
            t_town in LONDON_BOROUGHS_AND_DISTRICTS
            or any(cl in LONDON_BOROUGHS_AND_DISTRICTS for cl in t_parsed["locality_clauses"])
        )
        c_in_london = (
            c_town in LONDON_BOROUGHS_AND_DISTRICTS
            or any(cl in LONDON_BOROUGHS_AND_DISTRICTS for cl in c_parsed["locality_clauses"])
        )
        if (t_is_london and c_in_london) or (c_is_london and t_in_london):
            return {
                "score": 0.92,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "LONDON_BOROUGH_EQUIVALENT",
            }

        sim = max(_string_similarity(t_town, c_town), _token_similarity(t_loc, c_loc))
        if (
            sim < 0.88
            and t_town
            and c_town
            and max(len(t_town), len(c_town)) >= 6
            and _uk_phonetic_phrase(t_town) == _uk_phonetic_phrase(c_town)
            and _string_similarity(t_town, c_town) >= 0.58
        ):
            sim = max(sim, 0.90)
            m_type = "PHONETIC_MATCH"
        else:
            m_type = "FUZZY_TYPO" if sim >= 0.75 else "CONFLICT"

        return {
            "score": round(sim, 4),
            "target_value": t_loc,
            "candidate_value": c_loc,
            "match_type": m_type,
        }

    def _score_line_alignment(t_parsed: dict, c_parsed: dict) -> dict:
        """Compute hybrid positional (address1..3) and full-address bag-of-tokens similarity."""
        t_lines = t_parsed["normalized_lines"]
        c_lines = c_parsed["normalized_lines"]

        line_scores = []
        active_pos_scores = []
        for i in range(3):
            tl = t_lines[i] if i < len(t_lines) else ""
            cl = c_lines[i] if i < len(c_lines) else ""
            if not tl and not cl:
                line_scores.append(1.0)
            elif not tl or not cl:
                line_scores.append(0.0)
                active_pos_scores.append(0.0)
            else:
                sc = round(_token_similarity(tl, cl, ignore_stopwords=False), 4)
                line_scores.append(sc)
                active_pos_scores.append(sc)

        pos_avg = sum(active_pos_scores) / len(active_pos_scores) if active_pos_scores else 1.0
        full_tok_sim = _token_similarity(t_parsed["full_tokens_str"], c_parsed["full_tokens_str"], ignore_stopwords=True)

        # Blend 60% order/line-independent full token similarity + 40% positional line similarity
        blended = round(0.60 * full_tok_sim + 0.40 * pos_avg, 4)
        return {
            "score": blended,
            "target_value": " | ".join(t_lines),
            "candidate_value": " | ".join(c_lines),
            "match_type": "EXACT" if blended >= 0.99 else "HYBRID_LINE_TOKEN",
            "line_breakdown": {
                "address1": line_scores[0],
                "address2": line_scores[1],
                "address3": line_scores[2],
                "full_token_set": round(full_tok_sim, 4),
            },
        }

    # =========================================================================
    # 6. DYNAMIC WEIGHTING, COOPERATIVE PREMISE & CONFLICT MULTIPLIER ENGINE
    # =========================================================================

    BASE_WEIGHTS = {
        "building_number": 0.24,
        "postcode": 0.22,
        "sub_building": 0.16,
        "street": 0.16,
        "building_name": 0.12,
        "locality": 0.05,
        "line_alignment": 0.05,
    }

    def _evaluate_candidate(uprn, raw_cand: list, t_parsed: dict) -> dict:
        c_parsed = _parse_address_record(raw_cand)

        pc_res = _score_postcode(t_parsed["postcode_info"], c_parsed["postcode_info"])
        st_res = _score_street(t_parsed, c_parsed)
        bn_res = _score_building_name(t_parsed, c_parsed)
        num_res = _score_building_number(t_parsed, c_parsed, bn_res, st_res["score"])
        sub_res = _score_sub_building(t_parsed, c_parsed)
        loc_res = _score_locality(t_parsed, c_parsed)
        line_res = _score_line_alignment(t_parsed, c_parsed)

        if bn_res["match_type"] == "MISSING_ONE_SIDE" and num_res["score"] >= 0.90 and st_res["score"] >= 0.80:
            bn_res["score"] = 0.92
            bn_res["match_type"] = "COOPERATIVE_OMITTED_WITH_NUMBER_MATCH"

        raw_scores = {
            "postcode": pc_res,
            "building_number": num_res,
            "sub_building": sub_res,
            "street": st_res,
            "building_name": bn_res,
            "locality": loc_res,
            "line_alignment": line_res,
        }

        weights = dict(BASE_WEIGHTS)

        if num_res["match_type"] == "NOT_APPLICABLE":
            weights["building_number"] = 0.0
            if bn_res["match_type"] != "NOT_APPLICABLE":
                weights["building_name"] += BASE_WEIGHTS["building_number"]

        if bn_res["match_type"] == "NOT_APPLICABLE":
            weights["building_name"] = 0.0

        if sub_res["match_type"] == "NOT_APPLICABLE":
            weights["sub_building"] = 0.0

        if st_res["match_type"] == "NOT_APPLICABLE":
            weights["street"] = 0.0

        if pc_res["match_type"] == "MISSING_ONE_SIDE":
            weights["postcode"] = 0.08
        elif pc_res["match_type"] == "BOTH_MISSING":
            weights["postcode"] = 0.0

        total_w = sum(weights.values())
        if total_w > 0:
            norm_weights = {k: round(v / total_w, 4) for k, v in weights.items()}
        else:
            norm_weights = {k: round(1.0 / len(weights), 4) for k in weights}

        residual = round(1.0 - sum(norm_weights.values()), 4)
        if residual != 0.0:
            max_k = max(norm_weights, key=lambda k: norm_weights[k])
            norm_weights[max_k] = round(norm_weights[max_k] + residual, 4)

        pre_penalty_score = 0.0
        component_scores_out = {}
        for comp_name, res in raw_scores.items():
            w = norm_weights[comp_name]
            s = round(res["score"], 4)
            ws = round(w * s, 4)
            pre_penalty_score += w * s
            comp_entry = {
                "score": s,
                "weight": w,
                "weighted_score": ws,
                "target_value": res["target_value"],
                "candidate_value": res["candidate_value"],
                "match_type": res["match_type"],
            }
            if "line_breakdown" in res:
                comp_entry["line_breakdown"] = res["line_breakdown"]
            component_scores_out[comp_name] = comp_entry

        pre_penalty_score = min(1.0, max(0.0, pre_penalty_score))

        penalties = []
        multiplier = 1.0

        if num_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "BUILDING_NUMBER_CONFLICT", "multiplier": 0.45})
            multiplier *= 0.45
        elif num_res["match_type"] == "SUFFIX_CONFLICT":
            penalties.append({"reason": "BUILDING_NUMBER_SUFFIX_CONFLICT", "multiplier": 0.55})
            multiplier *= 0.55
        elif num_res["match_type"] == "MISSING_ONE_SIDE":
            penalties.append({"reason": "BUILDING_NUMBER_MISSING_ONE_SIDE", "multiplier": 0.62})
            multiplier *= 0.62

        if sub_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "SUB_BUILDING_CONFLICT", "multiplier": 0.55})
            multiplier *= 0.55
        elif sub_res["match_type"] == "PARENT_CHILD_PARTIAL":
            penalties.append({"reason": "PARENT_CHILD_SUB_BUILDING_MISMATCH", "multiplier": 0.82})
            multiplier *= 0.82

        if bn_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "BUILDING_NAME_CONFLICT", "multiplier": 0.60})
            multiplier *= 0.60
        elif bn_res["match_type"] == "MISSING_ONE_SIDE" and num_res["match_type"] == "NOT_APPLICABLE":
            penalties.append({"reason": "BUILDING_NAME_MISSING_NO_NUMBER", "multiplier": 0.55})
            multiplier *= 0.55

        if st_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "STREET_CONFLICT", "multiplier": 0.55})
            multiplier *= 0.55

        if pc_res["match_type"] in ("CONFLICT", "SAME_AREA_ONLY"):
            non_pc_strong = (
                st_res["score"] >= 0.90
                and loc_res["score"] >= 0.85
                and (num_res["score"] >= 0.90 or bn_res["score"] >= 0.90)
            )
            pc_mult = 0.85 if non_pc_strong else 0.60
            penalties.append({"reason": "POSTCODE_CONFLICT", "multiplier": pc_mult})
            multiplier *= pc_mult

        overall_score = round(pre_penalty_score * multiplier, 4)
        pre_penalty_score = round(pre_penalty_score, 4)

        if overall_score >= 0.95 and multiplier == 1.0:
            confidence = "EXACT"
        elif overall_score >= 0.82 and multiplier >= 0.80:
            confidence = "HIGH"
        elif overall_score >= 0.65:
            confidence = "MEDIUM"
        elif overall_score >= 0.40:
            confidence = "LOW"
        else:
            confidence = "NO_MATCH"

        return {
            "uprn": uprn,
            "address": list(raw_cand) if isinstance(raw_cand, (list, tuple)) else [raw_cand],
            "overall_score": overall_score,
            "pre_penalty_score": pre_penalty_score,
            "confidence": confidence,
            "is_ambiguous": False,
            "ambiguity_note": None,
            "penalties_applied": penalties,
            "component_scores": component_scores_out,
        }

    # =========================================================================
    # 7. INVERTED-INDEX PRE-SCREENING FOR LARGE CANDIDATE POOLS (> 2,000)
    # =========================================================================

    t_parsed = _parse_address_record(target_address)

    if not candidates or not isinstance(candidates, dict):
        return {
            "target": {"raw": list(target_address) if isinstance(target_address, (list, tuple)) else [target_address], "parsed": t_parsed},
            "best_match": None,
            "candidates": [],
            "metadata": {"total_candidates": 0, "evaluated_candidates": 0, "shortlisted": False},
        }

    total_candidates = len(candidates)
    shortlisted_flag = False
    items_to_evaluate = list(candidates.items())

    if total_candidates > 2000:
        shortlisted_flag = True
        pc_full_idx = collections.defaultdict(list)
        pc_out_idx = collections.defaultdict(list)
        num_idx = collections.defaultdict(list)
        tok_idx = collections.defaultdict(list)
        all_cand_map = {}

        for uprn, raw_c in items_to_evaluate:
            all_cand_map[uprn] = raw_c
            rec_c = list(raw_c) if isinstance(raw_c, (list, tuple)) else [raw_c]
            while len(rec_c) < 4:
                rec_c.append("")
            pc_slot = _strip_postcode_noise("" if rec_c[3] is None else str(rec_c[3]))
            c_str_raw = " ".join("" if x is None else str(x) for x in rec_c[:3]).upper()
            if not pc_slot:
                m_emb = EMBEDDED_POSTCODE_RE.search(c_str_raw)
                if m_emb:
                    pc_slot = m_emb.group(1)

            pc_compact = pc_slot.replace(" ", "")
            if pc_compact:
                pc_full_idx[pc_compact].append(uprn)
                if pc_compact.startswith("BFPO"):
                    pc_out_idx["BFPO"].append(uprn)
                elif len(pc_compact) >= 5:
                    pc_out_idx[pc_compact[:-3]].append(uprn)
                else:
                    pc_out_idx[pc_compact].append(uprn)

            # Fast normalized tokens & house numbers (including cardinal words and ranges)
            c_ascii = unicodedata.normalize("NFKD", c_str_raw).encode("ascii", "ignore").decode("ascii")
            c_ascii = re.sub(r"['’`]", "", c_ascii)
            raw_words = re.findall(r"[A-Z0-9]+", c_ascii)
            seen_toks = set()
            seen_nums = set()
            for w in raw_words:
                w_can = STREET_SUFFIX_MAP.get(w, BUILDING_NAME_CANONICAL.get(w, w))
                if w_can not in seen_toks:
                    seen_toks.add(w_can)
                    tok_idx[w_can].append(uprn)
                if w in CARDINAL_WORDS:
                    n_str = str(CARDINAL_WORDS[w])
                    if n_str not in seen_nums:
                        seen_nums.add(n_str)
                        num_idx[n_str].append(uprn)
                elif w[0].isdigit():
                    m_base = re.match(r"^(\d{1,5})", w)
                    if m_base:
                        b_str = m_base.group(1)
                        if b_str not in seen_nums:
                            seen_nums.add(b_str)
                            num_idx[b_str].append(uprn)
                    if w not in seen_nums:
                        seen_nums.add(w)
                        num_idx[w].append(uprn)
            # Index explicit numeric ranges like 12-16
            for m_rng in re.finditer(r"\b(\d{1,5})-(\d{1,5})\b", c_ascii):
                rs, re_ = int(m_rng.group(1)), int(m_rng.group(2))
                if 0 < re_ - rs <= 20:
                    for val in range(rs, re_ + 1):
                        v_str = str(val)
                        if v_str not in seen_nums:
                            seen_nums.add(v_str)
                            num_idx[v_str].append(uprn)

        scores_acc = collections.defaultdict(float)
        t_pc_full = t_parsed["postcode"].replace(" ", "")
        t_pc_out = t_parsed["postcode_info"]["outward"]

        if t_pc_full:
            for u in pc_full_idx.get(t_pc_full, ()):
                scores_acc[u] += 6.0
        if t_pc_out:
            for u in pc_out_idx.get(t_pc_out, ()):
                scores_acc[u] += 2.5

        t_rng = t_parsed["building_number_range"]
        if t_rng:
            for n_val in range(t_rng[0], min(t_rng[1], t_rng[0] + 20) + 1):
                for u in num_idx.get(str(n_val), ()):
                    scores_acc[u] += 3.5

        t_toks = set(t_parsed["full_tokens_str"].split())
        if t_parsed["sub_info"]["id"]:
            t_toks.add(t_parsed["sub_info"]["id"])
        for tok in t_toks:
            postings = tok_idx.get(tok)
            if postings:
                idf = 1.0 / math.log(2.0 + len(postings))
                weight = 1.0 + 2.5 * idf
                for u in postings:
                    scores_acc[u] += weight

        ranked_uprns = sorted(scores_acc.keys(), key=lambda u: scores_acc[u], reverse=True)[:500]
        if len(ranked_uprns) < 500:
            ranked_set = set(ranked_uprns)
            for u in all_cand_map:
                if u not in ranked_set:
                    ranked_uprns.append(u)
                    ranked_set.add(u)
                    if len(ranked_uprns) >= 500:
                        break
        items_to_evaluate = [(u, all_cand_map[u]) for u in ranked_uprns]

    # =========================================================================
    # 8. SCORE ALL CANDIDATES, RANK & CHECK AMBIGUITY
    # =========================================================================

    scored_candidates = [
        _evaluate_candidate(uprn, raw_cand, t_parsed)
        for uprn, raw_cand in items_to_evaluate
    ]

    scored_candidates.sort(
        key=lambda c: (
            c["overall_score"],
            c["pre_penalty_score"],
            c["component_scores"]["line_alignment"]["score"],
        ),
        reverse=True,
    )

    best_match = scored_candidates[0] if scored_candidates else None

    if best_match and len(scored_candidates) >= 2:
        runner_up = scored_candidates[1]
        diff = round(best_match["overall_score"] - runner_up["overall_score"], 4)
        is_strict_exact_winner = (
            best_match["overall_score"] == 1.0 and runner_up["overall_score"] < 1.0
        )
        if not is_strict_exact_winner and best_match["overall_score"] >= 0.60 and diff <= 0.025:
            best_match["is_ambiguous"] = True
            best_match["ambiguity_note"] = (
                f"Runner-up UPRN {runner_up['uprn']} scored {runner_up['overall_score']} "
                f"(within {diff} of best match {best_match['overall_score']})."
            )

    return {
        "target": {
            "raw": list(target_address) if isinstance(target_address, (list, tuple)) else [target_address],
            "parsed": {
                "postcode": t_parsed["postcode"],
                "outward_code": t_parsed["postcode_info"]["outward"],
                "inward_code": t_parsed["postcode_info"]["inward"],
                "sub_building": t_parsed["sub_building"],
                "sub_building_canonical": t_parsed["sub_building_canonical"],
                "building_number": t_parsed["building_number"],
                "building_number_range": t_parsed["building_number_range"],
                "building_name": t_parsed["building_name"],
                "street": t_parsed["street"],
                "dependent_street": t_parsed["dependent_street"],
                "locality": t_parsed["locality"],
                "normalized_lines": t_parsed["normalized_lines"],
            },
        },
        "best_match": best_match,
        "candidates": scored_candidates,
        "metadata": {
            "total_candidates": total_candidates,
            "evaluated_candidates": len(scored_candidates),
            "shortlisted": shortlisted_flag,
        },
    }
