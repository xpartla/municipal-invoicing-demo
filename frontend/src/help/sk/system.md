# Systém: parametre, zvyklosti a kontrola znalostí

**Systém** má štyri záložky: **Parametre**, **Účtovacie zvyklosti**, **Číselné rady** a **Kontrola znalostí**. Všetko v nich platí pre jeden rok; rok vyberiete hore.

## Parametre

Nastavenia, ktoré návrh používa pre faktúry roka:

- **Obec je platiteľom DPH**;
- **Predvolený zdroj**, keď faktúru neplatí dotácia, napríklad _41_;
- **Predvolená rada** dodávateľských faktúr, napríklad _FD_;
- **Účet záväzku (DAL)**, napríklad _321 000_;
- **Rada školskej jedálne** a **Účet záväzku školskej jedálne**, napríklad _FDŠJ_ a _321 080_.

Kým parametre roka nie sú uložené, program pre faktúry roka nenavrhuje.

## Účtovacie zvyklosti

Vlastné pravidlá obce pre návrh:

- **Analytické účty** ku každému syntetickému účtu, zvlášť na strane MD a DAL. Pravidlá sa skúšajú v poradí a prvé, ktorého podmienky platia všetky, určí analytický účet. Podmienky sú **Pojmy** (napríklad _telecom_), **Funkcia** (oddiel a trieda, napríklad _09 601_), **EK začína** (napríklad _632_), **Zdroj** a **Slová** z faktúry (hviezdička nahrádza koncovku, napríklad _chodnik\*_). Ak neplatí žiadne pravidlo, použije sa predvolený analytický účet. Ak pravidlo uvádza účet, ktorý v účtovom rozvrhu nie je, návrh použije analytiku 000 alebo jediný analytický účet syntetického účtu; inak pošle faktúru na kontrolu.
- **Školská jedáleň:** potraviny pre jedáleň idú na vlastnú položku a vlastný účet, v rade a so záväzkom z parametrov.
- **Vlastné pojmy**, ktoré poznajú len pravidlá obce, napríklad jej obecný podnik.
- **Transfery:** zdroje, pri ktorých obec transfer nikdy nečaká.

Zmeny uložíte tlačidlom **Uložiť zvyklosti**. Každé uloženie dostane číslo revízie a zapíše sa do auditu; faktúra si pamätá revíziu, s ktorou bola navrhnutá.

## Číselné rady

Počítadlá, použité čísla a medzery. Pozri [Číselné rady](ciselne-rady).

## Kontrola znalostí

Zoznam toho, čo bráni návrhu alebo čo by program navrhol mimo číselníkov:

- chýbajúce číselníky alebo globálne číselníky roka a chýbajúce všeobecné pravidlá roka;
- zvyklosti, ktoré uvádzajú účet mimo účtového rozvrhu;
- ekonomické klasifikácie z rozpočtu, ktoré nemajú pravidlo pre syntetický účet; ich položky program nenavrhuje (napríklad mzdy);
- predchádzajúce faktúry dodávateľov, ktoré uvádzajú kódy mimo aktívnych číselníkov.

Zistenia sú **chyby**, **upozornenia** a **poznámky** a pri každom je odkaz tam, kde sa dá opraviť. Kontrola bez chýb je jeden z krokov **Začíname** na Domove.
