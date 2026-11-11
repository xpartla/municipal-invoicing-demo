# Číselné rady

Každá zaúčtovaná faktúra dostane číslo dokladu v číselnom rade, napríklad **FD/144/26**: rad FD, poradové číslo 144 a rok 2026. Dodávateľské faktúry sú v rade FD, potraviny pre školskú jedáleň v rade FDŠJ. Rady a tvar ich čísel sú v číselníku **Číselné rady dokladov**, predvolené rady v **Systéme** na záložke **Parametre**.

## Odkiaľ je číslo

- **Číslo napísané rukou** na faktúre je číslo dokladu. Číslo, ktoré zadáte alebo opravíte pri kontrole údajov, platí rovnako.
- Ak číslo chýba, **počítadlo** zaradí faktúru podľa **dátumu dodania**: hneď za poslednú zaúčtovanú faktúru radu dodanú v ten deň alebo skôr.
- **Elektronická faktúra** rukou písané číslo nemá: zaúčtovanie ju zaradí podľa dátumu dodania. Pri kontrole údajov vidíte ďalšie číslo počítadla ako náhľad a môžete zadať vlastné.

## Keď je číslo obsadené

V rade a roku má každé číslo najviac jeden doklad. Ak dve faktúry chcú rovnaké číslo, dostane ho tá, ktorá bola **dodaná skôr**. Druhá dostane nasledujúce číslo a ďalšie zaúčtované faktúry sa posunú o jedno, až po prvé voľné číslo.

Posúvajú sa len zaúčtované faktúry. Exportovaná alebo uhradená faktúra a čísla z importu predchádzajúcich zaúčtovaní sa nemenia nikdy. Ak by posun musel zasiahnuť niektorú z nich, program zaúčtovanie odmietne a napíše prečo; číslo potom zadáte ručne.

Pred zaúčtovaním program ukáže, aké číslo doklad dostane a ktoré doklady sa posunú. Každé prečíslovanie je v histórii faktúry (_Prečíslovaná_) a v audite.

## Číselné rady v Systéme

**Systém**, záložka **Číselné rady**, ukazuje pre každý rad a rok:

- **posledné použité** a **ďalšie** číslo;
- **použité čísla** a čo ich drží: zaúčtovaná faktúra, číslo ponechané pre faktúru so zrušeným zaúčtovaním, alebo číslo z importu či z účtovného programu;
- **medzery:** čísla, ktoré zatiaľ nemá žiadny doklad.

Kým sa počítadlo nesynchronizuje s účtovným programom, jeho stav upravíte tlačidlom **Upraviť počítadlo**, napríklad na začiatku používania programu alebo nového roka. Počítadlo nemôže ísť pod najvyššie použité číslo a každá zmena sa zapíše do auditu. Číselné rady roka vidíte aj na **Domove**.

Rady sú na každý rok osobitne a nový rok začína od nuly, kým počítadlo nenastavíte. Pozri [Prechod na nový rok](prechod-na-novy-rok).
