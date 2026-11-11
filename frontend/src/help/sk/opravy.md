# Opravy, ručné zadanie a zrušenie zaúčtovania

Návrh, ktorý nesedí, opravíte pred zaúčtovaním. Oprava sa stane vzorom pre ďalšie faktúry toho istého dodávateľa: nabudúce program navrhne opravené zaúčtovanie.

## Opraviť a prijať

Na karte **Návrh a zaúčtovanie** otvorí **Opraviť a prijať** úpravu riadkov:

- **rozpočtovú položku**, účty **MD** a **DAL** a **transfer** vyberáte len z číselníkov obce; začnite písať kód alebo názov;
- po výbere položky program doplní účty, transfer a popisy podľa pravidiel alebo podľa predchádzajúcej faktúry dodávateľa; môžete ich zmeniť;
- riadky môžete **pridať** a **odstrániť**, napríklad keď faktúru treba rozdeliť medzi obecný úrad a materskú školu;
- pod riadkami vidíte, či dávajú spolu sumu faktúry; rozdiel len upozorní, kód mimo číselníkov uloženie nedovolí;
- do **Poznámky k oprave** môžete napísať, prečo ste opravovali.

**Uložiť opravu** pokračuje zaúčtovaním.

Chybný údaj faktúry (suma, dátum, dodávateľ) neopravujte v riadkoch, ale na karte **Kontrola údajov**; po potvrdení program navrhne znova. Pozri [Kontrola údajov](kontrola-udajov).

## Zadať ručne

Ak program nenavrhol žiadny riadok, napríklad pri dobropise alebo pri nákupe, pre ktorý nemá pravidlo, ponúkne **Zadať ručne**: rovnakú úpravu riadkov, len prázdnu.

Faktúru bez súboru zadáte cez **Nová faktúra** a **Zadať ručne**: formulár má rovnaké polia ako kontrola údajov. Údaje faktúry vo formáte JSON doň vložíte tlačidlom **Vložiť JSON**.

## Zrušiť zaúčtovanie

Zaúčtovanú faktúru, ktorá ešte nie je exportovaná ani uhradená, vrátite tlačidlom **Zrušiť zaúčtovanie**:

- faktúra sa vráti na kontrolu a navrhne sa znova;
- jej zaúčtovanie sa z pamäte dodávateľa odstráni;
- číslo dokladu sa uvoľní, ak je v rade posledné; inak ostane tejto faktúre.

## Vyradiť

Faktúru, ktorá do účtovníctva nepatrí (omyl, iný doklad ako faktúra), vyradíte tlačidlom **Vyradiť**, aj s dôvodom. Vyradiť sa dá len nezaúčtovaná faktúra a vyradenie sa nedá vrátiť.

## História

Karta **História** zapisuje každý krok faktúry: kto a kedy ju nahral, potvrdil, zaúčtoval, prečísloval, exportoval, označil ako uhradenú alebo vyradil, aj s dôvodom, ak bol zadaný. Ak za používateľa pracoval administrátor, je tam uvedené „administrátor ako používateľ“.
