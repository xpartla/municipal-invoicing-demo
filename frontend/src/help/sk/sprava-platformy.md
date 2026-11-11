# Správa platformy

Pre administrátora. Po prihlásení sa otvorí **Platforma**.

## Platforma

Počty servisných účtov, klientov a používateľov, faktúr nahraných v mesiaci, strán prečítaných OCR, neúspešných úloh, prihlásení za 7 dní a neodoslaných e-mailov. Každý počet vedie na svoju obrazovku.

## Servisné účty

Servisný účet vytvoríte a zrušíte, pridáte a odoberiete jeho pracovníkov a priradíte mu klientov alebo ich odoberiete. Klient má najviac jeden servisný účet. Po zrušení servisného účtu jeho klienti ostanú bez servisného účtu a pracovníci stratia prístup.

## Používatelia

Všetko, čo servisný účet (pozri [Klienti, kopírovanie a šablóny](klienti)), u všetkých klientov, a navyše pri účtoch:

- **Zablokovať** a **Odblokovať**; zablokovaním sa prihlásenia účtu ukončia;
- **Odhlásiť všade**;
- **Zmazať** a **Obnoviť**;
- **Vymazať natrvalo**: meno, e-maily a prístupy sa odstránia a nedajú sa obnoviť; v audite a pri faktúrach ostane len identifikátor účtu;
- **Prihlásiť sa ako**.

## Prihlásiť sa ako

Na overenie problému sa môžete prihlásiť ako iný používateľ, nie však ako administrátor. Zadáte dôvod, napríklad číslo hlásenia. Vidíte presne to, čo používateľ, a môžete za neho pracovať. Hore je pruh s jeho menom, dôvodom a tlačidlom **Ukončiť**. Každá akcia sa zapíše do auditu s vaším menom ako „administrátor ako používateľ“. Prihlásenie skončí najneskôr po 60 minútach.

## Audit

Záznam každej zmeny a bezpečnostnej udalosti: prihlásení, zmien hesla, importov, zaúčtovaní a ďalších. Filtrovať môžete podľa toho, kto akciu urobil, klienta, akcie (celej, alebo jej začiatku s bodkou, napríklad _invoice._) a obdobia. Záznamy auditu sa nedajú zmeniť ani zmazať.

## Úlohy

Dlhšie operácie bežia na pozadí ako úlohy: čítanie dokladov, importy, kopírovanie klientov, exporty. Vidíte ich stav, pokusy a poslednú chybu. Neúspešnú úlohu môžete **Spustiť znova**, čakajúcu **Zrušiť**.

Na tejto stránke je aj **Export údajov klienta**: súbor ZIP so všetkými údajmi jedného klienta vo formáte JSON (aj jeho používateľov bez hesiel a záznamy auditu) a s jeho súbormi, napríklad pre žiadosť o prístup k osobným údajom. Export sa zapíše do auditu a stiahnete si ho z tabuľky úloh.

## Odoslané e-maily

V tejto verzii program e-maily neodosiela. Pozvánky, odkazy na heslo a potvrdenia e-mailu čakajú tu a odkazy v nich fungujú.

## Vyhodnotenie

Návrhy programu porovnané s očakávaným zaúčtovaním vymyslených faktúr: koľko je správnych, koľko ide na kontrolu a koľko je chybných bez upozornenia, po dodávateľoch aj po jednotlivých prípadoch. Slúži na sledovanie kvality návrhu pri zmenách programu.
