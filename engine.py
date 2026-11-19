"""reno-forge engine.

Pure standard library. Takes a renovation brief in plain text and returns a
materials takeoff, a cost roll-up, a schedule, a tool checklist, a scored
review with findings and a prioritised fix plan.
"""

import math
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta

from materials import (
    CONTAINER_UNITS,
    LONG_LEAD_HINT,
    MATERIALS_BY_ID,
    MEASURE_UNITS,
    SKILL_DIFFICULTY,
    TASKS_BY_ID,
    TOOLS,
    UNIT_ALIASES,
    match_material,
    normalise_unit,
)

# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------

PROFILES = {
    "general": {
        "label": "General review",
        "weights": {"takeoff": 0.22, "cost": 0.22, "schedule": 0.18, "safety": 0.24, "completeness": 0.14},
    },
    "budget_audit": {
        "label": "Budget audit",
        "weights": {"takeoff": 0.20, "cost": 0.38, "schedule": 0.12, "safety": 0.18, "completeness": 0.12},
    },
    "diy_feasibility": {
        "label": "DIY feasibility",
        "weights": {"takeoff": 0.18, "cost": 0.16, "schedule": 0.16, "safety": 0.20, "completeness": 0.30},
    },
    "timeline": {
        "label": "Timeline realism",
        "weights": {"takeoff": 0.14, "cost": 0.12, "schedule": 0.44, "safety": 0.18, "completeness": 0.12},
    },
    "safety_code": {
        "label": "Safety and code",
        "weights": {"takeoff": 0.12, "cost": 0.10, "schedule": 0.12, "safety": 0.48, "completeness": 0.18},
    },
}

AXES = OrderedDict([
    ("takeoff", ("Take-off accuracy", "Are the quantities you will buy right?")),
    ("cost", ("Cost control", "Is the money under control?")),
    ("schedule", ("Schedule realism", "Will it actually take as long as you think?")),
    ("safety", ("Safety and code", "Will this build fail inspection or hurt someone?")),
    ("completeness", ("Project completeness", "Is anything missing from the plan?")),
])

SEVERITY_POINTS = {"high": 18.0, "medium": 8.0, "low": 3.0}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

VERDICT_BANDS = [
    (85, "ready_to_build", "Ready to build"),
    (70, "mostly_ready", "Mostly ready"),
    (55, "needs_attention", "Needs attention"),
    (40, "needs_rework", "Needs rework"),
    (0, "unsafe_plan", "Unsafe or unbuildable plan"),
]

# --------------------------------------------------------------------------
# Small parsing helpers
# --------------------------------------------------------------------------

SECTION_ALIASES = {
    "materials": "materials", "material": "materials", "supplies": "materials",
    "shopping list": "materials", "shopping list:": "materials", "bill of materials": "materials",
    "scope": "scope", "scope of work": "scope", "work": "scope", "tasks": "scope",
    "description": "scope", "plan": "scope", "what we're doing": "scope", "renovation": "scope",
    "tools": "tools", "tool": "tools", "equipment": "tools", "my tools": "tools", "toolbox": "tools",
    "budget": "budget", "cost": "budget", "costs": "budget", "price": "budget", "money": "budget",
    "schedule": "schedule", "timeline": "schedule", "timing": "schedule", "dates": "schedule",
    "details": "details", "notes": "details", "info": "details", "project": "details",
    "project info": "details", "conditions": "details", "constraints": "details",
}

KEY_FIELDS = {
    "budget": "budget", "total budget": "budget", "budget target": "budget", "max budget": "budget",
    "spend limit": "budget",
    "tax": "tax_pct", "sales tax": "tax_pct", "vat": "tax_pct", "tax rate": "tax_pct",
    "contingency": "contingency_pct", "contingency budget": "contingency_pct", "contingency allowance": "contingency_pct",
    "labor": "labor", "labour": "labor", "labor cost": "labor", "labour cost": "labor",
    "start": "start_date", "start date": "start_date", "startdate": "start_date",
    "deadline": "deadline", "finish": "deadline", "finish date": "deadline",
    "complete by": "deadline", "due": "deadline", "must be done by": "deadline",
    "duration": "duration_days", "timeframe": "duration_days", "time frame": "duration_days",
    "how long": "duration_days", "time available": "duration_days",
    "skill": "skills", "skills": "skills", "skill level": "skills", "my skill level": "skills",
    "experience": "skills", "skillset": "skills",
    "type": "project_type", "project type": "project_type", "room": "project_type",
    "area": "area", "total area": "area", "floor area": "area", "room size": "area",
    "size": "area", "square footage": "area",
    "location": "location", "setting": "location", "indoor or outdoor": "location",
    "year built": "year_built", "home built": "year_built",
}

MONEY_RE = re.compile(r"^\$?\s*([\d,]+(?:\.\d+)?)\s*(k)?$", re.I)
PCT_RE = re.compile(r"^([\d.]+)\s*%")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
PRICE_RE = re.compile(
    r"\$\s*(?P<price>\d+(?:[.,]\d+)?)\s*(?:k\b)?"
    r"(?:\s*(?:/|per\s+|@)\s*(?P<basis>[A-Za-z][A-Za-z./]*(?:\s+[A-Za-z][A-Za-z./]*)?))?",
    re.I,
)
_UNIT_PHRASES = sorted(UNIT_ALIASES.keys(), key=len, reverse=True)


def parse_money(raw):
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("$", "").strip()
    if not s:
        return None
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*(k|K)?$", s)
    if not m:
        m2 = re.match(r"^(-?\d+(?:\.\d+)?)\s*(k|K)\b", s)
        if not m2:
            return None
        return float(m2.group(1)) * 1000.0
    val = float(m.group(1))
    if m.group(2):
        val *= 1000.0
    return val


def parse_pct(raw):
    if raw is None:
        return None
    m = PCT_RE.match(str(raw).strip())
    if m:
        return float(m.group(1)) / 100.0
    try:
        val = float(str(raw).strip().rstrip("%"))
    except ValueError:
        return None
    if 0 < val <= 100:
        return val / 100.0
    return None


def parse_date(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d %Y", "%B %d %Y", "%b %d", "%B %d"):
        try:
            d = datetime.strptime(s, fmt)
            if fmt in ("%b %d", "%B %d"):
                d = d.replace(year=date.today().year)
            return d.date().isoformat()
        except ValueError:
            continue
    return None


CONTAINER_FAMILY = {
    "gal": "gallon", "gallon": "gallon", "can": "gallon",
    "sheet": "sheet", "box": "box", "pkg": "box", "pack": "box",
    "bag": "bag", "tub": "tub", "tube": "tube", "roll": "roll",
    "bundle": "bundle", "piece": "piece", "each": "piece",
    "slab": "slab", "sqyd": "sqyd", "set": "set", "pair": "pair",
}


def basis_kind(basis, mat):
    """How a quoted price basis applies: 'measure', 'container' or None."""
    if basis is None or mat is None:
        return None
    measure, pack = mat["measure"], mat["pack"]
    if basis == measure and basis not in ("each", "count"):
        return "measure"
    if basis in ("each", "count") and measure == "each":
        return "measure"
    if CONTAINER_FAMILY.get(basis) == CONTAINER_FAMILY.get(pack):
        return "container"
    if basis == "sqyd" and measure == "sqft":
        return "container"
    if basis == measure:
        return "measure"
    return None


def name_similarity(a, b):
    """Token overlap between two material names."""
    ta = set(re.findall(r"[a-z0-9]+", (a or "").lower()))
    tb = set(re.findall(r"[a-z0-9]+", (b or "").lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def normalise_measure(value, unit, material):
    """Convert a (value, unit) pair into the material's canonical measure."""
    if value is None:
        return None, None
    mat = MATERIALS_BY_ID.get(material)
    if mat is None:
        return value, unit
    target = mat["measure"]
    if unit == target:
        return value, target
    # sqm -> sqft
    if unit == "sqm" and target == "sqft":
        return value * 10.7639104167, "sqft"
    if unit == "sqft" and target == "sqm":
        return value / 10.7639104167, "sqm"
    # sqft -> sqyd (carpet is measured in sqft but sold by the yard)
    if unit == "sqft" and target == "sqyd":
        return value / 9.0, "sqyd"
    if unit == "sqyd" and target == "sqft":
        return value * 9.0, "sqft"
    # a container quantity converts through the pack size
    if unit in CONTAINER_UNITS and mat["pack"] == unit:
        return value * mat["pack_size"], target
    if unit == "each" and target == "each":
        return value, "each"
    return None, None


def extract_qty(text):
    """Find a '60 sqft' style quantity. Returns (qty, unit, rest).

    The unit phrase is matched against the known alias table, so '12x12' in a
    material name is not mistaken for a quantity while '18 linear ft' is.
    """
    nums = list(NUM_RE.finditer(text))
    best = None
    for i, m in enumerate(nums):
        stop = nums[i + 1].start() if i + 1 < len(nums) else len(text)
        tail = text[m.end():stop].strip()
        low_tail = tail.lower()
        for phrase in _UNIT_PHRASES:
            if not low_tail.startswith(phrase):
                continue
            after = tail[len(phrase):]
            if after and (after[0].isalnum() or after[0] == "."):
                continue
            unit = normalise_unit(phrase)
            if unit is None:
                continue
            best = (float(m.group(0).replace(",", "")), unit, m.start())
            break
    if best is None:
        # a trailing bare number counts, e.g. 'Drywall screws 800'
        m = re.search(r"(?<![\dXx])(\d+(?:[.,]\d+)?)\s*$", text.strip())
        if m:
            qty = float(m.group(1).replace(",", ""))
            rest = text.strip()[: m.start(1)].strip(" \t-:,;")
            return qty, None, rest or text
        return None, None, text
    qty, unit, idx = best
    rest = text[:idx].strip(" 	-:,;")
    if not rest:
        return qty, unit, text
    return qty, unit, rest




def parse_material_line(line):
    """Parse one materials line into a dict of raw fields."""
    raw = line.strip()
    if not raw:
        return None
    text = raw.lstrip("-*• 	")
    price = None
    basis = None
    m = PRICE_RE.search(text)
    if m:
        digits = m.group("price").replace(",", "")
        if digits.count(".") <= 1:
            price = float(digits)
        if m.group("basis"):
            raw_basis = m.group("basis").strip()
            basis = normalise_unit(raw_basis)
            if basis is None and " " in raw_basis:
                basis = normalise_unit(raw_basis.split()[0])
        text = (text[: m.start()] + " " + text[m.end():]).strip()
    text = re.sub(r"\s*@+\s*$", "", text).rstrip("-,;: ")
    qty, unit, rest = extract_qty(text)
    name = rest.strip(" 	-:,;")
    if not name:
        name = text.strip(" 	-:,;")
        qty = unit = None
    return {
        "raw": raw,
        "name": name,
        "qty": qty,
        "unit": unit,
        "price": price,
        "basis": basis,
    }


DEMO_WORDS = ("remove", "demo", "demolition", "strip", "tear out", "rip out", "take out",
              "existing", "old ", "discard", "haul away", "haul-away")

WET_SURFACE_WORDS = ("shower", "tub surround", "wet room", "wet area", "splash zone",
                     "splashback zone", "shower pan", "pool", "sauna")
WET_WORDS = ("bathroom", "bath", "shower", "tub", "wet room", "wet area", "sink area")

PERMIT_WORDS = ("permit", "building department", "inspection", "code", "engineer", "architect",
                "survey", "zoning")

STRUCTURAL_WORDS = ("load bearing", "load-bearing", "bearing wall", "support wall",
                    "header", "structural", "rmr", "truss", "remove a wall",
                    "wall removal", "demolish a wall")

HAZMAT_WORDS = ("asbestos", "lead paint", "popcorn ceiling", "viny", "asbestos tile",
                "lead-based", "lead based", "pre-1978", "pre 1978")


def is_demo_line(text):
    low = " " + str(text).lower() + " "
    return any(w in low for w in DEMO_WORDS)


# --------------------------------------------------------------------------
# Brief parsing
# --------------------------------------------------------------------------

def split_sections(lines):
    sections = OrderedDict()
    current = "details"
    for raw in lines:
        stripped = re.sub(r"^[#>*\s]+", "", raw.strip())
        stripped = re.sub(r"[:：]\s*$", "", stripped).strip().lower()
        if stripped in SECTION_ALIASES:
            current = SECTION_ALIASES[stripped]
            continue
        sections.setdefault(current, []).append(raw.rstrip())
    return sections


def parse_brief(text):
    """Parse the free-text brief into structured inputs."""
    text = text or ""
    raw_lines = text.splitlines()
    sections = split_sections(raw_lines)
    all_lines = [ln.strip() for ln in raw_lines if ln.strip()]

    fields = {}
    for ln in all_lines:
        m = re.match(r"^(?P<key>[A-Za-z][A-Za-z /]{0,26}?)\s*[:=]\s*(?P<val>.+)$", ln)
        if not m:
            continue
        key = m.group("key").strip().lower()
        val = m.group("val").strip()
        field = KEY_FIELDS.get(key)
        if field and field not in fields:
            fields[field] = val

    project_name = None
    for ln in all_lines:
        m = re.match(r"^project\s*[:=]\s*(.+)$", ln, re.I)
        if m:
            project_name = m.group(1).strip()
            break
    if not project_name:
        for ln in sections.get("details", []):
            candidate = re.sub(r"^[#>*\s]+", "", ln.strip()).strip()
            if candidate and not re.match(r"^[A-Za-z][A-Za-z /]{0,26}\s*[:=]", candidate):
                project_name = candidate
                break
    if not project_name:
        project_name = "Untitled renovation"

    scope_items = []
    for ln in sections.get("scope", []):
        item = re.sub(r"^[-*•\s]+", "", ln.strip())
        if not item:
            continue
        qty, unit, rest = extract_qty(item)
        if unit is None:
            # try 'Area: 60 sqft' style inside the line
            m = re.search(r"(?:area|size|quantity|qty)\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*([A-Za-z][A-Za-z./]{0,18})", item, re.I)
            if m:
                u = normalise_unit(m.group(2))
                if u:
                    qty, unit = float(m.group(1).replace(",", "")), u
        scope_items.append({
            "text": item,
            "qty": qty,
            "unit": unit,
            "demo": is_demo_line(item),
        })

    material_lines = []
    for ln in sections.get("materials", []):
        item = re.sub(r"^[-*•\s]+", "", ln.strip())
        if not item or ":" == item:
            continue
        parsed = parse_material_line(item)
        if parsed and parsed["name"]:
            material_lines.append(parsed)

    user_tools = []
    for ln in sections.get("tools", []):
        item = re.sub(r"^[-*•\s]+", "", ln.strip())
        if item:
            user_tools.append(item)

    # numbers that appear anywhere as a bare area
    area = None
    if "area" in fields:
        qty, unit, _ = extract_qty(fields["area"])
        if qty is not None and unit in ("sqft", "sqm", "sqyd"):
            area = qty * (10.7639104167 if unit == "sqm" else (9.0 if unit == "sqyd" else 1.0))
        else:
            area = parse_money(fields["area"])
    if area is None:
        for item in scope_items:
            if item["qty"] and item["unit"] == "sqft":
                area = max(area or 0, item["qty"])
    if area is None:
        for ln in all_lines:
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:sq\s?ft|sq\.?\s?feet|square feet)", ln, re.I)
            if m:
                area = float(m.group(1).replace(",", ""))
                break

    project_type = (fields.get("project_type") or "").strip().lower()
    if not project_type:
        hay = (" ".join(all_lines)).lower()
        if any(w in hay for w in ("bathroom", "bath ", "shower", "tub ", "vanity", "toilet")):
            project_type = "bathroom"
        elif "kitchen" in hay:
            project_type = "kitchen"
        elif "deck" in hay:
            project_type = "deck"
        elif any(w in hay for w in ("drywall", "sheetrock", "hang drywall")):
            project_type = "drywall"
        elif any(w in hay for w in ("flooring", "floor ", "laminate", "hardwood", "carpet")):
            project_type = "flooring"
        elif any(w in hay for w in ("paint", "repaint")):
            project_type = "painting"
        elif any(w in hay for w in ("patio", "paver", "retaining wall", "walkway")):
            project_type = "patio"
        else:
            project_type = "general"

    location = (fields.get("location") or "").strip().lower()
    if not location:
        hay = (" ".join(all_lines)).lower()
        location = "outdoor" if any(w in hay for w in ("deck", "patio", "exterior", "outdoor", "yard", "driveway")) else "indoor"

    skills = (fields.get("skills") or "").strip().lower()
    if skills:
        if "begin" in skills or "novice" in skills or "first" in skills:
            skills = "beginner"
        elif "adv" in skills or "pro" in skills or "expert" in skills:
            skills = "advanced"
        elif "inter" in skills or "mid" in skills or "some" in skills:
            skills = "intermediate"
        else:
            skills = skills or "unknown"

    budget = parse_money(fields.get("budget"))
    labor = parse_money(fields.get("labor"))
    tax_pct = parse_pct(fields.get("tax_pct"))
    contingency_pct = parse_pct(fields.get("contingency_pct"))
    duration_days = None
    if "duration_days" in fields:
        dm = re.match(r"^([\d.]+)", str(fields["duration_days"]).strip())
        if dm:
            duration_days = float(dm.group(1))
    year_built = None
    if "year_built" in fields:
        ym = re.search(r"(19|20)\d{2}", str(fields["year_built"]))
        if ym:
            year_built = int(ym.group(0))

    return {
        "project_name": project_name,
        "project_type": project_type,
        "location": location,
        "skills": skills or "unknown",
        "area_sqft": area,
        "budget": budget,
        "labor": labor,
        "tax_pct": tax_pct,
        "contingency_pct": contingency_pct,
        "duration_days": duration_days,
        "start_date": parse_date(fields.get("start_date")),
        "deadline": parse_date(fields.get("deadline")),
        "year_built": year_built,
        "scope_items": scope_items,
        "materials": material_lines,
        "user_tools": user_tools,
        "sections": {k: v for k, v in sections.items()},
        "raw_text": text,
        "all_lines": all_lines,
    }


# --------------------------------------------------------------------------
# Materials takeoff
# --------------------------------------------------------------------------

COMPANION_AREA = {"grout": "tile", "thinset": "tile", "waterproof": "tile"}
NO_QTY_OK = {"spacer", "fasteners", "abrasive", "protection", "roller", "disposal", "ppe", "masking_tape"}


def build_takeoff(brief):
    """Build the materials takeoff. Returns (rows, notes)."""
    rows = []
    notes = []
    scope = brief["scope_items"]
    area = brief["area_sqft"]

    tile_area = None
    for item in scope:
        if item["demo"]:
            continue
        if item["qty"] and item["unit"] in ("sqft", "sqm"):
            val = item["qty"] * (10.7639104167 if item["unit"] == "sqm" else 1.0)
            mid, kw = match_material(item["text"])
            if mid in ("tile", "backsplash") or (kw and "tile" in kw):
                tile_area = max(tile_area or 0, val)
    if tile_area is None:
        for item in scope:
            if item["demo"]:
                continue
            if item["qty"] and item["unit"] in ("sqft", "sqm"):
                tile_area = max(tile_area or 0, item["qty"] * (10.7639104167 if item["unit"] == "sqm" else 1.0))
                break

    seen = {}
    for parsed in brief["materials"]:
        name = parsed["name"]
        mid, kw = match_material(name)
        mat = MATERIALS_BY_ID.get(mid) if mid else None
        flags = []

        row = {
            "name": name,
            "source_line": parsed["raw"],
            "material_id": mid,
            "keyword": kw,
            "label": mat["label"] if mat else "Unrecognised material",
            "known": bool(mat),
            "measure": mat["measure"] if mat else (parsed["unit"] or "each"),
            "pack": mat["pack"] if mat else "each",
            "pack_label": mat["pack_label"] if mat else "each",
            "pack_size": mat["pack_size"] if mat else 1.0,
            "waste": mat["waste"] if mat else 0.10,
            "cure_hours": mat["cure"] if mat else 0,
            "price": parsed["price"],
            "basis": parsed["basis"],
            "need": None,
            "need_unit": None,
            "need_source": None,
            "packs": None,
            "cost": None,
            "waste_cost": None,
            "flags": flags,
        }

        # 1. quantity written on the material line
        stated_qty = parsed["qty"]
        stated_unit = parsed["unit"]
        need = None
        need_source = None
        if stated_qty is not None and mat is not None:
            if stated_unit is None:
                # a bare number against a counted material means 'each'
                if mat["measure"] == "each":
                    if mat["pack_size"] and mat["pack_size"] > 1 and stated_qty > mat["pack_size"]:
                        # 'screws 800' against a box of 200 is one box of 800
                        need = mat["pack_size"]
                        need_source = "read as one pack of %d" % stated_qty
                        flags.append("pack_content_reading")
                    else:
                        need, need_source = stated_qty, "stated on the material line"
            else:
                conv, _ = normalise_measure(stated_qty, stated_unit, mid)
                if conv is not None:
                    need, need_source = conv, "stated on the material line"
                elif stated_unit in ("lb", "gal"):
                    need, need_source = None, None
                else:
                    flags.append("unit_mismatch")
                    notes.append(
                        f"{name}: quantity is in {stated_unit} but the material is measured in {mat['measure']}."
                    )
        elif stated_qty is not None and mat is None:
            need, need_source = stated_qty, "stated on the material line"
            row["need_unit"] = stated_unit

        # 2. quantity from a scope line
        if need is None and mat is not None:
            best = None
            for item in scope:
                if item["demo"] or not item["qty"]:
                    continue
                imid, ikw = match_material(item["text"])
                variants = set(mat.get("variants", []))
                if kw and ikw and variants and (kw in variants or ikw in variants):
                    # these keywords pick out different products, so they must match exactly
                    hit = (kw == ikw)
                else:
                    hit = (imid == mid)
                if not hit:
                    continue
                conv, _ = normalise_measure(item["qty"], item["unit"], mid)
                if conv is None:
                    if mat["measure"] == "each":
                        flags.append("quantity_not_derivable")
                    continue
                if best is None or conv > best[0]:
                    best = (conv, item["text"])
            if best:
                need, need_source = best[0], "scope: " + best[1]

        # 3. companion area (grout/thinset/waterproof follow the tile area)
        if need is None and mid in COMPANION_AREA:
            comp = COMPANION_AREA[mid]
            comp_area = None
            for item in scope:
                if item["demo"] or not item["qty"] or item["unit"] not in ("sqft", "sqm"):
                    continue
                imid, _ = match_material(item["text"])
                if imid == comp:
                    comp_area = item["qty"] * (10.7639104167 if item["unit"] == "sqm" else 1.0)
                    break
            if comp_area is None:
                comp_area = tile_area
            if comp_area:
                need = comp_area
                need_source = "companion to the tiled area"

        # 4. project area fallback
        if need is None and mat is not None and mat["measure"] == "sqft" and area:
            need = area
            need_source = "assumed from the stated total area"
            flags.append("area_assumed")

        # 5. caulk perimeter estimate
        if need is None and mid == "caulk" and tile_area:
            need = 4.0 * math.sqrt(max(tile_area, 1.0))
            need_source = "estimated perimeter of the tiled area"

        row["need"] = need
        row["need_unit"] = mat["measure"] if mat else (parsed["unit"] or "each")
        row["need_source"] = need_source

        if need is None and mat is not None and mid not in NO_QTY_OK:
            flags.append("missing_quantity")
        if parsed["price"] is None:
            flags.append("missing_price")
        if parsed["price"] is not None and parsed["basis"] is None:
            flags.append("price_no_basis")
        if parsed["basis"] and mat is not None:
            if basis_kind(parsed["basis"], mat) is None:
                flags.append("basis_mismatch")

        if mid:
            seen[mid] = seen.get(mid, 0) + 1

        # waste and packs
        if need is not None:
            waste = row["waste"]
            need_w = need * (1.0 + waste)
            row["need_with_waste"] = need_w
            if mat is not None and mat["pack_size"]:
                packs = need_w / mat["pack_size"]
                row["packs"] = packs
                row["packs_to_buy"] = int(math.ceil(packs - 1e-9))
            else:
                row["packs"] = need_w
                row["packs_to_buy"] = int(math.ceil(need_w))
        else:
            row["need_with_waste"] = None
            row["packs"] = None
            row["packs_to_buy"] = None

        # cost
        price = parsed["price"]
        basis = parsed["basis"]
        row["cost"] = None
        if price is not None and need is not None and mat is not None:
            kind = basis_kind(basis, mat)
            if kind == "measure":
                row["cost"] = need * (1.0 + row["waste"]) * price
                row["price_per_measure"] = price
                row["cost_basis"] = "per " + basis
            elif kind == "container":
                packs_to_buy = row.get("packs_to_buy") or 0
                row["cost"] = packs_to_buy * price
                row["price_per_measure"] = price / mat["pack_size"] if mat["pack_size"] else None
                row["cost_basis"] = "per " + basis

            if row["cost"] is not None:
                base = need * (row.get("price_per_measure") or 0.0)
                row["waste_cost"] = max(row["cost"] - base, 0.0)

        rows.append(row)

    for i, row in enumerate(rows):
        for prev in rows[:i]:
            if not row["material_id"] or row["material_id"] != prev["material_id"]:
                continue
            if row.get("basis") != prev.get("basis"):
                continue
            if row.get("keyword") != prev.get("keyword"):
                continue
            if name_similarity(row["name"], prev["name"]) > 0.55:
                row["flags"].append("duplicate_material")
                prev["flags"].append("duplicate_material")

    return rows, notes



# --------------------------------------------------------------------------
# Cost roll-up
# --------------------------------------------------------------------------

def build_cost(rows, brief):
    material_total = sum(r["cost"] for r in rows if r.get("cost") is not None)
    priced = [r for r in rows if r.get("cost") is not None]
    unpriced = [r for r in rows
                if r.get("price") is None or (r.get("need") is not None and r.get("cost") is None)]
    waste_total = sum(r.get("waste_cost") or 0.0 for r in rows)

    labor = brief.get("labor") or 0.0
    contingency_pct = brief.get("contingency_pct")
    tax_pct = brief.get("tax_pct")

    subtotal = material_total + labor
    contingency = subtotal * contingency_pct if contingency_pct else 0.0
    taxable = subtotal + contingency
    tax = taxable * tax_pct if tax_pct else 0.0
    total = taxable + tax

    budget = brief.get("budget")
    variance = None
    if budget is not None:
        variance = total - budget

    return {
        "material_total": material_total,
        "waste_total": waste_total,
        "labor": labor,
        "labor_known": brief.get("labor") is not None,
        "contingency_pct": contingency_pct,
        "contingency": contingency,
        "tax_pct": tax_pct,
        "tax": tax,
        "total": total,
        "budget": budget,
        "variance": variance,
        "priced_count": len(priced),
        "unpriced_count": len(unpriced),
        "unpriced": [r["name"] for r in unpriced],
        "complete": not unpriced,
        "per_item": sorted(
            [{"name": r["name"], "cost": r["cost"]} for r in priced if r.get("cost")],
            key=lambda d: -d["cost"],
        )[:8],
    }


# --------------------------------------------------------------------------
# Schedule
# --------------------------------------------------------------------------

MATERIAL_TASK = {
    "tile": "tile", "backsplash": "tile", "thinset": "tile", "spacer": "tile",
    "grout": "grout", "caulk": "caulk", "backer": "backer", "waterproof": "waterproof",
    "paint": "paint", "primer": "prime", "roller": "paint", "abrasive": "prep",
    "drywall": "drywall_hang", "mud": "drywall_finish", "fasteners": "drywall_hang",
    "flooring": "flooring_install", "carpet": "flooring_install", "underlay": "flooring_install",
    "baseboard": "trim_install", "trim": "trim_install", "transition": "trim_install",
    "cabinet": "cabinet_install", "counter": "cabinet_install",
    "fixture": "fixture_install", "pipe": "fixture_install",
    "electrical": "electrical", "wire": "electrical",
    "lumber": "framing", "plywood": "framing", "insulation": "framing",
    "concrete": "footings", "gravel": "paver_base", "sand": "paver_base", "paver": "paver_base",
    "stain": "deck_finish", "disposal": "haul", "protection": "demo",
}

AREA_SCALED_TASKS = {"tile", "backer", "waterproof", "grout", "paint", "prep",
                      "drywall_hang", "drywall_finish", "flooring_install", "cabinet_install"}
REF_AREA = 60.0
WORK_HOURS_PER_DAY = 8.0


def build_schedule(brief, rows):
    project_type = brief["project_type"]
    hay = " ".join([brief["project_name"]] + [s["text"] for s in brief["scope_items"]]
                   + [r["name"] for r in rows]).lower()

    selected = []
    for task in TASKS_BY_ID.values():
        if task["types"] and project_type not in task["types"]:
            continue
        triggered = any(re.search(r"\b" + re.escape(trig) + r"\b", hay)
                        for trig in task["triggers"])
        if not triggered:
            continue
        selected.append(task)

    # a tiling job implies demo, subfloor and backer even if the brief is terse
    ids = {t["id"] for t in selected}
    if "tile" in ids:
        for extra in ("demo", "subfloor", "backer", "cleanup"):
            if extra not in ids:
                selected.append(TASKS_BY_ID[extra])
                ids.add(extra)

    # dependencies are resolved against the steps that are actually in the plan
    dep_map = {}
    for task in selected:
        dep_map[task["id"]] = [d for d in task["deps"] if d in ids]
    if "cleanup" in dep_map:
        dep_map["cleanup"] = [i for i in dep_map if i != "cleanup"]

    # material cures per task
    task_materials = {}
    for r in rows:
        tid = MATERIAL_TASK.get(r["material_id"])
        if tid:
            task_materials.setdefault(tid, []).append(r)

    area = brief["area_sqft"]
    for task in selected:
        hours = task["hours"]
        if task["id"] in AREA_SCALED_TASKS and area:
            scale = max(0.45, min(3.0, area / REF_AREA))
            hours = max(1.0, round(hours * scale, 1))
        task["computed_hours"] = hours
        cures = [t.get("cure", 0) for t in task_materials.get(task["id"], [])]
        task["cure_after"] = max([task.get("cure", 0)] + cures) if cures else task.get("cure", 0)

    # topological order
    order = []
    remaining = {t["id"]: t for t in selected}
    guard = 0
    while remaining and guard < 100:
        guard += 1
        progressed = False
        for tid in list(remaining):
            deps = [d for d in dep_map.get(tid, []) if d in remaining]
            if not deps:
                order.append(remaining.pop(tid))
                progressed = True
        if not progressed:
            order.extend(list(remaining.values()))
            break

    # schedule
    by_id = {t["id"]: t for t in order}
    computed = {}
    start_h = 0.0
    for task in order:
        tid = task["id"]
        deps = [d for d in dep_map.get(tid, []) if d in computed]
        if deps:
            start = max(computed[d]["ready_h"] for d in deps)
        elif computed:
            # a step with no resolved dependency still follows the work already planned
            start = max(c["ready_h"] for c in computed.values())
        else:
            start = 0.0
        end = start + task["computed_hours"]
        computed[tid] = {
            "id": tid,
            "name": task["name"],
            "start_h": start,
            "end_h": end,
            "ready_h": end + task["cure_after"],
            "hours": task["computed_hours"],
            "cure_after": task["cure_after"],
            "deps": deps,
            "tools": task["tools"],
            "materials": [r["name"] for r in task_materials.get(tid, [])],
        }

    total_hours = sum(t["hours"] for t in computed.values())
    total_with_cure = max([t["ready_h"] for t in computed.values()], default=0.0)
    working_days = total_with_cure / WORK_HOURS_PER_DAY

    start_date = brief.get("start_date")
    finish_date = None
    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            finish_date = (sd + timedelta(days=math.ceil(working_days))).isoformat()
        except ValueError:
            finish_date = None

    timeline = []
    for task in order:
        c = computed[task["id"]]
        timeline.append({
            "id": c["id"],
            "name": c["name"],
            "start_h": round(c["start_h"], 1),
            "end_h": round(c["end_h"], 1),
            "ready_h": round(c["ready_h"], 1),
            "hours": c["hours"],
            "cure_after": c["cure_after"],
            "day": int(math.floor(c["start_h"] / WORK_HOURS_PER_DAY)) + 1,
            "materials": c["materials"],
            "tool_keys": c["tools"],
            "tools": [TOOLS[t]["name"] for t in c["tools"] if t in TOOLS],
        })

    return {
        "tasks": timeline,
        "total_hours": round(total_hours, 1),
        "calendar_hours": round(total_with_cure, 1),
        "working_days": round(working_days, 1),
        "start_date": start_date,
        "finish_date": finish_date,
        "project_type": project_type,
    }


def build_tools(brief, schedule):
    required = OrderedDict()
    for task in schedule["tasks"]:
        for key in task.get("tool_keys", task["tools"]):
            required.setdefault(key, [])
    have_keys = set()
    for line in brief["user_tools"]:
        low = " " + line.lower() + " "
        for key, meta in TOOLS.items():
            for kw in meta.get("kw", []):
                if kw in low:
                    have_keys.add(key)
                    break
    missing = []

    for key, tasks in required.items():
        if key not in have_keys:
            missing.append({
                "key": key,
                "name": TOOLS[key]["name"],
                "alternative": TOOLS[key]["alt"],
                "needed_for": tasks,
            })
    return {
        "required": [{"key": k, "name": TOOLS[k]["name"], "tasks": v} for k, v in required.items()],
        "have": sorted(have_keys),
        "have_count": len(have_keys),
        "missing": missing,
        "listed_count": len(brief["user_tools"]),
    }


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

def finding(fid, axis, severity, title, why, fix, evidence):
    return {
        "id": fid,
        "axis": axis,
        "severity": severity,
        "title": title,
        "why": why,
        "fix": fix,
        "evidence": evidence,
    }


def run_findings(brief, rows, cost, schedule, tools):
    out = []
    scope = brief["scope_items"]
    area = brief["area_sqft"]
    hay = " ".join(brief["all_lines"]).lower()
    material_ids = {r["material_id"] for r in rows if r["material_id"]}
    material_names = " ".join(r["name"].lower() for r in rows)
    scope_text = " ".join(s["text"].lower() for s in scope)

    # ---- take-off ------------------------------------------------------
    if not rows:
        out.append(finding(
            "no_materials", "takeoff", "high",
            "No materials could be read from the brief",
            "The materials section is empty or unparsable, so there is nothing to take off and nothing to buy.",
            "List each material on its own line as 'Name: quantity unit @ $price /unit'.",
            "materials section: %d lines" % len(brief["materials"])))
    if area is None and not any(r["need"] for r in rows):
        out.append(finding(
            "no_area", "takeoff", "high",
            "No area or quantity anywhere in the brief",
            "Without a floor area or a count, every quantity in this plan is a guess and the shopping list will be wrong.",
            "Add the area to the scope, e.g. 'Install tile: 60 sqft' or 'Total area: 60 sqft'.",
            "no area found in %d scope lines" % len(scope)))

    for r in rows:
        if "missing_quantity" in r["flags"]:
            sev = "high" if r["measure"] == "sqft" else "medium"
            out.append(finding(
                "missing_quantity", "takeoff", sev,
                "Quantity missing for %s" % r["name"],
                "There is no quantity for %s, so it cannot be added to the shopping list." % r["name"],
                "Add the quantity to the material line or to a scope line that mentions it.",
                r["source_line"]))
        if "pack_content_reading" in r["flags"]:
            out.append(finding(
                "pack_content_reading", "takeoff", "low",
                "Quantity for %s was read as the contents of one pack" % r["name"],
                "The number on the line is larger than a single pack, so it was read as the count inside one pack.",
                "If you need several packs, write the pack count: '%s: 3 box'." % r["name"],
                r["source_line"]))
        if "quantity_not_derivable" in r["flags"]:
            out.append(finding(
                "quantity_not_derivable", "takeoff", "medium",
                "Quantity for %s cannot be derived from the scope" % r["name"],
                "The scope measures this material in a different unit from the one it is sold in, so the count stays unknown.",
                "Add the count to the scope, e.g. 'base cabinets: 10 each'.",
                r["source_line"]))
        if "missing_price" in r["flags"]:
            out.append(finding(
                "missing_price", "cost", "high",
                "No price for %s" % r["name"],
                "The total cost is only a floor while a material has no price. The overrun shows up later, as a change order.",
                "Add a price and its unit, e.g. '@ $14.50 /sheet'.",
                r["source_line"]))
        if "price_no_basis" in r["flags"]:
            out.append(finding(
                "price_no_basis", "cost", "high",
                "Price for %s has no unit basis" % r["name"],
                "'%s' has a number but no unit to attach it to, so the price cannot be applied to a quantity." % r["name"],
                "State the basis, e.g. '$14.50 /sheet' or '$2.35 /sqft'.",
                r["source_line"]))
        if "basis_mismatch" in r["flags"]:
            out.append(finding(
                "basis_mismatch", "takeoff", "medium",
                "Price basis does not match %s" % r["name"],
                "The price is quoted per %s but %s is measured in %s. The two numbers are not comparable."
                % (r["basis"], r["name"], r["measure"]),
                "Quote the price per %s, or restate the quantity in %s." % (r["measure"], r["measure"]),
                r["source_line"]))
        if "unit_mismatch" in r["flags"]:
            out.append(finding(
                "unit_mismatch", "takeoff", "medium",
                "Quantity unit does not match %s" % r["name"],
                "The quantity unit is not the unit this material is measured in, so the number was ignored.",
                "State the quantity in %s." % r["measure"],
                r["source_line"]))
        if "area_assumed" in r["flags"]:
            out.append(finding(
                "area_assumed", "takeoff", "medium",
                "%s quantity assumed from the total area" % r["name"],
                "No scope line ties %s to a quantity, so the whole floor area was assumed. If this material only covers part of the room you will over-buy." % r["name"],
                "Add a scope line such as 'Tile: 60 sqft' so the quantity comes from the scope instead of the assumption.",
                r["source_line"]))
        if "duplicate_material" in r["flags"]:
            out.append(finding(
                "duplicate_material", "takeoff", "medium",
                "%s appears more than once" % r["label"],
                "Two lines matched the same material, so the shopping list may double-count it.",
                "Merge the duplicate lines and keep the higher price if they differ.",
                r["source_line"]))
        if "unknown_material" in r["flags"]:
            out.append(finding(
                "unknown_material", "takeoff", "low",
                "%s is not in the material database" % r["name"],
                "Unknown materials fall back to a default 10% waste allowance and one-unit packaging, so the quantity is a rough guess.",
                "Add the coverage rate and pack size in the note, or reword the material so it matches a known one.",
                r["source_line"]))
        if r.get("cost") is not None and r["material_id"] in MATERIALS_BY_ID:
            ref = MATERIALS_BY_ID[r["material_id"]]["ref"]
            if ref:
                pack_price = r["cost"] / max(r.get("packs_to_buy") or 1, 1)
                if pack_price > ref[1] * 1.6:
                    out.append(finding(
                        "price_outlier", "cost", "medium",
                        "%s looks expensive per %s" % (r["name"], r["pack"]),
                        "About $%.2f per %s is well above the $%.2f-$%.2f typical range for this material."
                        % (pack_price, r["pack"], ref[0], ref[1]),
                        "Check the price and the pack size; a per-box price quoted per square foot is a common slip.",
                        r["source_line"]))
                elif pack_price < ref[0] * 0.4 and pack_price > 0:
                    out.append(finding(
                        "price_outlier_low", "cost", "low",
                        "%s looks cheap per %s" % (r["name"], r["pack"]),
                        "About $%.2f per %s is below the usual $%.2f-$%.2f range - check that it is not a per-piece price."
                        % (pack_price, r["pack"], ref[0], ref[1]),
                        "Confirm the unit the price applies to before buying.",
                        r["source_line"]))

    demo_scopes = [s for s in scope if s["demo"]]
    if demo_scopes:
        if not any(r["material_id"] == "disposal" for r in rows):
            out.append(finding(
                "no_disposal", "completeness", "medium",
                "Demo work with no disposal line",
                "Tearing out material creates debris, and disposal is often the line that surprises people on the invoice.",
                "Add a disposal line (dumpster, contractor bags or a haul-away service).",
                "; ".join(s["text"] for s in demo_scopes[:3])))

    demo_by_mat = {}
    install_by_mat = {}
    for s in scope:
        if not s["qty"] or s["unit"] not in ("sqft", "sqm"):
            continue
        smid, _ = match_material(s["text"])
        val = s["qty"] * (10.7639104167 if s["unit"] == "sqm" else 1.0)
        if s["demo"]:
            demo_by_mat[smid] = max(demo_by_mat.get(smid, 0.0), val)
        else:
            install_by_mat[smid] = max(install_by_mat.get(smid, 0.0), val)
    for smid, dval in demo_by_mat.items():
        ival = install_by_mat.get(smid)
        if not ival:
            continue
        if abs(dval - ival) > max(dval, ival) * 0.1:
            out.append(finding(
                "area_mismatch", "takeoff", "medium",
                "Removal and install areas differ by %.0f sqft" % abs(dval - ival),
                "The brief removes %.0f sqft of %s but installs %.0f sqft. One of them is wrong, and it changes both the order of work and the shopping list."
                % (dval, smid or "material", ival),
                "Check whether part of the area is being left as is, or whether a scope line is missing.",
                "removal %.0f sqft, install %.0f sqft" % (dval, ival)))

    # ---- cost ---
    # ---- cost -------------------------------------------------------
    if brief.get("budget") is None:
        out.append(finding(
            "no_budget", "cost", "medium",
            "No budget in the brief",
            "Without a budget there is nothing to measure the estimate against, so overrun risk is invisible until the invoice arrives.",
            "Add 'Budget: $X' to the brief.",
            "budget: not found"))
    else:
        if cost["variance"] is not None and cost["variance"] > 0:
            sev = "high" if cost["variance"] > brief["budget"] * 0.1 else "medium"
            out.append(finding(
                "budget_exceeded", "cost", sev,
                "Estimate is over budget by $%.0f" % cost["variance"],
                "The plan costs $%.0f against a $%.0f budget (%.0f%% over). The overage is %.0f%% of the budget."
                % (cost["total"], brief["budget"],
                   100.0 * cost["variance"] / max(brief["budget"], 1),
                   100.0 * cost["variance"] / max(brief["budget"], 1)),
                "Either cut scope, or find the money before buying anything. Changing tile and trim is usually cheaper than changing the layout.",
                "budget $%.0f, estimate $%.0f" % (brief["budget"], cost["total"])))
        if not cost["complete"]:
            out.append(finding(
                "incomplete_cost", "cost", "high",
                "The estimate is missing %d material price(s)" % cost["unpriced_count"],
                "The total of $%.0f only covers the priced materials, so it is a floor rather than an estimate." % cost["total"],
                "Price the unpriced materials before treating this number as the project cost.",
                ", ".join(cost["unpriced"][:6])))
        if not cost["labor_known"]:
            out.append(finding(
                "labor_missing", "cost", "medium",
                "Labor is not separated from materials",
                "Mixing labor into the material estimate hides the part of the cost you can negotiate and the part you can do yourself.",
                "Add a 'Labor: $X' line, or state whether you are doing the work yourself.",
                "labor: not found"))
        if cost["contingency_pct"] is None:
            out.append(finding(
                "no_contingency", "cost", "medium",
                "No contingency allowance",
                "Renovation estimates are routinely 10-20% light once a wall is opened and something is found behind it.",
                "Add a 10% contingency line to the budget and treat it as spent, not as profit.",
                "contingency: not found"))
        elif cost["contingency_pct"] < 0.05:
            out.append(finding(
                "low_contingency", "cost", "low",
                "Contingency is only %.0f%%" % (cost["contingency_pct"] * 100),
                "Less than 5% will not cover a surprise once demolition starts.",
                "Raise the contingency to 10% for a straightforward job, 15-20% for an old house.",
                "contingency: %.1f%%" % (cost["contingency_pct"] * 100)))
        if cost["tax_pct"] is None:
            out.append(finding(
                "tax_missing", "cost", "low",
                "Sales tax is not in the estimate",
                "Tax is added at the till, so an estimate without it is always short.",
                "Add 'Tax: 8.25%%' (your local rate) to the brief.",
                "tax: not found"))
        if any("allowance" in r["name"].lower() for r in rows):
            out.append(finding(
                "allowance_line", "cost", "medium",
                "A line is priced as an allowance",
                "An allowance is a placeholder, and the real cost lands as a change order later.",
                "Replace the allowance with a fixed price or a firm quote.",
                "; ".join(r["source_line"] for r in rows if "allowance" in r["name"].lower())[:160]))

    # ---- schedule ------------------------------------------------------
    if not schedule["tasks"]:
        out.append(finding(
            "no_schedule", "schedule", "high",
            "No schedule could be built",
            "There are no recognised work steps in the brief, so there is no order of operations and no cure time to respect.",
            "Describe the work as scope lines (e.g. 'remove existing tile: 60 sqft', 'install backer board: 60 sqft').",
            "0 tasks matched"))
    else:
        if brief.get("duration_days") is not None and brief["duration_days"] < schedule["working_days"]:
            out.append(finding(
                "duration_optimistic", "schedule", "high",
                "Stated duration is %.0f days but the work needs %.1f" % (brief["duration_days"], schedule["working_days"]),
                "The work itself is %.0f hours and the cure and dry times add more, so a %.0f-day plan cannot absorb it."
                % (schedule["total_hours"], brief["duration_days"]),
                "Plan %.0f working days, and keep the cure days out of the working days." % math.ceil(schedule["working_days"]),
                "duration: %s days" % brief["duration_days"]))
        deadline = brief.get("deadline")
        if deadline and schedule.get("finish_date"):
            try:
                dl = datetime.strptime(deadline, "%Y-%m-%d").date()
                fd = datetime.strptime(schedule["finish_date"], "%Y-%m-%d").date()
                if fd > dl:
                    over = (fd - dl).days
                    out.append(finding(
                        "deadline_miss", "schedule", "high",
                        "Finish date lands %d day(s) after the deadline" % over,
                        "Starting %s, the work finishes %s - %d days past %s."
                        % (schedule["start_date"], schedule["finish_date"], over, deadline),
                        "Start earlier, cut scope, or move the deadline. Cure time is not compressible.",
                        "deadline %s, finish %s" % (deadline, schedule["finish_date"])))
            except ValueError:
                pass
        if brief.get("start_date") is None:
            out.append(finding(
                "no_start_date", "schedule", "low",
                "No start date",
                "Without a start date the finish date and the cure-day plan cannot be placed on a calendar.",
                "Add 'Start: 2026-11-24' to the brief.",
                "start date: not found"))
        if "same day" in hay or "same-day" in hay:
            if any("grout" in r["name"].lower() for r in rows) and any("tile" in r["name"].lower() for r in rows):
                out.append(finding(
                    "cure_same_day", "schedule", "high",
                    "Grout and tile scheduled on the same day",
                    "Thinset needs at least 24 hours before grouting, and grout needs 24 hours before the area gets wet.",
                    "Split the job across three days: set tile, grout the next day, use the shower the day after.",
                    "scope mentions the same day"))
        long_lead = [r for r in rows if r["material_id"] in LONG_LEAD_HINT]
        if long_lead and brief.get("start_date"):
            out.append(finding(
                "long_lead_material", "schedule", "medium",
                "%s usually needs to be ordered ahead" % long_lead[0]["name"],
                "Custom cabinets, counters, doors and special-order tile are made to order and can run 2-6 weeks.",
                "Order these before the demolition day, or the job waits on a delivery date.",
                ", ".join(r["name"] for r in long_lead[:4])))
        if brief.get("location") == "outdoor" and any(t["id"] in ("paint", "deck_finish", "prep") for t in schedule["tasks"]):
            out.append(finding(
                "weather_window", "schedule", "medium",
                "Outdoor finish work has no dry-weather window",
                "Exterior paint, stain and prep need a dry, mild stretch - usually 2-3 days with no rain and above 50F.",
                "Check the forecast and schedule the finish work into a dry window rather than a fixed date.",
                "location: outdoor"))

    # ---- safety and code ----------------------------------------------
    wet_area = any(w in hay for w in WET_WORDS)
    wet_surface = any(w in hay for w in WET_SURFACE_WORDS)
    if wet_surface and "tile" in material_ids and "waterproof" not in material_ids:
        out.append(finding(
            "no_waterproofing", "safety", "high",
            "Tiled wet surface with no waterproofing membrane",
            "Tile and grout are not waterproof. Without a membrane behind the tile, water reaches the framing and the floor below.",
            "Add a waterproofing membrane over the backer board and seal the corners, corners and the drain.",
            "wet surface detected; materials: %s" % (", ".join(sorted(material_ids)) or "none")))
    if "tile" in material_ids and "backer" not in material_ids:

        out.append(finding(
            "tile_on_subfloor", "safety", "high",
            "Tile goes down without a backer board",
            "Tile is rigid and the house moves. Without cement board the tile cracks along the joists, and in a wet area the water gets straight into the framing.",
            "Add 1/4 in cement backer board over the subfloor, fastened every 6-8 inches.",
            "tile present, backer board absent"))
    if brief.get("project_type") == "deck" and "concrete" not in material_ids:
        out.append(finding(
            "no_footings", "safety", "high",
            "Deck with no footings or concrete in the materials",
            "A deck needs posts on footings that go below the frost line - not on pavers or blocks on the soil.",
            "Add footings and post-hole concrete to the materials, and check the local frost depth.",
            "project type: deck"))
    permit_mentioned = any(w in hay for w in PERMIT_WORDS)
    if any(w in hay for w in STRUCTURAL_WORDS) and not permit_mentioned:
        out.append(finding(
            "structural_no_permit", "safety", "high",
            "Structural work with no permit or engineer in the plan",
            "Removing or moving a load-bearing wall changes how the house carries its load, and it is checked.",
            "Get a permit, and an engineer's letter for any load-bearing change. This is the one job that cannot be un-permitted later.",
            "structural keywords found, permit keywords absent"))
    if not permit_mentioned and (material_ids & {"electrical", "wire", "fixture", "pipe"}):
        out.append(finding(
            "permit_unknown", "safety", "medium",
            "No permit mentioned for electrical or plumbing work",
            "Rough-in work usually needs a permit and an inspection before it is covered up.",
            "Check the local building department before closing walls, and book the inspection before you finish.",
            "electrical or plumbing scope with no permit mention"))
    if brief.get("project_type") == "deck" and (brief.get("area_sqft") or 0) >= 100 and not permit_mentioned:
        out.append(finding(
            "deck_permit", "safety", "medium",
            "Deck of %.0f sqft with no permit in the plan" % (brief.get("area_sqft") or 0),
            "Most jurisdictions require a permit and a plan for a deck this size, and the footings have to go below the frost line.",
            "Check with the building department, and confirm the footing depth before you dig.",
            "deck of %.0f sqft, no permit mentioned" % (brief.get("area_sqft") or 0)))
    if brief.get("year_built") and brief["year_built"] < 1979 and any(w in hay for w in HAZMAT_WORDS):
        out.append(finding(
            "hazmat_risk", "safety", "high",
            "Possible lead or asbestos in material being removed",
            "In a house built before 1979, old floor covering, popcorn ceilings and some pipe insulation can contain lead or asbestos. Disturbing them by hand is a real exposure risk.",
            "Test the material before demolition, or hire a licensed abatement contractor. Do not sand or break it up.",
            "year built %d, suspect materials mentioned" % brief["year_built"]))
    elif any(w in hay for w in ("popcorn ceiling", "asbestos")):
        out.append(finding(
            "hazmat_risk_unknown_age", "safety", "medium",
            "Suspect material mentioned with no house age given",
            "Popcorn ceiling and old floor tile can contain asbestos depending on the year they were installed.",
            "Add the year the house was built, and test suspect material before demolition.",
            "suspect material keywords found"))
    if "electrical" in material_ids and wet_area and not any(w in hay for w in ("gfci", "gfi", "wet location", "weatherproof")):
        out.append(finding(
            "electrical_in_wet", "safety", "high",
            "Electrical device in a wet area with no GFCI noted",
            "GFCI protection is required in bathrooms and other wet locations, and it must trip before a shock becomes serious.",
            "Use GFCI-protected receptacles in the wet zone and confirm they trip when tested.",
            "wet area with electrical material"))
    if not any(w in hay for w in ("ppe", "respirator", "mask", "safety glasses", "gloves", "ear protection")):
        out.append(finding(
            "no_ppe", "safety", "medium",
            "No safety gear in the plan",
            "Tile dust, cement board dust, thinset and old flooring all carry real respiratory and eye risk.",
            "Add an N95 or P100 respirator, safety glasses and gloves to the materials.",
            "no PPE keywords in the brief"))
    if "electrical" in material_ids and not any(w in hay for w in ("licensed electrician", "electrician", "permit")):
        out.append(finding(
            "electrical_unqualified", "safety", "medium",
            "Electrical work with no licensed electrician or permit",
            "Panel work and new circuits are the highest-risk part of a home project and are code-checked.",
            "Use a licensed electrician for panel work and new circuits, and check whether a permit is needed.",
            "electrical material present with no electrician or permit mention"))

    # ---- completeness --------------------------------------------------
    if not brief["user_tools"]:
        out.append(finding(
            "no_tools_listed", "completeness", "medium",
            "No tool list",
            "Half the cost of a DIY project is knowing which tools you already own before you start, rather than mid-project.",
            "Add a 'Tools:' section listing what you own so the gaps show up now.",
            "tools section: 0 lines"))
    if tools["missing"]:
        out.append(finding(
            "tool_gap", "completeness", "medium",
            "%d tool(s) needed but not in your list" % len(tools["missing"]),
            "The plan needs %s. Renting one of these for a day is usually cheaper than buying it."
            % ", ".join(m["name"] for m in tools["missing"][:4]),
            "Buy, borrow or rent: " + "; ".join("%s - %s" % (m["name"], m["alternative"]) for m in tools["missing"][:3]),
            "; ".join(m["name"] for m in tools["missing"][:6])))
    if any(t["id"] == "tile" for t in schedule["tasks"]) and "transition" not in material_ids:
        out.append(finding(
            "no_transitions", "completeness", "low",
            "No transition strips",
            "Where new flooring meets carpet, tile or a threshold, an unfinished edge is the thing you notice every day.",
            "Add transition strips or a threshold for every floor change in the plan.",
            "tile or flooring scope without a transition line"))
    if any(t["id"] == "tile" for t in schedule["tasks"]) and wet_area and "caulk" not in material_ids:
        out.append(finding(
            "no_caulk", "completeness", "medium",
            "Wet area tiling with no caulk line",
            "Silicone at the corners of a shower or tub is what keeps water out of the wall behind the tile.",
            "Add a 100% silicone kitchen-and-bath tube for the internal corners and the tub surround.",
            "wet area tile scope with no caulk"))
    if any(t["id"] in ("tile", "flooring_install") for t in schedule["tasks"]) and "protection" not in material_ids:
        out.append(finding(
            "no_protection", "completeness", "low",
            "No floor protection in the materials",
            "Dust from demo and tile settles everywhere, and protecting the floor takes a roll of plastic and a few hours.",
            "Add a drop cloth or floor-protection roll.",
            "tile or flooring scope with no protection line"))
    skills = brief.get("skills")
    if skills in ("beginner", "unknown"):
        hard = [t for t in schedule["tasks"] if SKILL_DIFFICULTY.get(t["id"], 1) >= 3]
        if hard:
            out.append(finding(
                "skill_gap", "completeness", "medium",
                "Plan includes %d advanced step(s) for a %s-level project" % (len(hard), skills),
                "Steps like %s are where first-time renovators usually damage materials rather than themselves."
                % ", ".join(h["name"].lower() for h in hard[:3]),
                "Hire a trade for %s and keep the rest." % ", ".join(h["name"].lower() for h in hard[:2]),
                "skill: %s" % skills))
    if not any(t["id"] == "cleanup" for t in schedule["tasks"]) and schedule["tasks"]:
        out.append(finding(
            "no_cleanup", "completeness", "low",
            "No cleanup step in the sequence",
            "Cleanup is the step that decides whether the room is usable at the end of the last day.",
            "Add a final clean and protection removal to the scope.",
            "%d tasks scheduled, no cleanup task" % len(schedule["tasks"])))
    if not scope:
        out.append(finding(
            "no_scope_section", "completeness", "medium",
            "No scope section",
            "Without a scope the plan cannot be checked against itself - quantities come from the materials list but there is nothing to verify them against.",
            "Add a 'Scope:' section describing what is being removed, installed and left alone.",
            "scope section: 0 lines"))
    if area is None and rows:
        out.append(finding(
            "no_area_known", "completeness", "low",
            "No floor area in the brief",
            "Paint, tile and underlayment all scale with area, so quantities fall back to guesses.",
            "Add 'Total area: 120 sqft'.",
            "area: not found"))

    return out


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score_review(findings, brief, cost, schedule, profile_key):
    profile = PROFILES.get(profile_key, PROFILES["general"])
    weights = profile["weights"]
    axes = {}
    for axis in AXES:
        score = 100.0
        for f in findings:
            if f["axis"] == axis:
                score -= SEVERITY_POINTS[f["severity"]]
        axes[axis] = {"score": round(max(0.0, score), 1),
                      "label": AXES[axis][0],
                      "question": AXES[axis][1]}

    caps = []

    def cap(axis, value, reason):
        if axis in axes and axes[axis]["score"] > value:
            axes[axis]["score"] = float(value)
            caps.append({"axis": axis, "value": value, "reason": reason})

    safety_high = [f for f in findings if f["axis"] == "safety" and f["severity"] == "high"]
    cost_high = [f for f in findings if f["axis"] == "cost" and f["severity"] == "high"]
    takeoff_high = [f for f in findings if f["axis"] == "takeoff" and f["severity"] == "high"]
    schedule_high = [f for f in findings if f["axis"] == "schedule" and f["severity"] == "high"]

    if safety_high:
        cap("safety", 30, "a high-severity safety finding")
    if len(safety_high) >= 2:
        cap("safety", 22, "two or more high-severity safety findings")
    if cost_high:
        cap("cost", 45, "a high-severity cost finding")
    if takeoff_high:
        cap("takeoff", 40, "a high-severity take-off finding")
    if schedule_high:
        cap("schedule", 45, "a high-severity schedule finding")
    if brief.get("budget") and cost.get("variance") and cost["variance"] > 0:
        cap("cost", 42, "the estimate is over budget")
    if not cost["complete"]:
        cap("cost", 50, "the estimate is missing material prices")
    if not schedule["tasks"]:
        cap("schedule", 25, "no schedule could be built")
    if brief.get("skills") in ("beginner", "unknown") and any(f["id"] == "skill_gap" for f in findings):
        cap("completeness", 45, "the plan is beyond the stated skill level")
    if not brief["user_tools"]:
        cap("completeness", 55, "no tool list was provided")

    overall = sum(axes[a]["score"] * weights[a] for a in axes)

    overall_caps = []
    if len(safety_high) >= 2:
        overall_caps.append((38, "two or more high-severity safety findings"))
    elif safety_high:
        overall_caps.append((45, "a high-severity safety finding"))
    if cost.get("variance") and brief.get("budget") and cost["variance"] > brief["budget"] * 0.1:
        overall_caps.append((58, "the estimate is more than 10% over budget"))
    if not cost["complete"]:
        overall_caps.append((62, "the estimate is missing material prices"))
    if any(f["id"] == "no_area" for f in findings):
        overall_caps.append((40, "there is no area or quantity to build from"))
    if any(f["id"] == "no_materials" for f in findings):
        overall_caps.append((25, "no materials could be read"))
    for value, reason in overall_caps:
        if overall > value:
            overall = value
            caps.append({"axis": "overall", "value": value, "reason": reason})

    verdict = VERDICT_BANDS[-1][1]
    verdict_label = VERDICT_BANDS[-1][2]
    for threshold, key, label in VERDICT_BANDS:
        if overall >= threshold:
            verdict, verdict_label = key, label
            break
    if safety_high and overall >= 55:
        verdict, verdict_label = "needs_rework", "Needs rework"

    return {
        "overall": round(overall, 1),
        "axes": axes,
        "weights": weights,
        "profile": profile_key,
        "profile_label": profile["label"],
        "verdict": verdict,
        "verdict_label": verdict_label,
        "caps": caps,
        "severity_counts": {
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "medium": sum(1 for f in findings if f["severity"] == "medium"),
            "low": sum(1 for f in findings if f["severity"] == "low"),
        },
    }


def build_fix_plan(findings, score):
    plan = []
    for f in findings:
        points = SEVERITY_POINTS[f["severity"]]
        weight = score["weights"].get(f["axis"], 0.2)
        axis_remaining = score["axes"][f["axis"]]["score"]
        gain = min(points, axis_remaining) * weight
        plan.append({
            "id": f["id"],
            "axis": f["axis"],
            "severity": f["severity"],
            "title": f["title"],
            "fix": f["fix"],
            "gain": round(gain, 1),
        })
    plan.sort(key=lambda p: (SEVERITY_RANK[p["severity"]], -p["gain"]))
    for i, item in enumerate(plan, 1):
        item["order"] = i
    return plan


# --------------------------------------------------------------------------
# Top-level
# --------------------------------------------------------------------------

def analyse(text, profile="general"):
    if profile not in PROFILES:
        profile = "general"
    brief = parse_brief(text)
    rows, notes = build_takeoff(brief)
    cost = build_cost(rows, brief)
    schedule = build_schedule(brief, rows)
    tools = build_tools(brief, schedule)
    findings = run_findings(brief, rows, cost, schedule, tools)
    score = score_review(findings, brief, cost, schedule, profile)
    fix_plan = build_fix_plan(findings, score)

    assumptions = []
    if brief.get("area_sqft"):
        assumptions.append("Floor area of %.0f sqft taken from the brief." % brief["area_sqft"])
    if brief.get("tax_pct") is None:
        assumptions.append("Sales tax not stated, so the total excludes tax.")
    if brief.get("contingency_pct") is None:
        assumptions.append("No contingency applied.")
    if brief.get("labor") is None:
        assumptions.append("Labor is not included in the total.")
    assumptions.append("Waste allowances are the database defaults per material.")
    assumptions.append("Cure times are conservative minimums for typical product data sheets.")

    return {
        "project": {
            "name": brief["project_name"],
            "type": brief["project_type"],
            "location": brief["location"],
            "skills": brief["skills"],
            "area_sqft": brief["area_sqft"],
            "start_date": brief["start_date"],
            "deadline": brief["deadline"],
            "year_built": brief["year_built"],
        },
        "profile": profile,
        "score": score,
        "takeoff": {
            "rows": rows,
            "count": len(rows),
            "notes": notes,
            "material_total": cost["material_total"],
            "waste_total": cost["waste_total"],
        },
        "cost": cost,
        "schedule": schedule,
        "tools": tools,
        "findings": findings,
        "fix_plan": fix_plan,
        "assumptions": assumptions,
    }


def to_markdown(result):
    p = result["project"]
    s = result["score"]
    cost = result["cost"]
    out = []
    out.append("# %s - renovation review" % p["name"])
    out.append("")
    out.append("**Profile:** %s | **Score:** %.1f/100 (%s) | **Verdict:** %s"
               % (s["profile_label"], s["overall"], s["verdict"], s["verdict_label"]))
    out.append("")
    out.append("| Axis | Score |")
    out.append("| --- | --- |")
    for axis, data in s["axes"].items():
        out.append("| %s | %.1f |" % (data["label"], data["score"]))
    out.append("")
    out.append("## Cost")
    out.append("")
    out.append("- Materials: $%.2f (of which $%.2f is waste allowance)" % (cost["material_total"], cost["waste_total"]))
    out.append("- Labor: %s" % ("$%.2f" % cost["labor"] if cost["labor_known"] else "not stated"))
    out.append("- Contingency: %s" % ("%.0f%% = $%.2f" % (cost["contingency_pct"] * 100, cost["contingency"])
                                      if cost["contingency_pct"] is not None else "not applied"))
    out.append("- Tax: %s" % ("%.2f%% = $%.2f" % (cost["tax_pct"] * 100, cost["tax"])
                              if cost["tax_pct"] is not None else "not applied"))
    out.append("- **Total: $%.2f**" % cost["total"])
    if cost["budget"] is not None:
        out.append("- Budget: $%.2f (variance %s$%.2f)" % (
            cost["budget"], "+" if cost["variance"] > 0 else "", cost["variance"] or 0.0))
    out.append("")
    out.append("## Materials takeoff")
    out.append("")
    out.append("| Material | Need | With waste | Buy | Price | Est. cost |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for r in result["takeoff"]["rows"]:
        need = "%.0f %s" % (r["need"], r["need_unit"]) if r["need"] is not None else "?"
        nw = "%.0f" % r["need_with_waste"] if r.get("need_with_waste") is not None else "?"
        buy = "%d %s" % (r["packs_to_buy"], r["pack"]) if r.get("packs_to_buy") is not None else "?"
        price = "$%.2f / %s" % (r["price"], r["basis"]) if r.get("price") is not None and r.get("basis") else "?"
        c = "$%.2f" % r["cost"] if r.get("cost") is not None else "?"
        out.append("| %s | %s | %s | %s | %s | %s |" % (r["name"], need, nw, buy, price, c))
    out.append("")
    out.append("## Schedule")
    out.append("")
    out.append("Total hands-on time %.0f h, %.1f working days including cure time." %
               (result["schedule"]["total_hours"], result["schedule"]["working_days"]))
    out.append("")
    out.append("| Day | Step | Hours | Cure after |")
    out.append("| --- | --- | --- | --- |")
    for t in result["schedule"]["tasks"]:
        out.append("| %d | %s | %.1f | %dh |" % (t["day"], t["name"], t["hours"], t["cure_after"]))
    out.append("")
    out.append("## Findings")
    out.append("")
    for f in sorted(result["findings"], key=lambda x: (SEVERITY_RANK[x["severity"]], x["axis"])):
        out.append("### [%s/%s] %s" % (f["severity"].upper(), f["axis"], f["title"]))
        out.append("")
        out.append("- Why it matters: %s" % f["why"])
        out.append("- Fix: %s" % f["fix"])
        out.append("- Evidence: %s" % f["evidence"])
        out.append("")
    out.append("## Prioritised fix plan")
    out.append("")
    for item in result["fix_plan"]:
        out.append("%d. (%s, +%.1f pts) %s - %s" % (item["order"], item["severity"], item["gain"],
                                                     item["title"], item["fix"]))
    out.append("")
    out.append("## Assumptions")
    out.append("")
    for a in result["assumptions"]:
        out.append("- %s" % a)
    return "\n".join(out)


def to_csv(result):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["material", "need", "need_unit", "waste_pct", "need_with_waste",
                "pack", "packs_to_buy", "price", "price_basis", "est_cost", "need_source"])
    for r in result["takeoff"]["rows"]:
        w.writerow([
            r["name"],
            "%.2f" % r["need"] if r["need"] is not None else "",
            r["need_unit"] or "",
            "%.0f%%" % (r["waste"] * 100),
            "%.2f" % r["need_with_waste"] if r.get("need_with_waste") is not None else "",
            r["pack"],
            r.get("packs_to_buy") if r.get("packs_to_buy") is not None else "",
            "%.2f" % r["price"] if r.get("price") is not None else "",
            r.get("basis") or "",
            "%.2f" % r["cost"] if r.get("cost") is not None else "",
            r.get("need_source") or "",
        ])
    return buf.getvalue()
