# Übergabe: Stand und offene Punkte

Diese Datei fasst zusammen, was in der bisherigen Zusammenarbeit entschieden
wurde. Die Funktionen selbst beschreibt die `README.md`.

## Stand am 25.11.2026

- **Zweig `main`:** läuft auf dem Server `asc01` unter `~/ticket/helpdesk`
  (Docker Compose, PostgreSQL). Dort bestehen alle Tests.
- **Zweig `neues-design`:** neue Gestaltung mit Seitenleiste, kompakter
  Darstellung, dunklem Design und austauschbaren Designs. 80 Tests bestehen
  (lokal mit SQLite geprüft). Noch nicht nach `main` übernommen; der Auftraggeber
  hat die Richtung mit „sieht gut aus“ bestätigt, die Firmenfarben fehlen noch.

## Nächste Aufgabe

Die beiden Designs an die Firmenauftritte anpassen:

- `ebner.ticket` nach https://www.elektro-ebner.at/
- `forstenlechner.ticket` nach https://www.forstenlechner.at/

Bisher stehen in `static/css/brand-ebner.css` und
`static/css/brand-forstenlechner.css` nur Platzhalterfarben (Blau bzw. Rot), weil
die Websites nicht abrufbar waren. Zu übernehmen sind Hauptfarbe und
Zweitfarben, Schrift (oder eine frei verwendbare ähnliche), Formensprache der
Knöpfe und Flächen. Es bleibt ein dichtes Arbeitswerkzeug, keine Kopie der
Homepage.

Die **Logos** liefert der Auftraggeber als Datei; sie werden unter
`static/brand/<name>/logo.svg` oder `logo.png` abgelegt und nicht nachgezeichnet.

Noch offen ist die Frage, wie die beiden Namen genutzt werden: zwei getrennte
Installationen, eine gemeinsame unter zwei Adressen (`BRAND_HOSTS`) oder nur
eines der Designs.

## So wird geprüft

```bash
pip install --break-system-packages "Django==5.2.*" "whitenoise==6.*" markdown nh3 tzdata reportlab
python manage.py test                     # ohne POSTGRES_HOST läuft alles mit SQLite
python manage.py makemigrations --check --dry-run
DEBUG=1 python manage.py runserver        # nach migrate, createcachetable, ensure_admin
```

Seiten mit einem Browser ansehen und Bildschirmfotos vergleichen. Designs lassen
sich als Bearbeiter mit `?design=ebner` bzw. `?design=forstenlechner` ansehen,
`?design=aus` beendet die Vorschau. Nicht lokal prüfbar sind die Volltextsuche
mit PostgreSQL, der Container-Aufbau sowie Mailserver, LDAP und SSO.

## Festlegungen des Auftraggebers

- Internes Ticketsystem für ein Unternehmen der Elektrobranche mit rund
  100 Personen, mit Wissensbasis, Zeiterfassung und Projekt-Management.
- Technik: Django mit PostgreSQL in Docker Compose. Ein Umbau auf Angular wurde
  besprochen und verworfen.
- Gelöste Tickets erzeugen einen Entwurf für die Wissensbasis, der vor der
  Veröffentlichung von einem Bearbeiter freigegeben wird.
- Mandanten: Kunden oder Abteilungen als Organisationen in einem System.
  Ansprechpartner sehen alle Tickets ihrer Organisation, andere nur eigene.
- Planung auf Tagesebene ohne Uhrzeiten. Der Wochenpool wird wöchentlich für die
  nächsten fünf Tage gefüllt; Tickets lassen sich zuordnen oder selbst
  übernehmen, Anzeige je Bearbeiter, Ansicht „Nur meine“ oder „Alle“.
- Die Kalender-Anbindung für Outlook ist vorhanden, dem Auftraggeber aber nicht wichtig.
- Geräte- und Inventarverwaltung wurde bewusst ausgenommen.
- Navigation als Seitenleiste.

## Arbeitsweise

- Änderungen kommen auf einen Zweig und werden gepusht; der Auftraggeber holt sie
  auf dem Server mit `git pull` und `docker compose up -d --build`.
- Neue Datenbankfelder nur über zusätzliche Migrationen, weil die Datenbank auf
  dem Server Echtdaten enthält.
- Die `.env` mit Zugangsdaten gehört nie ins Repository.
- Vor jedem Push: Tests ausführen und die betroffenen Seiten ansehen.

## Besprochen, aber noch nicht umgesetzt

Nach Nutzen für den Betrieb geordnet:

1. Melden ohne Konto, etwa über einen QR-Code, für Monteure, Lager und Lehrlinge
   ohne E-Mail-Adresse
2. Interne Wissensartikel, die nur die IT sieht
3. Mehrfachbearbeitung in der Ticketliste
4. Vertrauliche Tickets und Schwärzen versehentlich geposteter Passwörter
5. Vertretung bei Abwesenheit
6. Geräteverzeichnis mit Prüffristen sowie Verträge und Lizenzen mit Ablaufdatum
7. Zuordnen, Abhaken und Verschieben ohne Neuladen der Seite; Pool und Übersicht
   aktualisieren sich selbst
8. Zum Wochenpool: Rückblick geplant gegen erledigt über mehrere Wochen,
   Teamkapazität beim Befüllen, frei festlegbare Reihenfolge

## Vor dem Echtbetrieb

HTTPS über einen Reverse Proxy, eigene Passwörter und `SECRET_KEY` in der `.env`,
SMTP und Postfach einrichten, eine Sicherung probeweise einspielen, Stammdaten
anlegen, regionale Feiertage ergänzen, Zeiterfassung und Auswertungen je
Bearbeiter mit dem Betriebsrat abklären.
