# Kontrola údajov

Pred návrhom zaúčtovania overíte, či program faktúru prečítal správne. Robí sa to na karte **Kontrola údajov**: vľavo je doklad, vpravo prečítané polia.

## Doklad

Doklad môžete priblížiť, oddialiť a posúvať. Keď kliknete do poľa, na doklade sa zvýrazní miesto, odkiaľ sa hodnota prečítala. Pri elektronickej faktúre je namiesto skenu jej zobrazenie; pri ISDOC v PDF aj strany PDF a samotné XML.

## Poradie polí

1. **Rukou na doklade:** dátum zaúčtovania a poradové číslo dokladu, nad nimi zväčšený výrez poznámky a pod nimi návrhy.
2. **Dodávateľ:** názov, IČO, DIČ, IČ DPH, IBAN a adresa.
3. **Faktúra:** číslo faktúry, variabilný symbol, dátum vystavenia, dodania a splatnosti a druh dokladu (faktúra alebo dobropis).
4. **Sumy:** bez DPH, DPH a spolu na úhradu.
5. **Položky** faktúry s popisom a sumou.
6. **Poznámky na faktúre**, napríklad obdobie alebo číslo zmluvy.

## Farby

- **Žltá:** hodnota sa prečítala s nízkou istotou alebo neprešla kontrolou, napríklad kontrolnou číslicou IČO či IBAN, súčtom súm alebo poradím dátumov. Dôvod je pri poli.
- **Červená:** povinné pole je prázdne.

Ani pole bez farby nemusí byť správne. Porovnajte s dokladom aspoň sumu, IČO a variabilný symbol.

Nad poliami môžu byť upozornenia z čítania: faktúra je adresovaná inému odberateľovi, názov dodávateľa je doplnený z predchádzajúcich faktúr, faktúra neuvádza IČO, IBAN, variabilný symbol alebo splatnosť.

## Rukou písané údaje

Dátum zaúčtovania a číslo dokladu potvrdzujete vždy, aj keď ich program prečítal. Ak číslo nezadáte, doplní ho pri zaúčtovaní počítadlo podľa dátumu dodania. Pozri [Číselné rady](ciselne-rady).

Elektronická faktúra poznámku nemá: číslo pridelí zaúčtovanie a ako dátum zaúčtovania program navrhne deň nahratia.

Dátum dodania je povinný, lebo podľa neho sa doklady radia. Ak na faktúre nie je, označte, že platí dátum vystavenia.

## Klávesnica

- **Enter** potvrdí pole a prejde na ďalšie pochybné; v prázdnom rukou písanom poli vezme prvý návrh.
- **Tab** preskočí na ďalšie pochybné pole.

## Potvrdenie

**Potvrdiť** údaje uloží a program hneď navrhne zaúčtovanie; uvidíte ho na karte **Návrh a zaúčtovanie**. Ak ste prišli z Novej faktúry, **Ďalšia na kontrolu** otvorí ďalšiu prečítanú faktúru.

Kým faktúra nie je zaúčtovaná, údaje môžete opraviť a potvrdiť znova; program potom navrhne znova.

## Keď sa súbor nepodarí prečítať

Faktúra má stav _Neprečítaná_ a pri nej je dôvod. Môžete ju **Prečítať znova** alebo údaje zadať ručne; súbor ostane pri faktúre.
