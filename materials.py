"""Knowledge base for reno-forge: units, materials, tools and task templates.

Everything here is plain data + pure functions. No network calls, no API keys.
"""

# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------

MEASURE_UNITS = {
    "sqft", "sqm", "sqyd", "lf", "bf", "each", "cuft", "gal", "lb", "hour", "day", "count",
}

CONTAINER_UNITS = {
    "sheet", "box", "bag", "tub", "roll", "gallon", "can", "bucket", "bundle",
    "tube", "pkg", "pair", "set", "piece", "slab", "sqyd",
}

UNIT_ALIASES = {
    "sqft": "sqft", "sq ft": "sqft", "sq. ft": "sqft", "sf": "sqft", "square foot": "sqft",
    "square feet": "sqft", "sq feet": "sqft", "ft2": "sqft", "sq ft.": "sqft",
    "sqm": "sqm", "sq m": "sqm", "m2": "sqm", "square meter": "sqm", "square meters": "sqm",
    "sqyd": "sqyd", "sq yd": "sqyd", "square yard": "sqyd", "square yards": "sqyd", "yd2": "sqyd",
    "lf": "lf", "lin ft": "lf", "linear ft": "lf", "linear feet": "lf", "linear foot": "lf",
    "linft": "lf", "ft": "lf", "feet": "lf", "foot": "lf", "running ft": "lf",
    "bf": "bf", "bd ft": "bf", "board foot": "bf", "board feet": "bf", "boardfeet": "bf",
    "each": "each", "pc": "each", "piece": "each", "units": "each", "unit": "each", "ea": "each",
    "cuft": "cuft", "cu ft": "cuft", "cubic foot": "cuft", "cubic feet": "cuft", "ft3": "cuft",
    "gal": "gal", "gallon": "gal", "gallons": "gal",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "hour": "hour", "hr": "hour", "hours": "hour",
    "day": "day", "days": "day",
    "sheet": "sheet", "sheets": "sheet", "sh": "sheet",
    "box": "box", "boxes": "box", "bx": "box",
    "bag": "bag", "bags": "bag",
    "tub": "tub", "tubs": "tub", "bucket": "tub", "pail": "tub",
    "roll": "roll", "rolls": "roll",
    "gallon can": "gallon", "gal can": "gallon", "can": "can", "cans": "can",
    "bundle": "bundle", "bundles": "bundle", "bdl": "bundle",
    "tube": "tube", "tubes": "tube",
    "pkg": "pkg", "package": "pkg", "packages": "pkg",
    "pair": "pair", "pairs": "pair", "set": "set", "sets": "set",
    "slab": "slab", "slabs": "slab",
}

# Conversion factors into the canonical measure for a material.
SQFT_PER_SQM = 10.7639104167


def normalise_unit(raw):
    """Return a canonical unit string, or None."""
    if raw is None:
        return None
    key = " ".join(str(raw).strip().lower().replace(".", " ").split())
    key = key.replace(".", "")
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    if key.endswith("/"):
        key = key[:-1].strip()
        if key in UNIT_ALIASES:
            return UNIT_ALIASES[key]
    # plural / singular fallback
    for cand in (key, key.rstrip("s"), key + "s"):
        if cand in UNIT_ALIASES:
            return UNIT_ALIASES[cand]
    return None


def is_measure(unit):
    return unit in MEASURE_UNITS


def is_container(unit):
    return unit in CONTAINER_UNITS


# --------------------------------------------------------------------------
# Material database
#
# measure      : canonical unit the material is quantified in
# pack         : the container a homeowner actually buys
# pack_size    : how much measure one pack contains
# waste        : default waste allowance for that material
# cure         : hours of cure/dry time after installation
# ref          : (low, high) typical price per pack, used for outlier checks
# --------------------------------------------------------------------------

MATERIALS = [
    {"id": "tile", "label": "Tile (ceramic / porcelain)", "kw": ["porcelain", "ceramic", "tile", "mosaic"],
     "measure": "sqft", "pack": "box", "pack_size": 12.0, "pack_label": "box (12 sqft)",
     "waste": 0.10, "cure": 0, "ref": (18.0, 140.0), "wet": True, "long_lead": False},
    {"id": "backer", "label": "Cement backer board", "kw": ["cement board", "backer board", "backer", "tile backer", "hardie backer"],
     "measure": "sqft", "pack": "sheet", "pack_size": 12.0, "pack_label": "sheet (3x4)",
     "waste": 0.10, "cure": 24, "ref": (9.0, 32.0), "wet": True, "long_lead": False},
    {"id": "thinset", "label": "Thinset / tile mortar", "kw": ["thinset", "tile mortar", "mortar", "adhesive", "mastic", "bonding"],
     "measure": "sqft", "pack": "bag", "pack_size": 12.0, "pack_label": "25 lb bag (~12 sqft)",
     "waste": 0.15, "cure": 24, "ref": (12.0, 34.0), "wet": True, "long_lead": False},
    {"id": "grout", "label": "Grout", "kw": ["grout", "pointing"],
     "measure": "sqft", "pack": "tub", "pack_size": 200.0, "pack_label": "tub (5 lb)",
     "waste": 0.08, "cure": 24, "ref": (8.0, 30.0), "wet": True, "long_lead": False},
    {"id": "caulk", "label": "Caulk / silicone sealant", "kw": ["caulk", "silicone", "sealant"],
     "measure": "lf", "pack": "tube", "pack_size": 26.0, "pack_label": "tube (~26 lf)",
     "waste": 0.10, "cure": 24, "ref": (4.0, 16.0), "wet": True, "long_lead": False},
    {"id": "waterproof", "label": "Waterproofing membrane", "kw": ["waterproof", "membrane", "pan", "duraflex", "aqua"],
     "measure": "sqft", "pack": "gallon", "pack_size": 50.0, "pack_label": "gallon",
     "waste": 0.15, "cure": 24, "ref": (30.0, 90.0), "wet": True, "long_lead": False},
    {"id": "paint", "label": "Paint", "kw": ["paint", "emulsion", "latex paint"],
     "measure": "sqft", "pack": "gallon", "pack_size": 350.0, "pack_label": "gallon (~350 sqft)",
     "waste": 0.10, "cure": 4, "ref": (25.0, 75.0), "wet": False, "long_lead": False},
    {"id": "primer", "label": "Primer", "kw": ["primer", "undercoat", "bonding primer"],
     "measure": "sqft", "pack": "gallon", "pack_size": 350.0, "pack_label": "gallon",
     "waste": 0.10, "cure": 1, "ref": (20.0, 65.0), "wet": False, "long_lead": False},
    {"id": "stain", "label": "Deck stain / sealer", "kw": ["deck stain", "stain", "sealer", "polyurethane", "poly"],
     "measure": "sqft", "pack": "gallon", "pack_size": 500.0, "pack_label": "gallon",
     "waste": 0.10, "cure": 48, "ref": (25.0, 90.0), "wet": False, "long_lead": False},
    {"id": "drywall", "label": "Drywall / sheetrock", "kw": ["drywall", "sheetrock", "plasterboard", "gypsum board"],
     "measure": "sqft", "pack": "sheet", "pack_size": 32.0, "pack_label": "sheet (4x8)",
     "waste": 0.10, "cure": 0, "ref": (9.0, 24.0), "wet": False, "long_lead": False},
    {"id": "mud", "label": "Joint compound / mud", "kw": ["joint compound", "mud", "spackle", "skim coat"],
     "measure": "sqft", "pack": "box", "pack_size": 450.0, "pack_label": "box (4.5 gal)",
     "waste": 0.10, "cure": 24, "ref": (12.0, 35.0), "wet": False, "long_lead": False},
    {"id": "fasteners", "label": "Fasteners / screws", "kw": ["drywall screw", "screw", "nail", "fastener", "drywall tape", "mesh tape", "joist hanger", "hanger"],
     "measure": "each", "pack": "box", "pack_size": 200.0, "pack_label": "box (200)",
     "waste": 0.05, "cure": 0, "ref": (8.0, 25.0), "wet": False, "long_lead": False},
    {"id": "abrasive", "label": "Sandpaper / abrasive", "kw": ["sandpaper", "sand paper", "grit", "sanding"],
     "measure": "each", "pack": "pack", "pack_size": 10.0, "pack_label": "pack of 10",
     "waste": 0.05, "cure": 0, "ref": (4.0, 18.0), "wet": False, "long_lead": False},
    {"id": "flooring", "label": "Flooring (plank / laminate)", "kw": ["laminate", "hardwood", "engineered", "plank", "luxury vinyl", "lvp", "flooring", "vinyl plank"],
     "measure": "sqft", "pack": "box", "pack_size": 20.0, "pack_label": "box (20 sqft)",
     "waste": 0.08, "cure": 0, "ref": (30.0, 110.0), "wet": False, "long_lead": False},
    {"id": "carpet", "label": "Carpet", "kw": ["carpet", "broadloom"],
     "measure": "sqft", "pack": "sqyd", "pack_size": 9.0, "pack_label": "square yard",
     "waste": 0.08, "cure": 0, "ref": (18.0, 70.0), "wet": False, "long_lead": False},
    {"id": "underlay", "label": "Underlayment / moisture barrier", "kw": ["underlayment", "underlayment", "pad", "felt paper", "moisture barrier"],
     "measure": "sqft", "pack": "roll", "pack_size": 300.0, "pack_label": "roll",
     "waste": 0.10, "cure": 0, "ref": (18.0, 70.0), "wet": False, "long_lead": False},
    {"id": "trim", "label": "Trim / casing", "kw": ["casing", "trim", "moulding", "molding", "architrave"],
     "measure": "lf", "pack": "piece", "pack_size": 8.0, "pack_label": "8 ft length",
     "waste": 0.10, "cure": 0, "ref": (8.0, 40.0), "wet": False, "long_lead": False},
    {"id": "baseboard", "label": "Baseboard", "kw": ["baseboard", "base board", "skirting", "scribe"],
     "measure": "lf", "pack": "piece", "pack_size": 8.0, "pack_label": "8 ft length",
     "waste": 0.10, "cure": 0, "ref": (10.0, 45.0), "wet": False, "long_lead": False},
    {"id": "door", "label": "Door / door frame", "kw": ["door", "door frame", "doorframe"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (70.0, 600.0), "wet": False, "long_lead": True},
    {"id": "window", "label": "Window", "kw": ["window", "sash"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (200.0, 1200.0), "wet": False, "long_lead": True},
    {"id": "cabinet", "label": "Cabinet / vanity", "kw": ["cabinet", "vanity", "base cabinet", "wall cabinet"],
     "variants": ["base cabinet", "wall cabinet", "vanity"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (180.0, 2500.0), "wet": False, "long_lead": True},
    {"id": "counter", "label": "Countertop", "kw": ["counter", "countertop", "worktop", "counter top"],
     "measure": "sqft", "pack": "slab", "pack_size": 30.0, "pack_label": "slab",
     "waste": 0.05, "cure": 0, "ref": (600.0, 2400.0), "wet": False, "long_lead": True},
    {"id": "backsplash", "label": "Backsplash tile", "kw": ["backsplash", "back splash"],
     "measure": "sqft", "pack": "box", "pack_size": 10.0, "pack_label": "box (10 sqft)",
     "waste": 0.12, "cure": 0, "ref": (25.0, 90.0), "wet": True, "long_lead": False},
    {"id": "lumber", "label": "Lumber", "kw": ["lumber", "timber", "wood stud", "joist", "beam"],
     "measure": "bf", "pack": "piece", "pack_size": 1.0, "pack_label": "board foot",
     "waste": 0.15, "cure": 0, "ref": (2.0, 12.0), "wet": False, "long_lead": False},
    {"id": "plywood", "label": "Plywood / sheathing", "kw": ["plywood", "sheathing", "osb", "mdf", "hardboard"],
     "measure": "sqft", "pack": "sheet", "pack_size": 32.0, "pack_label": "sheet (4x8)",
     "waste": 0.10, "cure": 0, "ref": (25.0, 85.0), "wet": False, "long_lead": False},
    {"id": "concrete", "label": "Concrete / cement", "kw": ["concrete", "cement", "quikrete", "post hole"],
     "measure": "cuft", "pack": "bag", "pack_size": 0.6, "pack_label": "80 lb bag (0.6 cuft)",
     "waste": 0.10, "cure": 168, "ref": (4.0, 12.0), "wet": False, "long_lead": False},
    {"id": "gravel", "label": "Gravel / base rock", "kw": ["gravel", "base rock", "crushed stone", "road base"],
     "measure": "cuft", "pack": "bag", "pack_size": 0.5, "pack_label": "bag",
     "waste": 0.10, "cure": 0, "ref": (3.0, 12.0), "wet": False, "long_lead": False},
    {"id": "sand", "label": "Sand", "kw": ["sand", "leveling sand", "play sand"],
     "measure": "cuft", "pack": "bag", "pack_size": 0.5, "pack_label": "bag",
     "waste": 0.10, "cure": 0, "ref": (3.0, 12.0), "wet": False, "long_lead": False},
    {"id": "mulch", "label": "Mulch", "kw": ["mulch", "bark", "landscape fabric"],
     "measure": "cuft", "pack": "bag", "pack_size": 2.0, "pack_label": "bag (2 cuft)",
     "waste": 0.10, "cure": 0, "ref": (2.0, 10.0), "wet": False, "long_lead": False},
    {"id": "paver", "label": "Paver", "kw": ["paver", "paving stone", "flagstone", "retaining block"],
     "measure": "sqft", "pack": "each", "pack_size": 1.0, "pack_label": "each (1 sqft)",
     "waste": 0.10, "cure": 0, "ref": (2.0, 12.0), "wet": False, "long_lead": False},
    {"id": "sod", "label": "Sod / turf", "kw": ["sod", "turf", "lawn"],
     "measure": "sqft", "pack": "sqyd", "pack_size": 9.0, "pack_label": "square yard",
     "waste": 0.05, "cure": 0, "ref": (9.0, 40.0), "wet": False, "long_lead": True},
    {"id": "insulation", "label": "Insulation", "kw": ["insulation", "batting", "mineral wool", "fiberglass"],
     "measure": "sqft", "pack": "bag", "pack_size": 64.0, "pack_label": "bag (~64 sqft)",
     "waste": 0.05, "cure": 0, "ref": (40.0, 120.0), "wet": False, "long_lead": False},
    {"id": "shingle", "label": "Roof shingles", "kw": ["shingle", "roofing", "roof"],
     "measure": "sqft", "pack": "bundle", "pack_size": 33.0, "pack_label": "bundle (33 sqft)",
     "waste": 0.10, "cure": 0, "ref": (60.0, 160.0), "wet": False, "long_lead": False},
    {"id": "wire", "label": "Electrical wire / cable", "kw": ["romex", "wire", "cable", "conduit", "nm-b"],
     "measure": "lf", "pack": "roll", "pack_size": 250.0, "pack_label": "roll (250 lf)",
     "waste": 0.10, "cure": 0, "ref": (25.0, 180.0), "wet": False, "long_lead": False},
    {"id": "electrical", "label": "Electrical device / fixture", "kw": ["outlet", "switch", "receptacle", "light fixture", "fan", "thermostat"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (5.0, 300.0), "wet": False, "long_lead": False},
    {"id": "pipe", "label": "Plumbing pipe", "kw": ["pipe", "cpvc", "pex", "drain line", "supply line"],
     "measure": "lf", "pack": "piece", "pack_size": 10.0, "pack_label": "10 ft length",
     "waste": 0.10, "cure": 0, "ref": (3.0, 40.0), "wet": True, "long_lead": False},
    {"id": "fixture", "label": "Plumbing fixture", "kw": ["faucet", "toilet", "sink", "showerhead", "valve", "shower valve"],
     "variants": ["faucet", "toilet", "sink", "showerhead", "shower valve", "valve"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (25.0, 900.0), "wet": True, "long_lead": False},
    {"id": "protection", "label": "Floor / surface protection", "kw": ["drop cloth", "plastic sheeting", "floor protection", "cardboard"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.05, "cure": 0, "ref": (3.0, 40.0), "wet": False, "long_lead": False},
    {"id": "spacer", "label": "Tile spacers / levelling clips", "kw": ["spacer", "levelling clip", "leveling clip"],
     "measure": "each", "pack": "box", "pack_size": 50.0, "pack_label": "box (50)",
     "waste": 0.05, "cure": 0, "ref": (3.0, 18.0), "wet": False, "long_lead": False},
    {"id": "transition", "label": "Transition / threshold strip", "kw": ["transition", "threshold", "reducer"],
     "measure": "lf", "pack": "piece", "pack_size": 8.0, "pack_label": "8 ft length",
     "waste": 0.10, "cure": 0, "ref": (8.0, 45.0), "wet": False, "long_lead": False},
    {"id": "roller", "label": "Roller / brush covers", "kw": ["roller", "paint brush", "brush cover"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.05, "cure": 0, "ref": (3.0, 25.0), "wet": False, "long_lead": False},
    {"id": "disposal", "label": "Disposal / bags / dumpster", "kw": ["dumpster", "disposal", "trash bag", "contractor bag", "haul away", "haul-away"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (5.0, 600.0), "wet": False, "long_lead": False},
    {"id": "framing_lumber", "label": "Framing lumber (2x4)", "kw": ["framing", "2x4", "pressure treated lumber", "deck framing", "wall framing"],
     "measure": "lf", "pack": "piece", "pack_size": 8.0, "pack_label": "8 ft length",
     "waste": 0.15, "cure": 0, "ref": (8.0, 30.0), "wet": False, "long_lead": False},
    {"id": "deckboard", "label": "Deck board", "kw": ["deck board", "decking", "decking board"],
     "measure": "lf", "pack": "piece", "pack_size": 8.0, "pack_label": "8 ft length",
     "waste": 0.10, "cure": 0, "ref": (12.0, 45.0), "wet": False, "long_lead": False},
    {"id": "ppe", "label": "Safety gear (respirator, glasses)", "kw": ["respirator", "n95", "p100", "safety glasses", "ear protection"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (5.0, 40.0), "wet": False, "long_lead": False},
    {"id": "masking_tape", "label": "Masking tape", "kw": ["painter's tape", "masking tape", "painters tape"],
     "measure": "each", "pack": "each", "pack_size": 1.0, "pack_label": "each",
     "waste": 0.0, "cure": 0, "ref": (3.0, 16.0), "wet": False, "long_lead": False},
]

MATERIALS_BY_ID = {m["id"]: m for m in MATERIALS}

# keyword -> material id, longest keyword wins when matching
_MATERIAL_INDEX = []
for _m in MATERIALS:
    for _kw in _m["kw"]:
        _MATERIAL_INDEX.append((_kw, _m["id"]))
_MATERIAL_INDEX.sort(key=lambda kv: -len(kv[0]))


def match_material(text):
    """Return (material_id, matched_keyword) for a free-text material name.

    Plural forms match too, so 'Tile spacers' finds the spacer material and
    not the tile material.
    """
    if not text:
        return None, None
    low = " " + str(text).lower() + " "
    best = None
    for kw, mid in _MATERIAL_INDEX:
        if re.search(r"\b" + re.escape(kw) + r"s?\b", low):
            if best is None or len(kw) > len(best[1]):
                best = (mid, kw)
    return (best[0], best[1]) if best else (None, None)



# --------------------------------------------------------------------------
# Tool database
# --------------------------------------------------------------------------

TOOLS = {
    "tile_saw": {"name": "Wet tile saw", "alt": "Rent a wet saw for a day, or use a manual snap cutter for straight cuts",
                 "kw": ["tile saw", "wet saw"]},
    "notched_trowel": {"name": "Notched trowel (1/4 in notch for 1/4 in tile)", "alt": "A notched plastic trowel from a hardware store works for small areas",
                       "kw": ["notched trowel", "trowel"]},
    "grout_float": {"name": "Grout float", "alt": "A soft rubber float or a piece of cardboard works", "kw": ["grout float"]},
    "mortar_mixer": {"name": "Drill with paddle mixer", "alt": "Mix thinset in a bucket with a mixing paddle or sturdy stick", "kw": ["paddle mixer"]},
    "chisel": {"name": "Chisel and hammer", "alt": "A pry bar and a flat screw driver will lift most old flooring", "kw": ["chisel", "pry bar", "hammer"]},
    "demo_saw": {"name": "Demo saw / reciprocating saw", "alt": "An oscillating multi-tool cuts tile and trim without a full saw", "kw": ["demo saw", "reciprocating saw", "oscillating", "multi-tool", "multitool"]},
    "level": {"name": "Spirit level (24 in or longer)", "alt": "A straightedge with a phone level works for checking plumb", "kw": ["spirit level", "level"]},
    "stud_finder": {"name": "Stud finder", "alt": "Tap and knock on the wall to find studs; a magnet on a nail also works", "kw": ["stud finder"]},
    "drywall_saw": {"name": "Drywall saw / utility knife", "alt": "A utility knife with a fresh blade and a straightedge cuts drywall", "kw": ["drywall saw", "utility knife"]},
    "mud_pan": {"name": "Mud pan and drywall knives (6 in + 12 in)", "alt": "A plastic putty knife and a shallow tray work for small patches", "kw": ["mud pan", "putty knife", "drywall knife"]},
    "sander": {"name": "Orbital sander", "alt": "A sanding block and 120/220 grit paper is fine for a small room", "kw": ["sander", "sanding block"]},
    "sprayer": {"name": "Paint sprayer", "alt": "A quality roller with a microfibre cover cuts edges instead", "kw": ["sprayer", "spray gun"]},
    "roller_frame": {"name": "Roller frame and covers", "alt": "A foam roller in a tray works for flat walls", "kw": ["roller frame", "roller", "paint roller"]},
    "ladder": {"name": "Step ladder (and an extension ladder for high work)", "alt": "A sturdy step ladder rated above your working height", "kw": ["ladder"]},
    "ppe": {"name": "Respirator (N95/P100), safety glasses, gloves, ear protection", "alt": "A dust mask rated N95 and safety glasses are the minimum",
            "kw": ["respirator", "n95", "p100", "safety glasses", "gloves", "ear protection", "dust mask"]},
    "saw": {"name": "Circular saw or miter saw", "alt": "A hand saw and a speed square work for straight cuts", "kw": ["circular saw", "miter saw", "hand saw", "table saw"]},
    "jigsaw": {"name": "Jigsaw", "alt": "A hand saw with a fresh blade plus a template", "kw": ["jigsaw"]},
    "drill": {"name": "Drill/driver with bits", "alt": "A good screwdriver set plus a cordless drill covers most fixings", "kw": ["drill", "cordless drill", "driver"]},
    "wrench": {"name": "Basin wrench and adjustable pliers", "alt": "Channellocks plus a strap wrench will often free a stuck fitting", "kw": ["basin wrench", "wrench", "pliers", "channellocks"]},
    "post_hoe": {"name": "Post hole digger / auger", "alt": "A narrow digging bar and a lot of elbow grease", "kw": ["post hole", "auger", "digger"]},
    "wheelbarrow": {"name": "Wheelbarrow and shovel", "alt": "Buckets and a flat shovel move most of a day's debris", "kw": ["wheelbarrow", "shovel", "bucket"]},
    "concrete_mixer": {"name": "Concrete mixer or wheelbarrow for mixing", "alt": "Mixing bags in a wheelbarrow works for a few bags", "kw": ["concrete mixer", "cement mixer"]},
    "level_laser": {"name": "Laser or long level for grading", "alt": "A long straightedge and a line level", "kw": ["laser"]},
    "tile_cutter": {"name": "Manual tile cutter", "alt": "A scoring tool with a snapping rail", "kw": ["tile cutter", "snap cutter"]},
    "shop_vac": {"name": "Shop vac", "alt": "A broom and a dustpan work, but expect to sweep twice", "kw": ["shop vac", "vacuum"]},
    "broom": {"name": "Broom and dustpan", "alt": "A stiff brush and a bucket", "kw": ["broom", "dustpan"]},
    "sponge": {"name": "Grout sponge / float pad", "alt": "A damp cellulose sponge works for wiping grout", "kw": ["sponge"]},
    "miter_saw": {"name": "Miter saw", "alt": "A hand miter box with a backsaw makes the same cuts", "kw": ["miter saw", "miter box"]},
    "caulk_gun": {"name": "Caulk gun", "alt": "A cheap dripless gun from a hardware store is fine", "kw": ["caulk gun"]},
    "chalk_line": {"name": "Chalk line", "alt": "A pencil line snapped with a string and a nail", "kw": ["chalk line"]},
    "square": {"name": "Speed square / straightedge", "alt": "A folding carpenter square or a straight timber edge", "kw": ["speed square", "carpenter square", "square"]},
}

#
# triggers : keywords that pull the task into the schedule
# hours    : hands-on working time
# cure     : extra wait (hours) after the task before the next task may start
# tools    : tool keys required
# types    : project types the task belongs to (None = any type)
# deps     : task ids that must finish first
# --------------------------------------------------------------------------

TASKS = [
    {"id": "demo", "name": "Demo and remove existing material", "hours": 4, "cure": 0,
     "triggers": ["demo", "demolition", "remove existing", "strip", "tear out", "rip out", "remove old", "tearout"],
     "tools": ["ppe", "chisel", "demo_saw", "wheelbarrow", "broom"], "types": None, "deps": []},
    {"id": "haul", "name": "Haul away debris", "hours": 2, "cure": 0,
     "triggers": ["haul", "disposal", "dumpster", "trash removal", "remove debris"],
     "tools": ["wheelbarrow"], "types": None, "deps": ["demo"]},
    {"id": "subfloor", "name": "Repair and level the subfloor", "hours": 5, "cure": 24,
     "triggers": ["subfloor", "leveling", "level the", "plywood subfloor", "floor level", "screed"],
     "tools": ["level", "saw", "drill"], "types": None, "deps": ["demo"]},
    {"id": "framing", "name": "Framing and blocking", "hours": 8, "cure": 0,
     "triggers": ["framing", "frame wall", "blocking", "studs", "header", "beam"],
     "tools": ["saw", "drill", "level", "ppe"], "types": None, "deps": ["demo"]},
    {"id": "waterproof", "name": "Waterproof membrane (wet area)", "hours": 3, "cure": 24,
     "triggers": ["waterproof", "membrane", "shower pan", "wet area"],
     "tools": ["roller_frame"], "types": ["bathroom", "kitchen"], "deps": ["subfloor"]},
    {"id": "backer", "name": "Install cement backer board", "hours": 4, "cure": 24,
     "triggers": ["backer", "cement board", "tile backer"],
     "tools": ["notched_trowel", "drill", "level"], "types": None, "deps": ["subfloor"]},
    {"id": "tile", "name": "Set tile", "hours": 8, "cure": 24,
     "triggers": ["tile", "tiling", "set tile", "lay tile", "backsplash", "install tile"],
     "tools": ["tile_saw", "notched_trowel", "level", "tile_cutter", "square"], "types": None, "deps": ["backer"]},
    {"id": "grout", "name": "Grout and clean", "hours": 3, "cure": 24,
     "triggers": ["grout", "pointing"],
     "tools": ["grout_float", "sponge"], "types": None, "deps": ["tile"]},
    {"id": "caulk", "name": "Caulk and seal joints", "hours": 1, "cure": 24,
     "triggers": ["caulk", "sealant", "silicone"],
     "tools": ["caulk_gun"], "types": None, "deps": ["grout"]},
    {"id": "drywall_hang", "name": "Hang drywall", "hours": 8, "cure": 0,
     "triggers": ["hang drywall", "drywall hang", "install drywall", "sheetrock"],
     "tools": ["drywall_saw", "drill", "level", "ppe"], "types": None, "deps": ["framing"]},
    {"id": "drywall_finish", "name": "Tape, mud and sand drywall", "hours": 6, "cure": 24,
     "triggers": ["mud", "joint compound", "tape and mud", "skim coat", "finish drywall", "sand drywall"],
     "tools": ["mud_pan", "sander", "ppe"], "types": None, "deps": ["drywall_hang"]},
    {"id": "prep", "name": "Prep surfaces (clean, scrape, sand, patch)", "hours": 4, "cure": 4,
     "triggers": ["prep", "sand", "clean the walls", "patch", "fill holes", "scraping"],
     "tools": ["sander", "broom", "mud_pan"], "types": None, "deps": []},
    {"id": "prime", "name": "Prime", "hours": 2, "cure": 3,
     "triggers": ["prime", "primer", "undercoat"],
     "tools": ["roller_frame", "broom"], "types": None, "deps": ["prep"]},
    {"id": "paint", "name": "Paint", "hours": 6, "cure": 6,
     "triggers": ["paint", "repaint", "colour", "color", "coat the walls"],
     "tools": ["roller_frame", "broom", "ppe"], "types": None, "deps": ["prime"]},
    {"id": "flooring_install", "name": "Install flooring", "hours": 7, "cure": 0,
     "triggers": ["install flooring", "lay flooring", "flooring", "plank floor", "carpet", "laminate"],
     "tools": ["saw", "jigsaw", "level", "ppe"], "types": None, "deps": ["subfloor"]},
    {"id": "trim_install", "name": "Install trim and baseboard", "hours": 4, "cure": 0,
     "triggers": ["baseboard", "trim", "casing", "moulding"],
     "tools": ["saw", "miter_saw", "level", "chalk_line"], "types": None, "deps": ["paint"]},
    {"id": "cabinet_install", "name": "Install cabinets and counters", "hours": 8, "cure": 0,
     "triggers": ["cabinet", "counter", "vanity", "worktop"],
     "tools": ["level", "drill", "ppe"], "types": None, "deps": ["subfloor"]},
    {"id": "fixture_install", "name": "Install fixtures (faucet, toilet, sink)", "hours": 4, "cure": 0,
     "triggers": ["faucet", "toilet", "sink", "showerhead", "fixture", "plumb"],
     "tools": ["wrench", "ppe"], "types": None, "deps": ["cabinet_install"]},
    {"id": "electrical", "name": "Electrical rough-in and devices", "hours": 6, "cure": 0,
     "triggers": ["electrical", "outlet", "receptacle", "switch", "wiring", "wire", "light fixture"],
     "tools": ["drill", "ppe"], "types": None, "deps": []},
    {"id": "footings", "name": "Dig and pour footings", "hours": 8, "cure": 168,
     "triggers": ["footing", "post hole", "concrete pour", "piers", "deck frame"],
     "tools": ["post_hoe", "concrete_mixer", "level", "ppe"], "types": ["deck"], "deps": []},
    {"id": "deck_framing", "name": "Frame the deck", "hours": 10, "cure": 0,
     "triggers": ["deck frame", "framing", "joist", "beam", "ledger"],
     "tools": ["saw", "drill", "level", "ppe"], "types": ["deck"], "deps": ["footings"]},
    {"id": "deck_boards", "name": "Lay deck boards", "hours": 8, "cure": 0,
     "triggers": ["deck board", "decking", "deck surface"],
     "tools": ["saw", "level", "ppe"], "types": ["deck"], "deps": ["deck_framing"]},
    {"id": "deck_finish", "name": "Sand and stain the deck", "hours": 6, "cure": 48,
     "triggers": ["stain", "seal", "deck finish"],
     "tools": ["sander", "roller_frame"], "types": ["deck"], "deps": ["deck_boards"]},
    {"id": "paver_base", "name": "Base and compaction for paving", "hours": 8, "cure": 0,
     "triggers": ["paver", "patio", "retaining wall", "walkway", "flagstone"],
     "tools": ["wheelbarrow", "level_laser", "ppe"], "types": None, "deps": []},
    {"id": "cleanup", "name": "Final clean and protection removal", "hours": 2, "cure": 0,
     "triggers": ["cleanup", "clean up", "sweep", "vacuum", "final clean"],
     "tools": ["shop_vac", "broom"], "types": None, "deps": []},
]

TASKS_BY_ID = {t["id"]: t for t in TASKS}

# Skill levels a project can be attempted at.
SKILL_DIFFICULTY = {
    "tile": 3, "drywall_hang": 3, "drywall_finish": 3, "framing": 3, "footings": 3,
    "deck_framing": 3, "electrical": 3, "fixture_install": 3, "subfloor": 2,
    "cabinet_install": 2, "painting": 1, "prep": 1, "trim_install": 2, "flooring_install": 2,
    "paver_base": 2, "waterproof": 3, "backer": 2, "grout": 1, "demo": 1, "cleanup": 1,
}

# Materials whose availability depends on a lead time.
LONG_LEAD_HINT = {m["id"] for m in MATERIALS if m.get("long_lead")}

import re  # noqa: E402  (kept last so the pure-data tables read first)
