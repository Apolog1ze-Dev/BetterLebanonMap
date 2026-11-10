# Better Lebanon Map

[English](README.md) · **Français** · [العربية](README.ar.md)

**Une expérience : organiser la carte du Liban pour que chacun puisse s'y repérer par adresse.**

**Ouvrir la carte : https://apolog1ze-dev.github.io/BetterLebanonMap/**

Dans la plus grande partie du Liban, les rues n'ont pas de nom en usage et les bâtiments n'ont pas
de numéro. On s'oriente donc par repères : « après la pharmacie, deuxième immeuble à gauche ». Ce
projet essaie de montrer à quoi ressemblerait un système d'adresses complet. Il part des données
OpenStreetMap du Liban et donne à chaque rue un nom en arabe, en français et en anglais, à chaque
bâtiment un numéro, et à chaque lieu une localité, un district et un gouvernorat. Le résultat est
une carte où l'on cherche par localité, rue et numéro.

C'est une expérience et une proposition, pas un système d'adresses officiel. Aucune autorité n'a
adopté ces noms et ces numéros, et ils ne doivent pas être versés dans OpenStreetMap, qui
n'enregistre que les noms existant sur le terrain.

## Ce que fait la carte

- **Elle trouve une adresse quelle que soit la façon de l'écrire**, en arabe, en français ou en
  anglais : `22 rue des cedres bikfaya`, `شارع الأرز 22 بكفيا`, `Achrafieh`, `pharmacie bikfaya`.
  Les accents, les hamzas et les virgules sont facultatifs, et l'orthographe n'a pas à être exacte.
- **Elle présente chaque adresse comme une plaque de rue**, avec le numéro, le nom de la rue en
  lettres arabes et latines, et des boutons pour l'itinéraire, le partage et la copie.
- **Elle dit à quel point la réponse est exacte.** Un numéro porté par un bâtiment ouvre ce
  bâtiment. Un numéro qu'aucun bâtiment ne porte encore est montré comme une position approximative
  dans la rue.
- **Elle donne l'adresse de n'importe quel endroit.** Cliquez sur un bâtiment, faites un clic droit
  (ou un appui long) n'importe où, ou demandez l'adresse de l'endroit où vous êtes.
- **Elle calcule des itinéraires** en voiture ou à pied, de porte à porte, avec les nouveaux noms
  de rues.
- **Elle trouve les repères** : environ 15 000 commerces, écoles, lieux de culte et pharmacies
  nommés, chacun avec l'adresse du bâtiment le plus proche.
- Elle fonctionne sur téléphone et sur ordinateur, en arabe (de droite à gauche), en français et
  en anglais.

## Comment fonctionne une adresse

- **Le numéro est une distance.** Le n° 240 est à 240 mètres du début de sa rue. Les numéros
  impairs sont à gauche, les pairs à droite. Un nouveau bâtiment reçoit un numéro sans que celui
  des autres change.
- **Les noms de rues.** Les noms présents dans OpenStreetMap sont conservés. Les routes menant à la
  localité voisine portent son nom. Les autres rues reçoivent un nom tiré d'un thème commun à leur
  quartier (arbres, fleurs, oiseaux…), si bien qu'un nom indique aussi à peu près où l'on se
  trouve. Une impasse porte le nom de la rue qu'elle quitte et le numéro où elle la quitte :
  « Impasse des Cèdres 360 ».
- **Plusieurs accès possibles.** La carte ne peut pas toujours savoir par quelle rue on accède à un
  bâtiment. Un tel bâtiment a une adresse dans chaque rue par laquelle on peut y accéder, et toutes
  y mènent. Quiconque connaît le bâtiment peut indiquer la bonne.

## Ce qu'elle couvre

Construite à partir de l'extrait OpenStreetMap du Liban :

| | |
| --- | --- |
| Bâtiments ayant une adresse | 715 147 |
| Rues nommées | 92 417 |
| Villes et villages (zones cadastrales officielles) | 1 547 |
| Adresses secondaires, pour les bâtiments à plusieurs accès | 366 875 |

## À garder à l'esprit

- **Ce n'est pas officiel.** Considérez-la comme une proposition à discuter, ou comme une base de
  travail pour une municipalité.
- **Elle ne sait que ce que sait OpenStreetMap.** Un bâtiment qui n'y est pas cartographié n'a pas
  d'adresse ici.
- **La rue d'une maison est parfois une supposition.** Pour les maisons dont la rue est connue, la
  rue la plus proche est la bonne dans 69 % des cas ; avec les adresses secondaires, la bonne rue
  figure parmi les adresses de la maison dans 96 % des cas.
- **Les noms générés sont générés.** La plupart des noms de rues ont été fabriqués par des règles,
  en trois langues. Une relecture à la main de 420 noms, sur une version antérieure, a relevé un
  problème dans 15 d'entre eux.
- **La carte est simple.** Elle dessine les routes, les bâtiments et les limites, sans relief ni
  occupation du sol.

## L'utiliser soi-même

Il faut Python avec [uv](https://docs.astral.sh/uv/), et les données d'entrée indiquées dans les
[notes techniques](docs/METHOD.md#run).

```bash
uv sync
uv run python -I -m better_lebanon_map.pipeline     # construit les données, environ 8 minutes
uv run python -m better_lebanon_map.serve           # puis ouvrir http://localhost:8765
node tools/geocode_eval.mjs                         # vérifie la recherche sur des adresses tirées au hasard
```

Pour mettre la carte en ligne comme site statique sur GitHub Pages :

```bash
uv run python -I -m better_lebanon_map.publish --repo owner/name --push
```

## Aider à l'améliorer

- Sur la fiche d'une adresse, répondez à « L'entrée est-elle dans une autre rue ? » si vous
  connaissez le bâtiment.
- Corrigez ou ajoutez des rues, des noms et des bâtiments dans
  [OpenStreetMap](https://www.openstreetmap.org) même : la prochaine version les reprendra.
- Ouvrez un ticket pour tout ce qui paraît faux.

## Licence et crédits

- Le logiciel est © 2026 Karim Dagher, sous [licence Apache 2.0](LICENSE). Vous pouvez l'utiliser,
  le modifier et le redistribuer, y compris à des fins commerciales, à condition de conserver la
  mention de droit d'auteur et le fichier [NOTICE](NOTICE) qui crédite son auteur.
- Données cartographiques © les contributeurs d'[OpenStreetMap](https://www.openstreetmap.org/copyright),
  Open Database License.
- Limites © OCHA, [COD-AB Liban](https://data.humdata.org/dataset/cod-ab-lbn), CC BY-IGO.
- Allées issues de [Microsoft RoadDetections](https://github.com/microsoft/RoadDetections), Open
  Database License.
- Les adresses et les noms de rues qui en sont dérivés sont disponibles sous Open Database License.

La façon dont la carte est construite, dont elle a été vérifiée, et ce qui a été essayé puis
abandonné se trouvent dans les [notes techniques](docs/METHOD.md) (en anglais).
