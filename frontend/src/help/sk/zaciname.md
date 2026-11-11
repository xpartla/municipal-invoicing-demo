# Začíname

Program pripraví z došlej dodávateľskej faktúry obce návrh zaúčtovania: účty MD a DAL, rozpočtovú položku a hlavičku dokladu. Návrh skontrolujete, prijmete alebo opravíte a zaúčtovanú faktúru exportujete do účtovného programu.

## Cesta faktúry

1. **Nahratie.** Na stránke **Nová faktúra** nahráte sken, fotografiu, PDF alebo elektronickú faktúru (XML), prípadne faktúru zadáte ručne. Pozri [Nahrávanie a skenovanie faktúr](skenovanie).
2. **Čítanie.** Program prečíta údaje faktúry: zo skenu pomocou OCR, z PDF z jeho textu, z elektronickej faktúry priamo.
3. **Kontrola údajov.** Prečítané údaje porovnáte s dokladom a potvrdíte, aj dátum a číslo, ktoré ste na doklad napísali rukou. Pozri [Kontrola údajov](kontrola-udajov).
4. **Návrh.** Po potvrdení program navrhne zaúčtovanie a vysvetlí, prečo. Pozri [Ako čítať návrh zaúčtovania](navrh).
5. **Zaúčtovanie.** Návrh prijmete alebo opravíte a doklad dostane číslo v číselnom rade. Pozri [Opravy](opravy) a [Číselné rady](ciselne-rady).
6. **Export a úhrada.** Zaúčtované faktúry exportujete do súboru pre účtovný program a po zaplatení ich označíte ako uhradené. Pozri [Export do TOPSETu a úhrady](export-do-topsetu).

Ako program rozhoduje, opisuje článok [Ako to funguje](ako-to-funguje).

## Menu

| Položka           | Čo v nej nájdete                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Domov             | Prehľad mesiaca: ukazovatele, grafy, čo vyžaduje pozornosť, číselné rady a prvé kroky.                                   |
| Faktúry           | Všetky faktúry s filtrami a hromadnými akciami. Pozri [Zoznam faktúr](faktury).                                          |
| Číselníky         | Rozpočet, účtový rozvrh, číselné rady dokladov, transfery a strediská. Pozri [Číselníky a importy](ciselniky-a-importy). |
| Importy a exporty | História importov a exportov, nový import a export, šablóny mapovania.                                                   |
| Úložisko          | Všetky súbory: doklady faktúr, importované a exportované súbory.                                                         |
| Správy            | Pripravujeme: správy a upozornenia od servisného účtu a administrátora.                                                  |
| Systém            | Parametre, účtovacie zvyklosti, číselné rady a kontrola znalostí. Pozri [Systém](system).                                |

Nad menu je tlačidlo **Nová faktúra**, pod ním **Pomocník**, **Profil** a **Odhlásiť**. Otáznik vpravo hore otvorí návod k obrazovke, na ktorej práve ste. Na úzkej obrazovke menu otvoríte tlačidlom vľavo hore; na počítači ho šípkou pod menu zbalíte na ikony.

## Roly

- **Iba na čítanie** vidí všetko, ale nič nemení: nenahráva, neúčtuje ani neimportuje.
- **Používateľ** spracúva faktúry svojej obce, importuje a upravuje číselníky a mení nastavenia v Systéme.
- **Servisný účet** je účtovnícka firma, ktorá spracúva faktúry viacerých obcí; jej pracovníci medzi nimi prepínajú. Pozri [Klienti, kopírovanie a šablóny](klienti).
- **Administrátor** spravuje celú platformu. Pozri [Správa platformy](sprava-platformy).

## Domov

Domov ukazuje vybraný mesiac; šípkami prejdete na predchádzajúci alebo nasledujúci.

- **Ukazovatele:** koľko faktúr sa v mesiaci nahralo, koľko z nich čaká na kontrolu údajov, je na kontrolu alebo sa nepodarilo prečítať, a koľko faktúr sa v mesiaci zaúčtovalo a za akú sumu. Každý ukazovateľ otvorí tieto faktúry v zozname.
- **Grafy a tabuľky:** zaúčtované po dňoch a za posledných 12 mesiacov, podľa druhu dokladu, najčastejší dodávatelia a dodávatelia s najvyššou sumou, podľa funkcie (oddiel a trieda), podiel faktúr na kontrolu a medián času od nahratia po zaúčtovanie. Každý graf sa dá prepnúť na tabuľku.
- **Čerpanie rozpočtu** po položkách, ak importovaný rozpočet obsahuje sumy.
- **Vyžaduje pozornosť:** neprečítané faktúry, faktúry, ktoré čakajú najdlhšie, a chýbajúce číselníky roka.
- **Číselné rady** roka: posledné a ďalšie číslo a medzery.

Kým nie sú hotové, ukazuje Domov aj kroky **Začíname**: doplniť adresu a bankový účet obce, importovať číselníky na rok, odstrániť chyby v kontrole znalostí a zaúčtovať prvú faktúru.

## Profil

V **Profile** zmeníte svoje meno, e-mail na upozornenia, prihlasovací e-mail a heslo. Prihlasovací e-mail sa zmení až po potvrdení odkazu, ktorý príde na novú adresu. Heslo má aspoň 12 znakov a nesmie patriť medzi bežne používané. V Profile vidíte aj zariadenia, v ktorých ste prihlásení, a môžete sa z nich odhlásiť. Prihlásenie skončí po 8 hodinách nečinnosti, najneskôr po 7 dňoch.

Používateľ obce v Profile dopĺňa aj adresu a bankový účet obce. Názov, IČO a DIČ obce mení servisný účet alebo administrátor; oni obci prideľujú aj variabilný symbol.

## Úložisko

**Úložisko** zoznamuje všetky súbory klienta podľa druhu (doklady, importy, exporty) s veľkosťou a dátumom. Pri každom súbore je, čo ho používa: faktúra, import alebo export. Každý súbor sa dá stiahnuť.
