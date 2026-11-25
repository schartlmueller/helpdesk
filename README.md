# Helpdesk

Webbasiertes Ticketsystem für den IT-Support mit Wissensbasis, Zeiterfassung und
Projekt-Management. Läuft mit Docker Compose (Django + PostgreSQL).

## Start

```bash
cp .env.example .env      # Passwörter und SECRET_KEY anpassen
docker compose up -d --build
docker compose exec web python manage.py test
```

Danach ist das System unter http://localhost:8000 erreichbar.
Erste Anmeldung mit `ADMIN_USER` / `ADMIN_PASSWORD` aus der `.env`
(ohne `.env`: `admin` / `admin` – bitte sofort ändern).

Der dritte Befehl führt die mitgelieferten Tests aus. Sie decken den Kernablauf
aller Bereiche ab und sind der schnellste Weg, Fehler zu finden.

Falls eine frühere Fassung schon einmal gestartet wurde: Die Datenbankstruktur
wurde neu aufgebaut. Vorher mit `docker compose down -v` die alten Daten entfernen.

### Dienste

| Dienst | Aufgabe |
|---|---|
| `web` | die Anwendung |
| `db` | PostgreSQL |
| `worker` | E-Mail-Abruf, Eskalation, wiederkehrende Tickets, Wiedervorlagen, Erinnern und automatisches Schließen, Stoppen vergessener Uhren, Feiertage, Löschfristen |
| `backup` | tägliche Sicherung nach `./backups` |
| `clamav` | Virenscanner, nur bei Bedarf (siehe unten) |

## Benutzer und Rollen

Benutzer werden unter **Verwaltung → Benutzer** angelegt, entstehen automatisch
beim ersten Login über LDAP/SSO oder beim ersten Ticket per E-Mail.

| Rolle | Einstellung | Darf |
|---|---|---|
| Melder | normaler Benutzer | eigene Tickets anlegen und verfolgen, Wissensbasis lesen und bewerten |
| Ansprechpartner | Melder mit Haken „Ansprechpartner“ in seiner Organisation | zusätzlich alle Tickets der eigenen Organisation sehen und beantworten |
| Bearbeiter | Haken bei „Mitarbeiter-Status“ | alle Tickets, Wissensbasis pflegen, Projekte, Zeiten, Statistik |
| Administrator | Haken bei „Superuser-Status“ | zusätzlich alles unter „Verwaltung“ |

In der Verwaltung werden auch gepflegt: **Teams**, **Kategorien** (mit zuständigem
Team), **Textbausteine**, **Anfrage-Formulare**, **Feiertage**, **Zeiteinträge** und
**API-Schlüssel**. Ein Bearbeiter ohne
Superuser-Status sieht dort nur, wofür er Berechtigungen bekommen hat.

**Passwörter:** Über „Passwort vergessen oder noch keines gesetzt?“ auf der
Anmeldeseite bekommt jeder mit hinterlegter E-Mail-Adresse einen Link zum Setzen
eines Passworts, auch Personen, die bisher nur per E-Mail Tickets geschickt haben.
Ein Klick auf den eigenen Namen oben rechts führt zu „Passwort ändern“.
Nach 5 falschen Anmeldeversuchen ist ein Benutzername 15 Minuten gesperrt
(`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCK_MINUTES`).

## Übersicht

Die Startseite zeigt Bearbeitern oben den Handlungsbedarf (offen, nicht zugewiesen,
ohne Antwort, überfällig, Entwürfe) und darunter die Entwicklung der letzten 14,
30 oder 90 Tage, wahlweise nur für eine Art von Tickets:

- **Kacheln:** heute neu angelegt, neu im Zeitraum, erledigt im Zeitraum und der
  aktuelle Bestand mit Veränderung gegenüber dem Beginn des Zeitraums.
- **Offene Tickets (Burn-down):** eine Linie mit dem Bestand am Ende jedes Tages.
  Fällt sie, wird mehr erledigt als neu angelegt.
- **Neu und erledigt:** Säulenpaare je Tag, bei 90 Tagen je Kalenderwoche.
- Mit der Maus (oder per Antippen) zeigt jedes Diagramm die Werte des Tages; die
  Zahlen stehen zusätzlich als Tabelle bereit.
- **Offen nach Art** und die **zuletzt angelegten Tickets**.

Als erledigt zählt ein Ticket ab „Gelöst“; wird es wieder geöffnet, zählt es
wieder zum Bestand. Zusammengeführte Tickets werden nicht mitgezählt.

### Art des Tickets

Jedes Ticket kann als **Fehler**, **Erweiterung** oder **Nice to have** eingestuft
werden: beim Anlegen (freiwillig), später im Ticket unter „Bearbeiten und planen“
oder über die Schnittstelle (`kind`: `bug`, `feature`, `nice`). Die Ticketliste,
die Übersicht und die Statistik lassen sich danach filtern bzw. auswerten.
Tickets per E-Mail kommen zunächst als „nicht eingestuft“ an.

## Erscheinungsbild

Die Oberfläche hat eine Seitenleiste, eine Kopfzeile mit Ticketsuche und ein
helles sowie ein dunkles Design (Umschalter oben rechts, sonst nach
Systemeinstellung). Die Schrift IBM Plex Sans liegt im Projekt; der Browser ruft
nichts von außen ab.

**Austauschbares Design:** Drei Designs sind angelegt: `helpdesk` (neutral),
`ebner` (ebner.ticket) und `forstenlechner` (forstenlechner.ticket). Sie
unterscheiden sich in Name, Farben und optional im Logo.

- **Grundeinstellung:** `BRAND=ebner` oder `BRAND=forstenlechner` in der `.env`,
  danach `docker compose up -d`.
- **Je Adresse ein Design:** Läuft dieselbe Installation unter zwei Namen, ordnet
  `BRAND_HOSTS=ebner.ticket=ebner,forstenlechner.ticket=forstenlechner` jedem
  Hostnamen sein Design zu. Daten und Benutzer bleiben dabei gemeinsam.
- **Vorschau:** Bearbeiter hängen `?design=ebner` oder `?design=forstenlechner` an
  eine Adresse, um ein Design anzusehen; `?design=aus` beendet die Vorschau.
  Sie gilt nur für die eigene Sitzung.
- **Farben anpassen:** Jedes Design ist eine kleine Datei
  `static/css/brand-<name>.css` mit einer Handvoll Farbwerten, jeweils für hell
  und dunkel. Die mitgelieferten Werte sind Platzhalter und keine geprüften
  Firmenfarben.
- **Logo:** Eine Datei `static/brand/<name>/logo.svg` oder `logo.png` ersetzt den
  Schriftzug in der Seitenleiste und auf der Anmeldeseite; Hinweise stehen in
  `static/brand/LIESMICH.txt`.
- **Weiteres Design:** Eintrag in `core/brands.py` ergänzen und eine Farbdatei
  nach dem Muster der vorhandenen anlegen.

## Organisationen (Kunden oder Abteilungen)

Unter **Mehr → Organisationen** legen Bearbeiter Kunden oder Abteilungen an und
ordnen ihnen Personen zu. Ein IT-Team betreut so mehrere Kunden in einem System.

- Jede Person gehört zu höchstens einer Organisation. Ihre Tickets gehören
  automatisch dazu (im Ticket änderbar).
- **Automatische Zuordnung:** Trägt eine Organisation E-Mail-Domains ein, werden
  neue Melder mit passender Adresse beim ersten Ticket zugeordnet.
- **Sichtbarkeit:** Melder sehen nur ihre eigenen Tickets. **Ansprechpartner**
  sehen alle Tickets ihrer Organisation, im Browser, per E-Mail-Antwort und über
  die Schnittstelle. Tickets anderer Organisationen sieht niemand außer den Bearbeitern.
- **Wissensartikel** sind für alle lesbar, außer bei „Nur sichtbar für“ ist eine
  Organisation gewählt. Bei Entwürfen aus Tickets einer Organisation weist die
  Prüfseite darauf hin; ohne Auswahl ist der Artikel für alle Kunden sichtbar.
- **Störungsmeldungen** lassen sich auf eine Organisation beschränken.
- Ticketliste, Statistik und Leistungsnachweis lassen sich je Organisation auswerten.
- Bearbeiter, Teams, Kategorien und Einstellungen gelten für alle Organisationen
  gemeinsam. Vollständig getrennte Mandanten mit eigenen Bearbeitern gibt es nicht.

## Tickets

- **Anlegen:** im Browser, per E-Mail oder über die Schnittstelle. Bearbeiter können
  ein Ticket im Namen einer anderen Person erfassen (bestehendes Konto wählen oder
  E-Mail-Adresse eingeben), etwa nach einem Anruf.
- **Benachrichtigungen an Bearbeiter:** bei neuem Ticket, bei Zuweisung, bei Antwort
  des Melders und bei überschrittener Zielzeit. Empfänger ist der zugewiesene
  Bearbeiter, sonst das Team, sonst alle Bearbeiter.
- **In Kopie:** weitere E-Mail-Adressen am Ticket erhalten alle Antworten und dürfen
  per E-Mail mitantworten.
- **Teams:** Eine Kategorie kann einem Team gehören; neue Tickets landen dann
  automatisch dort. Die Ticketliste lässt sich nach Team filtern.
- **Textbausteine:** Auswahl über dem Antwortfeld, Pflege in der Verwaltung.
- **Zusammenführen:** Ein doppeltes Ticket wandert samt Antworten, Anhängen und
  Zeiten in ein anderes und wird geschlossen.
- **Änderungsverlauf:** Jede Änderung an Status, Priorität, Bearbeiter usw. wird mit
  Benutzer und Zeitpunkt protokolliert (im Ticket unter „Änderungsverlauf“).
- **Interne Notizen**, die der Melder nicht sieht.
- **Anfrage-Formulare:** Vorlagen wie „Neuer Mitarbeiter“ mit festen Feldern
  (Text, Auswahl, Datum, Zahl, Ja/Nein) und Pflichtfeldern. Sie erscheinen über
  dem normalen Ticketformular; aus den Angaben entsteht ein Ticket mit passender
  Kategorie, Priorität und passendem Team. Pflege unter Verwaltung → Anfrage-Formulare.
- **Verknüpfte Tickets:** Haupt- und Untertickets sowie „hängt zusammen mit“.
  Beim Lösen eines Haupttickets lassen sich alle offenen Untertickets mit
  derselben Lösung lösen; jeder Melder wird benachrichtigt. Das ist für Störungen
  mit vielen Betroffenen gedacht. Verknüpfungen sehen nur Bearbeiter.
- **Störungsmeldungen:** Unter **Mehr → Störungsmeldungen** legt man ein Banner an,
  das allen oben auf jeder Seite erscheint, bis es beendet wird oder abläuft.
- **Blättern:** Ticketliste und Wissensbasis zeigen 50 bzw. 30 Einträge je Seite.

### Warten, Wiedervorlage und automatisches Schließen

- **Zwei Warte-Status:** „Wartet auf Rückmeldung“ (der Melder ist am Zug) und
  „Wartet auf Dritte“ (Lieferant, Provider, Softwareanbieter).
- **Zielzeit pausiert:** In beiden Status läuft die Lösungszeit nicht. Beim
  Weiterarbeiten verschiebt sie sich um die gewartete Arbeitszeit; wartende
  Tickets gelten nicht als überfällig und lösen keine Eskalation aus.
- **Wiedervorlage:** Im Ticket unter „Bearbeiten und planen“ ein Datum bei
  „Wiedervorlage am“ setzen. An diesem Tag bekommt der Bearbeiter eine E-Mail und
  das Ticket steht wieder auf „In Bearbeitung“. Die Ticketliste hat dafür den
  Filter „Mit Wiedervorlage“.
- **Erinnerung an den Melder:** Wartet ein Ticket 3 Tage auf Rückmeldung, wird der
  Melder einmal erinnert; nach 10 Tagen ohne Antwort wird es geschlossen und der
  Melder informiert. Antwortet der Melder, geht es sofort wieder in Bearbeitung.
- **Gelöste Tickets** werden 7 Tage nach der Lösung automatisch geschlossen; die
  Lösungs-E-Mail kündigt das an. Wiedereröffnen bleibt jederzeit möglich.
- Die Fristen stehen in der `.env` (`WAITING_REMINDER_DAYS`, `WAITING_CLOSE_DAYS`,
  `AUTO_CLOSE_DAYS`; 0 schaltet die jeweilige Automatik aus). „Wartet auf Dritte“
  wird nie automatisch geschlossen.

### Checklisten

Jedes Ticket kann eine Checkliste mit abhakbaren Punkten haben, sichtbar für
Bearbeiter. Zu jedem erledigten Punkt steht, wer ihn wann abgehakt hat.

- **Vorlagen** wie „Eintritt Mitarbeiter“ (Konto, Handy, Schlüssel, Lizenzen,
  Fahrzeug) pflegt man unter Verwaltung → Checklisten-Vorlagen, ein Punkt pro Zeile.
- Eine Vorlage lässt sich im Ticket einfügen oder einem **Anfrage-Formular** bzw.
  einem **wiederkehrenden Ticket** hinterlegen; dann hängt sie automatisch an
  jedem so angelegten Ticket.
- Beim Lösen weist das Ticket auf offene Punkte hin, verhindert das Lösen aber nicht.

### Suche

Die Ticketsuche durchsucht Betreff, Beschreibung, Lösung, alle Antworten und die
Namen der Anhänge. Bei mehreren Wörtern müssen alle vorkommen; eine Zahl findet
auch die Ticketnummer. Interne Notizen durchsuchen nur Bearbeiter. Die
Schnittstelle (`?q=`) verwendet dieselbe Suche.

### Zielzeiten und Eskalation

Zielzeiten zählen standardmäßig nur innerhalb der Geschäftszeiten
(Mo–Fr 08:00–17:00): Dringend 4, Hoch 8, Normal 24, Niedrig 56 Arbeitsstunden.
Anpassbar über `BUSINESS_OPEN`, `BUSINESS_CLOSE`, `BUSINESS_DAYS` und
`SLA_HOURS_...`; mit `SLA_BUSINESS_HOURS=0` wird rund um die Uhr gerechnet.

Es gibt zwei Zielzeiten je Ticket:

| Priorität | Erste Antwort | Lösung |
|---|---|---|
| Dringend | 1 h | 4 h |
| Hoch | 2 h | 8 h |
| Normal | 8 h | 24 h |
| Niedrig | 16 h | 56 h |

Als erste Antwort zählt die erste für den Melder sichtbare Antwort eines
Bearbeiters (Browser, E-Mail oder Schnittstelle); interne Notizen zählen nicht.
Die Reaktionszeiten sind über `SLA_RESPONSE_HOURS_...` einstellbar.

**Feiertage** zählen nicht mit. Beim ersten Start werden die gesetzlichen
Feiertage für Österreich eingetragen (`HOLIDAY_COUNTRY=AT`, alternativ `DE` für die
bundesweiten deutschen Feiertage oder leer), jeweils für das laufende und das
nächste Jahr. Regionale Feiertage und Betriebsurlaub ergänzt man unter
Verwaltung → Feiertage. Bereits berechnete Zielzeiten ändern sich dadurch nicht.

Ist eine Zielzeit überschritten, verschickt der Dienst `worker` einmalig einen
Hinweis an Bearbeiter und Team: „Noch keine Antwort“ bei der Reaktionszeit,
„ÜBERFÄLLIG“ bei der Lösungszeit.

## Vom Ticket zum Wissensartikel

1. Beim Anlegen eines Tickets werden schon beim Tippen des Betreffs passende
   veröffentlichte Artikel vorgeschlagen.
2. Der Bearbeiter sieht im Ticket ebenfalls passende Artikel und kann deren Lösung
   mit einem Klick übernehmen.
3. Über **Ticket lösen** trägt er die Lösung ein. Der Melder erhält sie als Antwort
   im Ticket und per E-Mail.
4. Aus Betreff, Problembeschreibung und Lösung entsteht automatisch ein Entwurf in
   der Wissensbasis (abwählbar per Haken).
5. Unter **Entwürfe** prüft ein Bearbeiter den Text. Gibt es schon ähnliche
   veröffentlichte Artikel, weist die Seite darauf hin. Nach der Freigabe ist der
   Artikel für alle sichtbar und durchsuchbar.

### Wissensbasis

- **Formatierung** mit Markdown (fett, Überschriften, Listen, nummerierte Schritte,
  Tabellen). Eingebettetes HTML wird bereinigt.
- **Bilder und Dateien** lassen sich beim Bearbeiten hochladen und per kopierbarer
  Zeile in den Text einsetzen.
- **Suche:** Volltextsuche von PostgreSQL mit deutscher Wortstammbildung, ergänzt
  um eine Teilwortsuche. Treffer im Titel zählen am meisten.
- **Rückmeldung:** Leser können „Hat geholfen: Ja/Nein“ angeben; die Zahlen sehen
  Bearbeiter im Artikel und in der Statistik.

## Zeiterfassung und Planung

- **Start:** Die Uhr beginnt, sobald ein Bearbeiter im Ticket auf „Bearbeitung starten“
  klickt, den Status auf „In Bearbeitung“ setzt oder einem neuen Ticket zum ersten
  Mal antwortet.
- **Pause:** „Pause“ hält die eigene Uhr an, „Fortsetzen“ startet sie wieder.
  Jeder Abschnitt wird einzeln mit Beginn und Ende gespeichert.
- **Ende:** Beim Lösen des Tickets wird die Uhr automatisch beendet, ebenso beim
  Wechsel auf „Wartet auf Rückmeldung“, „Wartet auf Dritte“ oder „Geschlossen“.
- Pro Bearbeiter läuft immer nur eine Uhr. Wer ein anderes Ticket oder eine
  Projektaufgabe startet, pausiert damit die vorige. Die laufende Uhr steht oben
  in der Kopfzeile.
- **Nachtragen:** im Ticket und in der Projektaufgabe unter „Zeit nachtragen“
  (Datum, Beginn, Dauer).
- **Vergessene Uhren** werden nach `TIMER_MAX_HOURS` (Standard 10) Stunden
  automatisch gestoppt und entsprechend gekennzeichnet.
- **Planung:** Im Ticket unter „Bearbeiten und planen“ lassen sich ein Termin
  und der geplante Aufwand in Minuten setzen.
- Die Seite **Zeiten** zeigt die gebuchte Zeit je Bearbeiter für einen Zeitraum
  (auch als CSV für Excel) sowie alle offenen Tickets nach Termin, mit gebuchter
  und geplanter Zeit.

## Leistungsnachweis

Unter **Mehr → Leistungsnachweis** wählt man Organisation und Zeitraum (Standard:
der vergangene Monat) und erhält alle gebuchten Zeiten, gruppiert nach Ticket bzw.
Projektaufgabe, mit Datum, Bearbeiter, Uhrzeit, Notiz und Summe. Die Auswertung
lässt sich als PDF herunterladen. Enthalten sind beendete Zeiteinträge an Tickets
der Organisation und an Aufgaben von Projekten, die der Organisation zugeordnet
sind. Stundensätze und Beträge enthält der Nachweis nicht.

## Wochenpool

Der Wochenpool ist der Vorrat an Tickets, die in einer Woche erledigt werden
sollen. Bei der wöchentlichen Planung wird er gefüllt; danach nimmt sich jeder
Bearbeiter selbst, was er erledigt.

- **Planen:** Auf der Seite **Wochenpool** unten unter „Planung“ die offenen Tickets
  ankreuzen und in den Pool der Woche legen. Die Liste ist nach Priorität und
  Zielzeit sortiert und lässt sich durchsuchen und nach Art filtern. Alternativ in
  der Wochenplanung Karten in den Bereich „Wochenpool“ ziehen oder im Ticket auf
  „In den Wochenpool dieser Woche“ klicken. Mit „Nächste“ plant man die Folgewoche.
- **Zuordnen:** Beim Planen lassen sich die angekreuzten Tickets über „Zuordnen an“
  gleich einem Bearbeiter geben. Später ändert man die Zuordnung direkt am Ticket
  im Pool über die Auswahl mit den Namen; „– frei –“ gibt es wieder für alle frei.
  Der Bearbeiter wird per E-Mail benachrichtigt.
- **Übernehmen:** Nicht zugeordnete Tickets nimmt sich jeder Bearbeiter selbst mit
  „Übernehmen“ oder „und starten“ (startet gleich die Zeiterfassung). Ist jemand
  schneller, bekommt der Zweite einen Hinweis.
- **Anzeige:** Die Tickets sind nach Bearbeiter gruppiert, die eigenen zuerst, mit
  Anzahl offen und erledigt sowie geplantem Aufwand; daneben steht die Gruppe
  „Nicht zugeordnet“. Mit „Nur meine“ sieht jeder nur seine eigenen Tickets, mit
  „Alle“ das ganze Team. Die Wahl bleibt bis zur nächsten Umstellung erhalten.
- **Stand der Woche:** Kacheln für frei, übernommen und erledigt mit
  Fortschrittsbalken, dazu der geplante Aufwand. Die Übersicht zeigt, wie viele
  Tickets im Pool noch frei sind.
- **Ungeplantes:** Tickets außerhalb des Pools lassen sich wie bisher bearbeiten
  und lösen. Die Pool-Seite zählt sie als „Daneben erledigt“; so sieht man, wie
  viel ungeplante Arbeit in der Woche angefallen ist.
- **Wochenwechsel:** Was am Ende der Woche offen ist, bleibt im alten Pool. Die
  neue Woche zeigt einen Hinweis mit dem Knopf „In diese Woche übernehmen“.
- **Zusammenspiel mit der Wochenplanung:** Pool-Tickets ohne festen Tag stehen dort
  oben im Bereich „Wochenpool“. Wer mag, zieht sie auf einen Tag und Bearbeiter;
  nötig ist das nicht.

## Wochenplanung

Die Seite **Planung** zeigt eine Woche als Raster: eine Zeile je Bearbeiter, eine
Spalte je Arbeitstag.

- **Einplanen:** Tickets aus „Noch nicht geplant“ mit der Maus auf einen Tag und
  Bearbeiter ziehen. Das setzt im Ticket „Geplant für“ und den Bearbeiter; der
  Bearbeiter wird benachrichtigt, die Änderung steht im Verlauf.
- **Umplanen:** Karte auf einen anderen Tag oder Bearbeiter ziehen, oder zurück in
  „Noch nicht geplant“.
- **Auslastung:** Jede Zelle zeigt den geplanten Aufwand gegen die Tageskapazität
  und wird bei Überbuchung rot. Karten ohne geplanten Aufwand zählen nicht mit.
  Daneben steht die an diesem Tag tatsächlich gebuchte Zeit.
- **Kapazität:** Standard 8 Stunden pro Tag, je Bearbeiter einstellbar unter
  „Kapazität und Outlook-Kalender“ (für andere: Verwaltung → Planungsprofile).
- **Abwesenheiten:** Urlaub, Krankheit oder Schulung eintragen; an diesen Tagen ist
  die Kapazität null und die Zelle schraffiert. Dasselbe gilt für alle an Feiertagen.
- **Termin vorbei:** Offene Tickets mit vergangenem Planungstag stehen rechts in
  einer eigenen Liste und lassen sich neu einplanen.
- **Hinweis „nach Zielzeit“:** wenn der geplante Tag nach der Zielzeit des Tickets liegt.
- **Projektaufgaben** erscheinen im Raster, sobald in der Aufgabe „Geplant für“
  gesetzt ist, und lassen sich dann ebenfalls verschieben.
- Filter nach Team und Blättern zwischen den Wochen.

Geplant wird auf Tagesebene, ohne Uhrzeiten.

## Bedienung am Handy

- **Foto aufnehmen:** Beim Anlegen eines Tickets, in Anfrage-Formularen, bei jeder
  Antwort und an Projektaufgaben gibt es neben „Anhänge“ das Feld „Foto aufnehmen“.
  Am Handy öffnet es direkt die Kamera, am Computer die Bildauswahl.
- Auf kleinen Bildschirmen klappt das Menü hinter ☰ ein, Tabellen lassen sich
  seitlich wischen, Schaltflächen und Eingabefelder sind größer.
- **Karten verschieben ohne Maus:** In der Wochenplanung und am Kanban-Board hat
  jede Karte den Knopf ⇄. Karte damit auswählen, dann den Tag bzw. die Spalte
  antippen. Das funktioniert auch am Computer.
- Die Wochenplanung bleibt eine breite Tabelle und ist am Tablet oder Computer
  bequemer als am Handy.

## Wiederkehrende Tickets

Unter **Planung → Wiederkehrende Tickets** legt man Vorlagen an, etwa „Backups
prüfen“ monatlich. Zum Termin legt der Dienst `worker` automatisch ein Ticket an,
weist es zu, benachrichtigt den Bearbeiter und plant es auf den Termin-Tag ein.

- Intervalle: jeden Arbeitstag, wöchentlich, alle zwei Wochen, monatlich,
  vierteljährlich, halbjährlich, jährlich.
- **Vorlauf:** Das Ticket kann einige Tage vor dem Termin angelegt werden.
- Ein Termin am 31. bleibt am Monatsende, auch nach kurzen Monaten.
- War das System zum Termin aus, wird ein Ticket für heute angelegt; weiter
  zurückliegende Termine werden nicht nachgeholt.
- „Jeden Arbeitstag“ überspringt Wochenenden und Feiertage; die anderen Intervalle
  behalten ihren Kalendertag, auch wenn er auf ein Wochenende fällt.

## Outlook-Anbindung

Jeder Bearbeiter hat unter **Planung → Kapazität und Outlook-Kalender** eine
persönliche Kalender-Adresse. Outlook, Google Kalender und Apple Kalender können
sie abonnieren und zeigen dann die geplanten Tickets und Projektaufgaben als
Ganztagestermine mit Aufwand und Link zum Ticket.

- Die Anbindung ist nur lesend: Geplant wird im Helpdesk, der Kalender folgt.
- Outlook holt Änderungen in eigenen Abständen ab, das kann einige Stunden dauern.
- Outlook im Web und Microsoft 365 rufen die Adresse von Microsoft-Servern aus ab;
  dafür muss der Helpdesk aus dem Internet erreichbar und `SITE_URL` richtig
  gesetzt sein. Das klassische Outlook am Arbeitsplatz ruft direkt ab und
  funktioniert auch nur im Firmennetz.
- Die Adresse enthält einen geheimen Schlüssel statt einer Anmeldung. Sie lässt
  sich jederzeit neu erzeugen, die alte wird dann ungültig.

## Projekte

- Aufgaben auf einem Kanban-Board (Karten per Maus verschieben).
- Jede Aufgabe hat eine eigene Seite mit Kommentaren, Anhängen, geplantem Aufwand,
  Planungstag für die Wochenplanung und Zeiterfassung (Start, Pause; bei „Erledigt“ stoppt die Uhr).
- **Meilensteine** mit Termin und Fortschritt; Aufgaben lassen sich zuordnen.
- **Zeitachse** mit Balken je Aufgabe und Markierungen für Meilensteine.
- Tickets lassen sich einem Projekt zuordnen.

## Statistik

Die Seite **Statistik** zeigt für die letzten zwölf Monate: angelegte und gelöste
Tickets, durchschnittliche Lösungsdauer, Anteil eingehaltener Zielzeiten, gebuchte
Zeit, Verteilung nach Kategorie, Priorität und Bearbeiter sowie die meistgelesenen
Wissensartikel mit ihren Bewertungen.

## Dateianhänge und Virenprüfung

Beim Anlegen eines Tickets, bei jeder Antwort und an Projektaufgaben können mehrere
Dateien angehängt werden (Höchstgröße `MAX_UPLOAD_MB`, Standard 20 MB). Abrufbar
sind sie nur nach Anmeldung für den Melder und die Bearbeiter.

Virenprüfung mit ClamAV einschalten:

```bash
# in der .env:  CLAMAV_HOST=clamav
docker compose --profile clamav up -d
```

Der Scanner braucht etwa 2 GB Arbeitsspeicher und beim ersten Start einige
Minuten für die Signaturen. Ist er eingeschaltet, aber nicht erreichbar, werden
Uploads abgelehnt.

## Tickets per E-Mail

Der Dienst `worker` ruft ein IMAP-Postfach ab (Standard: jede Minute), sobald
`IMAP_HOST`, `IMAP_USER` und die Anmeldung in der `.env` gesetzt sind.

- Eine neue E-Mail wird zu einem Ticket, der Absender erhält eine Bestätigung mit
  der Ticketnummer im Betreff. Adressen aus dem Cc-Feld werden „in Kopie“ übernommen.
- Antworten mit `[Ticket #123]` im Betreff werden an das Ticket gehängt, wenn sie
  vom Melder, von einer Adresse in Kopie oder von einem Bearbeiter stammen.
  Der zitierte Verlauf wird abgeschnitten. Ein gelöstes Ticket wird durch die
  Antwort des Melders wieder geöffnet.
- HTML-E-Mails werden in lesbaren Text umgewandelt; das Original hängt als
  `nachricht.html` am Ticket.
- Anhänge werden übernommen und, falls eingeschaltet, auf Viren geprüft.
- Mit `MAIL_ALLOWED_DOMAINS` lässt sich der Eingang auf eigene Domains beschränken.
- Abwesenheitsnotizen, Newsletter und Unzustellbarkeitsmeldungen werden übersprungen.
- E-Mails, die sich nicht verarbeiten lassen, bleiben markiert im Postfach;
  der Grund steht in `docker compose logs worker`.

`DEFAULT_FROM_EMAIL` sollte die Adresse dieses Postfachs sein.
Einmaliger Testabruf: `docker compose exec web python manage.py fetch_mail`

**Microsoft 365:** Statt eines Passworts `IMAP_OAUTH_TENANT`, `IMAP_OAUTH_CLIENT_ID`
und `IMAP_OAUTH_CLIENT_SECRET` setzen (`IMAP_HOST=outlook.office365.com`,
`IMAP_USER` = Postfachadresse). Voraussetzung ist eine App-Registrierung in
Entra ID mit der Anwendungsberechtigung `IMAP.AccessAsApp` (Office 365 Exchange
Online), Administratorzustimmung und ein in Exchange Online registrierter
Dienstprinzipal mit Zugriff auf das Postfach.

## Anmeldung über LDAP oder Single Sign-On

Beides ist optional und wird über die `.env` eingeschaltet (Beispiele in
`.env.example`). Lokale Konten wie der Administrator funktionieren weiterhin.

**LDAP / Active Directory:** aktiv, sobald `LDAP_SERVER_URI` gesetzt ist. Benutzer
melden sich mit ihrem Domänen-Benutzernamen an und werden beim ersten Login
angelegt; Name und E-Mail kommen aus dem Verzeichnis. Mit `LDAP_STAFF_GROUP` und
`LDAP_ADMIN_GROUP` werden die Rollen bei jedem Login aus der Gruppenmitgliedschaft
gesetzt.

**Single Sign-On (OpenID Connect):** aktiv, sobald `OIDC_CLIENT_ID` gesetzt ist,
z. B. für Microsoft Entra ID, Keycloak oder Authentik. Beim Anbieter als
Redirect-URI `<SITE_URL>/oidc/callback/` eintragen. Benutzer werden über ihre
E-Mail-Adresse zugeordnet. Optional setzt `OIDC_STAFF_GROUP` die Bearbeiter-Rolle.

Hinweis: Ein per E-Mail angelegter Benutzer und sein späteres LDAP-Konto sind
zwei getrennte Konten, weil LDAP über den Benutzernamen zuordnet. Bei SSO passiert
das nicht.

## Schnittstelle (API)

JSON über HTTP, Anmeldung mit einem Schlüssel aus **Verwaltung → API-Schlüssel**.
Der Schlüssel handelt mit den Rechten seines Benutzers.

| Aufruf | Zweck |
|---|---|
| `GET /api/tickets/?status=open&q=drucker` | Tickets auflisten (höchstens 100) |
| `POST /api/tickets/` | Ticket anlegen: `title`, `description`, optional `priority`, `kind`, `category`, `requester_email`, `requester_name`; die Organisation ergibt sich aus dem Melder |
| `GET /api/tickets/<nr>/` | Ticket mit Verlauf |
| `POST /api/tickets/<nr>/comments/` | Antwort: `body`, optional `internal` |
| `GET /api/articles/?q=vpn` | Wissensartikel suchen |
| `GET /api/articles/<nr>/` | Wissensartikel lesen |

```bash
curl -X POST http://localhost:8000/api/tickets/ \
  -H "Authorization: Token DEIN_SCHLUESSEL" -H "Content-Type: application/json" \
  -d '{"title": "Platte voll", "description": "Server01 bei 95 %", "priority": "urgent"}'
```

## Betrieb

- **Daten** liegen in den Docker-Volumes `db_data` (Datenbank) und `media_data` (Anhänge).
- **Sicherung:** Der Dienst `backup` schreibt täglich `db_....sql.gz` und
  `anhaenge_....tar.gz` nach `./backups` und löscht Sicherungen nach
  `BACKUP_KEEP_DAYS` (Standard 14) Tagen. Den Ordner zusätzlich auf ein anderes
  System kopieren.
- **Wiederherstellen der Datenbank:**
  `gunzip -c backups/db_DATUM.sql.gz | docker compose exec -T db psql -U helpdesk helpdesk`
  (in eine leere Datenbank).
- **Löschfristen:** Mit `RETENTION_DAYS` werden abgeschlossene Tickets so viele
  Tage nach der letzten Änderung samt Antworten, Anhängen und Zeiteinträgen
  gelöscht (Standard 0 = nie). Wissensartikel bleiben erhalten.
- **Zugriff aus dem Netz:** Reverse Proxy mit HTTPS davorschalten und
  `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` sowie `BEHIND_HTTPS_PROXY=1` setzen.
- E-Mail-Versand über SMTP, sobald `EMAIL_HOST` gesetzt ist. Ohne Angabe landen
  die E-Mails nur im Log (`docker compose logs web worker`).

## Aufbau

| Ordner | Inhalt |
|---|---|
| `config/` | Einstellungen und URL-Übersicht |
| `tickets/` | Tickets, Verlauf, Anhänge, Zeiterfassung (`services.py`), Benachrichtigungen (`notify.py`), E-Mail-Eingang (`mail_in.py`, `mail_fetch.py`), Zielzeiten (`sla.py`), Hintergrundaufgaben (`maintenance.py`), Statistik (`stats.py`), Wochenplanung, wiederkehrende Tickets und Kalender (`planner.py`, `recurrence.py`, `ical.py`), Übersicht und Diagramme (`overview.py`, `charts.py`), Anfrage-Formulare (`request_forms.py`), Leistungsnachweis (`billing.py`, `pdf.py`) |
| `kb/` | Wissensartikel, Suche und Entwurf aus Ticket (`services.py`) |
| `projects/` | Projekte, Meilensteine, Aufgaben, Kanban-Board, Zeitachse |
| `api/` | Schnittstelle für andere Systeme |
| `core/` | Übersicht, Anmeldung, Organisationen und Sichtbarkeit (`orgs.py`), Feiertage, Störungsmeldungen, Virenprüfung, Hintergrunddienst, SSO |
| `templates/`, `static/` | Oberfläche |
