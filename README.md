# Better Lebanon Map

**English** · [Français](README.fr.md) · [العربية](README.ar.md)

**An experiment in organising the map of Lebanon so that people can find their way by address.**

In most of Lebanon streets have no name in use and buildings have no number, so people give
directions by landmarks: "after the pharmacy, second building on the left". This project tries out
what a complete address system could look like. It takes the OpenStreetMap data for Lebanon and
gives every street a name in Arabic, French and English, every building a house number, and every
place a town, district and governorate. The result is a map you can search by town, street and
house number.

It is an experiment and a proposal, not an official address system. No authority has adopted these
names and numbers, and they must not be uploaded to OpenStreetMap, which only records names that
exist on the ground.

## What the map does

- **Finds an address however it is typed**, in Arabic, French or English: `22 rue des cedres
  bikfaya`, `شارع الأرز 22 بكفيا`, `Achrafieh`, `pharmacie bikfaya`. Accents, hamzas and commas are
  optional, and spelling does not have to be exact.
- **Shows each address as a street plaque**, with the number, the street's name in Arabic and
  Latin letters, and buttons for directions, sharing and copying.
- **Says how exact an answer is.** A number that a building has opens that building. A number no
  building has yet is shown as an approximate spot on the street.
- **Tells you the address of any place.** Click a building, right-click (or long-press) anywhere,
  or ask for the address of where you are.
- **Gives directions** by car or on foot, door to door, using the new street names.
- **Finds landmarks**: about 15,000 named shops, schools, places of worship and pharmacies, each
  with the address of the nearest building.
- Works on phones and computers, in Arabic (right-to-left), French and English.

## How an address works

- **The house number is a distance.** Number 240 is 240 metres from the start of its street. Odd
  numbers are on the left, even numbers on the right. A new building gets a number without anyone
  else's changing.
- **Street names.** Names that exist in OpenStreetMap are kept. Roads leading to the next town are
  named after it. Other streets get a name from a theme shared by their neighbourhood (trees,
  flowers, birds...), so a name also tells you roughly where you are. A dead-end is named after the
  street it leaves and the number where it leaves it: "Impasse des Cèdres 360".
- **More than one way in.** The map cannot always tell which street a building is reached from.
  Such a building has an address on each street it may be reached from, and all of them lead to
  it. Anyone who knows the building can say which one is right.

## What it covers

Built from the OpenStreetMap extract of Lebanon:

| | |
| --- | --- |
| Buildings with an address | 715,147 |
| Named streets | 92,417 |
| Towns and villages (official cadastral areas) | 1,547 |
| Second addresses, for buildings with more than one way in | 366,875 |

## What to keep in mind

- **It is not official.** Treat it as a proposal to discuss, or as material a municipality could
  start from.
- **It only knows what OpenStreetMap knows.** A building that is not mapped there has no address
  here.
- **Which street a house belongs to is sometimes a guess.** For houses whose street is known, the
  nearest street is the right one 69% of the time; with the second addresses, the right street is
  among the house's addresses 96% of the time.
- **Generated names are generated.** Most street names were made up by rules, in three languages.
  A hand review of 420 names on an earlier build found a problem in 15 of them.
- **The map is plain.** It draws roads, buildings and boundaries, without terrain or land use.

## Run it yourself

You need Python with [uv](https://docs.astral.sh/uv/), and the inputs listed in the
[technical notes](docs/METHOD.md#run).

```bash
uv sync
uv run python -I -m better_lebanon_map.pipeline     # builds the map data, about 8 minutes
uv run python -m better_lebanon_map.serve           # then open http://localhost:8765
node tools/geocode_eval.mjs                         # checks the search on random addresses
```

To put the map online as a static site on GitHub Pages:

```bash
uv run python -I -m better_lebanon_map.publish --repo owner/name --push
```

## Help improve it

- On an address card, answer "Is the entrance on another street?" if you know the building.
- Fix or add streets, names and buildings in [OpenStreetMap](https://www.openstreetmap.org)
  itself: the next build picks them up.
- Open an issue for anything that looks wrong.

## Licence and credits

- The software is © 2026 Karim Dagher, under the [Apache License 2.0](LICENSE). You may use it,
  change it and redistribute it, including commercially, provided you keep the copyright and the
  [NOTICE](NOTICE) file that credits its author.
- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, Open Database
  License.
- Boundaries © OCHA, [COD-AB Lebanon](https://data.humdata.org/dataset/cod-ab-lbn), CC BY-IGO.
- Driveways from [Microsoft RoadDetections](https://github.com/microsoft/RoadDetections), Open
  Database License.
- The addresses and street names derived from them are available under the Open Database License.

How the map is built, how it was checked and what was tried and dropped is in the
[technical notes](docs/METHOD.md) (in English).
