# Mitwirken an Klipper (Contributing)

Vielen Dank, dass Sie zu Klipper beitragen möchten! Dieses Dokument beschreibt den Ablauf für das Einreichen von Änderungen an Klipper.

Informationen zum Melden eines Fehlers oder zur Kontaktaufnahme mit den Entwicklern finden Sie auf der [Kontaktseite](Contact.md).

## Überblick über den Beitragsprozess

Beiträge zu Klipper folgen im Allgemeinen diesem übergeordneten Ablauf:

1. Ein Einreicher (*Submitter*) beginnt mit dem Erstellen eines [GitHub Pull Requests](https://github.com/Klipper3d/klipper/pulls), sobald eine Einreichung bereit für den breiten Einsatz ist.
2. Sobald ein [Prüfer (Reviewer)](#prüfer-reviewers) verfügbar ist, um die Einreichung zu [prüfen](#was-sie-bei-einem-review-erwartet), weist er sich selbst dem Pull Request auf GitHub zu. Ziel des Reviews ist es, nach Fehlern (*Defects*) zu suchen und zu prüfen, ob die Einreichung den dokumentierten Richtlinien entspricht.
3. Nach einem erfolgreichen Review gibt der Prüfer das Review auf GitHub frei („approve the review“), und ein [Maintainer](#prüfer-reviewers) übernimmt die Änderung in den Klipper-`master`-Branch.

Wenn Sie an Erweiterungen arbeiten, sollten Sie in Erwägung ziehen, ein Thema auf [Klipper Discourse](Contact.md) zu starten (oder sich daran zu beteiligen). Eine laufende Diskussion im Forum erhöht die Sichtbarkeit der Entwicklungsarbeit und kann andere Nutzer anziehen, die daran interessiert sind, neue Funktionen zu testen.

## Was Sie bei einem Review erwartet

Beiträge zu Klipper werden vor dem Zusammenführen (*Merging*) geprüft. Das Hauptziel des Review-Prozesses besteht darin, auf Fehler zu prüfen und sicherzustellen, dass die Einreichung den in der Klipper-Dokumentation festgelegten Richtlinien folgt.

Es ist selbstverständlich, dass es viele Wege gibt, eine Aufgabe zu lösen; es ist nicht die Absicht des Reviews, über die „beste“ Implementierung zu diskutieren. Wo immer möglich, werden Review-Diskussionen bevorzugt, die sich auf Fakten und Messwerte stützen.

Die Mehrheit der Einreichungen führt zu Rückmeldungen (*Feedback*) aus einem Review. Seien Sie darauf vorbereitet, Feedback zu erhalten, weitere Details bereitzustellen und die Einreichung bei Bedarf anzupassen.

Typische Punkte, auf die ein Prüfer achtet:

1. **Ist die Einreichung fehlerfrei und bereit für den breiten Einsatz?**

   Von Einreichern wird erwartet, dass sie ihre Änderungen vor dem Einreichen testen. Die Prüfer suchen zwar nach Fehlern, testen die Einreichungen aber im Allgemeinen nicht selbst. Eine angenommene Einreichung wird oft innerhalb weniger Wochen nach der Annahme auf Tausenden von Druckern eingesetzt. Die Qualität der Einreichungen hat daher höchste Priorität.

   Das Haupt-GitHub-Repository [Klipper3d/klipper](https://github.com/Klipper3d/klipper) akzeptiert keine experimentellen Arbeiten. Einreicher sollten Experimente, Fehlersuche (*Debugging*) und Tests in ihren eigenen Repositories durchführen. Der [Klipper Discourse](Contact.md)-Server ist ein guter Ort, um auf neue Arbeiten aufmerksam zu machen und Benutzer zu finden, die bereit sind, Feedback aus der Praxis zu geben.

   Einreichungen müssen alle [Regressionstestfälle](Debugging.md) bestehen.

   Beim Beheben eines Fehlers im Code sollten Einreicher ein grundlegendes Verständnis für die eigentliche Ursache (*Root Cause*) dieses Fehlers haben, und der Fix sollte gezielt diese Ursache beheben.

   Code-Einreichungen sollten keinen übermäßigen Debugging-Code, keine Debugging-Optionen und kein Laufzeit-Debug-Logging enthalten.

   Kommentare in Code-Einreichungen sollten sich darauf konzentrieren, die Wartbarkeit des Codes zu verbessern. Einreichungen sollten keinen „auskommentierten Code“ und keine ausschweifenden Kommentare über frühere Implementierungen enthalten. Ebenso sollten keine übermäßigen „TODO“-Kommentare vorhanden sein.

   Aktualisierungen der Dokumentation sollten nicht als „Work in Progress“ (in Bearbeitung) gekennzeichnet sein.

2. **Bietet die Einreichung einen „hohen Nutzen“ (*High Impact*) für reale Benutzer bei realen Aufgaben?**

   Prüfer müssen – zumindest gedanklich – grob nachvollziehen können, „wer die Zielgruppe ist“, „wie groß diese Zielgruppe ungefähr ist“, welchen „Nutzen“ sie erhält, wie dieser „Nutzen gemessen wird“ und wie die „Ergebnisse dieser Messungen“ aussehen. In den meisten Fällen ist dies sowohl für den Einreicher als auch für den Prüfer offensichtlich und wird während eines Reviews nicht explizit erwähnt.

   Einreichungen für den Klipper-`master`-Branch sollten eine nennenswerte Zielgruppe haben. Als allgemeine „Faustregel“ gilt, dass Einreichungen auf eine Nutzerbasis von mindestens 100 realen Benutzern abzielen sollten.

   Wenn ein Prüfer nach Details zum „Nutzen“ einer Einreichung fragt, fassen Sie dies bitte nicht als Kritik auf. Die realen Vorteile einer Änderung zu verstehen, ist ein natürlicher Bestandteil eines Reviews.

   Bei der Diskussion von Vorteilen ist es vorzuziehen, über „Fakten und Messwerte“ zu sprechen. Im Allgemeinen suchen Prüfer nicht nach Antworten der Form „Jemand könnte Option X nützlich finden“ oder „Diese Einreichung fügt eine Funktion hinzu, die auch Firmware X implementiert“. Stattdessen ist es in der Regel besser, detailliert darzulegen, wie die Qualitätsverbesserung gemessen wurde und wie die Ergebnisse dieser Messungen aussahen – zum Beispiel: „Tests auf Acme-X1000-Druckern zeigen verbesserte Ecken, wie in Bild ... zu sehen ist“, oder „Die Druckzeit des realen Objekts X auf einem Foomatic-X900-Drucker sank von 4 Stunden auf 3,5 Stunden“. Es ist uns bewusst, dass Tests dieser Art erheblichen Zeit- und Arbeitsaufwand erfordern können. Einige der bekanntesten Funktionen von Klipper erforderten Monate der Diskussion, Überarbeitung, Tests und Dokumentation, bevor sie in den `master`-Branch aufgenommen wurden.

   Alle neuen Module, Konfigurationsoptionen, Befehle, Befehlsparameter und Dokumente sollten einen „hohen Nutzen“ (*High Impact*) haben. Wir möchten Benutzer weder mit Optionen belasten, die sie nicht sinnvoll konfigurieren können, noch mit Optionen, die keinen spürbaren Mehrwert bieten.

   Ein Prüfer kann um Klärung bitten, wie ein Benutzer eine Option konfigurieren soll – eine ideale Antwort enthält Details zum Ablauf, zum Beispiel: „Von Benutzern des MegaX500 wird erwartet, dass sie Option X auf 99.3 setzen, während Benutzer des Elite100Y Option X mithilfe des Verfahrens ... kalibrieren“.

   Wenn das Ziel einer Option darin besteht, den Code modularer zu gestalten, sollten Code-Konstanten gegenüber benutzerseitigen Konfigurationsoptionen bevorzugt werden.

   Neue Module, neue Optionen und neue Parameter sollten keine ähnliche Funktionalität wie bereits bestehende Module bieten – wenn die Unterschiede willkürlich sind, ist es vorzuziehen, das bestehende System zu nutzen oder den vorhandenen Code zu überarbeiten (*Refactoring*).

3. **Ist das Urheberrecht (*Copyright*) der Einreichung klar, angemessen und kompatibel?**

   Neue C-Dateien und Python-Dateien sollten einen eindeutigen Copyright-Hinweis enthalten. Orientieren Sie sich am bevorzugten Format der bestehenden Dateien. Das Beanspruchen eines Copyrights in einer bestehenden Datei, an der nur geringfügige Änderungen vorgenommen wurden, ist unerwünscht.

   Code, der aus Drittquellen übernommen wurde, muss mit der Klipper-Lizenz (GNU GPLv3) kompatibel sein. Größere Code-Ergänzungen von Drittanbietern sollten im Verzeichnis `lib/` abgelegt werden (und dem in [lib/README](../lib/README) beschriebenen Format folgen).

   Einreicher müssen eine [Signed-off-by-Zeile](#format-von-commit-nachrichten) mit ihrem vollständigen bürgerlichen Namen angeben. Damit bestätigt der Einreicher, dass er dem [Developer Certificate of Origin](developer-certificate-of-origin) zustimmt.

4. **Folgt die Einreichung den in der Klipper-Dokumentation festgelegten Richtlinien?**

   Insbesondere sollte der Code den Richtlinien in [Code_Overview.md](Code_Overview.md) folgen, und Konfigurationsdateien sollten den Richtlinien in [Example_Configs.md](Example_Configs.md) entsprechen.

5. **Wurde die Klipper-Dokumentation aktualisiert, um die neuen Änderungen widerzuspiegeln?**

   Mindestens die Referenzdokumentation muss entsprechend den Code-Änderungen aktualisiert werden:
   * Alle Befehle und Befehlsparameter müssen in [G-Codes.md](G-Codes.md) dokumentiert werden.
   * Alle benutzerseitigen Module und ihre Konfigurationsparameter müssen in [Config_Reference.md](Config_Reference.md) dokumentiert werden.
   * Alle exportierten „Statusvariablen“ müssen in [Status_Reference.md](Status_Reference.md) dokumentiert werden.
   * Alle neuen „Webhooks“ und ihre Parameter müssen in [API_Server.md](API_Server.md) dokumentiert werden.
   * Jede Änderung, die eine nicht abwärtskompatible Änderung an einem Befehl oder einer Konfigurationsdatei-Einstellung bewirkt, muss in [Config_Changes.md](Config_Changes.md) dokumentiert werden.

   Neue Dokumente sollten in [Overview.md](Overview.md) sowie im Website-Index [docs/_klipper3d/mkdocs.yml](../docs/_klipper3d/mkdocs.yml) eingetragen werden.

6. **Sind die Commits sauber aufgebaut, behandeln jeweils nur ein einzelnes Thema pro Commit und sind voneinander unabhängig?**

   Commit-Nachrichten sollten dem [bevorzugten Format](#format-von-commit-nachrichten) entsprechen.

   Commits dürfen keine Merge-Konflikte aufweisen. Neue Ergänzungen zum Klipper-`master`-Branch erfolgen immer über ein „Rebase“ oder „Squash and Rebase“. Es ist für Einreicher im Allgemeinen nicht notwendig, ihre Einreichung bei jedem Update des Klipper-`master`-Repositorys neu zusammenzuführen (*re-merge*). Liegt jedoch ein Merge-Konflikt vor, wird empfohlen, den Konflikt mittels `git rebase` aufzulösen.

   Jeder Commit sollte eine einzelne übergeordnete Änderung behandeln. Große Änderungen sollten in mehrere unabhängige Commits aufgeteilt werden. Jeder Commit sollte „für sich allein stehen können“, damit Werkzeuge wie `git bisect` und `git revert` zuverlässig funktionieren.

   reine Formatierungs-/Leerzeichenänderungen (*Whitespace Changes*) sollten nicht mit funktionalen Änderungen vermischt werden. Im Allgemeinen werden unnötige Whitespace-Änderungen nicht akzeptiert, es sei denn, sie stammen vom etablierten „Eigentümer“ des geänderten Codes.

Klipper schreibt keinen strengen „Coding Style Guide“ vor, aber Änderungen an bestehendem Code sollten dem übergeordneten Code-Fluss, dem Einrückungsstil und der Formatierung des vorhandenen Codes folgen. Einreichungen neuer Module und Systeme haben mehr Flexibilität beim Programmierstil, es wird jedoch bevorzugt, dass dieser neue Code einem intern konsistenten Stil und allgemeinen branchenüblichen Programmierstandards folgt.

Es ist nicht das Ziel eines Reviews, über „bessere Implementierungen“ zu diskutieren. Wenn ein Prüfer jedoch Schwierigkeiten hat, die Implementierung einer Einreichung nachzuvollziehen, kann er um Änderungen bitten, um die Implementierung transparenter zu machen. Insbesondere wenn Prüfer sich nicht davon überzeugen können, dass eine Einreichung fehlerfrei ist, können Anpassungen erforderlich sein.

Im Rahmen eines Reviews kann ein Prüfer einen alternativen Pull Request zu einem Thema erstellen. Dies kann geschehen, um ein übermäßiges „Hin und Her“ bei kleineren formalen Punkten zu vermeiden und so den Einreichungsprozess zu beschleunigen. Es kann auch vorkommen, weil die Diskussion einen Prüfer dazu inspiriert, eine alternative Implementierung zu entwickeln. Beide Situationen sind ein normales Ergebnis eines Reviews und sollten nicht als Kritik an der ursprünglichen Einreichung verstanden werden.

### Mithilfe bei Reviews

Wir freuen uns über Unterstützung bei Reviews! Es ist nicht erforderlich, ein [gelisteter Prüfer](#prüfer-reviewers) zu sein, um ein Review durchzuführen. Einreicher von GitHub Pull Requests werden ebenfalls ermutigt, ihre eigenen Einreichungen anhand dieser Kriterien zu überprüfen.

Um bei einem Review zu helfen, folgen Sie den unter [Was Sie bei einem Review erwartet](#was-sie-bei-einem-review-erwartet) beschriebenen Schritten, um die Einreichung zu überprüfen. Fügen Sie nach Abschluss der Prüfung einen Kommentar mit Ihren Ergebnissen zum GitHub Pull Request hinzu. Wenn die Einreichung das Review besteht, geben Sie dies bitte ausdrücklich im Kommentar an – zum Beispiel: „Ich habe diese Änderung gemäß den Schritten im CONTRIBUTING-Dokument geprüft und für mich sieht alles gut aus“. Wenn Sie einige Schritte des Reviews nicht durchführen konnten, geben Sie bitte explizit an, welche Schritte geprüft wurden und welche nicht – zum Beispiel: „Ich habe den Code nicht auf Fehler geprüft, aber alles andere im CONTRIBUTING-Dokument kontrolliert und es sieht gut aus“.

Wir schätzen auch das Testen von Einreichungen sehr. Wenn der Code getestet wurde, fügen Sie bitte einen Kommentar mit Ihren Testergebnissen (Erfolg oder Misserfolg) zum GitHub Pull Request hinzu. Geben Sie bitte ausdrücklich an, dass der Code getestet wurde und wie die Ergebnisse ausfielen – zum Beispiel: „Ich habe diesen Code auf meinem Acme900Z-Drucker mit einem Vasendruck getestet und die Ergebnisse waren gut“.

### Prüfer (Reviewers)

Die „Reviewer“ von Klipper sind:

| Name                   | GitHub-ID         | Interessengebiete |
| ---------------------- | ----------------- | ----------------- |
| Dmitry Butyugin        | @dmbutyugin       | Input Shaping, Resonanztests, Kinematik |
| Eric Callahan          | @Arksine          | Bett-Nivellierung (*Bed Leveling*), MCU-Flashen |
| James Hartley          | @JamesH1978       | Konfigurationsdateien |
| Kevin O'Connor         | @KevinOConnor     | Kern-Bewegungssystem (*Core Motion System*), Mikrocontroller-Code |

Bitte „pingen“ (erwähnen) Sie keinen der Prüfer direkt an und richten Sie Einreichungen nicht persönlich an einzelne Prüfer. Alle Prüfer beobachten die Foren und Pull Requests und übernehmen Reviews, sobald sie Zeit dafür haben.

Die „Maintainer“ von Klipper sind:

| Name                   | GitHub-Name       |
| ---------------------- | ----------------- |
| Kevin O'Connor         | @KevinOConnor     |

## Format von Commit-Nachrichten

Jeder Commit sollte eine Commit-Nachricht haben, die ähnlich wie das folgende Beispiel formatiert ist:

```
modul: Großgeschriebene, kurze (max. 50 Zeichen) Zusammenfassung

Ausführlicherer erklärender Text, falls erforderlich. Brechen Sie die
Zeilen bei etwa 75 Zeichen um. In manchen Kontexten wird die erste Zeile
als Betreff einer E-Mail und der Rest des Textes als Nachrichtentext
behandelt. Die Leerzeile, die die Zusammenfassung vom Textkörper trennt,
ist entscheidend (sofern Sie den Textkörper nicht ganz weglassen);
Werkzeuge wie rebase können durcheinanderkommen, wenn beides direkt
aufeinanderfolgt.

Weitere Absätze folgen nach Leerzeilen.

Signed-off-by: Mein Name <meineemail@example.org>
```

Im obigen Beispiel sollte `modul` der Name einer Datei oder eines Verzeichnisses im Repository sein (ohne Dateiendung). Zum Beispiel: `clocksync: Fix typo in pause() call at connect time`. Der Zweck der Angabe eines Modulnamens in der Commit-Nachricht besteht darin, Kontext für die Commit-Kommentare bereitzustellen.

Es ist wichtig, dass jeder Commit eine „Signed-off-by“-Zeile enthält – sie bestätigt, dass Sie dem [Developer Certificate of Origin](developer-certificate-of-origin) zustimmen. Sie muss Ihren echten Namen (leider keine Pseudonyme oder anonymen Beiträge) sowie eine aktuelle E-Mail-Adresse enthalten.

## Mitwirken an Klipper-Übersetzungen

Das [Klipper-translations-Projekt](https://github.com/Klipper3d/klipper-translations) widmet sich der Übersetzung von Klipper in verschiedene Sprachen. [Weblate](https://hosted.weblate.org/projects/klipper/) hostet alle Gettext-Strings zum Übersetzen und Prüfen. Sprachversionen (*Locales*) können auf [klipper3d.org](https://www.klipper3d.org) angezeigt werden, sobald sie die folgenden Anforderungen erfüllen:

- [ ] 75 % Gesamtabdeckung
- [ ] Alle Hauptüberschriften (H1) sind übersetzt
- [ ] Ein Pull Request mit aktualisierter Navigationshierarchie in `klipper-translations` liegt vor.

Um Frustrationen beim Übersetzen fachspezifischer Begriffe zu verringern und einen Überblick über laufende Übersetzungen zu erhalten, können Sie einen Pull Request einreichen, der die `readme.md` im [Klipper-translations-Projekt](https://github.com/Klipper3d/klipper-translations) ergänzt. Sobald eine Übersetzung fertig ist, kann die entsprechende Anpassung im Klipper-Projekt vorgenommen werden.

Wenn eine Übersetzung bereits im Klipper-Repository vorhanden ist und die oben genannte Checkliste nicht mehr erfüllt, wird sie nach einem Monat ohne Updates als veraltet (*out-of-date*) markiert.

Sobald die Anforderungen erfüllt sind, müssen Sie:

1. die Datei [active_translations](https://github.com/Klipper3d/klipper-translations/blob/translations/active_translations) im Repository `klipper-translations` aktualisieren,
2. Optional: eine Datei `manual-index.md` im Ordner `docs\locals\<lang>` des `klipper-translations`-Repositorys hinzufügen, um die sprachspezifische `index.md` zu ersetzen (die automatisch generierte `index.md` wird nicht korrekt dargestellt).

Bekannte Probleme:
1. Derzeit gibt es keine Methode, um Bilder in der Dokumentation direkt zu übersetzen.
2. Es ist nicht möglich, Titel in der `mkdocs.yml` zu übersetzen.
