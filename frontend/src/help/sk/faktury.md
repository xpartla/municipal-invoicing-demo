# Zoznam faktúr

Stránka **Faktúry** ukazuje všetky faktúry klienta. Kliknutím na faktúru otvoríte jej detail.

## Stavy

| Stav             | Význam                                                                        |
| ---------------- | ----------------------------------------------------------------------------- |
| Nahraná, Číta sa | súbor sa práve číta                                                           |
| Neprečítaná      | súbor sa nepodarilo prečítať; prečítajte ho znova alebo faktúru zadajte ručne |
| Prečítaná        | čaká na kontrolu údajov                                                       |
| Skontrolovaná    | údaje sú potvrdené, ale návrh nie je, napríklad chýbajú číselníky roka        |
| Na kontrolu      | návrh treba skontrolovať; dôvod je pri návrhu                                 |
| Pripravená       | návrh je bez výhrad a čaká na prijatie                                        |
| Zaúčtovaná       | má číslo dokladu a je vzorom pre dodávateľa                                   |
| Exportovaná      | bola v exporte do súboru                                                      |
| Uhradená         | je označená ako zaplatená                                                     |
| Vyradená         | do účtovníctva nepatrí                                                        |
| Duplicitná       | rovnaký súbor bol nahraný už predtým                                          |

## Stĺpce a zoradenie

Tlačidlo **Stĺpce** vyberie, ktoré stĺpce vidíte; prehliadač si výber zapamätá. Kliknutím na hlavičku stĺpca faktúry zoradíte, ďalším kliknutím opačne.

## Filtre

- **Hľadať:** dodávateľ, číslo faktúry, VS alebo číslo dokladu.
- **Dodávateľ** (názov alebo IČO), **Stav** (aj viac naraz), **Rad**, **Zdroj** (sken, PDF, e-faktúra, ručné zadanie), **Kontrola** (na kontrolu alebo bez kontroly) a **Len mnou nahrané**.
- V **Ďalších filtroch**: dátumy od–do (vystavená, splatná, zaúčtovaná, nahraná, zaúčtovaná v aplikácii, exportovaná, uhradená), suma od–do, **Položka alebo EK** (napríklad _632_ alebo _632005 41_), **MD** a **DAL**.

_Zaúčtovaná_ je dátum zaúčtovania na doklade; _zaúčtovaná v aplikácii_ je deň, keď ste faktúru zaúčtovali v programe. Podľa neho počíta Domov.

Filtre sú v adrese stránky: filtrovaný zoznam si uložte medzi obľúbené alebo pošlite odkaz kolegovi. **Zrušiť filtre** ich zruší. Ukazovatele na Domove otvárajú zoznam už s filtrom.

## Hromadné akcie

Zaškrtnite faktúry, alebo všetky na strane, a vyberte:

- **Exportovať vybrané:** pozri [Export do TOPSETu a úhrady](export-do-topsetu);
- **Označiť ako uhradené** s dátumom úhrady: len zaúčtované a exportované faktúry; úhrada sa nedá vrátiť;
- **Navrhnúť znova:** nový návrh pre nezaúčtované faktúry, napríklad po importe číselníkov;
- **Vyradiť** nezaúčtované faktúry; vyradenie sa nedá vrátiť.

Po akcii program napíše, koľko faktúr sa spracovalo a ktoré nie a prečo. Tlačidlo **Exportovať** bez výberu exportuje faktúry podľa filtrov.
