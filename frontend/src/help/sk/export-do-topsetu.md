# Export do TOPSETu a úhrady

Zaúčtované faktúry prenesiete do účtovného programu. Priamy import do TOPSETu zatiaľ nie je, lebo jeho formát nepoznáme; program preto ponúka kopírovanie a export do súboru.

## Kopírovanie z návrhu

Pri jednej faktúre skopírujete hodnoty z karty **Návrh a zaúčtovanie** tlačidlom pri každej hodnote alebo celý riadok naraz a vložíte ich do TOPSETu. Pozri [Ako čítať návrh zaúčtovania](navrh).

## Export do súboru

1. Na stránke **Faktúry** vyberte faktúry alebo nastavte filtre, napríklad _Stav: Zaúčtovaná_.
2. Kliknite na **Exportovať** (faktúry podľa filtrov) alebo **Exportovať vybrané**. V **Importy a exporty** je aj **Nový export**: zaúčtované faktúry, ktoré ešte neboli exportované.
3. Vyberte formát: **CSV pre Excel** (bodkočiarka a desatinná čiarka, ako ich čaká slovenský Excel) alebo **XLSX**.
4. Program ukáže, koľko faktúr sa exportuje, koľko z nich už exportovaných bolo (export sa zopakuje) a koľko sa vynechá, lebo nie sú zaúčtované.
5. Po **Exportovať** si súbor stiahnite.

Súbor má jeden riadok na každý riadok rozpočtu faktúry:

- hlavičku dokladu: rad, číslo, dátum zaúčtovania, dodávateľa a jeho IČO, číslo faktúry, VS, dátum vystavenia a splatnosti a sumu;
- zaúčtovanie: MD, DAL, sumu a popis;
- rozpočet: položku a jej päť častí, transfer a popis.

Exportované faktúry dostanú stav **Exportovaná**. Exporty aj s ich súbormi nájdete v **Importy a exporty** a v **Úložisku**. Hodnotu, ktorú by Excel čítal ako vzorec, program upraví tak, aby sa nevykonala.

## Úhrada

Keď obec faktúru zaplatí, označte ju **Označiť ako uhradené** a zadajte dátum úhrady: jednu faktúru na jej stránke, viac naraz v zozname faktúr. Uhradiť sa dá zaúčtovaná alebo exportovaná faktúra. Úhrada sa nedá vrátiť a uhradená faktúra sa už neprečísluje.
