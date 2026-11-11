# Globálne číselníky

Globálne číselníky platia pre všetky obce, každý na jeden rok. Spravuje ich administrátor na stránke **Globálne číselníky**.

| Číselník                        | Zdroj                                                                      |
| ------------------------------- | -------------------------------------------------------------------------- |
| Ekonomická klasifikácia         | opatrenie MF SR č. MF/010175/2004-42 v znení účinnom pre daný rok          |
| Funkčná klasifikácia (SK COFOG) | vyhláška č. 257/2014 Z. z.                                                 |
| Zdroje financovania             | prílohy Príručky na zostavenie návrhu rozpočtu verejnej správy na daný rok |
| Rámcová účtová osnova           | opatrenie MF SR č. MF/014454/2022-36 v platnom znení                       |

## Prehľad podľa rokov

Tabuľka **Prehľad podľa rokov** ukazuje, ktorý číselník je na ktorý rok a koľko má riadkov. Pred začiatkom nového roka pripravte všetky štyri. Zdroje sú väčšinou zverejnené ako PDF, preto ich treba prepísať do súboru CSV so stĺpcami _code_ a _name_.

## Import

Import globálneho číselníka používa rovnakého sprievodcu ako import číselníkov obce: súbor, mapovanie, skúšobný import s rozdielom oproti aktívnej verzii a nakoniec import. Každý import vytvorí novú verziu. Pozri [Číselníky a importy](ciselniky-a-importy).

## Na čo slúžia

Podľa globálnych číselníkov sa kontrolujú číselníky obcí pri importe:

- EK, zdroj, oddiel a trieda položky rozpočtu, ktoré globálny číselník roka nepozná, sú **chyby**; importovať sa dajú len s vedomým potvrdením;
- syntetický účet, ktorý nie je v rámcovej účtovej osnove, je **upozornenie**.

Chýbajúci globálny číselník roka ukáže kontrola znalostí každého klienta.
