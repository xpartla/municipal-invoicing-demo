# Ako to funguje

Program vezme došlú dodávateľskú faktúru obce a navrhne, čo účtovník zadá do účtovného programu: zaúčtovanie záväzku (účty MD a DAL), rozpočet záväzku (rozpočtovú položku, prípadne transfer) a hlavičku dokladu (rad, číslo dokladu a dátum zaúčtovania). Návrh vzniká podľa pravidiel, nie umelou inteligenciou, a pri každom poli program vysvetlí, prečo ho navrhol.

## 1. Ako sa faktúra dostane do programu

Faktúra prichádza jedným z troch spôsobov:

- **Sken alebo fotografia** (PDF, JPG, PNG, TIFF). Program obrázok vyrovná a zvýrazní a text prečíta nástrojom OCR (Tesseract) v slovenčine. Hľadá známe označenia: IČO, DIČ, IČ DPH, číslo účtu, variabilný symbol, dátum vystavenia, dodania a splatnosti, sumu na úhradu, dodávateľa a odberateľa. Osobitne hľadá rukou písaný dátum a číslo dokladu, ktoré ste napísali na faktúru.
- **PDF s textom**, napríklad faktúra, ktorá prišla e-mailom. Text sa vezme priamo z PDF, bez OCR, a je presný.
- **Elektronická faktúra**: XML vo formáte UBL (Peppol) alebo ISDOC, aj ISDOC vložené do PDF. Údaje sa prevezmú tak, ako ich poslal dodávateľ.

Po prečítaní program overí, čo sa dá overiť: kontrolné číslice IČO a IBAN, či suma bez DPH a DPH dávajú sumu na úhradu, poradie dátumov a či je faktúra adresovaná tejto obci. Názov a adresu dodávateľa, ktoré sa neprečítali, doplní podľa IČO z predchádzajúcich faktúr.

Faktúru, ktorá sa nedá prečítať, môžete prečítať znova alebo zadať ručne. Faktúru bez súboru zadáte cez **Nová faktúra** a **Zadať ručne**.

## 2. Kontrola údajov

Prečítané údaje vidíte vedľa dokladu. Polia prečítané s nízkou istotou alebo s chybou v kontrole sú žlté, prázdne povinné polia červené. Rukou písaný dátum a číslo potvrdzujete vždy; nad nimi je zväčšený výrez poznámky. Až potvrdené údaje program navrhne zaúčtovať. Pozri [Kontrola údajov](kontrola-udajov).

## 3. Ako program navrhuje

Program vychádza z toho, čo o obci vie:

- **pamäť dodávateľov:** ako obec dodávateľa zaúčtovala naposledy;
- **číselníky obce:** rozpočet, účtový rozvrh, číselné rady a transfery;
- **pravidlá:** ktorá ekonomická klasifikácia patrí ku ktorému syntetickému účtu, slovník pojmov (elektrina, telefón, palivo, potraviny…) s ich typickými položkami, slová, podľa ktorých pozná funkciu (obecný úrad, materská škola, školská jedáleň, verejné osvetlenie…), a účtovacie zvyklosti obce, ktoré určujú analytické účty.

Postupuje takto:

1. **Dodávateľ.** Nájde ho podľa IČO, prípadne podľa názvu.
2. **Hlavička.** Rad je FD, pri potravinách pre školskú jedáleň FDŠJ. Číslo dokladu a dátum zaúčtovania sú tie, ktoré ste napísali rukou; chýbajúce číslo doplní počítadlo. Pozri [Číselné rady](ciselne-rady).
3. **Rozpočtová položka.** Ak obec od dodávateľa už účtovala a faktúra je o tom istom, použije jeho posledné zaúčtovanie. Inak v texte faktúry nájde pojmy a funkciu a vyberie položku rozpočtu, ktorá im zodpovedá. Ak sa časti faktúry týkajú rôznych budov alebo činností, rozdelí ju na viac riadkov.
4. **Účty.** Účet MD určí podľa ekonomickej klasifikácie položky a zvyklostí obce, účet DAL podľa radu (záväzok voči dodávateľovi). Pri dotácii pripojí transfer. Popisy napíše tak, ako ich píše obec.
5. **Kontroly.** Každý kód overí v číselníkoch obce. Upozorní aj na už použité číslo dokladu, na zaúčtovanú faktúru s rovnakým dodávateľom a variabilným symbolom a na dátum zaúčtovania pred vystavením faktúry.
6. **Istota.** Ak si nie je istý, napríklad pasuje viac položiek, faktúru platí dotácia alebo sa niečo prečítalo s nízkou istotou, označí návrh **Na kontrolu** a napíše prečo.

Ak nepasuje nič, napríklad pri dobropise alebo nákupe, aký obec ešte nemala, program nenavrhne žiadny riadok a ponúkne **Zadať ručne**.

Pri každom poli návrhu je v časti **Prečo práve toto** jeho zdroj: precedens dodávateľa, pravidlo, slovník pojmov, podobnosť popisu, rukou na doklade alebo počítadlo dokladov. Pozri [Ako čítať návrh zaúčtovania](navrh).

## 4. Čo zmení zaúčtovanie

Keď návrh prijmete alebo opravíte a zaúčtujete:

- doklad dostane číslo v číselnom rade: rukou napísané číslo, ak je voľné; ak ho už má faktúra dodaná skôr, dostane nasledujúce a ďalšie doklady sa posunú;
- zaúčtovanie sa stane posledným vzorom dodávateľa, takže jeho ďalšiu faktúru program navrhne rovnako; oprava teda program „naučí“;
- faktúra je pripravená na export.

Číselníky sa zaúčtovaním nemenia. Kým faktúra nie je exportovaná ani uhradená, zaúčtovanie sa dá zrušiť. Pozri [Opravy](opravy).

## 5. Čo program nerobí

- Nezapisuje do účtovného programu. Zaúčtovanie prenesiete tlačidlami na kopírovanie alebo zo súboru exportu; priamy import do TOPSETu príde, keď bude známy jeho formát.
- Nezosúlaďuje čísla dokladov s účtovným programom; stav počítadla upravíte v Systéme.
- Nenavrhuje dobropisy ani položky, pre ktoré nemá pravidlo, napríklad mzdy a transfery; tie zadáte ručne.
- Nerozdeľuje súbor s viacerými faktúrami: v jednom súbore má byť jedna faktúra.
- Nepáruje úhrady s bankovými výpismi; úhradu označíte sami.
- Kódy nevyberá umelou inteligenciou, ale podľa histórie dodávateľov, spísaných pravidiel a porovnávania textov. Strojové učenie používa len OCR pri čítaní písma.
- V tejto verzii neposiela e-maily; pozvánky a odkazy na heslo čakajú u administrátora.

## Údaje faktúry vo formáte JSON

Údaje faktúry tak, ako ich program prečítal a ako ste ich skontrolovali, nájdete pri každej faktúre na karte **Údaje faktúry** v časti **Vstup z OCR (JSON)**. Ide o dohodnutý formát medzi čítaním a návrhom, preto sú názvy polí anglické. Rovnaký formát vložíte pri ručnom zadaní tlačidlom **Vložiť JSON**.
