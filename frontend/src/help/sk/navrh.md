# Ako čítať návrh zaúčtovania

Karta **Návrh a zaúčtovanie** ukazuje, čo program navrhuje zadať do účtovného programu. Je usporiadaná ako záložky v TOPSETe: zaúčtovanie záväzku a rozpočet záväzku.

## Hlavička

Navrhnutý **rad**, **číslo dokladu** a **dátum zaúčtovania**, pod nimi značky:

- **Kódy overené** alebo **Chyba v kódoch:** či sú všetky kódy v číselníkoch obce;
- **Bez kontroly** alebo **Na kontrolu:** či si je program istý; pri _Na kontrolu_ je dôvod v časti **Prečo na kontrolu**;
- **Známy dodávateľ** alebo **Nový dodávateľ:** či už obec od dodávateľa účtovala;
- **Istota:** najslabšie z navrhnutých polí.

## Zaúčtovanie záväzku

Riadky s účtom **MD**, účtom **DAL**, sumou a popisom.

## Rozpočet záväzku

Riadky s rozpočtovou položkou rozpísanou na päť častí (EK, zdroj, oddiel, trieda, analytika), so sumou, popisom a prípadne transferom.

## Kopírovanie

Každá hodnota má tlačidlo na kopírovanie. Sumy sa kopírujú v tvare _93,71_. Tlačidlo pri riadku skopíruje celý riadok s hodnotami oddelenými tabulátorom, takže ho do tabuľky vložíte naraz.

## Iná položka

Ak program našiel viac možností, pri riadku rozpočtu je výber **Iná položka**. Výber vymení celý riadok: položku, účty, transfer aj popisy. **Pôvodný návrh** vráti, čo program navrhol.

## Prečo práve toto

Pri každom poli je, odkiaľ sa vzalo:

| Zdroj                | Význam                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------ |
| precedens dodávateľa | tak obec tohto dodávateľa zaúčtovala naposledy                                             |
| pravidlo             | z pravidiel alebo účtovacích zvyklostí obce, napríklad účet podľa ekonomickej klasifikácie |
| slovník pojmov       | text faktúry obsahuje pojem, ktorý k položke patrí                                         |
| podobnosť popisu     | text faktúry sa podobá popisu položky v rozpočte                                           |
| rukou na doklade     | z poznámky, ktorú ste napísali na faktúru                                                  |
| počítadlo dokladov   | ďalšie číslo v rade                                                                        |
| faktúra              | priamo z údajov faktúry                                                                    |

Pod tým je istota po poliach, kontroly, ktoré prešli, a upozornenia.

## Čo ďalej

- **Prijať:** návrh je správny.
- **Prijať so zmenou:** ak ste vybrali inú položku.
- **Opraviť a prijať:** otvorí úpravu riadkov. Pozri [Opravy](opravy).
- **Navrhnúť znova:** nový návrh s aktuálnymi číselníkmi a pamäťou dodávateľov, napríklad po importe.
- **Zadať ručne:** keď program nenavrhol žiadny riadok.

Pred zaúčtovaním program ukáže, aké číslo doklad dostane a či sa posunú čísla iných dokladov; **Zaúčtovať** to potvrdí. Pozri [Číselné rady](ciselne-rady). **Ďalšia faktúra** potom otvorí ďalšiu faktúru na spracovanie.
