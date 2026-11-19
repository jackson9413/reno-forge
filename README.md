# reno-forge

**Home renovation planner and materials takeoff workbench.** Paste the brief you
got from a contractor (or wrote yourself), get back the shopping list with the
right pack counts, a cost roll-up, a schedule that respects cure times, the
tools you are missing, and a scored review of what the plan gets wrong.

Everything runs on your machine. No API keys, no network calls, no LLM.

---

## What it does

1. **Reads the brief.** Sections named `Scope`, `Materials`, `Tools`,
   `Budget` and `Schedule` are treated as headings. Material lines look like
   `Porcelain tile 12x12 @ $2.35 /sqft`. Quantities can live on the material
   line (`Cement board: 5 sheet`) or in the scope (`Install cement backer
   board: 60 sqft`), and the tool links the two.
2. **Takes off the materials.** Every material has a measure, a pack size, a
   waste allowance and a cure time in a local database of 45 materials. The
   engine applies the waste allowance, converts to the container you actually
   buy (6 boxes of tile, not "66 sqft"), and prices it against the quoted
   basis (per sqft, per box, per bag, per each).
3. **Rolls up the cost.** Materials, waste allowance, labor, contingency and
   sales tax, then the gap to your budget.
4. **Builds the schedule.** Work steps come from the scope and the materials,
   are ordered by dependency, scaled by area, and separated by the cure times
   that actually decide whether the job works (thinset 24 h before grouting,
   grout 24 h before the shower gets used, concrete 7 days).
5. **Checks the tools.** Every step needs tools; the ones you did not list
   come back with a cheaper alternative.
6. **Scores the plan.** Five axes - take-off accuracy, cost control, schedule
   realism, safety and code, project completeness - scored 0-100 with
   structural caps so a plan cannot look good by skipping the hard part. A
   tiled shower with no waterproofing caps safety at 30 and the whole review
   at 45, whatever else it did right.
7. **Finds the gaps.** Around 45 findings, each with the evidence that
   triggered it, why it matters and a concrete fix, plus a prioritised fix
   plan with the score each fix buys back.
8. **Exports.** Markdown report, JSON, and a shopping-list CSV. Saved reviews
   go into a local SQLite log with a 1-5 star self-rating.

## Review profiles

| Profile | What it is for |
| --- | --- |
| General review | Everything, weighted evenly |
| Budget audit | Cost control and the take-off behind it |
| DIY feasibility | Tool gaps, skill level, whether you can actually do it |
| Timeline realism | The schedule, the cure times and the deadline |
| Safety and code | Waterproofing, permits, footings, GFCI, lead and asbestos |

## The brief format

Plain text is fine - the parser is forgiving. This is the shape it likes:

```text
Project: Bathroom floor retile

Type: bathroom
Total area: 60 sqft

Scope:
- Remove existing vinyl tile and vinyl backing: 60 sqft
- Repair and level the subfloor: 60 sqft
- Install cement backer board: 60 sqft
- Install 12x12 porcelain tile: 60 sqft
- Grout and clean the floor: 60 sqft
- Caulk the floor edge joint: 18 linear ft
- Install primed baseboard: 18 linear ft
- Haul away debris

Materials:
- Porcelain tile 12x12 @ $2.35 /sqft
- Cement board 3x4 @ $14.50 /sheet
- Thinset mortar 25 lb @ $18.00 /bag
- Grout premixed 5 lb @ $12.00 /tub

Tools:
- Wet tile saw
- Notched trowel
- Grout float

Budget: $1,450
Tax: 8.25%
Contingency: 10%
Labor: $0
Skills: intermediate
Start: 2026-11-23
Deadline: 2026-12-20
```

Optional keys: `Type`, `Total area`, `Budget`, `Labor`, `Tax`, `Contingency`,
`Skills`, `Start`, `Deadline`, `Location`, `Year built`, `Duration`.

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Then open <http://127.0.0.1:8765>.

Or in one step:

```bash
./run.sh
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The suite covers the parser, the take-off maths, the cost roll-up, the
schedule, the safety caps, the exports, the API and a calibration check that
keeps the six built-in samples inside their expected score bands.

## API

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/health` | Liveness |
| GET | `/api/profiles` | The review profiles and their weights |
| GET | `/api/samples` | The six built-in sample briefs |
| POST | `/api/analyze` | `{brief, profile}` -> the full review |
| POST | `/api/export` | `{brief, profile, format: md\|csv\|json}` -> a file |
| POST | `/api/runs` | Save a review to the local log |
| GET | `/api/runs` | List saved reviews |
| GET/PATCH/DELETE | `/api/runs/<id>` | Read, rate or delete one |

## Built-in samples

| Sample | Score | Verdict | What it demonstrates |
| --- | --- | --- | --- |
| `bathroom_retile` | ~98 | Ready to build | The control case: a complete brief |
| `bedroom_repaint` | ~89 | Ready to build | Painting, area-driven quantities |
| `basement_drywall` | ~88 | Ready to build | Drywall repair, beginner skill level |
| `living_room_floor` | ~62 | Needs attention | No prices at all - the estimate is a floor |
| `kitchen_cabinets` | ~58 | Needs attention | Long-lead cabinets, an allowance line, over budget |
| `backyard_deck` | ~45 | Needs rework | No footings, no permit, beginner doing framing |

## Layout

```
app.py            Flask API, static hosting, SQLite run log
engine.py         Parsing, take-off, cost, schedule, findings, scoring
materials.py      Material, tool and task knowledge base
static/           Dark vanilla-JS UI (no build step)
samples/          Six calibration briefs
tests/            Engine and API tests
```

## What it is not

It is not a contractor, a structural engineer or a code inspector. It cannot
know your subfloor condition, your local frost depth or what your building
department wants. Where it flags a permit, an engineer or a licensed
electrician, that is the tool telling you to go and ask a human.
