# Číselníky a importy

Číselníky sú zoznamy kódov z účtovného programu obce. Program z nich navrhuje a pri oprave pripustí len kódy, ktoré v nich sú. Číselníky sú na každý rok osobitne.

## Číselníky obce

| Záložka               | Čo obsahuje                                                                                          |
| --------------------- | ---------------------------------------------------------------------------------------------------- |
| Výdavkový rozpočet    | položky rozpočtu; kľúč tvorí EK, zdroj, oddiel, trieda a analytika, napríklad _632005 41 01 110 000_ |
| Príjmový rozpočet     | príjmové položky; z ich dotačných riadkov sú odvodené transfery                                      |
| Účtový rozvrh         | syntetické a analytické účty, napríklad _518 003_                                                    |
| Číselné rady dokladov | rady dokladov s tvarom čísla, napríklad _FD/XXX/RR_                                                  |
| Transfery             | transfery k dotáciám so zdrojom financovania                                                         |
| Strediská             | strediská, ak ich obec používa                                                                       |

Na stránke **Číselníky** vyberiete rok a verziu. Hľadanie nerozlišuje veľké a malé písmená ani diakritiku. Neaktívne riadky sú sivé a program ich nenavrhuje.

## Úprava riadkov

Riadok môžete **pridať**, **upraviť**, **deaktivovať** a znova aktivovať. Každá zmena vytvorí novú verziu číselníka; predchádzajúce ostanú vo **Verzie a zmeny**, kde vidíte aj rozdiely medzi verziami. Upravovať sa dá len aktívna verzia.

Faktúra si pamätá verzie číselníkov, s ktorými bola navrhnutá; **Navrhnúť znova** použije aktuálne.

## Import zo súboru

Celý číselník nahradíte importom: **Importovať** na stránke Číselníky alebo **Nový import** v **Importy a exporty**. Sprievodca má päť krokov:

1. **Súbor:** čo importujete, rok a súbor CSV, XLSX alebo XLS.
2. **Čítanie:** hárok, riadok s hlavičkou, kódovanie a oddeľovač CSV (rozpoznajú sa samé) a ukážka prvých riadkov.
3. **Mapovanie:** ku každému poľu stĺpec súboru alebo pevná hodnota a úpravy hodnoty, napríklad rozdelenie kľúča _637005 41 01 110 000_ na časti alebo doplnenie núl. Sprievodca mapovanie navrhne podľa šablóny alebo podľa názvov stĺpcov.
4. **Kontrola:** skúšobný import ukáže počet riadkov, chyby a upozornenia s číslom riadku, rozdiel oproti aktívnej verzii (pridané, zmenené, odstránené) a ukážku.
5. **Hotovo:** **Importovať** vytvorí novú verziu číselníka a urobí ju aktívnou.

Chyby v súbore, napríklad nečitateľný riadok, chybný kľúč alebo súbor s IČO inej obce, import nedovolia: opravte súbor alebo mapovanie a skúšobný import spustite znova. Kódy, ktoré nepoznajú [globálne číselníky](globalne-ciselniky) roka (EK, zdroj, oddiel, trieda), import tiež zastavia, ale môžete ich vedome importovať tlačidlom **Importovať napriek…**; potvrdenie sa zapíše do auditu.

## Šablóny mapovania

Mapovanie uložíte ako šablónu tlačidlom **Uložiť mapovanie ako šablónu** a pomenujete ju podľa zdroja, napríklad _TOPSET – Účtový rozvrh_. Pri ďalšom súbore s rovnakými hlavičkami ju sprievodca použije sám. Program má vstavané šablóny pre exporty z TOPSETu: účtový rozvrh, výdavkový a príjmový rozpočet a rady dokladov. Šablóny klienta sú v **Importy a exporty**, kde ich môžete aj odstrániť.

## Kniha došlých faktúr

Import **Kniha došlých faktúr** (predchádzajúce zaúčtovania) naplní pamäť dodávateľov faktúrami zaúčtovanými pred začiatkom používania programu. Program potom aj prvú faktúru známeho dodávateľa navrhne tak, ako ju obec účtuje. Čísla týchto dokladov sa označia ako použité. Doklad, ktorý už v programe je, sa preskočí s upozornením.

## Po importe

Skontrolujte **Systém**, záložku **Kontrola znalostí**: ukáže napríklad položky rozpočtu, ktoré program nevie navrhnúť. Pozri [Systém](system).
