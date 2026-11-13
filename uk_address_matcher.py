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
    import math
    import re
    import unicodedata

    # =========================================================================
    # 1. COMPREHENSIVE UK DOMAIN LOOKUP TABLES & DICTIONARIES
    # =========================================================================

    # Saints and St-prefix place/street names where "ST" means "SAINT", not "STREET"
    SAINT_NAMES = {
        "ABBS", "ALBANS", "ALDATES", "ANDREWS", "ANNES", "ANNS", "ANTHONY",
        "ASAPH", "AUGUSTINES", "AUSTELL", "BARNABAS", "BARTHOLOMEWS", "BEES",
        "BENETS", "BLAIZE", "BOTOLPHS", "BRIDES", "BUDEAUX", "CATHERINES",
        "CHADS", "CLAIRS", "CLEMENTS", "COLUMB", "CROSS", "CUTHBERT", "CUTHBERTS",
        "CYRES", "DAVIDS", "DENYS", "DOGMAELS", "DOMINICK", "DUNSTANS", "EDMUNDS",
        "EDWARDS", "ENODER", "ERTH", "EVAL", "EWE", "FAGANS", "FAITHS", "FILLANS",
        "FINBARRS", "FRANCIS", "GALL", "GENNYS", "GEORGE", "GEORGES", "GERMANS",
        "GILES", "GOVANS", "GREGORYS", "HELEN", "HELENS", "HILDA", "HILDAS",
        "HILARY", "ILLTYDS", "ISSEY", "IVES", "JAMES", "JOHNS", "JOHN", "JOSEPHS",
        "JUDE", "JUDES", "JULIANS", "JUST", "KATHERINES", "KEVERNE", "KEW",
        "KEYNE", "LAWRENCE", "LEONARDS", "LEVAN", "LUKES", "MABYN", "MAGNUS",
        "MARGARETS", "MARKS", "MARTINS", "MARTIN", "MARY", "MARYS", "MATTHEWS",
        "MAWES", "MELLONS", "MERRYN", "MEWAN", "MICHAEL", "MICHAELS", "MINVER",
        "MONANS", "NEOT", "NEOTS", "NICHOLAS", "NINIANS", "OLAVES", "OSWALD",
        "OSWALDS", "OSYTH", "PANCRAS", "PATRICKS", "PAUL", "PAULS", "PETERS",
        "PETER", "PHILIPS", "piran", "PIRANS", "QUINTIN", "SAVIOUR", "SAVIOURS",
        "SEPULCHRE", "STEPHENS", "STEPHEN", "SWITHUN", "SWITHUNS", "TEATH",
        "THOMAS", "TUDY", "VEEP", "VINCENTS", "WENN", "WINNOW", "WOLSTANS",
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
        "10TH": 10, "TENTH": 10,
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
        "CHS": "CHASE", "CHASE": "CHASE",
        "CPS": "COPSE", "COPSE": "COPSE", "COPPICE": "COPPICE",
        "CRFT": "CROFT", "CROFT": "CROFT",
        "DENE": "DENE", "DEAN": "DENE",
        "DRFT": "DRIFT", "DRIFT": "DRIFT",
        "END": "END", "FURLONG": "FURLONG", "GARTH": "GARTH", "GATE": "GATE",
        "GLADE": "GLADE", "GLD": "GLADE", "GLEN": "GLEN", "GLEBE": "GLEBE",
        "HTH": "HEATH", "HEATH": "HEATH", "HEDGES": "HEDGES",
        "LEAZE": "LEAZE", "LEA": "LEA",
        "MEAD": "MEAD", "MDW": "MEADOW", "MEADOW": "MEADOW", "MEADOWS": "MEADOWS",
        "MWS": "MEWS", "MEWS": "MEWS",
        "MT": "MOUNT", "MOUNT": "MOUNT",
        "NOOK": "NOOK", "ORCHARD": "ORCHARD", "ORCHARDS": "ORCHARDS",
        "PTH": "PATH", "PATH": "PATH", "PATHWAY": "PATHWAY",
        "PADDOCK": "PADDOCK", "PADDOCKS": "PADDOCKS",
        "QUAD": "QUADRANT", "QUADRANT": "QUADRANT",
        "REACH": "REACH", "RDG": "RIDGE", "RIDGE": "RIDGE", "RIDGEWAY": "RIDGEWAY",
        "RISE": "RISE", "ROW": "ROW", "SIDE": "SIDE", "SPINNEY": "SPINNEY",
        "STRAND": "STRAND", "VLE": "VALE", "VALE": "VALE",
        "VLY": "VALLEY", "VALLEY": "VALLEY",
        "YD": "YARD", "YARD": "YARD",
        "COMMON": "COMMON", "LAWNS": "LAWNS", "LAWN": "LAWN",
        " EMBANKMENT": "EMBANKMENT", "EMBANKMENT": "EMBANKMENT",
        # Scottish street suffixes
        "BRAE": "BRAE", "BRAES": "BRAE", "WYND": "WYND", "LOAN": "LOAN",
        "LOANING": "LOANING", "GAIT": "GAIT", "VENNEL": "VENNEL", "PEND": "PEND",
        "RIGG": "RIGG", "KNOWE": "KNOWE", "LINKS": "LINKS",
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
        "WHARF", "ARCADE", "COPSE", "COPPICE", "DENE", "SPINNEY",
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

    # Sub-building type canonicalization
    SUB_BUILDING_TYPES = {
        "FLAT": "FLAT", "FLT": "FLAT", "FLATS": "FLAT",
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

    FLOOR_CANONICAL_MAP = {
        "SUB BASEMENT": -2, "LOWER GROUND": -1, "LWR GND": -1, "LWR GRD": -1,
        "LG": -1, "BASEMENT": -1, "BSMT": -1, "CELLAR": -1, "GARDEN": 0,
        "GROUND": 0, "GND": 0, "GRD": 0, "GF": 0, "G": 0,
        "FIRST": 1, "1ST": 1, "1F": 1,
        "SECOND": 2, "2ND": 2, "2F": 2,
        "THIRD": 3, "3RD": 3, "3F": 3,
        "FOURTH": 4, "4TH": 4, "4F": 4,
        "FIFTH": 5, "5TH": 5, "5F": 5,
        "SIXTH": 6, "6TH": 6, "SEVENTH": 7, "7TH": 7,
        "EIGHTH": 8, "8TH": 8, "NINTH": 9, "9TH": 9, "TENTH": 10, "10TH": 10,
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
        "DURHAM": "COUNTY DURHAM", "CO DURHAM": "COUNTY DURHAM", "COUNTY DURHAM": "COUNTY DURHAM",
        "TYNE AND WEAR": "TYNE AND WEAR", "MERSEYSIDE": "MERSEYSIDE",
        "GREATER MANCHESTER": "GREATER MANCHESTER", "GT MANCHESTER": "GREATER MANCHESTER",
        "WEST MIDLANDS": "WEST MIDLANDS", "W MIDLANDS": "WEST MIDLANDS",
        "GREATER LONDON": "GREATER LONDON",
        "AVON": "AVON", "CLEVELAND": "CLEVELAND", "HUMBERSIDE": "HUMBERSIDE",
        "HEREFORDSHIRE": "HEREFORDSHIRE", "HEREFORD": "HEREFORDSHIRE",
        "RUTLAND": "RUTLAND", "ISLE OF WIGHT": "ISLE OF WIGHT", "IOW": "ISLE OF WIGHT",
        # Wales & Scotland counties
        "PEMBS": "PEMBROKESHIRE", "PEMBROKESHIRE": "PEMBROKESHIRE",
        "CARMS": "CARMARTHENSHIRE", "CARMARTHENSHIRE": "CARMARTHENSHIRE",
        "GLAM": "GLAMORGAN", "MID GLAMORGAN": "GLAMORGAN", "SOUTH GLAMORGAN": "GLAMORGAN", "WEST GLAMORGAN": "GLAMORGAN",
        "MON": "MONMOUTHSHIRE", "MONMOUTHSHIRE": "MONMOUTHSHIRE",
        "GWENT": "GWENT", "GWYNEDD": "GWYNEDD", "POWYS": "POWYS", "CLWYD": "CLWYD", "DYFED": "DYFED",
        "CEREDIGION": "CEREDIGION", "ANGLESEY": "ANGLESEY", "ISLE OF ANGLESEY": "ANGLESEY",
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
        "KINGSTON", "RICHMOND", "HOUNSLOW", "HILLEDON", "HILLINGDON", "EALING",
        "BRENT", "HARROW", "BARNET", "ENFIELD", "HARINGEY",
        # Inner/Outer London Districts within LONDON post town
        "BATTERSEA", "BALHAM", "BELGRAVIA", "BERMONDSEY", "BETHNAL GREEN",
        "BLACKHEATH", "BLOOMSBURY", "BOW", "BRIXTON", "BROCKLEY", "CAMBERWELL",
        "CANARY WHARF", "CATFORD", "CHARLTON", "CHISWICK", "CLAPHAM",
        "CLERKENWELL", "COVENT GARDEN", "CRYSTAL PALACE", "DALSTON", "DEPTFORD",
        "DULWICH", "EARLS COURT", "EAST DULWICH", "ELEPHANT AND CASTLE",
        "ELTHAM", "FARRINGDON", "FINCHLEY", "FINSBURY", "FITZROVIA",
        "FOREST HILL", "GOLDERS GREEN", "HAMPSTEAD", "HARLESDEN", "HENDON",
        "HERNE HILL", "HIGHBURY", "HIGHGATE", "HOLBORN", "HOLLOWAY", "HOMERTON",
        "HOXTON", "KENNINGTON", "KENSAL GREEN", "KENTISH TOWN", "KILBURN",
        "KINGS CROSS", "KNIGHTSBRIDGE", "LEWISHAM", "LEYTON", "LEYTONSTONE",
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
        "ACTON",
    }

    COUNTRY_NOISE = {
        "UK", "U K", "UNITED KINGDOM", "GREAT BRITAIN", "GB", "GBR",
        "ENGLAND", "SCOTLAND", "WALES", "CYMRU", "NORTHERN IRELAND", "NI",
    }

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
            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
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

        # Use 3-row rolling buffer for memory efficiency
        prev2 = list(range(len2 + 1))
        prev1 = list(range(len2 + 1))
        curr = [0] * (len2 + 1)

        for i in range(1, len1 + 1):
            curr[0] = i
            c1 = s1[i - 1]
            for j in range(1, len2 + 1):
                c2 = s2[j - 1]
                cost = 0 if c1 == c2 else 1
                val = min(
                    prev1[j] + 1,       # deletion
                    curr[j - 1] + 1,    # insertion
                    prev1[j - 1] + cost # substitution
                )
                if i > 1 and j > 1 and c1 == s2[j - 2] and s1[i - 2] == c2:
                    val = min(val, prev2[j - 2] + 1)  # transposition
                curr[j] = val
            prev2, prev1, curr = prev1, curr, prev2

        dist = prev1[len2]
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

        # High-value British place/street orthographic reductions
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
            (" HAPPISBURGH", "HAZEBR"),
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

        # Keep first letter canonicalized
        first = w[0]
        if first == "C":
            first = "S" if w[1:2] in ("E", "I", "Y") else "K"
        elif first == "Q":
            first = "K"
        elif first == "X":
            first = "S"

        # Transform remainder into consonant skeleton
        rest = w[1:]
        # Soft C -> S, hard C -> K
        rest = re.sub(r"C(?=[EIY])", "S", rest)
        rest = rest.replace("C", "K").replace("Q", "K").replace("X", "KS").replace("Z", "S")
        # Silent W after S/T in UK suffixes (-SWICK, -TWorth)
        rest = re.sub(r"(?<=[ST])W(?=[IYO])", "", rest)
        # Drop H unless after S/C/T
        rest = re.sub(r"(?<![SCT])H", "", rest)
        # Drop vowels from interior
        rest = re.sub(r"[AEIOUY]", "", rest)
        # Collapse adjacent duplicate consonants
        collapsed = [first]
        for ch in rest:
            if ch != collapsed[-1]:
                collapsed.append(ch)
        return "".join(collapsed)

    def _uk_phonetic_phrase(phrase: str) -> str:
        tokens = [t for t in phrase.split() if t not in ("THE", "AND", "OF", "AT", "IN")]
        return " ".join(_uk_phonetic_word(t) for t in tokens if t)

    def _string_similarity(s1: str, s2: str) -> float:
        """Combined character-level similarity using max/blend of Jaro-Winkler and Damerau-Levenshtein."""
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        jw = _jaro_winkler(s1, s2)
        dl = _damerau_levenshtein_sim(s1, s2)
        return 0.55 * dl + 0.45 * jw

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
            # True token subset (one phrase's tokens are completely contained in the other)
            coverage = len(inter) / max(len(set1), len(set2))
            set_sim = max(set_sim, 0.82 + 0.18 * coverage)

        # 3. Greedy Bipartite Fuzzy Token Alignment (catches typos in individual words)
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
                if sc < 0.85 and len(tok_a) >= 4 and len(tok_b) >= 4:
                    if _uk_phonetic_word(tok_a) == _uk_phonetic_word(tok_b):
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
    EMBEDDED_POSTCODE_RE = re.compile(
        r"\b(GIR\s*0AA|[A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b"
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
        Returns `(canonical_postcode, outward, inward, sector, unit, edits)` or `None`.
        """
        s = re.sub(r"[^A-Z0-9]", "", raw_compact.upper())
        if len(s) < 5 or len(s) > 7:
            return None

        out_raw = s[:-3]
        in_raw = s[-3:]
        in_template = "DLL"

        # Repair inward code (1 digit + 2 letters)
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

        # Try valid outward templates for len(out_raw)
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

    def _parse_postcode(pc_raw: str, lines_raw: list) -> tuple:
        """
        Extract and parse UK postcode from `pc_raw` (or embedded in `lines_raw`).
        Returns `(postcode_info_dict, cleaned_lines)`.
        """
        cleaned_lines = list(lines_raw)
        pc_str = (pc_raw or "").strip().upper()
        pc_str = re.sub(r"[^A-Z0-9\s]", "", pc_str)
        pc_str = re.sub(r"\s+", " ", pc_str).strip()

        # If postcode slot is empty, check lines in reverse order for an embedded UK postcode
        if not pc_str:
            for idx in range(len(cleaned_lines) - 1, -1, -1):
                line_up = cleaned_lines[idx].upper()
                m_emb = EMBEDDED_POSTCODE_RE.search(line_up)
                if m_emb:
                    pc_str = m_emb.group(1).strip()
                    cleaned_lines[idx] = (
                        cleaned_lines[idx][: m_emb.start()]
                        + " "
                        + cleaned_lines[idx][m_emb.end() :]
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

        # Fallback unparsed string
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
        # Standardize ranges/slashes around numbers and letters
        s = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", s)
        s = re.sub(r"(?<=\d)\s+TO\s+(?=\d)", "-", s)
        # Replace other punctuation (except commas, hyphens, slashes) with spaces
        s = re.sub(r"[^A-Z0-9,\-/&\s]", " ", s)
        s = s.replace("&", " AND ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _normalize_written_numbers_in_clause(clause: str) -> str:
        """Convert leading or sub-building written numbers (ONE..NINETY NINE, FIRST..TENTH)."""
        tokens = clause.split()
        if not tokens:
            return clause

        # Convert compound cardinal numbers like TWENTY ONE -> 21
        out = []
        i = 0
        n = len(tokens)
        while i < n:
            tok = tokens[i]
            # Check tens + units (e.g., TWENTY FOUR)
            if (
                tok in ("TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY")
                and i + 1 < n
                and tokens[i + 1] in ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE")
            ):
                val = CARDINAL_WORDS[tok] + CARDINAL_WORDS[tokens[i + 1]]
                out.append(str(val))
                i += 2
                continue
            # Convert standalone cardinal word if at start of clause (before street/building)
            # or immediately after FLAT / UNIT / APT / SUITE / NO / NUMBER
            if tok in CARDINAL_WORDS:
                prev_tok = out[-1] if out else ""
                next_tok = tokens[i + 1] if i + 1 < n else ""
                is_sub_prefix = prev_tok in SUB_BUILDING_TYPES or prev_tok in ("NO", "NUMBER")
                is_clause_start = (i == 0 and n >= 2 and next_tok not in ("COTTAGE", "COTTAGES", "HOUSE", "BARN", "OAKS", "ELMS", "PINES", "ACRES", "MILE", "WAYS", "BRIDGES", "TUNNELS", "LIONS", "CROWNS", "BELLS", "SWANS", "HORSESHOES", "KEYS", "FEATHERS", " TUNS"))
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

        # Strip "NO" / "NUMBER" before a digit
        final_tokens = []
        for idx, t in enumerate(out):
            if t in ("NO", "NUMBER") and idx + 1 < len(out) and re.match(r"^\d+", out[idx + 1]):
                continue
            final_tokens.append(t)
        return " ".join(final_tokens)

    def _normalize_saint_and_tokens(tokens: list) -> list:
        """Disambiguate ST (SAINT vs STREET) and expand standard UK abbreviations."""
        res = []
        n = len(tokens)
        i = 0
        while i < n:
            t = tokens[i]
            if t in ("ST", "SAINT") and i + 1 < n:
                nxt = tokens[i + 1]
                if nxt in SAINT_NAMES:
                    res.append("SAINT")
                    # Normalize saint name possessive (ST JOHN -> SAINT JOHNS if followed by street suffix)
                    i += 1
                    continue
            res.append(t)
            i += 1
        return res

    # Sub-building extraction patterns
    SUB_PREFIX_RE = re.compile(
        r"\b(FLAT|FLT|APARTMENT|APT|APPT|UNIT|UNT|SUITE|STE|ROOM|RM|STUDIO|MAISONETTE|"
        r"PENTHOUSE|ANNEX|ANNEXE|WORKSHOP|STALL|KIOSK|PLOT|BERTH|CARAVAN|CHALET|CABIN|"
        r"BLOCK|BLK)\s*(?:NO\s*)?([0-9]+[A-Z]?|[A-Z](?=\b)|[0-9]+/[0-9]+)\b"
    )
    FLOOR_RE = re.compile(
        r"\b(SUB\s+BASEMENT|LOWER\s+GROUND|LWR\s+GND|LWR\s+GRD|BASEMENT|BSMT|CELLAR|"
        r"GARDEN|GROUND|GND|GRD|FIRST|1ST|SECOND|2ND|THIRD|3RD|FOURTH|4TH|FIFTH|5TH|"
        r"SIXTH|6TH|SEVENTH|7TH|EIGHTH|8TH|NINTH|9TH|TENTH|10TH|MEZZANINE|TOP|UPPER|"
        r"LOWER|MIDDLE|ATTIC)\s+(?:FLOOR|FLR|FL)\b"
        r"(?:\s+(FLAT|FLT|APT|APARTMENT|UNIT|SUITE|ROOM|LEFT|RIGHT|FRONT|REAR))?"
        r"(?:\s+([0-9]+[A-Z]?|[A-Z](?=\b)))?"
    )
    STANDALONE_FLAT_FLOOR_RE = re.compile(
        r"\b(BASEMENT|BSMT|LOWER\s+GROUND|GARDEN|GROUND|FIRST|1ST|SECOND|2ND|THIRD|3RD|"
        r"TOP|UPPER|LOWER|ATTIC|REAR|FRONT|STUDIO)\s+(FLAT|FLT|APARTMENT|APT|MAISONETTE)\b"
        r"(?:\s+([0-9]+[A-Z]?|[A-Z](?=\b)))?"
    )
    SCOTTISH_TENEMENT_RE = re.compile(
        r"\b(?:FLAT\s+)?([0-9]|G)F([0-9]|[LRM])\b|\b([0-9]|G)/([LR]|[1-9])\b"
    )

    def _extract_sub_building(clauses: list) -> tuple:
        """
        Extract sub-building/flat/floor information across clauses.
        Returns `(sub_info_dict, remaining_clauses)`.
        """
        sub_parts = []
        sub_id = ""
        sub_type = ""
        sub_floor = None
        new_clauses = []

        # Count total numbers across clauses to know if a slash like "1/2" is accompanied by a street number
        all_text = " , ".join(clauses)
        distinct_numbers = re.findall(r"\b\d+[A-Z]?\b", all_text)

        for cl in clauses:
            working = cl

            # 1. Check explicit Floor expression (e.g. "FIRST FLOOR FLAT 2", "GROUND FLOOR")
            m_flr = FLOOR_RE.search(working)
            if m_flr:
                flr_word, sub_kind, flr_id = m_flr.groups()
                sub_floor = FLOOR_CANONICAL_MAP.get(flr_word, sub_floor)
                if flr_id and not sub_id:
                    sub_id = flr_id
                if sub_kind and not sub_type:
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
                sub_type = SUB_BUILDING_TYPES.get(kind_word, "FLAT")
                if sff_id and not sub_id:
                    sub_id = sff_id
                sub_parts.append(m_sff.group(0).strip())
                working = (working[: m_sff.start()] + " " + working[m_sff.end() :]).strip()

            # 3. Check standard Sub-building prefix (e.g. "FLAT 2", "UNIT 4B", "APT A")
            while True:
                m_sub = SUB_PREFIX_RE.search(working)
                if not m_sub:
                    break
                kw, ident = m_sub.groups()
                canon_kw = SUB_BUILDING_TYPES.get(kw, kw)
                if not sub_type or sub_type == "FLOOR":
                    sub_type = canon_kw
                if not sub_id:
                    sub_id = ident
                sub_parts.append(f"{canon_kw} {ident}")
                working = (working[: m_sub.start()] + " " + working[m_sub.end() :]).strip()

            # 4. Check Scottish tenement notation (e.g., "2F1", "1/2", "G/L") when another house number exists
            if len(distinct_numbers) >= 2 or re.search(r"\b([0-9]|G)F([0-9]|[LRM])\b", working):
                m_scot = SCOTTISH_TENEMENT_RE.search(working)
                if m_scot:
                    g1, g2, g3, g4 = m_scot.groups()
                    if g1 is not None:
                        fl_c, pos_c = g1, g2
                    else:
                        fl_c, pos_c = g3, g4
                    sub_floor = 0 if fl_c == "G" else int(fl_c)
                    sub_id = f"{fl_c}F{pos_c}"
                    sub_type = "FLAT"
                    sub_parts.append(m_scot.group(0).strip())
                    working = (working[: m_scot.start()] + " " + working[m_scot.end() :]).strip()

            # 5. Check standalone bare "FLAT" / "BASEMENT" / "PENTHOUSE" / "ANNEX" / "STUDIO" clause
            working_clean = re.sub(r"\s+", " ", working).strip()
            if working_clean in ("FLAT", "THE FLAT", "STUDIO", "THE STUDIO", "PENTHOUSE", "THE PENTHOUSE", "ANNEX", "ANNEXE", "THE ANNEX", "THE ANNEXE", "MAISONETTE", "THE MAISONETTE", "BASEMENT", "THE BASEMENT", "GROUND FLOOR", "FIRST FLOOR", "SECOND FLOOR", "THIRD FLOOR", "TOP FLOOR"):
                if "BASEMENT" in working_clean:
                    sub_floor = -1
                elif "GROUND" in working_clean:
                    sub_floor = 0
                elif "FIRST" in working_clean:
                    sub_floor = 1
                elif "SECOND" in working_clean:
                    sub_floor = 2
                elif "THIRD" in working_clean:
                    sub_floor = 3
                elif "TOP" in working_clean or "PENTHOUSE" in working_clean:
                    sub_floor = 99
                if not sub_type:
                    sub_type = working_clean.replace("THE ", "")
                sub_parts.append(working_clean.replace("THE ", ""))
                working_clean = ""

            if working_clean:
                new_clauses.append(working_clean)

        # Also check if the first remaining clause starts with a bare number/letter clause
        # strictly before another clause that starts with a house number + street
        # e.g., ["2", "14 HIGH STREET"] or ["2A", "14 HIGH STREET"]
        if (
            not sub_id
            and len(new_clauses) >= 2
            and re.match(r"^([0-9]{1,3}[A-Z]?|[A-H])$", new_clauses[0])
            and re.match(r"^\d+(?:-\d+)?[A-Z]?\s+[A-Z]", new_clauses[1])
        ):
            sub_id = new_clauses[0]
            sub_type = "FLAT"
            sub_parts.append(f"FLAT {sub_id}")
            new_clauses = new_clauses[1:]

        display = " ".join(sub_parts).strip()
        # Normalize canonical sub-building token
        canon_id = sub_id
        return {
            "display": display,
            "type": sub_type,
            "id": canon_id,
            "floor": sub_floor,
            "has_sub": bool(display or sub_id or sub_floor is not None),
        }, new_clauses

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
            is_second_last_before_dir = (idx == n - 2 and norm[-1] in DIRECTIONAL_MAP)
            if (is_last or is_second_last_before_dir) and tok in STREET_SUFFIX_MAP and n >= 2:
                canon_sfx = STREET_SUFFIX_MAP[tok]
                out.append(canon_sfx)
                suffix = canon_sfx
            elif idx == 0 and tok in ("HEOL", "FFORDD", "STRYD", "LON", "LLWYBR"):
                # Welsh prefix thoroughfare word
                out.append(tok)
                suffix = tok
            elif tok in DIRECTIONAL_MAP and (idx == 0 or idx == n - 1):
                out.append(DIRECTIONAL_MAP[tok])
            else:
                out.append(tok)

        full_street = " ".join(out)
        # Core street name strips leading "THE" and trailing street suffix
        core_tokens = [t for i, t in enumerate(out) if not (i == 0 and t == "THE")]
        if suffix and len(core_tokens) >= 2 and core_tokens[-1] == suffix:
            core_tokens = core_tokens[:-1]
        elif suffix and len(core_tokens) >= 2 and core_tokens[0] == suffix:
            core_tokens = core_tokens[1:]
        core_street = " ".join(core_tokens) if core_tokens else full_street
        return full_street, core_street, suffix

    def _parse_premise_number_token(tok: str):
        """
        Parse a house number token like `14`, `14A`, `12-14`, `12-14A`.
        Returns `(display_str, start_num, end_num, suffix_letter)` or `None`.
        """
        m = re.match(r"^(\d{1,5})(?:-(\d{1,5}))?([A-Z])?$", tok)
        if not m:
            return None
        s_num = int(m.group(1))
        e_num = int(m.group(2)) if m.group(2) else s_num
        sfx = m.group(3) or ""
        if e_num < s_num:
            # Handle truncated range like 12-4 -> 12-14
            if s_num >= 10 and e_num < 10 and (s_num % 10) < e_num:
                e_num = (s_num // 10) * 10 + e_num
            else:
                s_num, e_num = e_num, s_num
        disp = f"{s_num}-{e_num}{sfx}" if s_num != e_num else f"{s_num}{sfx}"
        return disp, s_num, e_num, sfx

    def _parse_address_record(raw_record: list) -> dict:
        """
        Parse a 4-element UK address list `[address1, address2, address3, postcode]`
        into canonical UK PAF / AddressBase semantic components and normalized lines.
        """
        # Pad or fold to 4 elements
        rec = list(raw_record) if isinstance(raw_record, (list, tuple)) else [raw_record]
        while len(rec) < 4:
            rec.append("")
        if len(rec) > 4:
            rec = [rec[0], rec[1], ", ".join(str(x) for x in rec[2:-1] if x), rec[-1]]

        raw_lines = ["" if x is None else str(x).strip() for x in rec[:3]]
        raw_pc = "" if rec[3] is None else str(rec[3]).strip()

        # 1. Extract & validate postcode (including scanning lines if needed)
        pc_info, lines_no_pc = _parse_postcode(raw_pc, raw_lines)

        # 2. Clean each positional line and split into sub-clauses
        cleaned_lines = [_clean_text(ln) for ln in lines_no_pc]
        clauses = []
        for line_idx, ln in enumerate(cleaned_lines):
            if not ln:
                continue
            for part in ln.split(","):
                p = _normalize_written_numbers_in_clause(part.strip())
                if p and p not in COUNTRY_NOISE:
                    clauses.append(p)

        # 3. Extract Sub-Building (Flat / Unit / Floor / Scottish tenement)
        sub_info, rem_clauses = _extract_sub_building(clauses)

        # 4. Classify remaining clauses into:
        #    - PO Box
        #    - Building Number + Street
        #    - Building Name / Organization
        #    - Locality / Post Town / County
        building_num_disp = ""
        building_num_range = None  # (start, end, suffix)
        building_name_parts = []
        street_candidates = []     # list of (full_street, core_street, suffix)
        locality_parts = []

        # Helper to check if a token list is a known County or London Borough or Town
        def _is_pure_locality_clause(toks: list) -> bool:
            phrase = " ".join(toks)
            if phrase in UK_COUNTY_MAP or phrase in LONDON_BOROUGHS_AND_DISTRICTS or phrase == "LONDON":
                return True
            # Strip trailing county from phrase
            for c_len in (3, 2, 1):
                if len(toks) > c_len:
                    tail = " ".join(toks[-c_len:])
                    if tail in UK_COUNTY_MAP:
                        return True
            return False

        for cl_idx, cl in enumerate(rem_clauses):
            toks = cl.split()
            if not toks:
                continue

            # Check PO Box
            m_pobox = re.search(r"\b(?:P\s*O\s*BOX|POST\s+OFFICE\s+BOX)\s*(\d+[A-Z]?)\b", cl)
            if m_pobox:
                building_name_parts.append(f"PO BOX {m_pobox.group(1)}")
                continue

            # Check slash number at start of clause: e.g. "2/14 HIGH STREET"
            if (
                not sub_info["has_sub"]
                and re.match(r"^(\d+[A-Z]?)/(\d+[A-Z]?)$", toks[0])
                and len(toks) >= 2
            ):
                m_sl = re.match(r"^(\d+[A-Z]?)/(\d+[A-Z]?)$", toks[0])
                sub_info["id"] = m_sl.group(1)
                sub_info["type"] = "FLAT"
                sub_info["display"] = f"FLAT {m_sl.group(1)}"
                sub_info["has_sub"] = True
                toks = [m_sl.group(2)] + toks[1:]

            # Check if clause starts with a premise number (e.g. "14 HIGH STREET" or standalone "14")
            num_parsed = _parse_premise_number_token(toks[0])
            if num_parsed and (len(toks) == 1 or toks[1] not in ("FLOOR", "FLR", "FL", "MILE", "ACRES", "OAKS", "ELMS", "PINES")):
                disp_n, s_n, e_n, sfx_n = num_parsed
                if not building_num_disp:
                    building_num_disp = disp_n
                    building_num_range = (s_n, e_n, sfx_n)
                rest_toks = toks[1:]
                if not rest_toks:
                    continue

                # If rest_toks has a strong street suffix in the middle followed by locality (e.g. "14 HIGH STREET GUILDFORD")
                split_street_idx = -1
                for k in range(1, len(rest_toks)):
                    cand_sfx = STREET_SUFFIX_MAP.get(rest_toks[k], "")
                    if cand_sfx in STRONG_STREET_SUFFIXES and k < len(rest_toks) - 1:
                        # Check if token after street suffix is a directional/gate or a town
                        after_tok = rest_toks[k + 1]
                        if after_tok not in DIRECTIONAL_MAP and after_tok not in ("GATE", "END", "HILL", "PARK", "GREEN", "COMMON", "SIDE", "ESTATE"):
                            split_street_idx = k + 1
                            break

                if split_street_idx > 0:
                    st_toks = rest_toks[:split_street_idx]
                    loc_toks = rest_toks[split_street_idx:]
                    street_candidates.append(_canonicalize_street_tokens(st_toks))
                    locality_parts.append(" ".join(loc_toks))
                else:
                    street_candidates.append(_canonicalize_street_tokens(rest_toks))
                continue

            # Check if clause has an embedded number before a street at the end of a named building clause
            # e.g. "ROSE COTTAGE 14 HIGH STREET"
            emb_num_idx = -1
            for k in range(1, len(toks) - 1):
                if _parse_premise_number_token(toks[k]) and (
                    STREET_SUFFIX_MAP.get(toks[-1], "") in STRONG_STREET_SUFFIXES
                    or STREET_SUFFIX_MAP.get(toks[-1], "") in DUAL_PURPOSE_SUFFIXES
                ):
                    emb_num_idx = k
                    break

            if emb_num_idx > 0:
                bname_toks = toks[:emb_num_idx]
                building_name_parts.append(" ".join(bname_toks))
                disp_n, s_n, e_n, sfx_n = _parse_premise_number_token(toks[emb_num_idx])
                if not building_num_disp:
                    building_num_disp = disp_n
                    building_num_range = (s_n, e_n, sfx_n)
                street_candidates.append(_canonicalize_street_tokens(toks[emb_num_idx + 1 :]))
                continue

            # Strip leading "OFF" for dependent thoroughfares (e.g. "OFF STATION ROAD")
            is_off_street = False
            if toks[0] == "OFF" and len(toks) >= 2:
                toks = toks[1:]
                is_off_street = True

            last_tok = toks[-1]
            second_last_tok = toks[-2] if len(toks) >= 2 else ""
            canon_last_sfx = STREET_SUFFIX_MAP.get(last_tok, "")
            if not canon_last_sfx and last_tok in DIRECTIONAL_MAP and second_last_tok in STREET_SUFFIX_MAP:
                canon_last_sfx = STREET_SUFFIX_MAP[second_last_tok]

            has_Welsh_street_prefix = toks[0] in ("HEOL", "FFORDD", "STRYD", "LON", "LLWYBR")

            # Check if it's a pure Building / House / Commercial Name
            is_building_name = (
                last_tok in BUILDING_NAME_SUFFIXES
                or any(t in COMMERCIAL_KEYWORDS for t in toks)
                or (len(toks) >= 2 and " ".join(toks[-2:]) in COMMERCIAL_KEYWORDS)
                or (toks[0] in ("TY", "PLAS", "BWTHYN", "FFARM") and not has_Welsh_street_prefix)
            )

            # Check if it's a strong street
            is_strong_street = (
                canon_last_sfx in STRONG_STREET_SUFFIXES
                or has_Welsh_street_prefix
                or is_off_street
            )

            # Check if it ends in a dual-purpose word (like COURT, GARDENS, PARK, HILL, GREEN, HOUSE+STREET)
            is_dual_purpose = canon_last_sfx in DUAL_PURPOSE_SUFFIXES

            if is_strong_street:
                street_candidates.append(_canonicalize_street_tokens(toks))
            elif is_building_name and not is_dual_purpose:
                building_name_parts.append(" ".join(toks))
            elif is_dual_purpose:
                # Could be either a Building Name ("SOVEREIGN COURT") or a Street ("HAMPTON COURT" / "KENSINGTON GARDENS").
                # Temporarily add to street_candidates with a flag; we resolve after inspecting all clauses!
                street_candidates.append(_canonicalize_street_tokens(toks))
            elif _is_pure_locality_clause(toks):
                locality_parts.append(" ".join(toks))
            else:
                # Positional heuristics for suffixless clauses:
                # - If it's the very first clause (in address1) and no building_name or building_number was seen yet,
                #   and later clauses exist for street/locality, treat as building_name (e.g. "THE OLD RECTORY" or "TESCO").
                # - If it's in the last clause or after a street has already been found, treat as locality (town/village).
                if not street_candidates and not building_num_disp and not building_name_parts and cl_idx < len(rem_clauses) - 1:
                    building_name_parts.append(" ".join(toks))
                else:
                    locality_parts.append(" ".join(toks))

        # 5. Resolve Dual-Purpose / Multiple Street Candidates
        # e.g., ["SOVEREIGN COURT", "14 HIGH STREET"]: "SOVEREIGN COURT" was added to street_candidates,
        # followed by "HIGH STREET". Since "SOVEREIGN COURT" has no number and ends in a dual-purpose word
        # ("COURT"), promote it to `building_name`!
        primary_street = ""
        primary_street_core = ""
        primary_street_suffix = ""
        dependent_street = ""

        if len(street_candidates) == 1:
            primary_street, primary_street_core, primary_street_suffix = street_candidates[0]
        elif len(street_candidates) >= 2:
            first_st, first_core, first_sfx = street_candidates[0]
            second_st, second_core, second_sfx = street_candidates[1]
            if first_sfx in DUAL_PURPOSE_SUFFIXES and second_sfx in STRONG_STREET_SUFFIXES and not building_name_parts:
                # First is actually a Building/Block name (e.g. "SOVEREIGN COURT, HIGH STREET")
                building_name_parts.append(first_st)
                primary_street, primary_street_core, primary_street_suffix = street_candidates[1]
                if len(street_candidates) >= 3:
                    dependent_street = street_candidates[2][0]
            else:
                # Dependent thoroughfare + Primary thoroughfare (e.g. "CHESTNUT CLOSE, OFF STATION ROAD")
                primary_street, primary_street_core, primary_street_suffix = street_candidates[0]
                dependent_street = street_candidates[1][0]

        # Fallback: if no street was found, and there are >= 2 locality_parts (e.g. rural village street without suffix + post town),
        # or if building_num_disp was found before an un-suffixed thoroughfare name
        if not primary_street and locality_parts and len(locality_parts) >= 2 and not building_num_disp:
            # First locality part might be a suffixless thoroughfare or hamlet
            pass

        # 6. Canonicalize Building Name
        raw_bname = " ".join(building_name_parts).strip()
        bname_tokens = []
        for t in raw_bname.split():
            bname_tokens.append(BUILDING_NAME_CANONICAL.get(t, t))
        canonical_bname = " ".join(bname_tokens)

        # 7. Canonicalize Locality & separate Post Town vs County
        raw_locality = " ".join(locality_parts).strip()
        # Normalize "UPON" / "ON" / hyphens in town names
        loc_norm = raw_locality.replace("-", " ")
        loc_norm = re.sub(r"\bUPON\b", "ON", loc_norm)
        loc_tokens = [t for t in loc_norm.split() if t not in COUNTRY_NOISE]

        # Extract any recognized UK County from locality tokens
        extracted_county = ""
        town_tokens = list(loc_tokens)
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
            ln_toks = _normalize_saint_and_tokens(_normalize_written_numbers_in_clause(ln.replace(",", " ")).split())
            ln_canon = [STREET_SUFFIX_MAP.get(t, BUILDING_NAME_CANONICAL.get(t, t)) for t in ln_toks if t not in COUNTRY_NOISE]
            norm_lines.append(" ".join(ln_canon))
        full_tokens_str = " ".join(filter(None, norm_lines))

        return {
            "postcode": pc_info["canonical"],
            "postcode_info": pc_info,
            "sub_building": sub_info["display"],
            "sub_info": sub_info,
            "building_number": building_num_disp,
            "building_number_range": building_num_range,
            "building_name": canonical_bname,
            "street": primary_street,
            "street_core": primary_street_core,
            "street_suffix": primary_street_suffix,
            "dependent_street": dependent_street,
            "locality": canonical_locality,
            "town": canonical_town,
            "county": extracted_county,
            "normalized_lines": norm_lines,
            "full_tokens_str": full_tokens_str,
        }

    # =========================================================================
    # 5. COMPONENT-BY-COMPONENT SCORING FUNCTIONS
    # =========================================================================

    def _score_postcode(t_pc: dict, c_pc: dict) -> dict:
        """Score UK Postcode component (outward, sector, unit, OCR repairs, transpositions)."""
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

        # Compare structured components when both have outward codes
        if t_pc["outward"] and c_pc["outward"]:
            same_outward = t_pc["outward"] == c_pc["outward"]
            same_sector = same_outward and bool(t_pc["sector"]) and (t_pc["sector"] == c_pc["sector"])

            if same_sector:
                # If one is a partial outward+sector postcode (e.g. "GU1 3")
                if t_pc["is_partial"] or c_pc["is_partial"]:
                    return {"score": 0.78, "target_value": t_val, "candidate_value": c_val, "match_type": "PARTIAL_SECTOR_MATCH"}
                # Check 1-edit typo or transposition in 2-letter Unit (e.g. "3AB" vs "3BA" or "3AA")
                unit_sim = _damerau_levenshtein_sim(t_pc["unit"], c_pc["unit"])
                if unit_sim >= 0.50:
                    return {"score": 0.85, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_SECTOR_UNIT_TYPO"}
                return {"score": 0.75, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_SECTOR"}

            if same_outward:
                if t_pc["is_partial"] or c_pc["is_partial"]:
                    return {"score": 0.65, "target_value": t_val, "candidate_value": c_val, "match_type": "PARTIAL_OUTWARD_MATCH"}
                # Same outward, different sector; check if unit is identical (sector digit typo, e.g. GU1 3AA vs GU1 2AA)
                if t_pc["unit"] and t_pc["unit"] == c_pc["unit"]:
                    return {"score": 0.72, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_OUTWARD_AND_UNIT_SECTOR_TYPO"}
                return {"score": 0.55, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_OUTWARD"}

            # Different outward code: check if Inward code is identical and Outward differs by 1 edit (e.g. GU1 3AA vs GU2 3AA)
            if t_pc["inward"] and t_pc["inward"] == c_pc["inward"]:
                out_sim = _damerau_levenshtein_sim(t_pc["outward"], c_pc["outward"])
                if out_sim >= 0.66:
                    return {"score": 0.65, "target_value": t_val, "candidate_value": c_val, "match_type": "OUTWARD_TYPO_INWARD_EXACT"}

            if t_pc["area"] and t_pc["area"] == c_pc["area"]:
                return {"score": 0.25, "target_value": t_val, "candidate_value": c_val, "match_type": "SAME_AREA_ONLY"}

            return {"score": 0.0, "target_value": t_val, "candidate_value": c_val, "match_type": "CONFLICT"}

        # Fallback character similarity
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

        # Case 1: Target has suffix (e.g. 14A, no sub_building) and Candidate has no suffix (14) + sub_building (Flat A / Flat 1)
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

        # Case 2: Candidate has suffix (14A, no sub_building) and Target has no suffix (14) + sub_building (Flat A / Flat 1)
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

    def _score_building_number(t_parsed: dict, c_parsed: dict, bname_score: float, street_score: float) -> dict:
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

        # Check if number is present on only one side
        if not t_rng or not c_rng:
            # Cooperative premise check: if one side omitted the house number, but both sides share an exact/strong
            # Building Name (e.g. "Rose Cottage, High Street" vs "Rose Cottage, 14 High Street") on the same street!
            if bname_score >= 0.88 and street_score >= 0.80:
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

        # Both have building numbers
        if t_val == c_val:
            return {
                "score": 1.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "EXACT",
            }

        # Check Flat <-> Number Suffix Equivalence (14A <-> Flat A, 14 or Flat 1, 14)
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

        # Same exact number range (e.g. both are 14), but suffixes differ (14 vs 14A, or 14A vs 14B)
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

        # Range containment / overlap (e.g. 12 vs 12-14, or 14 vs 12-16)
        overlap_start = max(t_s, c_s)
        overlap_end = min(t_e, c_e)
        if overlap_start <= overlap_end:
            # Single number inside a range
            if t_s == t_e or c_s == c_e:
                single_n = t_s if t_s == t_e else c_s
                rng_s, rng_e = (c_s, c_e) if t_s == t_e else (t_s, t_e)
                # Check if single_n is one of the endpoints or has matching odd/even parity
                if single_n in (rng_s, rng_e) or (single_n % 2 == rng_s % 2):
                    return {
                        "score": 0.90,
                        "target_value": t_val,
                        "candidate_value": c_val,
                        "match_type": "RANGE_MATCH",
                    }
                # Contiguous parade range (e.g. 13 inside 12-14)
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

        # Explicit conflict between different house numbers (e.g. 12 vs 14)
        return {
            "score": 0.0,
            "target_value": t_val,
            "candidate_value": c_val,
            "match_type": "CONFLICT",
        }

    def _score_sub_building(t_parsed: dict, c_parsed: dict) -> dict:
        """Score Sub-building / Flat / Unit / Floor component."""
        t_sub = t_parsed["sub_info"]
        c_sub = c_parsed["sub_info"]
        t_val = t_parsed["sub_building"]
        c_val = c_parsed["sub_building"]

        # Check Flat <-> Building Number Suffix equivalence first (e.g., Flat 1, 14 <-> 14A)
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

        # Parent vs Child shell discrepancy (one has a flat/unit, the other is the parent building)
        if t_sub["has_sub"] != c_sub["has_sub"]:
            return {
                "score": 0.40,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "PARENT_CHILD_PARTIAL",
            }

        # Both have sub-buildings
        if t_val == c_val:
            return {
                "score": 1.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "EXACT",
            }

        t_id, c_id = t_sub["id"], c_sub["id"]
        t_fl, c_fl = t_sub["floor"], c_sub["floor"]

        # Both have explicit sub-building IDs (e.g. "2" vs "2", or "A" vs "1", or "1" vs "2")
        if t_id and c_id:
            if t_id == c_id:
                return {
                    "score": 1.0,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "CANONICAL_EXACT",
                }
            # Letter <-> Number equivalence (Flat A <-> Flat 1, Flat B <-> Flat 2)
            if LETTER_TO_NUMBER_MAP.get(t_id) == c_id or LETTER_TO_NUMBER_MAP.get(c_id) == t_id:
                return {
                    "score": 0.94,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "LETTER_NUMBER_EQUIVALENT",
                }
            # Scottish tenement equivalence (e.g. "1F1" vs "1/1" or "FLAT 1" on 1st floor)
            if t_fl is not None and c_fl is not None and t_fl == c_fl:
                return {
                    "score": 0.75,
                    "target_value": t_val,
                    "candidate_value": c_val,
                    "match_type": "SAME_FLOOR_DIFFERENT_SUB_ID",
                }
            return {
                "score": 0.0,
                "target_value": t_val,
                "candidate_value": c_val,
                "match_type": "CONFLICT",
            }

        # Both have floor levels without conflicting IDs (e.g. "1ST FLOOR" vs "FIRST FLOOR FLAT")
        if t_fl is not None and c_fl is not None:
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

        # One has Floor (e.g. "GROUND FLOOR FLAT") and the other has ID ("FLAT 1" or "FLAT A")
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
            # Check if the street name was placed inside building_name on one side (e.g. "14 SOVEREIGN COURT")
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

        # Check Dependent Street cross-matching (e.g. "CHESTNUT CLOSE, OFF STATION ROAD" vs "CHESTNUT CLOSE" or "STATION ROAD")
        if (t_dep and t_dep == c_st) or (c_dep and c_dep == t_st):
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

        # Exact core street match (e.g. "HIGH" == "HIGH", or "SAINT JOHNS" == "SAINT JOHNS")
        if t_core and c_core and t_core == c_core:
            if not t_sfx or not c_sfx:
                return {
                    "score": 0.90,
                    "target_value": t_st,
                    "candidate_value": c_st,
                    "match_type": "CORE_EXACT_SUFFIX_OMITTED",
                }
            # Different suffixes (e.g. "OAK AVENUE" vs "OAK ROAD")
            return {
                "score": 0.78,
                "target_value": t_st,
                "candidate_value": c_st,
                "match_type": "CORE_EXACT_SUFFIX_DIFF",
            }

        # Compare full street and core street using multi-metric similarity + UK phonetic similarity
        full_sim = max(_string_similarity(t_st, c_st), _token_similarity(t_st, c_st))
        core_sim = max(_string_similarity(t_core, c_core), _token_similarity(t_core, c_core)) if (t_core and c_core) else full_sim

        sfx_bonus = 0.05 if (t_sfx and t_sfx == c_sfx) else (-0.06 if (t_sfx and c_sfx and t_sfx != c_sfx) else 0.0)
        combined_sim = min(0.98, max(full_sim, core_sim + sfx_bonus))

        # Check UK phonetic match on core street name (e.g., BEAUCHAMP <-> BEECHAM, MARYLEBONE <-> MARLEYBONE)
        if t_core and c_core and _uk_phonetic_phrase(t_core) == _uk_phonetic_phrase(c_core):
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

        # Check cross-field match if one side classified a Court/Mews/Building as street
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
            # Preliminary missing-one-side score; refined in cooperative premise pass once number & street scores are known
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

        # Strip leading "THE" for canonical comparison ("THE OLD RECTORY" == "OLD RECTORY")
        t_clean = re.sub(r"^THE\s+", "", t_bn).strip()
        c_clean = re.sub(r"^THE\s+", "", c_bn).strip()
        if t_clean == c_clean:
            return {
                "score": 0.99,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "CANONICAL_EXACT",
            }

        # Explicit PO Box number comparison ("PO BOX 452" vs "PO BOX 999")
        m_po_t = re.search(r"\bPO BOX\s+(\d+[A-Z]?)\b", t_clean)
        m_po_c = re.search(r"\bPO BOX\s+(\d+[A-Z]?)\b", c_clean)
        if m_po_t or m_po_c:
            if m_po_t and m_po_c:
                if m_po_t.group(1) == m_po_c.group(1):
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
            return {
                "score": 0.0,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "CONFLICT",
            }

        # Separate core building name from generic building suffixes (e.g., COTTAGE, HOUSE, COURT, LODGE)
        # so "ROSE COTTAGE" vs "IVY COTTAGE" compares "ROSE" vs "IVY" instead of matching on "COTTAGE".
        t_toks = t_clean.split()
        c_toks = c_clean.split()
        t_sfx = t_toks[-1] if (len(t_toks) >= 2 and (t_toks[-1] in BUILDING_NAME_SUFFIXES or t_toks[-1] in DUAL_PURPOSE_SUFFIXES)) else ""
        c_sfx = c_toks[-1] if (len(c_toks) >= 2 and (c_toks[-1] in BUILDING_NAME_SUFFIXES or c_toks[-1] in DUAL_PURPOSE_SUFFIXES)) else ""
        t_core = " ".join(t_toks[:-1]) if t_sfx else t_clean
        c_core = " ".join(c_toks[:-1]) if c_sfx else c_clean

        if t_core == c_core and t_core:
            sc = 0.92 if (not t_sfx or not c_sfx) else 0.80
            return {
                "score": sc,
                "target_value": t_bn,
                "candidate_value": c_bn,
                "match_type": "CORE_BUILDING_NAME_MATCH",
            }

        core_sim = max(_string_similarity(t_core, c_core), _token_similarity(t_core, c_core))
        sfx_adj = 0.03 if (t_sfx and t_sfx == c_sfx and core_sim >= 0.70) else (-0.05 if (t_sfx and c_sfx and t_sfx != c_sfx) else 0.0)
        sim = min(0.98, max(0.0, core_sim + sfx_adj))

        if sim < 0.88 and t_core and c_core and _uk_phonetic_phrase(t_core) == _uk_phonetic_phrase(c_core):
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

        # If Post Town matches exactly and only County was omitted on one side (e.g. "GUILDFORD" vs "GUILDFORD SURREY")
        if t_town and c_town and t_town == c_town:
            return {
                "score": 0.98,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "TOWN_EXACT_COUNTY_OPTIONAL",
            }

        # Check subset match (e.g. dependent locality + post town "BROCKENHURST LYMINGTON" vs "BROCKENHURST")
        t_set = set(t_town.split())
        c_set = set(c_town.split())
        if t_set and c_set and (t_set.issubset(c_set) or c_set.issubset(t_set)):
            return {
                "score": 0.95,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "SUBSET_MATCH",
            }

        # Check Greater London Borough / District <-> "LONDON" equivalence
        t_is_london = t_town == "LONDON" or t_loc == "GREATER LONDON"
        c_is_london = c_town == "LONDON" or c_loc == "GREATER LONDON"
        t_in_london_boroughs = t_town in LONDON_BOROUGHS_AND_DISTRICTS or any(
            b in t_loc for b in LONDON_BOROUGHS_AND_DISTRICTS
        )
        c_in_london_boroughs = c_town in LONDON_BOROUGHS_AND_DISTRICTS or any(
            b in c_loc for b in LONDON_BOROUGHS_AND_DISTRICTS
        )
        if (t_is_london and c_in_london_boroughs) or (c_is_london and t_in_london_boroughs):
            return {
                "score": 0.92,
                "target_value": t_loc,
                "candidate_value": c_loc,
                "match_type": "LONDON_BOROUGH_EQUIVALENT",
            }

        sim = max(_string_similarity(t_town, c_town), _token_similarity(t_loc, c_loc))
        if sim < 0.88 and t_town and c_town and _uk_phonetic_phrase(t_town) == _uk_phonetic_phrase(c_town):
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
                active_pos_scores.append(0.25)
            else:
                sc = _token_similarity(tl, cl, ignore_stopwords=False)
                line_scores.append(round(sc, 4))
                active_pos_scores.append(sc)

        pos_avg = sum(active_pos_scores) / len(active_pos_scores) if active_pos_scores else 1.0
        full_tok_sim = _token_similarity(t_parsed["full_tokens_str"], c_parsed["full_tokens_str"], ignore_stopwords=True)

        # Blend 65% order/line-independent full token similarity + 35% strict positional line similarity
        blended = round(0.65 * full_tok_sim + 0.35 * pos_avg, 4)
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

        # 1. Score individual components
        pc_res = _score_postcode(t_parsed["postcode_info"], c_parsed["postcode_info"])
        st_res = _score_street(t_parsed, c_parsed)
        bn_res = _score_building_name(t_parsed, c_parsed)
        num_res = _score_building_number(t_parsed, c_parsed, bn_res["score"], st_res["score"])
        sub_res = _score_sub_building(t_parsed, c_parsed)
        loc_res = _score_locality(t_parsed, c_parsed)
        line_res = _score_line_alignment(t_parsed, c_parsed)

        # Cooperative Premise Resolution:
        # If one side has a Building Name/Business Name (e.g. "Rose Cottage, 14 High St" or "Tesco, 14 High St")
        # and the other side only has "14 High St", and building_number + street match strongly,
        # treat the unmentioned Building Name as a cooperative pass with minimal tie-breaker penalty!
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

        # 2. Compute Context-Aware Dynamic Weights
        weights = dict(BASE_WEIGHTS)

        # If neither side has a building_number (e.g., named rural house "Rose Cottage, Church Lane"),
        # transfer `building_number`'s 0.24 weight to `building_name` (or `street` if no building_name).
        if num_res["match_type"] == "NOT_APPLICABLE":
            weights["building_number"] = 0.0
            if bn_res["match_type"] != "NOT_APPLICABLE":
                weights["building_name"] += BASE_WEIGHTS["building_number"]

        # If neither side has a building_name, redistribute its weight
        if bn_res["match_type"] == "NOT_APPLICABLE":
            weights["building_name"] = 0.0

        # If neither side has a sub_building, redistribute its weight
        if sub_res["match_type"] == "NOT_APPLICABLE":
            weights["sub_building"] = 0.0

        # If neither side has a street (e.g. rural named property + village only)
        if st_res["match_type"] == "NOT_APPLICABLE":
            weights["street"] = 0.0

        # If postcode is missing on one or both sides, reduce postcode weight to 0.08 so street+premise+town carry the match
        if pc_res["match_type"] in ("MISSING_ONE_SIDE", "BOTH_MISSING"):
            weights["postcode"] = 0.06 if pc_res["match_type"] == "MISSING_ONE_SIDE" else 0.0

        # Normalize active weights so they sum to 1.0000 exactly
        total_w = sum(weights.values())
        if total_w > 0:
            norm_weights = {k: round(v / total_w, 4) for k, v in weights.items()}
        else:
            norm_weights = {k: round(1.0 / len(weights), 4) for k in weights}

        # Adjust largest active weight by any 0.0001 rounding residual so weights sum to 1.0
        residual = round(1.0 - sum(norm_weights.values()), 4)
        if residual != 0.0:
            max_k = max(norm_weights, key=lambda k: norm_weights[k])
            norm_weights[max_k] = round(norm_weights[max_k] + residual, 4)

        # 3. Calculate Pre-Penalty Weighted Score
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

        # 4. Apply Non-Linear Conflict Penalty Multipliers
        penalties = []
        multiplier = 1.0

        # (a) Building Number Conflict (`12` vs `14`)
        if num_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "BUILDING_NUMBER_CONFLICT", "multiplier": 0.45})
            multiplier *= 0.45
        elif num_res["match_type"] == "SUFFIX_CONFLICT":
            penalties.append({"reason": "BUILDING_NUMBER_SUFFIX_CONFLICT", "multiplier": 0.55})
            multiplier *= 0.55
        elif num_res["match_type"] == "MISSING_ONE_SIDE":
            penalties.append({"reason": "BUILDING_NUMBER_MISSING_ONE_SIDE", "multiplier": 0.62})
            multiplier *= 0.62

        # (b) Sub-Building / Flat Conflict (`Flat 1` vs `Flat 2`)
        if sub_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "SUB_BUILDING_CONFLICT", "multiplier": 0.55})
            multiplier *= 0.55
        elif sub_res["match_type"] == "PARENT_CHILD_PARTIAL":
            penalties.append({"reason": "PARENT_CHILD_SUB_BUILDING_MISMATCH", "multiplier": 0.82})
            multiplier *= 0.82

        # (c) Building Name Conflict (`Rose Cottage` vs `Ivy Cottage`)
        if bn_res["match_type"] == "CONFLICT":
            penalties.append({"reason": "BUILDING_NAME_CONFLICT", "multiplier": 0.60})
            multiplier *= 0.60
        elif bn_res["match_type"] == "MISSING_ONE_SIDE" and num_res["match_type"] == "NOT_APPLICABLE":
            penalties.append({"reason": "BUILDING_NAME_MISSING_NO_NUMBER", "multiplier": 0.55})
            multiplier *= 0.55

        # (d) Street Conflict (`High Street` vs `Station Road`)
        if st_res["match_type"] == "CONFLICT" and st_res["score"] < 0.45:
            penalties.append({"reason": "STREET_CONFLICT", "multiplier": 0.55})
            multiplier *= 0.55

        # (e) Outward Postcode Conflict (`SW1A` vs `GU1`)
        if pc_res["match_type"] == "CONFLICT":
            # Relax penalty if premise + street + locality match >= 0.92 (indicates user typed wrong postcode)
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

        # 5. Assign Confidence Tier
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
    # 7. FAST PRE-SCREENING FOR LARGE CANDIDATE POOLS (> 2,000 CANDIDATES)
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
        t_pc_out = t_parsed["postcode_info"]["outward"]
        t_pc_full = t_parsed["postcode"].replace(" ", "")
        t_num = t_parsed["building_number"]
        t_toks = set(t_parsed["full_tokens_str"].split())

        quick_scored = []
        for uprn, raw_c in items_to_evaluate:
            c_str = " ".join(str(x) for x in raw_c if x is not None).upper()
            c_pc = str(raw_c[3] if len(raw_c) > 3 and raw_c[3] else "").upper().replace(" ", "")
            q_sc = 0.0
            if t_pc_full and c_pc == t_pc_full:
                q_sc += 5.0
            elif t_pc_out and c_pc.startswith(t_pc_out):
                q_sc += 2.5
            if t_num and re.search(r"\b" + re.escape(t_num) + r"\b", c_str):
                q_sc += 3.0
            c_words = set(re.findall(r"[A-Z0-9]+", c_str))
            q_sc += len(t_toks & c_words) * 0.8
            quick_scored.append((q_sc, uprn, raw_c))

        quick_scored.sort(key=lambda x: x[0], reverse=True)
        items_to_evaluate = [(u, rc) for _, u, rc in quick_scored[:500]]

    # =========================================================================
    # 8. SCORE ALL CANDIDATES, RANK & CHECK AMBIGUITY
    # =========================================================================

    scored_candidates = [
        _evaluate_candidate(uprn, raw_cand, t_parsed)
        for uprn, raw_cand in items_to_evaluate
    ]

    # Sort descending by overall_score, then pre_penalty_score, then full_token_set score
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
        if best_match["overall_score"] >= 0.60 and diff <= 0.025:
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
