# Better Lebanon Map: technical notes

How the map is built and checked: the pipeline's method, the measurements behind its choices, the
experiments that failed, and the files it writes. For what the project is and how to use it, see
the [README](../README.md) ([français](../README.fr.md), [العربية](../README.ar.md)).

The output is a **proposal dataset**, not official addressing, and must **not** be uploaded to
OpenStreetMap: OSM only records names that exist on the ground, and mass edits need an
approved import. Use it as a review/advocacy layer or as input for municipalities.

## Run

```bash
uv sync
uv run python -I -m better_lebanon_map.pipeline                 # ~8 min; extracts on first run
uv run python -I -m better_lebanon_map.pipeline --export-only   # rewrite outputs from the last run
uv run python -I -m better_lebanon_map.audit                    # name-quality audit of the last build
uv run python -m better_lebanon_map.serve                       # then open http://localhost:8765
node tools/geocode_eval.mjs                                     # score the search on random addresses
uv run python -I -m better_lebanon_map.publish --repo owner/name --push   # publish on GitHub Pages
```

The audit checks every street, route-only, commune, district and governorate name in all three
languages: Latin letters in Arabic names (or Arabic in Latin ones), English word order in French
names and the reverse, doubled type words and repeated words, codes used as names, Arabizi,
lowercase starts and lowercase nouns after a French article, mandate-era circumflex spellings,
OSM names with no street type, a place named twice in a road between places ("Route Dhour El
Choueir - Dhour El Choueir" for "طريق ضهور الشوير - الشوير"), stray spacing, missing names and
letter-by-letter spellings (streets and route-only names). It exits non-zero if any check fails and
writes the details to `data/output/name_audit.json`, with three lists to read rather than count:
Arabic names transcribed from Latin-only names; names from OSM tags whose Latin and Arabic do not
sound alike (another place or person, or a translation the dictionaries do not know); and communes
whose Latin name does not sound like their Arabic one, judged on the dictionaries alone (with the
gazetteer of village names, every commune would match itself).

Inputs:

- OpenStreetMap: Geofabrik extract at `data/raw/lebanon-latest.osm.pbf`
  (`https://download.geofabrik.de/asia/lebanon-latest.osm.pbf`, ODbL). Re-download it and pass
  `--re-extract` to refresh.
- Official boundaries: OCHA's Lebanon COD-AB v02 (`data/raw/cod_ab/`, from
  `https://data.humdata.org/dataset/cod-ab-lbn`, CC BY-IGO, reviewed October 2025): 1,627
  cadastral villages, 26 districts, 8 governorates. Attribution: "Boundaries © OCHA".
- Roads Microsoft detected in Bing satellite imagery (Maxar, Airbus):
  `https://github.com/microsoft/RoadDetections`, ODbL. The Lebanon rows of `Western_Asia.zip`
  are kept in `data/raw/ms_roads/lebanon.tsv`; only stretches no OSM way runs along are used, as
  driveways (Method, step 4).
- Driveways drawn by people who know a place: `data/corrections/access.geojson`, one LineString
  (WGS84) per driveway from the street to the house, drawn for example on geojson.io. Each one
  applies on every rebuild and wins over OSM's ways and the imagery.
- Streets chosen by people who know a house: `data/corrections/streets.jsonl`, one line per house,
  written when someone confirms a street on an address card (see "Which street?" below). Each
  applies on every rebuild.
- The Central Administration of Statistics' list of localities by cadastral code, as transcribed
  on `https://wiki.openstreetmap.org/wiki/LebanonPlaceNames`: read by hand to settle the names of
  26 cadasters (`CAS_NAMES` in `localities.py`).

## The viewer

The map fills the page. On a desktop a floating card holds the search box and whatever is
selected; on a phone the search box floats at the top and the card is a drawer at the bottom, dragged
by its handle or its content between three rests (folded, half open, fully open). Arabic
(right-to-left), French and English, chosen from a menu on a phone; light and dark.

- **Home** a search box, "My address" (the address of where you are) and "Directions", three
  searches to try, and one sentence on how the numbers work, with the rest behind "How addresses
  work". A standing line says the addresses are proposed, not official.
- **Search** one box for towns, streets, full addresses and landmarks in any language:
  `22 rue des cedres bikfaya`, `شارع الأرز 22 بكفيا`, `Achrafieh`, `pharmacie bikfaya`. Accents,
  hamzas and commas are optional and the number may come before or after the street. When nothing
  matches as typed, the query is read again by sound and with one typing slip allowed per word, so
  `22 rue des cedrse bikfaiya` and `juniyah` still arrive (see "Checking the search"). Results are
  grouped by kind (town, street, address, landmark), each with its icon. Press `/` to jump to it.
- **An address is a street plaque**: the number and the street's name in Arabic and Latin letters
  on a blue sign, like Beirut's enamel plaques, with Directions, Share and Copy under it, where it
  stands on the street ("535 metres from the start of Cedar Street, on the left side"), and the
  address in the two other languages, each with its own copy button.
- **Every answer says how exact it is.** A number a building has opens that building, badged "Exact
  building". A number no building has is still a place, since a number is a distance: the plaque
  is dashed, the badge says "Approximate spot", the card explains where the pin stands and offers
  the closest numbered building. A number past the end of the street opens the street and says so.
- **"Is the entrance on another street?"** A building with second addresses lists them and asks
  whoever knows it which street its entrance is on, one button per street (see "Which street?").
- **Cards** for a street (its sign, how many buildings, its odd and even numbers, and why it has
  its name behind "Where the name comes from"), a town (district, governorate, counts; the
  boundary's status behind "About the boundary") and a landmark (15,000 named shops, schools,
  places of worship, pharmacies... from OSM, each with the address of the nearest building).
- **What is the address here?** Click a building, or right-click (long-press on a phone) anywhere
  for the nearest address.
- **Directions** by car or on foot between any two addresses, landmarks or map points, computed in
  the browser on the whole-country road graph: the time for each way of travelling, then steps
  with a turn icon each, such as "Turn right onto Rue des Cèdres" and "Arrive at 722 Rue des
  Cèdres, Bikfaya, on your right". A road with no name is told by the street it leads to ("At the
  roundabout, take the exit toward Hawthorn Lane").
- **Map controls** at the corner: map style, where I am, zoom. Map style holds the base maps (the
  default is drawn by the viewer itself from the map's own data: no tiles, no outside service;
  OpenStreetMap's tiles and Esri's gray, terrain and satellite tiles are options), what to show
  (buildings, house numbers, boundaries, place names), coloring streets by where their name comes
  from, and the legend.
- Links keep the view and selection (`#18/33.917/35.690&a=...`). The page loads Leaflet from unpkg
  and the Readex Pro typeface from Google Fonts; without the font it falls back to the system's.

## Which street? Second addresses

A house takes its nearest street unless a driveway is known (Method, step 4). That is often wrong
for a house that does not front a street, and the map cannot tell: of the 8,828 houses whose
street the build knows from a driveway, the nearest street is the right one for 6,091
(69%). A classifier on street and building geometry did not pick better (68% against
67% on held-out communes), and no vision model small enough to run locally was good enough (next
section).

So the build does not pick. A building whose street is not known gets an address on each street it
may be reached from, and all of them lead to it (`aliases.py`):

- its own address, on the nearest street: the one drawn on the map;
- when it does not front that street (more than 25 m from it): an alias on up to three other
  streets, those at most 60 m farther from its walls than the nearest one;
- when it fronts its street: an alias on the other street of a corner, one within 10 m of its walls.

A street is left out when the straight way to it crosses another street (true of 0.2% of the
houses' known streets, and of a quarter of the others), or when it only comes that near where it
meets the building's own street. An alias is numbered like any address, by its metres along that
street and its side; it takes the next free number when a building of that street has it, so
buildings' own numbers never move.

With this extract 218,903 buildings have 366,875 aliases, and every full address is
still unique. Tried on the houses whose street is known, as if it were not, the known street is
among the house's addresses for 8,462 of 8,828 (96%): whichever street
someone types for their house, the search arrives at it, where the nearest street alone was right
for 69%. The build prints this check on every run (`houses_with_known_street` in
`stats.json`).

The address card lists the building's other addresses and says the map cannot tell which street
it is reached from. Someone who knows the house settles it there: "Confirm it is reached from
<street>" saves one line in `data/corrections/streets.jsonl` (through `serve`; on a published copy
it opens a GitHub issue instead, see below). At the next build the house belongs to that street
alone, numbered where it meets it, and loses its aliases.

## Checking the search

`node tools/geocode_eval.mjs` runs the viewer's own search code on addresses drawn at random from
the built map, typed several ways, and counts how often the first result is that building:

1,500 addresses, seed 1, on the build of 2026-11-10:

| Typed | First result is the building |
| --- | --- |
| As written, French | 100.0% (1,500 of 1,500) |
| As written, English | 100.0% (1,500 of 1,500) |
| As written, Arabic | 100.0% (1,500 of 1,500) |
| No accents or commas, number after the street | 100.0% (1,500 of 1,500) |
| Arabic, number after the street | 100.0% (1,500 of 1,500) |
| Arabic typed without hamzas or ta marbuta | 100.0% (714 of 714) |
| Town respelled | 99.3% (1,324 of 1,334) |
| Typing slip in the street | 99.2% (1,166 of 1,175) |
| Typing slip in the town | 99.1% (1,114 of 1,124) |
| Street respelled | 98.9% (750 of 758) |
| Alias, as written in French | 100.0% (463 of 463) |
| A number placed by its metres (1,087 buildings) | median 0.7 m from where the building meets the street, 90% within 1.9 m, 99% within 4.4 m |

"Respelled" writes a word another way Lebanese names are written in Latin letters (ou/u, ch/sh,
-ieh/-iye, a doubled letter, kh/5...); a "typing slip" swaps two letters, drops one or changes
one. The misses that remain are mostly roads between two towns typed with one of the towns
misspelled ("Route de Baaourta, Naame"), where the other town's road of the same name wins. The
last line checks the viewer's arithmetic for numbers no building has: it places a building's own
number by its metres and compares that with where the building meets the street.

The first run of this test found that one address in twenty did not find itself as written: a
street named after another town ("Route de Baaourta, Naameh") was searched in the wrong town, and
an Arabic name typed without its hamza did not match. Both are fixed; run it after any change to
`viewer/js/search.js`.

## Publishing on GitHub

The viewer is a static site: about 170 MB in 3,000 files, 60 MB to upload, nothing to run on a
server. `publish.py` puts it on GitHub Pages:

```bash
uv run python -I -m better_lebanon_map.publish --repo owner/name          # builds data/site and reports its size
uv run python -I -m better_lebanon_map.publish --repo owner/name --push   # pushes it to the gh-pages branch
```

1. Create the repository on GitHub (public: Pages is free for public repositories).
2. Run the command with `--push`. It needs `git` signed in to GitHub (`--remote` takes an SSH URL).
   The site goes up as one commit that replaces the one before, so the repository does not grow
   with every build; `data/site` keeps its own `.git`, so a later push uploads only the files that
   changed.
3. Once, in the repository's Settings > Pages: deploy from the branch `gh-pages`, folder `/`. The
   map is then at `https://owner.github.io/name/`; publish again after each rebuild.

The source can live on the main branch of the same repository: `.gitignore` keeps out the data,
which the pipeline regenerates, and the judge's satellite tiles, which Esri's terms do not allow
to be redistributed.

The published copy differs from the local one in three ways:

- **Base maps**: the viewer's own drawing and OpenStreetMap's tiles. Esri's tiles are offered only
  with `--esri-tiles`; their terms cover development and ask for an ArcGIS account beyond it.
- **Confirming a street** opens an issue of the repository with the correction, since there is no
  server to save it. Anyone can send one, so read each and label those to keep `accepted`; then
  `uv run python -I -m better_lebanon_map.corrections --repo owner/name` copies them into
  `data/corrections/streets.jsonl` for the next build.
- **The access judge's queue** (`judge.html`) is left out: it needs the local server.

To look at the published copy before pushing, serve `data/` and open `/site/` (the
`published-site` entry of `.claude/launch.json` does this on port 8766).

## Judging road access with a local vision model

A house takes its nearest street unless a driveway is drawn, mapped in OSM or seen in imagery
(Method, step 4), and has aliases on the other streets it may be reached from (above). The judge
is the other way to settle a house, kept as a tool: no model tried so far is good enough to run
unattended.
`judge.py` lets a vision-language model running on this machine settle the rest, house by house
from the farthest from any street (250 m) to the nearest. For each house it draws one picture: the
satellite photo beside a map of OSM's streets and buildings, the house in red, up to four candidate
streets lettered A–D in colour. The model answers which one the house is reached from, or "none",
twice with the letters shuffled; an answer both passes give with confidence 80 or more is applied
at the next build, any other waits for a person in the approval queue. Houses with a single street
within reach are recorded without asking.

`--method driveway` asks instead what these models are trained to do, locate something: on the
satellite photo alone (1000 pixels square, so pixel coordinates and the 0–1000 grid some models
answer in agree; the candidate streets drawn thin in yellow), point at the place on the street
where the house's way in joins it. The street is the candidate within 20 m of that spot; asked at
two zooms, the same street both times is applied without review. `--think` lets a reasoning model
think before its answer (JSON mode off, up to 4,096 tokens).

1. Serve a vision model behind an OpenAI-compatible endpoint. With Unsloth Studio, Qwen3-VL-8B
   (6.3 GB to download, fits a 16 GB GPU):

   ```bash
   unsloth studio run --model unsloth/Qwen3-VL-8B-Instruct-GGUF --gguf-variant UD-Q4_K_XL \
       --max-seq-length 8192 --api-only --port 8888 --api-key-name judge -y
   ```

   It prints an API key; give it to the judge as `JUDGE_API_KEY` (or `--api-key`). Ollama,
   llama.cpp's server or vLLM work the same way with `--endpoint` and `--model`.

   MiMo-VL-7B-RL (`unsloth/MiMo-VL-7B-RL-GGUF`, 6.2 GB) needs llama.cpp's server directly: through
   Studio it answers gibberish, and with its image encoder on the GPU it reads every image as
   "????", so the encoder runs on the CPU (about 12 s a picture). It thinks before answering, so
   add `--think` to the judge:

   ```bash
   M=$(ls -d ~/.cache/huggingface/hub/models--unsloth--MiMo-VL-7B-RL-GGUF/snapshots/*/)
   ~/.unsloth/llama.cpp/llama-server -m $M/MiMo-VL-7B-RL-UD-Q4_K_XL.gguf --mmproj $M/mmproj-F16.gguf \
       --no-mmproj-offload -ngl 99 -t 8 -c 8192 --jinja --flash-attn on \
       --alias unsloth/MiMo-VL-7B-RL-GGUF --port 8888 --host 127.0.0.1
   ```
2. Run it, stop it with Ctrl-C whenever you like, and run the same command to resume:

   ```bash
   export JUDGE_API_KEY=...   # the key Studio printed
   uv run python -I -m better_lebanon_map.judge run --endpoint http://127.0.0.1:8888/v1 \
       --model unsloth/Qwen3-VL-8B-Instruct-GGUF   # --method driveway, --think, --limit N, --auto 80
   uv run python -I -m better_lebanon_map.judge stats
   ```

   Score a model before a long run: `judge pilot --endpoint ... --model ...` judges the 81 houses
   of `data/judge/pilot.tsv`, whose way in was read beforehand off the same pictures (results
   below), in a database of its own per model, and compares. `--auto 101` sends every answer to
   the queue; `--backend nearest` fills the queue without a model.
3. Review the queue at `http://localhost:8765/judge.html` (with `serve` running): the least
   confident answers first, the satellite photo and the OSM map side by side, the candidates
   lettered and the model's choice dashed. <kbd>Enter</kbd> approves, <kbd>A</kbd>–<kbd>D</kbd>
   picks another street, <kbd>N</kbd> means no access visible, <kbd>S</kbd> skips.
4. Rebuild. Streets chosen or approved by a person apply first, then the model's own answers when
   they name another street than the nearest; the address card says which. After a new OSM extract,
   `judge plan` re-plans; decisions are kept (they record the building and where it meets its
   street, not street ids, which change between builds).

Progress lives in `data/judge/judge.sqlite`, satellite tiles in `data/judge/tiles`. The tiles are
Esri World Imagery unless `--imagery` gives another tile URL: check the provider's terms before
judging many houses.

**Pilot results: none of the small models tried is good enough to run on every house (too many
wrong changes, or too few right ones and too slow), so the full run has not been started.** The
pilot drew 81 houses at random from four distance bands (20 per band, 20–250 m from a street, each
with two or more candidates) plus a house whose driveway is known. Before any model ran, a person
(the AI assistant that built this pipeline) read the same pictures: 65 show the way in, and for 58
of those it is the nearest street, so the judge only helps if it finds the other 7 without moving
the rest.

- Qwen3-VL-8B (Unsloth's 4-bit GGUF, 0.76 houses a second on an RTX 4080 SUPER): the passes agreed
  on 42 houses. Of the 6 answers it would have applied alone that change the street, 2 are right,
  3 wrong and 1 cannot be told from the picture. It found 1 of the 7 houses reached from a farther
  street and missed the known one. Asking one yes/no question per street on a zoomed crop did not
  help: its answers followed the wording of the question (it said "yes" to 92% of wrong streets
  with one wording, "no" to two thirds of the right ones with another). Nor did the driveway
  method: asked to point at where the way in meets a street, to trace it, or to box it, it pointed
  at or boxed the house itself, whether outlined or marked with a dot (1 right of 12 houses whose
  way in is clear).
- MiMo-VL-7B-RL with the driveway method and `--think` (about 95 s a house: its image encoder runs
  on the CPU and it thinks for 500–1,700 tokens an answer): none of the street changes it would
  apply alone is wrong. It changed 3 houses, 2 rightly (one reached from a farther street, one
  from either street) and 1 that cannot be told from the picture. But it seldom finds the way in:
  of the 50 houses where its two zooms agreed, 41 are "none", 34 of them a spot 20–320 m from any
  of the streets (half beyond 70 m), and it found 1 of the 7 houses reached from a farther street,
  missing the known one. Where the zooms disagreed, its first answer named another street than
  the nearest on 5 houses whose way in shows, and 4 of those are wrong. Its agreed answers on top
  of the nearest street are right on 59 of the 65 houses instead of 58, but at its speed the
  212,700 buildings 20 m or more from a street would take up to 8 months (the 16,552 beyond
  100 m, 18 days).
- Ministral-3-3B: the same confidence (95) for every answer, a bias toward the first letter, and
  6 of 8 answers changed when the letters were reversed.
- LFM3-VL-2B could not be tried: its GGUF needs a newer llama.cpp than Unsloth Studio ships.

The nearest street alone is right on 58 of the 65 houses (89%): a model has to find the other 7
without spoiling those. The pilot's houses, readings and candidate distances are in
`data/judge/pilot.tsv` (a house whose streets change in a new extract is left out of the score),
so `judge pilot` repeats the test for a stronger model when one fits; until then the queue works as
a manual tool (`--backend nearest`, or a model with `--auto 101` so that nothing applies without a
person).

## Outputs

| File | Contents |
| --- | --- |
| `data/output/streets.gpkg` | Logical streets: `name_ar`/`name_fr`/`name_en`, `name_source`, `name_ref`, `old_name`, `needs_review`, `transcribed`, `duplicate_name`, OSM way ids |
| `data/output/addresses.gpkg`, `addresses.csv` | One row per building: house number, side, full address in 3 languages, OSM building id, `access` (`nearest`, `drawn`, `mapped`, `imagery`, `judged` or `approved`); layer `access_paths` holds the driveways |
| `data/output/boundaries.gpkg` | Layers `communes` (OCHA cadasters with `ocha_pcode`, `contested_km2`), `districts`, `governorates`, `contested` |
| `data/output/address_aliases.csv`, layer `aliases` of `addresses.gpkg` | One row per second address: the building, its number and full address on the other street, the distance from its walls to that street, and its own address (`primary_address_fr`) |
| `data/output/stats.json` | Counts from the last run, and the alias check on houses whose street is known |
| `data/corrections/streets.jsonl` | Streets confirmed on address cards, applied at each build |
| `data/judge/judge.sqlite` | The access judge's plan and decisions (model's and people's) |
| `data/judge/pilot.tsv` | 81 houses and the street each is reached from, read off the judge's pictures, to score a model (`judge pilot`) |
| `viewer/data/` | Per-commune streets/addresses/aliases and buildings, boundaries, search index, landmarks, main roads, routing graph |
| `data/site/` | The copy of the viewer that `publish.py` pushes to GitHub Pages |

## Method

Everything is deterministic: the same OSM extract always gives the same names and numbers.

1. **Extract** (`extract.py`): highways, buildings, landmarks, place nodes and admin boundaries.
2. **Communes** (`localities.py`): the official cadastral villages from OCHA (1,547 after
   OCHA's unnamed contested pieces join their neighbour), covering all of Lebanon. Arabic names
   are OCHA's; the usual French/English spelling is borrowed from the OSM commune or village of
   the same Arabic name. A cadaster covers several localities, and OCHA sometimes names a
   different one in each script (cadaster 35353 is "Fnaydeq" in English but "النبي خالد" in
   Arabic, two of its five localities in the CAS list): a commune is then named after one place
   in all three scripts, the OSM village its Latin name belongs to, else OCHA's Arabic name.
   Where that does not settle it -- OCHA's Latin is another locality ("Kfar Tay Kesrouane" for
   "دير زرعيا", a cadaster whose only locality in the CAS list is Kfar Tay, كفر تيه), a longer form
   ("Dhour El Choueir" for "الشوير", Dhour El Choueir being a locality of its own) or a typing
   slip ("Khayayeb" for Kharayeb) -- 26 cadasters take their names from the CAS list of
   localities for the same code, or from OSM's village. Street names spell a commune as it is
   named, so the road "طريق كفر تيه" is "Route de Kfar Tay". OCHA's Latin typing slips are
   corrected ("Mzaraat Zahleh" -> "Mazraat Zahleh", "Kfar hay" -> "Kfar Hay"), and
   mandate-era spellings lose their circumflexes ("Bhamdoûn" -> "Bhamdoun"). Districts are
   OCHA's; each sits in the governorate OSM gives it (9, including Keserwan-Jbeil), and
   governorate outlines are dissolved from districts so all lines agree. Beirut's OSM sectors act
   as quarters.
3. **Logical streets** (`network.py`): ways are cut at junctions; a main road's name carries on
   through straight unnamed stretches (OSM often drops it for a few hundred metres); named pieces
   are grouped by name within a commune when they are close: 300 m apart at most, 1,200 m along a
   main road. A street is one place: pieces of one name farther apart are separate streets, told
   apart by naming (step 5). Pieces that share only a municipal code join across 60 m at most,
   since a code is not a name: "شارع 65" is Street 65 of each Beirut sector it appears in, and
   Achrafieh's two, 1.6 km apart, are two streets. Unnamed pieces are chained by the straightest
   continuation at each junction.
4. **Buildings → streets** (`addressing.py`, `access.py`): the nearest street within 100 m,
   unless a driveway shows how a building more than 25 m from any street is reached: one drawn
   in the corrections file, a street a person confirmed on the address card or chose with the
   access judge (above), a driveway,
   track, footway or steps that OSM maps (OSM does not count them as streets), or a track seen in
   satellite imagery that OSM does not map. OSM's ways count where a group of connected ones
   meets exactly one street, for buildings up to 150 m along them: a group that meets two
   streets does not say which one a building is reached from. A track seen in imagery must leave
   one street and end without reaching another. The house at the end of a 75 m drive off Rue
   Broumana in Jouret Ballout is "2180 Rue Broumana", not "556 Rue des Chênes", the nearer street
   it cannot reach. Such a building belongs to the street its driveway leaves and is numbered
   where it leaves it, on that side; its card says how it is reached and the map draws the
   driveway. A way that reaches more than 10 buildings from one junction is a lane (a
   settlement's alleys, a farm's rows of greenhouses), not a driveway: numbered one after the
   other there, its buildings would push the street's numbers far past its metres, so they keep
   their nearest street. With this extract, 3,258 buildings are reached by a way OSM maps: 738
   belong to another street than the nearest one, 197 had no street within 100 m and now have an
   address, and the others are numbered where their way leaves the same street; 554 beside lanes
   keep the nearest. 5,569 are reached by a track seen in imagery (1,801 of them on another street
   than the nearest, or with none before), and one by a drawn driveway. Dead-ends are numbered from their
   open end.
5. **Names** (`naming.py`, `themes.py`), in order of preference:
   - existing OSM names, kept — except placeholders and municipal codes ("شارع 12",
     "Street 14-G-3-A", "زنقة 22", "الينار 1/17"), which get a name like unnamed streets and keep
     the code as `old_name`. A street's French and English come from OSM's `name:fr` / `name:en`
     tags that name what its Arabic name does: OSM often leaves another street's tags on a way
     (the road named "جادة الرئيس اللواء فؤاد شهاب" is tagged "Avenue Charles Malek" on most of its
     pieces), so a tag must sound like the Arabic or read back as it ("Rue de la Gare" is "شارع
     المحطة"); otherwise the other tag, or the Arabic spelled through the dictionaries, is used.
     A name with no street type in any script gets one ("Antoine Choueiri" -> "Rue Antoine
     Choueiri", "الوردانية - كفرنبرخ" -> "Route Wardaniyeh - Kfar Nabrakh");
   - "Route de X" for long roads leading into town X;
   - the most notable landmark on the street (church, mosque, school, park, spring; never
     brands, shops, codes or names longer than 40 characters), or the hamlet/neighbourhood it
     runs through;
   - through streets: themed names — trees, flowers, birds, sky, stars, heritage, values,
     gems, animals — one theme per sector of each commune, so a theme points to an area; when a
     large commune has used every theme, the same names again as "Chemin des Cèdres" (درب الأرز);
   - dead-ends and short passages: the street they open onto plus the house number at the
     junction, e.g. "Impasse des Cèdres 360" leaves Rue des Cèdres (Bikfaya) at no. 360, and
     "Impasse des Cèdres 360-45" leaves that one at its no. 45; deeper branches, dead-ends
     opening onto no named street or onto a road between two places ("Route Wadi Chahrour -
     Houmal"), get a themed name;
   - last resort: quarter + number.
   Names are unique per commune in all three languages (pieces sharing an Arabic name or a
   specific French name, close enough to be one street, are one: step 3).
   A name missing in one script is spelled, word by word, from: reviewed spellings
   (`spellings.py`: the ~350 words and phrases of real street names that nothing else knew, each
   looked up in its street name and OSM tags — translations such as "الاستقلال" → "de
   l'Indépendance" / "Independence", usual spellings such as "فخر الدين" → "Fakhreddine", titles,
   saints by their Western names after القديس ("Église Saint-Joseph", while "مار يوسف" stays "Mar
   Youssef"), Marian titles ("Our Lady of the Sea"), OSM typos); the gazetteer of village names;
   the themed names' vocabulary ("شارع الغار" in OSM is "Rue des Lauriers" / "Laurel Street"); a
   dictionary of type words and common Lebanese names; then a lexicon learned from OSM itself
   (`lexicon.py`: ~10,000 objects named in both scripts, words paired in order and kept only when
   they sound alike, e.g. "شحادة" ↔ "Chehadé"). An English name missing in OSM follows the French
   tag's spelling unless curated translations give every word ("Rue du Liban" → "Lebanon Street").
   If a word is still unknown and OSM has the name in the other Latin script, that spelling is
   used ("Bonjus Street" → "Rue Bonjus"). Only otherwise is a word spelled letter by letter, and
   the name flagged `needs_review`.
6. **Metric house numbers** (French *numérotation métrique*): number = metres from the street
   start (the end nearest the commune center, or a dead-end's entrance); odd on the left, even on
   the right; strictly increasing along each side. For a street drawn in OSM as separate pieces,
   the gaps count too, so the viewer shows that measured length.
7. **Second addresses** (`aliases.py`): an alias on each other street a building may be reached
   from, numbered the same way without moving any building's own number ("Which street?" above).
8. **Routing graph** (`routing.py`): all roads including motorways, ramps and footpaths, with
   one-way rules, linked to the named streets; the browser runs A* on it. Ramps, bridges and
   paths with an OSM name of their own keep it in directions, in all three scripts; one that
   could only be written by spelling a word letter by letter in another script (a campus path
   "Chemin Courts Tennis") is left unnamed in directions instead.

## Known limits

- OCHA lists 82 small areas as contested between cadasters; they are shaded on the map and
  counted in each commune's `contested_km2`.
- 13 of the 1,547 communes keep a Latin name that the dictionaries do not hear in their Arabic one
  (the audit lists them): an exonym ("Tyr" for "صور"), translations ("Beirut Central District" for
  "وسط بيروت", "Port of Beirut" for "المرفأ"), and spellings the CAS list gives or nearly gives ("Shayleh" for "سهيلة";
  "Chenan Aair" for "شننعير", which CAS writes "Chnanaair").
- Name quality is checked two ways: the audit above (every name, mechanical checks; it passes
  with zero findings) and independent reviews of random samples of 420 names read as a Lebanese
  reader would. Landmark and hamlet names were the weakest source, so a landmark now names a
  street only when its Arabic name is a landmark noun plus words the curated tables know, and is
  translated from the Arabic alone; other streets get theme names. The fifth review found a real
  problem (wrong or garbled, or unnatural, or the three languages disagreeing) in 28 of 420 names,
  6.7% (the first four found 71, 58, 49 and 53): none among 190 theme, dead-end and destination
  names; 20 among 140 OSM names, mostly slips in the OSM name itself (سارع for شارع, "Maisons
  Privee") or English that copies a French or foreign word ("Avenida Brasil", "Parlement"); 4
  among landmark names built on compound institution names ("Collège Notre-Dame de Jamhour").
  Each kind of slip was fixed by a rule, not name by name, and the sixth review, on a new sample
  of the rebuilt map, found 23 (5.5%): 14 among 140 OSM names (one language's words left in the
  other, "Cedres", "Rue Farm", "Rue Syrie"; typos such as "Rue Rua"), 4 among 30 route-only names,
  and 5 among 250 generated names (star names such as السماك, which reads as "the fishmonger").
  Those kinds were fixed in turn. The seventh review found 24 (5.7%), 21 of them where the system
  fills in a language OSM lacks: English made from French that kept French words ("Kurdes",
  "Amérique"), French made from English that kept English ("Rue principale de 1st"), and names
  read as common nouns (البير, Albert, as "the well"; "Mère Marguerite" as the daisy; خديجة الكبرى
  as "Khadigé Grande"). The eighth and ninth found 16 each (3.8%): OSM tags in the wrong language
  ("Round-about" as the French name), exonyms ("Asfahan" for Isfahan), titles ("Advocat" for
  المحامي; OSM's Arabic باتريسيا, Patricia, for "Patriarch"). Those were fixed by rules too, and the
  tenth review, on the final build, found 15 (3.6%), none among 210 theme, dead-end, landmark and
  place names. 13 are OSM or route-only names whose other script the system had to make: Arabic
  spelled from a Latin name in Latin word order ("شارع انطوان فرح إقامة", "K.F." spelled out), a
  French or English word left in the other language ("Centrale Square", "Rue Lower"), a name
  re-spelled by sound (عمرو as "Amar"/"Omar"). The other 2 are town spellings in destination names
  ("Aaintaroun" for Aitaroun). Over the ten reviews the count went 71, 58, 49, 53, 28, 23, 24, 16,
  16, 15; what remains is a long tail of single names, best fixed in OSM itself.
- No street name, and no name used in directions, is spelled by letter-by-letter guesswork
  (`needs_review` is 0, and route-only names that would need it are left unnamed). For 17 streets
  that OSM names only in Latin letters, with a word whose Arabic original was not found in OSM,
  the official list of localities (CAS) or web sources ("Rue Jean de Cruet", "Souk Sayyour"), the
  Arabic is a phonetic transcription checked by hand, marked `transcribed` in the data and on the
  street card. The reviewed spellings in `spellings.py` were written by the AI assistant that
  built this pipeline, from each street's context and those sources; a Lebanese reader should
  still skim them.
- OSM names are kept as mapped, so some of their oddities stay: a brand translated word for word
  ("طريق الواجهة البحرية للمدينة" for Waterfront City), a spelling that differs from the town's ("Qoubbeyaa" in Qobbayat),
  or two segments of one road tagged differently. The audit lists the names from OSM tags whose
  Latin and Arabic do not sound alike (about 55, mostly translations such as "Rue du Général" or
  acronyms such as "Rue F.R.A."); they were read one by one.
- Every full address is unique in Arabic, French and English. Village names shared by several
  communes carry their district ("Niha (Zahlé)"). When OSM gives two streets of one commune the
  same name in one language, one of them is spelled from its other OSM names instead; a compass
  qualifier ("Route de la Mer (Nord)") is the last resort, needed for 14 pairs with this extract:
  two separate roads of one commune that OSM names alike, such as the stretches of the coast road
  tagged "طريق البحر" in one commune more than 1,200 m apart.
- A building whose driveway is neither in OSM, nor drawn, nor seen in the imagery takes its
  nearest street, even when it is reached from another one: the map shows it under that street,
  and its aliases make it findable under the others. For about 4% of such houses the right street
  is not among them (farther than the rules reach, or across another street), until someone
  confirms it on the address card. Imagery shows a track, not a gate or
  a right of way; Microsoft's detections miss about one road in five (more under trees), and the
  imagery is a few years old in places. Of 55 imagery matches checked by eye on the satellite
  photo (15, then 40 drawn at random), none looked wrong: 23 show the track or alley clearly, 27
  a plausible way in, and for 5 the photo cannot tell; of the 11 among the 40 that change street,
  1 is clear, 8 plausible and 2 uncertain. Of 40 matches with OSM's ways drawn at random and
  checked the same way, 31 still apply once lanes are left out, and none looked wrong: of the 24
  that change street, 13 show the way in clearly, 9 plausibly, and 2 leave a corner where either
  street serves; the 7 that keep their street show it clearly. Drawing the driveway fixes a house
  for good, and so does mapping it in OSM, where a real driveway belongs; the access judge
  (above) can review the rest.
- Greenhouses that OSM maps as plain buildings (whole farms of them, as on the Akkar plain) get
  addresses like houses: 6 of the 40 OSM matches above were greenhouses.
- Numbering uses the building's center, not its entrance; a corner building is shown under one
  street and has an alias on the other.
- Aliases are generous: a house far from any street may have three, of which at most one is how
  it is really reached. They are never drawn as numbers on the map, only found by search and
  listed on the card.
- Landmarks keep the names OpenStreetMap has, in the scripts it has them: a shop named only in
  Latin letters is not found by an Arabic search.
- Coverage follows OSM: unmapped buildings get no address until they are mapped.
- The default base map has no terrain, land use or coastline detail: it draws only what the map
  itself knows. From zoom 14 that is every road OpenStreetMap has, at full detail: the named
  streets, and with each commune its motorways, ramps, roundabouts, unnamed stretches, tracks and
  paths (below that, a country-wide overview of the main roads simplified to 15 m). A bridge is
  not drawn above the road it crosses. Esri's tiles remain as options locally (free for development; a published copy
  leaves them out unless asked).
