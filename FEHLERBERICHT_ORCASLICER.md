# Umfassender Systematischer Fehler- und Sicherheitsbericht: OrcaSlicer & u1-klipper

**Projekt:** Snapmaker OrcaSlicer (v2.4.1) & Snapmaker U1 Klipper Firmware (u1-klipper)  
**Methode:** /systematic-debugging (Vollstaendige statische und logische Code-Analyse aller Subsysteme: C++ Slicing Engine `src/libslic3r/`, Netzwerk und IPC `src/slic3r/Utils/`, Benutzeroberflaeche `src/slic3r/GUI/`, Maschinenprofile `submodules/Profiles/Snapmaker/`, sowie Klipper Firmware `u1-klipper/klippy/` und Konfigurationen `u1-klipper/lava/`)  
**Gepruefte Fehlerklassen:**
1. Zero Day und Sicherheitsluecken (Remote Code Execution via Webview IPC, ungesicherte Protokollaufrufe, TLS-Pruefungsumgehung, Klartextlogging, unsichere temporaere Dateien)
2. Buffer Overflows und Out of Bounds (Stack Buffer Overflow via sprintf, Vector OOB-Zugriffe, Pufferunterabtastung)
3. Integer Overflows, Underflows und Truncation (64-Bit zu 32-Bit Dateigroessentruncation, Atomic-Underflows)
4. Division by Zero (WipeTower2 Division durch Null bei Gittern, Floatingpoint-NaN-Propagation)
5. Null Pointer Dereference / Segfaults (Ungesicherte Zeigerzugriffe auf get_curr_plate(), m_agent, inkompatible Wstring-Casts)
6. Speicherlecks, Socket und Handlelecks (Expat-Parser-Lecks, Ams-Objekt-Lecks, ungeschlossene Sockets)
7. Dangling Pointers und Use After Free (Thread Detach im Http-Destruktor, asynchrone Mqtt-Lambdas mit rohem this)
8. Deadlocks und Endlosschleifen (Unendliche blockierende Reads ohne Timeout im WebSocketClient)
9. Race Conditions und Nebenlaeufigkeitsfehler (Curl Global Init Race, ungeschuetzte Abbruchflags)
10. Logische Fehler und Parsingfehler (Fehlende break-Anweisungen, Fallthrough-Bugs, fehlerhafte Pfadkuerzung)
11. Schnittstellen, Firmware, API, Variablen und Datentypkonflikte (GCode-Syntaxfehler, unbekannte Makroparameter, Namenskonflikte, Datentyppruefungen, Extruderindex-Fehler, Farbcodedifferenzen, Koordinatenueberschreitungen)

---

## Inhaltsverzeichnis und Zusammenfassung nach Fehlerklassen

| Nr. | Fehlerklasse | Anzahl verifizierter Befunde | Hoechster Schweregrad | Hauptbetroffene Module |
| :--- | :--- | :---: | :---: | :--- |
| **1** | **Zero Day und Sicherheitsluecken** | 5 | **KRITISCH** | `SSWCP.cpp`, `PrinterWebView.cpp`, `Http.cpp`, `MQTT.cpp` |
| **2** | **Buffer Overflows und Out of Bounds** | 4 | **KRITISCH** | `AMF.cpp`, `fdm_U1.json`, `DeviceManager.cpp`, `SSWCP.cpp` |
| **3** | **Integer Overflows / Underflows / Truncation** | 2 | **HOCH** | `Http.cpp`, `MQTT.cpp` |
| **4** | **Division by Zero** | 3 | **KRITISCH** | `WipeTower2.cpp` |
| **5** | **Null Pointer / Segfaults / Inkompatible Casts** | 4 | **KRITISCH** | `Plater.cpp`, `Monitor.cpp`, `Http.cpp`, `AMF.cpp` |
| **6** | **Speicher-, Socket- und Handlelecks** | 4 | **HOCH** | `AMF.cpp`, `DeviceManager.cpp`, `SSWCP.cpp` |
| **7** | **Dangling Pointers und Use After Free** | 2 | **KRITISCH** | `Http.cpp`, `MQTT.cpp` |
| **8** | **Deadlocks und Thread-Hangs** | 2 | **HOCH** | `WebSocketClient.hpp`, `MQTT.cpp` |
| **9** | **Race Conditions und Concurrency** | 1 | **HOCH** | `Http.cpp` |
| **10** | **Logische Fehler und Parsingfehler** | 2 | **HOCH** | `AMF.cpp`, `WebSocketClient.hpp` |
| **11** | **Schnittstellen-, API- und Datentypkonflikte (OrcaSlicer vs. u1-klipper)** | 10 | **KRITISCH** | `Snapmaker U1 (0.4 nozzle).json`, `fdm_U1.json`, `GatewayDevice.cpp`, `GatewayProtocol.cpp`, `print_task_config.py`, `bed_mesh.py` |

**Gesamtzahl dokumentierter und verifizierter Befunde:** 39

---

## 1. Zero Day und Sicherheitsluecken (Security & Zero Day Vulnerabilities)

### [SEC-01] Beliebige URI Scheme Ausfuehrung & Remote Code Execution via WebView IPC (`SSWCP.cpp` & `PrinterWebView.cpp`)
- **Datei und Zeilen:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L692-L715), [PrinterWebView.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/PrinterWebView.cpp#L244-L252)
- **Schweregrad:** KRITISCH (CWE-20, CWE-937, CWE-78)
- **Ursachenanalyse (Root Cause):**
  In `PrinterWebView::OnScriptMessage` werden saemtliche IPC-Nachrichten beliebiger im Browser geladener Webseiten (z. B. Fluidd, Mainsail, Drittanbieter-Webinterfaces oder externe Weiterleitungen) ohne Origin-Verifikation direkt an `SSWCP::handle_web_message` durchgereicht. Dort verarbeitet `SSWCP_Instance::sw_OpenBrowser` den Befehl `"sw_OpenBrowser"`, extrahiert das Feld `m_param_data["url"]` vollstaendig ungeprueft und uebergibt es an `wxLaunchDefaultBrowser(wx_url)`. Unter Windows delegiert diese Funktion an die Win32 API `ShellExecuteEx`. Ein Angreifer kann dadurch boesartige Protokoll-Schemata (`file:///`, `smb://`, `ms-msdt:`, `calculator:`, `powershell:`) ausfuehren oder lokale Dateien oeffnen.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp:692
  void SSWCP_Instance::sw_OpenBrowser() {
      try {
          std::string url = m_param_data.count("url") ? m_param_data["url"].get<std::string>() : "";
          wxString wx_url  = wxString::FromUTF8(url);
          ...
          wxGetApp().CallAfter([wx_url, weak_self]() {
              ...
              bool res = wxLaunchDefaultBrowser(wx_url);
              ...
          });
      }
  }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Strikte Validierung des Schemas auf `http://` und `https://` sowie Pruefung der Ziel-Domain gegen eine Whitelist:
  ```cpp
  void SSWCP_Instance::sw_OpenBrowser() {
      try {
          std::string url = m_param_data.value("url", "");
          if (url.rfind("http://", 0) != 0 && url.rfind("https://", 0) != 0) {
              BOOST_LOG_TRIVIAL(error) << "Blocked unauthorized browser scheme: " << url;
              handle_general_fail(-1, "Unauthorized URL scheme");
              return;
          }
          wxString wx_url = wxString::FromUTF8(url);
          ...
      }
  }
  ```

---

### [SEC-02] Vollstaendig deaktivierte TLS-Zertifikatspruefung im HTTP-Client (`Http.cpp`)
- **Datei und Zeilen:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L205-L206)
- **Schweregrad:** KRITISCH (CWE-295: Improper Certificate Validation)
- **Ursachenanalyse (Root Cause):**
  In `Http::priv::priv` werden fuer jede HTTP-Sitzung `CURLOPT_SSL_VERIFYPEER` und `CURLOPT_SSL_VERIFYHOST` hardcodiert auf `0L` gesetzt. Damit werden TLS-Zertifikatsketten, Ablauffristen und Hostnamenuebereinstimmungen vollstaendig ignoriert. Jeder Angreifer im lokalen Netzwerk oder Man in the Middle kann Modell-Downloads manipulieren, Anmeldedaten und API-Tokens abfangen oder gefaelschte Konfigurationen einschleusen.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp:205
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
  ```
- **Loesungsansatz (Defensiver Fix):**
  Standardmaessig strikte Zertifikatspruefung aktivieren und den Systemzertifikatsspeicher einbinden:
  ```cpp
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
  #ifdef _WIN32
  ::curl_easy_setopt(curl, CURLOPT_SSL_OPTIONS, CURLSSLOPT_NATIVE_CA);
  #endif
  ```

---

### [SEC-03] Unsichere temporaere Dateierstellung fuer Private Keys im MQTT-Client (`MQTT.cpp`)
- **Datei und Zeilen:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L84-L120)
- **Schweregrad:** HOCH (CWE-377: Insecure Temporary File, CWE-59: Link Following)
- **Ursachenanalyse (Root Cause):**
  In `MqttClient::init_ssl` werden empfangene CA-Zertifikate, Client-Zertifikate und Private Keys in das globale Temp-Verzeichnis geschrieben (`temp_dir / ("key_" + client_id + std::to_string(int64_t(this)) + ".key")`). Die Dateinamen sind vorhersagbar und werden ohne restriktive Dateiberechtigungen (unter Linux/macOS standardmaessig 0644/0666) erzeugt. Lokale Prozesse koennen private Schluessel im Klartext mitlesen oder ueber Symlinks beliebige Dateien ueberschreiben.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:110
  boost::filesystem::path key_path = temp_dir / ("key_" + client_id + std::to_string(int64_t(this)) + ".key");
  if (!key_content.empty()) {
      boost::filesystem::ofstream key_file(key_path);
      key_file << key_content;
      key_file.close();
  }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Erstellung der temporaeren Dateien mit Zufallstoken und restriktiven Zugriffsbeschraenkungen (Modus 0600) oder direkte In-Memory-Uebergabe an OpenSSL ueber `SSL_CTX_use_PrivateKey` ohne Festplattenspeicherung.

---

### [SEC-04] Klartext-Protokollierung sensitiver TLS-Zertifikate und Zugangsdaten (`MQTT.cpp`)
- **Datei und Zeilen:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L74-L75)
- **Schweregrad:** HOCH (CWE-532: Insertion of Sensitive Information into Log File)
- **Ursachenanalyse (Root Cause):**
  Beim Initialisieren der SSL-Verbindung schreibt das Log-Makro `BOOST_LOG_TRIVIAL(info)` die vollstaendigen Inhalte von `ca_content`, `cert_content` und `username_` unmaskiert in die persistenten Anwendungslogdateien.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:74
  BOOST_LOG_TRIVIAL(info) << "[MQTT_INFO] initializing MQTT SSL connection, server_address: " << server_address_
      << ", ca_content: " << ca_content << ", cert_content: " << cert_content << ", username: " << username_;
  ```
- **Loesungsansatz (Defensiver Fix):**
  Zertifikatsinhalte niemals protokollieren, sondern lediglich deren Vorhandensein oder Laenge ausgeben:
  ```cpp
  BOOST_LOG_TRIVIAL(info) << "[MQTT_INFO] initializing MQTT SSL connection, server_address: " << server_address_
      << ", ca_present: " << !ca_content.empty() << ", cert_present: " << !cert_content.empty();
  ```

---

### [SEC-05] Deaktivierte TLS-Zertifikatsvalidierung in MQTT-Optionen (`MQTT.cpp`)
- **Datei und Zeilen:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L123)
- **Schweregrad:** HOCH (CWE-295: Improper Certificate Validation)
- **Ursachenanalyse (Root Cause):**
  `ssl_opts.set_verify(false);` deaktiviert die Pruefung des Serverzertifikats im Paho MQTT Client vollstaendig.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:122
  mqtt::ssl_options ssl_opts;
  ssl_opts.set_verify(false);
  ssl_opts.set_enable_server_cert_auth(true);
  ```
- **Loesungsansatz (Defensiver Fix):**
  `ssl_opts.set_verify(true);` aktivieren und Hostnamen-Pruefung erzwingen.

---

## 2. Buffer Overflows und Out of Bounds (Pufferueberlaeufe)

### [BOF-01] Klassischer Stack Buffer Overflow via `sprintf` in `AMF.cpp`
- **Datei und Zeilen:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L989-L992)
- **Schweregrad:** KRITISCH (CWE-121: Stack-based Buffer Overflow)
- **Ursachenanalyse (Root Cause):**
  In `extract_model_from_archive` wird ein fester Stack-Puffer `char error_buf[1024];` allokiert. Anschliessend wird `::sprintf` aufgerufen und `data->stat.m_filename` (welcher gemaess ZIP-Spezifikation bis zu 65.535 Bytes lang sein kann) zusammen mit der Fehlermeldung unbegrenzt hineingeschrieben. Eine manipulierte AMF- oder 3MF-Archivdatei fuehrt zum Ueberschreiben des Funktions-Stackframes und zur Ausfuehrung von Schadcode oder sofortigem Absturz.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp:989
  char error_buf[1024];
  ::sprintf(error_buf, "Parsing file %s error at line %d: {%s}", data->stat.m_filename, (int) XML_GetCurrentLineNumber(data->parser), data->ctx.error_message());
  throw Slic3r::FileIOError(error_buf);
  ```
- **Loesungsansatz (Defensiver Fix):**
  Verwendung von `snprintf` oder C++ `std::string` Formatierung:
  ```cpp
  std::string err_msg = (boost::format("Parsing file %s error at line %d: {%s}") 
      % data->stat.m_filename % (int) XML_GetCurrentLineNumber(data->parser) % data->ctx.error_message()).str();
  throw Slic3r::FileIOError(err_msg);
  ```

---

### [BOF-02] Vector Out of Bounds Zugriff auf nicht existierenden 6. Extruder in `fdm_U1.json`
- **Datei und Zeilen:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L183)
- **Schweregrad:** HOCH (CWE-125: Out-of-bounds Read)
- **Ursachenanalyse (Root Cause):**
  Im Start-G-Code von `fdm_U1.json` referenziert das Makro `is_extruder_used[5]` und `first_layer_temperature[5]`. Das Vektor-Array `is_extruder_used` besitzt gemaess Profilkonfiguration maximal 5 Elemente (Indizes 0 bis 4). Der Zugriff auf Index 5 loest eine Bereichsueberschreitung im Expression-Evaluator aus.
- **Betroffener Code:**
  ```json
  "machine_start_gcode": "PRINT_START ... {if is_extruder_used[4]}T4_TEMP={first_layer_temperature[4]}{endif} {if is_extruder_used[5]}T5_TEMP={first_layer_temperature[5]}{endif} ..."
  ```
- **Loesungsansatz (Defensiver Fix):**
  Bereinigung des Start-G-Codes auf die physikalisch vorhandenen 4 Extruder (Indizes 0 bis 3).

---

### [BOF-03] Vector Out of Bounds Zugriff bei `m_extder_data.extders` in `DeviceManager.cpp`
- **Datei und Zeilen:** [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L736-L757), [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L3412), [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L3585)
- **Schweregrad:** HOCH (CWE-125: Out-of-bounds Read/Write)
- **Ursachenanalyse (Root Cause):**
  An zahlreichen Stellen greift `DeviceManager.cpp` unkonditioniert ueber `m_extder_data.extders[MAIN_NOZZLE_ID]` auf das Element zu, ohne sicherzustellen, dass der Vektor mindestens `MAIN_NOZZLE_ID + 1` Elemente enthaelt. Bei Maschinen ohne initialisierte Extruderliste stuerzt der Prozess ab.
- **Loesungsansatz (Defensiver Fix):**
  Strikte Groessenpruefung:
  ```cpp
  if (MAIN_NOZZLE_ID < m_extder_data.extders.size()) {
      m_extder_data.extders[MAIN_NOZZLE_ID].ext_has_filament = hw_switch_state;
  }
  ```

---

### [BOF-04] Zeichenpuffer-Unterabtastung bei Multi Byte UTF-8 in `WCP_Logger::worker`
- **Datei und Zeilen:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L195)
- **Schweregrad:** MITTEL (CWE-125 / CWE-135)
- **Ursachenanalyse (Root Cause):**
  `asio::write(*socket, asio::buffer(log.ToUTF8().data(), log.length() + 1), ec);` berechnet die Laenge ueber `log.length()`. In wxWidgets liefert `log.length()` die Anzahl der Zeichen (UTF-16 unter Windows). Der UTF-8-Puffer `ToUTF8()` benoetigt fuer Sonderzeichen, Umlaute oder asiatische Schriftzeichen jedoch 2 bis 4 Bytes je Zeichen. Die uebergebene Laenge ist daher viel zu kurz und schneidet Nachrichten ab.
- **Loesungsansatz (Defensiver Fix):**
  Pufferlaenge direkt vom erzeugten UTF-8-Objekt abfragen:
  ```cpp
  const wxScopedCharBuffer utf8 = log.ToUTF8();
  asio::write(*socket, asio::buffer(utf8.data(), utf8.length()), ec);
  ```

---

## 3. Integer Overflows, Underflows und Truncation

### [INT-01] 32-Bit Dateigroessen-Truncation bei Uploads groesser als 2GB in `Http.cpp`
- **Datei und Zeilen:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L413)
- **Schweregrad:** HOCH (CWE-197: Numeric Truncation Error)
- **Ursachenanalyse (Root Cause):**
  `::curl_easy_setopt(curl, CURLOPT_INFILESIZE, filesize);` verwendet die Option `CURLOPT_INFILESIZE`, welche einen `long`-Wert erwartet. Unter 64-Bit Windows (MSVC Data Model LLP64) ist `long` lediglich 32 Bit gross. Dateigroessen ueber 2.147.483.647 Bytes laufen ueber, werden negativ oder abgeschnitten.
- **Loesungsansatz (Defensiver Fix):**
  Verwendung der 64-Bit cURL-Option:
  ```cpp
  ::curl_easy_setopt(curl, CURLOPT_INFILESIZE_LARGE, static_cast<curl_off_t>(filesize));
  ```

---

### [INT-02] Negativer Atomic Underflow in `MqttClient::pending_reconnect_checks`
- **Datei und Zeilen:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L487)
- **Schweregrad:** MITTEL (CWE-191: Integer Underflow)
- **Ursachenanalyse (Root Cause):**
  In Zeile 515 wird `pending_reconnect_checks.fetch_add(1)` ausgefuehrt, wenn die Verbindung fehlschlaegt, aber in bestimmten Verzweigungen von `connection_lost` wird nicht dekrementiert. Umgekehrt kann bei unbalanciertem `fetch_sub` der Zaehler unter Null fallen, wodurch die Destruktor-Warteschleife `while (pending_reconnect_checks.load(...) > 0)` fehlschlaegt.
- **Loesungsansatz (Defensiver Fix):**
  Zaehler vor Dekrement pruefen und nur dekrementieren, wenn `val > 0`.

---

## 4. Division by Zero (Hardware- und Logikfehler)

### [DIV-01] Division durch Null bei leeren WipeTower-Gittern in `WipeTower2.cpp`
- **Datei und Zeilen:** [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L2702-L2703)
- **Schweregrad:** KRITISCH (CWE-369: Divide By Zero)
- **Ursachenanalyse (Root Cause):**
  In `generate_empty_grid` wird berechnet:
  `int n = dy / (m_perimeter_width * sparse_factor); float spacing = (dy - m_perimeter_width) / (n - 1);`
  Wenn `dy` klein ist und `n == 1` ergibt, ist der Divisor `(n - 1) == 0`. Das Ergebnis ist `+inf` oder `NaN`. In der nachfolgenden Schleife und Berechnung `int loops_num = (m_wipe_tower_brim_width + spacing / 2.f) / spacing;` fuehrt die Konvertierung von `inf`/`NaN` in Integer zu undefiniertem Verhalten (0x80000000 auf x86) oder Hardware-Ausnahmen.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp:2702
  int   n       = dy / (m_perimeter_width * sparse_factor);
  float spacing = (dy - m_perimeter_width) / (n - 1);
  int   i       = 0;
  for (i = 0; i < n; ++i) {
      writer.extrude(writer.x(), y, feedrate).extrude(i % 2 ? left : right, y);
      y = y + spacing;
  }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Division durch Null absichern:
  ```cpp
  int n = dy / (m_perimeter_width * sparse_factor);
  float spacing = (n > 1) ? ((dy - m_perimeter_width) / (n - 1)) : 0.f;
  ```

---

### [DIV-02] Identische Division durch Null in Sparse Infill von `WipeTower2.cpp`
- **Datei und Zeilen:** [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L2913-L2914), [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L4510-L4511)
- **Schweregrad:** KRITISCH (CWE-369)
- **Ursachenanalyse (Root Cause):**
  Identischer Rechenschritt `float spacing = (dy - m_perimeter_width) / (n - 1);` an zwei weiteren Stellen ohne Pruefung auf `n > 1`.
- **Loesungsansatz (Defensiver Fix):**
  Bedingte Pruefung `(n > 1)` an beiden Stellen einpflegen.

---

### [DIV-03] Division durch Null bei Nulllaenge in `WipeTower2::volume_to_length`
- **Datei und Zeilen:** [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L489), [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L655)
- **Schweregrad:** HOCH (CWE-369)
- **Ursachenanalyse (Root Cause):**
  `volume / (layer_height * (line_width - layer_height * (1.f - float(M_PI) / 4.f)))` dividiert durch 0, wenn `layer_height == 0.f` oder `line_width == layer_height * (1 - PI/4)`.
- **Loesungsansatz (Defensiver Fix):**
  Pruefung des Nenners auf einen Mindestwert (`> 1e-5f`) vor der Division.

---

## 5. Null Pointer Dereference / Segfaults / Typ-Casts

### [NPE-01] Ungesicherte Nullzeigerdereferenzierung auf `get_curr_plate()` in `Plater.cpp`
- **Datei und Zeilen:** [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L12792), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L13670), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L15147), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L15449), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L15513), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L21603)
- **Schweregrad:** KRITISCH (CWE-476: NULL Pointer Dereference)
- **Ursachenanalyse (Root Cause):**
  `partplate_list.get_curr_plate()` gibt `nullptr` zurueck, wenn keine Druckplatte existiert oder die Liste zurueckgesetzt wird. Zahlreiche Methoden dereferenzieren diesen Zeiger direkt ohne Nullpruefung (`partplate_list.get_curr_plate()->empty()`, `->update_apply_result_invalid()`, `->can_slice()`). Dies fuehrt zu reproduzierbaren Abstuerzen (`EXCEPTION_ACCESS_VIOLATION`).
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp:12792
  bool plate_empty = partplate_list.get_curr_plate()->empty();
  ```
- **Loesungsansatz (Defensiver Fix):**
  Strikte Nullpruefung vor jedem Zugriff:
  ```cpp
  PartPlate* curr_plate = partplate_list.get_curr_plate();
  bool plate_empty = curr_plate ? curr_plate->empty() : true;
  ```

---

### [NPE-02] Ungesicherter Methodenaufruf auf `m_agent` in `Monitor.cpp`
- **Datei und Zeilen:** [Monitor.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Monitor.cpp#L361)
- **Schweregrad:** HOCH (CWE-476: NULL Pointer Dereference)
- **Ursachenanalyse (Root Cause):**
  In Zeile 350 wird `if (m_agent)` geprueft, aber in Zeile 361 wird `m_agent->refresh_connection();` ungeschuetzt aufgerufen. Der umschliessende `catch (...)`-Block faengt unter Windows/Linux keine CPU-Zugriffsverletzungen ab.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/Monitor.cpp:360
  try {
      m_agent->refresh_connection();
  }
  catch (...) { ; }
  ```
- **Loesungsansatz (Defensiver Fix):**
  ```cpp
  if (m_agent) {
      try {
          m_agent->refresh_connection();
      } catch (const std::exception& e) {
          BOOST_LOG_TRIVIAL(error) << e.what();
      }
  }
  ```

---

### [NPE-03] Gefaehrlicher Cast von `std::wstring` zu `char*` in `Http.cpp`
- **Datei und Zeilen:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L676)
- **Schweregrad:** KRITISCH (CWE-843: Access of Resource Using Incompatible Type)
- **Ursachenanalyse (Root Cause):**
  In `Http::form_add_file(const std::wstring& name, ...)` wird `(char*)name.c_str()` ausgefuehrt. Unter Windows ist `wchar_t` 2 Bytes breit (UTF-16 LE). Die direkte Reinterpretation als `char*` interpretiert das zweite Null-Byte des ersten Zeichens als Stringende. Der Feldname wird verstuemmelt und cURL greift fehlerhaft auf den Speicher zu.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp:674
  Http& Http::form_add_file(const std::wstring& name, const fs::path& path, boost::filesystem::ifstream::off_type offset, size_t length)
  {
      if (p) { p->form_add_file((char*)name.c_str(), path.c_str(), nullptr, offset, length); }
      return *this;
  }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Konvertierung von `std::wstring` nach `std::string` (UTF-8):
  ```cpp
  Http& Http::form_add_file(const std::wstring& name, const fs::path& path, boost::filesystem::ifstream::off_type offset, size_t length)
  {
      if (p) { 
          std::string utf8_name = boost::nowide::narrow(name);
          p->form_add_file(utf8_name.c_str(), path.string().c_str(), nullptr, offset, length); 
      }
      return *this;
  }
  ```

---

### [NPE-04] Ungueltiger Stack-Zustand und Nullzeigerzugriff im AMF-Parser (`AMF.cpp`)
- **Datei und Zeilen:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L250-L290)
- **Schweregrad:** HOCH (CWE-476)
- **Ursachenanalyse (Root Cause):**
  Wenn in `AMFParserContext::startElement` ein `<object>`-Tag ohne `id`-Attribut gefunden wird, bricht `this->stop()` ab, laesst aber den Stack `m_path` unbereinigt. Anschliessende Element-Handler dereferenzieren `m_object`, welches `nullptr` ist.
- **Loesungsansatz (Defensiver Fix):**
  Vor jedem Zugriff auf `m_object` oder `m_volume` explizite Nullpruefung einbauen.

---

## 6. Speicher-, Socket- und Handlelecks

### [LEAK-01] Permanenter Speicherverlust des Expat-Parsers in `AMF.cpp`
- **Datei und Zeilen:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L958-L1021)
- **Schweregrad:** HOCH (CWE-401: Missing Release of Memory after Effective Lifetime)
- **Ursachenanalyse (Root Cause):**
  `XML_Parser parser = XML_ParserCreate(nullptr);` wird in `extract_model_from_archive` erzeugt. Weder im regulaeren Ruecksprung noch in Fehlerausgaengen wird `XML_ParserFree(parser);` aufgerufen. Jeder Ladevorgang einer AMF-Archivdatei leakt den gesamten Expat-Parserkontext samt XML-Symboltabellen.
- **Loesungsansatz (Defensiver Fix):**
  Einsatz eines RAII Scope Guards:
  ```cpp
  XML_Parser parser = XML_ParserCreate(nullptr);
  if (!parser) return false;
  auto parser_cleanup = boost::make_scope_exit([&parser]() { XML_ParserFree(parser); });
  ```

---

### [LEAK-02] Leck saemtlicher `Ams`-Objekte im `MachineObject`-Destruktor (`DeviceManager.cpp`)
- **Datei und Zeilen:** [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L665-L674)
- **Schweregrad:** HOCH (CWE-401)
- **Ursachenanalyse (Root Cause):**
  Der Destruktor iteriert ueber `amsList`, loescht die `trayList`-Elemente ueber `delete tray_it->second;`, ruft aber niemals `delete it->second;` auf, bevor `amsList.clear()` ausgefuehrt wird. Saemtliche via `new Ams(...)` instanziierten Objekte verbleiben als Speicherlecks im Heap.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp:665
  for (auto it = amsList.begin(); it != amsList.end(); it++) {
      for (auto tray_it = it->second->trayList.begin(); tray_it != it->second->trayList.end(); tray_it++) {
          if (tray_it->second) {
              delete tray_it->second;
              tray_it->second = nullptr;
          }
      }
      it->second->trayList.clear();
      // FEHLT: delete it->second;
  }
  amsList.clear();
  ```
- **Loesungsansatz (Defensiver Fix):**
  ```cpp
  for (auto it = amsList.begin(); it != amsList.end(); it++) {
      for (auto tray_it = it->second->trayList.begin(); tray_it != it->second->trayList.end(); tray_it++) {
          delete tray_it->second;
      }
      it->second->trayList.clear();
      delete it->second;
  }
  amsList.clear();
  ```

---

### [LEAK-03] Socket- und Resolver-Leck bei Verbindungsfehlern in `WCP_Logger::run` (`SSWCP.cpp`)
- **Datei und Zeilen:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L120-L130)
- **Schweregrad:** HOCH (CWE-401 / CWE-775)
- **Ursachenanalyse (Root Cause):**
  `socket = new tcp::socket(io_ctx); resolver = new tcp::resolver(io_ctx);` werden ueber rohes `new` erzeugt. Schlaegt `asio::connect(*socket, ...)` fehl (z. B. Port 50000 geschlossen), kehrt die Methode sofort mit `return false;` zurueck. Bei jedem Aufruf von `run()` gehen Sockets und OS-Handles verloren.
- **Loesungsansatz (Defensiver Fix):**
  Kapselung in `std::unique_ptr<tcp::socket>` und `std::unique_ptr<tcp::resolver>`.

---

### [LEAK-04] Nicht modaler Dialog-Leck in `SSWCP_Instance::sw_OpenOrcaWebview`
- **Datei und Zeilen:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L728-L733)
- **Schweregrad:** MITTEL (CWE-401)
- **Ursachenanalyse (Root Cause):**
  `auto dialog = new WebUrlDialog(); dialog->Show();` erzeugt einen Dialog ohne Parent und ohne Zerstoerungslogik. Bei mehrfachem Aufruf leaken Fenster-Handles und Speicher.
- **Loesungsansatz (Defensiver Fix):**
  Event-Handler fuer `wxEVT_CLOSE_WINDOW` mit Aufruf von `Destroy()` sicherstellen.

---

## 7. Dangling Pointers und Use After Free

### [UAF-01] Use After Free durch `io_thread.detach()` im `Http`-Destruktor (`Http.cpp`)
- **Datei und Zeilen:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L539-L545)
- **Schweregrad:** KRITISCH (CWE-416: Use After Free)
- **Ursachenanalyse (Root Cause):**
  Wird ein `Http`-Objekt freigegeben, trennt `Http::~Http()` den laufenden Worker-Thread via `p->io_thread.detach();` ab. Unmittelbar danach wird `std::unique_ptr<priv> p` deallokiert. Der abgetrennte Thread greift im Hintergrund weiterhin auf die Instanzvariablen von `priv` (`curl`, `buffer`, etc.) zu, was zum Speicherzugriffsfehler und Absturz fuehrt.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp:539
  Http::~Http()
  {
      assert(! p || ! p->putFile);
      if (p && p->io_thread.joinable()) {
          p->io_thread.detach();
      }
  }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Kooperatives Abbrechen des I/O-Vorgangs und geordnetes `join()` im Destruktor:
  ```cpp
  Http::~Http()
  {
      if (p) {
          p->cancel();
          if (p->io_thread.joinable()) {
              p->io_thread.join();
          }
      }
  }
  ```

---

### [UAF-02] Use After Free & Race Condition in `MqttClient::CheckConnected()` (`MQTT.cpp`)
- **Datei und Zeilen:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L407-L425)
- **Schweregrad:** HOCH (CWE-416 / CWE-362)
- **Ursachenanalyse (Root Cause):**
  `std::async(std::launch::async, [this]() { ... })` erfasst den rohen `this`-Zeiger. Wird `MqttClient` vor Beendigung der asynchronen Funktion zerstoert, greift die Task auf freigegebenen Speicher zu.
- **Loesungsansatz (Defensiver Fix):**
  Verwendung von `std::enable_shared_from_this` und Erfassung eines `std::weak_ptr`.

---

## 8. Deadlocks und Thread-Hangs

### [DLK-01] Unendlicher Thread-Block ohne Timeout in `WebSocketClient::receive` (`WebSocketClient.hpp`)
- **Datei und Zeilen:** [WebSocketClient.hpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/WebSocketClient.hpp#L67-L76)
- **Schweregrad:** HOCH (CWE-834: Excessive Iteration / Hang)
- **Ursachenanalyse (Root Cause):**
  In `WebSocketClient::receive(int timeout = 0)` wird der Parameter `timeout` voellig ignoriert. `ws_.read(buffer);` blockiert synchron und unbegrenzt. Wenn der Moonraker- oder Klipper-Dienst die TCP-Verbindung nicht sauber schliesst, haengt der aufrufende Thread dauerhaft fest.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/WebSocketClient.hpp:67
  std::string receive(int timeout = 0){
      beast::flat_buffer buffer;
      ws_.read(buffer);
      return beast::buffers_to_string(buffer.data());
  }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Implementierung eines echten Stream-Timeouts:
  ```cpp
  std::string receive(int timeout_seconds = 5) {
      beast::flat_buffer buffer;
      beast::get_lowest_layer(ws_).expires_after(std::chrono::seconds(timeout_seconds > 0 ? timeout_seconds : 5));
      ws_.read(buffer);
      return beast::buffers_to_string(buffer.data());
  }
  ```

---

### [DLK-02] Blockierender `std::future`-Destruktor in `MqttClient::CheckConnected`
- **Datei und Zeilen:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L407)
- **Schweregrad:** MITTEL (CWE-833: Deadlock / Thread Hang)
- **Ursachenanalyse (Root Cause):**
  Der Rueckgabewert von `std::async(std::launch::async, ...)` wird einer lokalen Variablen zugewiesen. Bei Verlassen des Blocks blockiert der Destruktor von `std::future` synchron, bis der Thread fertig ist. Dies blockiert den UI-Thread bei Netzwerkunterbrechungen.
- **Loesungsansatz (Defensiver Fix):**
  Einsatz eines dedizierten Worker-Threads oder nicht-blockierendes Abfragen.

---

## 9. Race Conditions und Concurrency

### [RCE-01] Unsynchronisierte cURL-Initialisierung und Datenrennen auf `Http::cancel` (`Http.cpp`)
- **Datei und Zeilen:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L189), [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L839)
- **Schweregrad:** HOCH (CWE-362: Race Condition)
- **Ursachenanalyse (Root Cause):**
  `Http::tls_global_init()` enthaelt Aufrufe von `curl_global_init()`. Werden mehrere `Http`-Instanzen zeitgleich auf verschiedenen Threads erzeugt, erfolgt der Aufruf ungeschuetzt und fuehrt zu undefiniertem Verhalten in libcurl. Zudem ist `cancel` als gewoehnliches `bool` deklariert und wird ueber Thread-Grenzen hinweg ohne `std::atomic` gelesen und geschrieben.
- **Loesungsansatz (Defensiver Fix):**
  Absicherung von `tls_global_init` mittels `std::call_once` und Deklaration von `std::atomic<bool> cancel;`.

---

## 10. Logische Fehler und Parsingfehler

### [LOG-01] Fehlende `break`-Anweisung (Fallthrough) in `AMFParserContext::characters` (`AMF.cpp`)
- **Datei und Zeilen:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L489-L505)
- **Schweregrad:** HOCH (CWE-484: Omitted Break Statement in Switch)
- **Ursachenanalyse (Root Cause):**
  Im Switch-Statement von `AMFParserContext::characters` fehlt nach `case 6:` (Vertex-Tags) das `break;`. Die Ausfuehrung faellt ungehindert in `case 7:` (Koordinaten-Tags) durch. Dies fuehrt zu Datenkorruption und falschen Koordinatenwerten beim Parsen von AMF-Geometrien.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp:489
          case 6:
              switch (m_path.back()) {
                  case NODE_TYPE_VERTEX1: m_value[0].append(s, len); break;
                  case NODE_TYPE_VERTEX2: m_value[1].append(s, len); break;
                  case NODE_TYPE_VERTEX3: m_value[2].append(s, len); break;
                  default: break;
              }
              // FEHLT: break;
          case 7:
              switch (m_path.back()) {
                  case NODE_TYPE_COORDINATE_X: m_value[0].append(s, len); break;
                  case NODE_TYPE_COORDINATE_Y: m_value[1].append(s, len); break;
                  case NODE_TYPE_COORDINATE_Z: m_value[2].append(s, len); break;
                  default: break;
              }
  ```
- **Loesungsansatz (Defensiver Fix):**
  Explizites `break;` nach Zeile 495 und Zeile 502 ergaenzen.

---

### [LOG-02] Fehlerhafte Pfadkuerzung und String-Korruption in `WebSocketClient::connect`
- **Datei und Zeilen:** [WebSocketClient.hpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/WebSocketClient.hpp#L46-L47)
- **Schweregrad:** MITTEL (CWE-704: Incorrect Type Conversion or Cast)
- **Ursachenanalyse (Root Cause):**
  `_host[host.size()-1] = ' ';` ueberschreibt das letzte Zeichen mit einem Nullbyte, aendert aber nicht die String-Groesse `_host.size()`. Der an `ws_.handshake(_host, path)` uebergebene HTTP-Host-Header enthaelt ein eingebettetes Nullbyte, was bei standardkonformen WebSocket-Servern zu Handshake-Fehlern fuehrt.
- **Loesungsansatz (Defensiver Fix):**
  ```cpp
  if (!_host.empty() && _host.back() == '/') {
      _host.pop_back();
  }
  ```

---

## 11. Schnittstellen-, Firmware-, API- und Datentypkonflikte (OrcaSlicer vs. u1-klipper)

### [IF-01] Inkonsistente G-Code-Parametersyntax im Start-G-Code (`G28 Z Z_OFFSET -0.07` vs. `Z_OFFSET=-0.07`)
- **OrcaSlicer-Datei:** [Snapmaker U1 (0.4 nozzle).json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/Snapmaker%20U1%20(0.4%20nozzle).json#L51) (sowie 0.2, 0.6, 0.8)
- **Klipper-Firmware:** [homing_xyz_override.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/homing_xyz_override.py#L269)
- **Schweregrad:** HOCH (Syntax- und Parsinginkonsistenz)
- **Ursachenanalyse (Root Cause):**
  Im Start-G-Code aller U1-Maschinenprofile wird fuer "High Temp Plate" und "Graphic Effect Plate" der Befehl `G28 Z Z_OFFSET -0.07` (ohne Gleichheitszeichen) ausgegeben. Drei Zeilen darunter verwendet dasselbe Profil fuer `BED_MESH_CALIBRATE` die Syntax `Z_OFFSET=-0.07` (mit Gleichheitszeichen). In standardkonformem Klipper fuehrt das Fehlen des Gleichheitszeichens bei erweiterten G-Code-Befehlen zu Parserfehlern.
- **Betroffener Code:**
  ```json
  {if curr_bed_type=="High Temp Plate"}
  G28 Z Z_OFFSET -0.07
  {elsif curr_bed_type=="Graphic Effect Plate"}
  G28 Z Z_OFFSET -0.07
  {else}
  G28 Z
  {endif}
  ```
- **Loesungsansatz (Defensiver Fix):**
  G-Code-Parameter einheitlich mit Gleichheitszeichen notieren:
  ```gcode
  G28 Z Z_OFFSET=-0.07
  ```

---

### [IF-02] Nicht existierender Parameter `Z_OFFSET` in `BED_MESH_CALIBRATE` fuehrt zu verlorenem Z-Offset
- **OrcaSlicer-Datei:** [Snapmaker U1 (0.4 nozzle).json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/Snapmaker%20U1%20(0.4%20nozzle).json#L51)
- **Klipper-Firmware:** [bed_mesh.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/bed_mesh.py#L634-L675)
- **Schweregrad:** HOCH (Stiller Funktionsverlust / Kalibrierungsfehler)
- **Ursachenanalyse (Root Cause):**
  OrcaSlicer sendet `BED_MESH_CALIBRATE PROBE_COUNT=11,11 Z_OFFSET=-0.07`. Das Klipper-Modul `bed_mesh.py` besitzt in `update_config` und `cmd_BED_MESH_CALIBRATE` ueberhaupt keinen Parameter namens `Z_OFFSET`! Der uebergebene Offset wird vollstaendig ignoriert. Die beabsichtigte Duesenabstandskompensation fuer Smooth PEI und Graphic Effect Plates wird waehrend der Bettvermessung nicht angewendet, was zu Haftungsproblemen oder Duesenkratzern fuehrt.
- **Loesungsansatz (Defensiver Fix):**
  Z-Offset ueber den dafuer vorgesehenen Klipper-Standardbefehl `SET_GCODE_OFFSET Z_ADJUST=-0.07` nach der Kalibrierung anwenden.

---

### [IF-03] Namens- und Variablenkonflikt bei Duesenabfrage (`nozzle_diameters` vs. `nozzle_diameter` & `nozzle_volume_types` vs. `filament_volume_type`)
- **OrcaSlicer-Datei:** [GatewayDevice.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/GatewayDevice.cpp#L195-L204)
- **Klipper-Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L73-L80)
- **Schweregrad:** HOCH (Schnittstellen- und Datenaustauschfehler)
- **Ursachenanalyse (Root Cause):**
  In `GatewayDevice.cpp` sucht OrcaSlicer nach den JSON-Arrays `"nozzle_diameters"` und `"nozzle_volume_types"` (Plural). In `print_task_config_2.json` der Firmware heissen diese Felder jedoch `"nozzle_diameter"` (Singular) und `"filament_volume_type"`. Infolgedessen gibt `find_array` stets `nullptr` zurueck; Duesendurchmesser und High-Flow-Konfigurationen koennen vom Slicer nicht von der Firmware gelesen werden.
- **Betroffener Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/GatewayDevice.cpp:195
  if (const nlohmann::json* values = find_array(config, "nozzle_diameters"); values != nullptr)
  ...
  if (const nlohmann::json* values = find_array(config, "nozzle_volume_types"); values != nullptr)
  ```
- **Loesungsansatz (Defensiver Fix):**
  In `GatewayDevice.cpp` beide Schreibweisen unterstuetzen:
  ```cpp
  const nlohmann::json* values = find_array(config, "nozzle_diameters");
  if (!values) values = find_array(config, "nozzle_diameter");
  ...
  const nlohmann::json* flow_values = find_array(config, "nozzle_volume_types");
  if (!flow_values) flow_values = find_array(config, "filament_volume_type");
  ```

---

### [IF-04] Syntaxkonflikt bei `FLOW_CALIBRATE_EXTRUDERS` zwischen `SET_PRINT_PREFERENCES` und `SET_PRINT_TASK_PARAMETERS`
- **Klipper-Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L752) vs. [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L1188)
- **Schweregrad:** HOCH (Firmware-Absturz / G-Code-Befehlsfehler)
- **Ursachenanalyse (Root Cause):**
  In `cmd_SET_PRINT_PREFERENCES` wird der Parameter `FLOW_CALIBRATE_EXTRUDERS` per `flow_calibrate_extruders.split(',')` als reine Kommaliste geparst (z. B. `"0,1,2"`). In `cmd_SET_PRINT_TASK_PARAMETERS` parst dieselbe Datei denselben Parameter hingegen mit `self._parse_str_to_list(flow_calibrate_extruders)`, welches `ast.literal_eval` ausfuehrt und zwingend Python-Klammern erwartet (z. B. `"[0, 1, 2]"`). Wird das Kommaformat an `SET_PRINT_TASK_PARAMETERS` gesendet, wirft Klipper eine Exception (`ValueError: Not a list`). Wird umgekehrt das Listenformat an `SET_PRINT_PREFERENCES` gesendet, stuerzt `int("[0")` mit `ValueError` ab.
- **Loesungsansatz (Defensiver Fix):**
  Eine robuste Hilfsfunktion implementieren, die beide Formate transparent unterstuetzt:
  ```python
  def _parse_int_list(self, param_str):
      clean_str = param_str.strip("[]()")
      if not clean_str:
          return []
      return [int(x.strip()) for x in clean_str.split(',') if x.strip()]
  ```

---

### [IF-05] Datentyp-Fehlpruefung in `NOZZLE_DIAMETER_LIST` (`isinstance(..., float)` verwirft Integer-Werte)
- **Klipper-Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L1248-L1254)
- **Schweregrad:** HOCH (Vollstaendiger Konfigurationsverlust)
- **Ursachenanalyse (Root Cause):**
  In Zeile 1249 prueft `print_task_config.py`:
  `if not isinstance(nozzle_diameter_list[i], float): raise gcmd.error(...)`
  In Python ist `isinstance(0, float)` oder `isinstance(1, float)` stets **False**. Wenn OrcaSlicer oder der Benutzer fuer unbenutzte Extruder `0` oder fuer 1.0mm Duesen `1` uebergibt, schlaegt die Pruefung fehl, der gesamte Block wird abgefangen und die Duesendurchmesser werden auf Nullen zurueckgesetzt. Bei `nozzle_temp` (Zeile 1264) wurde hingegen korrekt `(float, int)` geprueft.
- **Loesungsansatz (Defensiver Fix):**
  ```python
  if not isinstance(nozzle_diameter_list[i], (float, int)):
      raise gcmd.error("[print_task_config] Invalid NOZZLE_DIAMETER")
  ```

---

### [IF-06] Falscher Extruderindex-Vergleich bei der Duesenpruefung in `print_task_config.py`
- **Klipper-Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L1402)
- **Schweregrad:** KRITISCH (Fehlerhafter Druckabbruch)
- **Ursachenanalyse (Root Cause):**
  Beim Abgleich der Duesendurchmesser vergleicht die Schleife:
  `if abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001:`
  Fuer JEDEN Extruder `i` (0, 1, 2, 3) wird gegen `nozzle_diameter[0]` (Extruder 0) verglichen anstatt gegen `nozzle_diameter[i]`. Wird Extruder 0 im Druck nicht verwendet (Durchmesser 0) und mit Extruder 1 (0.4mm) gedruckt, bricht Klipper den Druck sofort mit `nozzle diameter mismatch: f1_0 != e1_0.4` ab.
- **Betroffener Code:**
  ```python
  // E:/KI Projekte/u1-klipper/klippy/extras/print_task_config.py:1400
  for i in range(PHYSICAL_EXTRUDER_NUM):
      if tmp_print_task_config['extruders_used'][i]:
          if abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001:
              exception_code = 14
              raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
                               f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][0]} != e{i}_{actual_nozzle_diameter[i]}")
  ```
- **Loesungsansatz (Defensiver Fix):**
  Index `[i]` statt `[0]` verwenden:
  ```python
  for i in range(PHYSICAL_EXTRUDER_NUM):
      if tmp_print_task_config['extruders_used'][i]:
          if abs(tmp_print_task_config_2['nozzle_diameter'][i] - actual_nozzle_diameter[i]) > 0.001:
              exception_code = 14
              raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
                               f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][i]} != e{i}_{actual_nozzle_diameter[i]}")
  ```

---

### [IF-07] Kollision von Farbcode-Formaten (6-stelliges RGB vs. 8-stelliges RGBA vs. `#`-Praefix)
- **OrcaSlicer-Datei:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L33-L37), [GatewayDevice.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/GatewayDevice.cpp#L141-L164)
- **Klipper-Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L218-L224)
- **Schweregrad:** HOCH (Konfigurationsreset auf Werkseinstellungen)
- **Ursachenanalyse (Root Cause):**
  OrcaSlicer erzeugt Farbcodes mit vorangestellter Raute (z. B. `#FCE94F` oder `#FFFFFFFF`). `print_task_config.py` in Klipper fuehrt in `_early_check` strikte Laengenpruefungen durch:
  `len(tmp_print_task_config['filament_color_rgba'][i]) != 8` und `len(tmp_print_task_config['filament_color_multi'][i]['colors'][j]) != 6`.
  Wird ein 7- oder 9-stelliger String mit `#` uebertragen, wirft `_early_check` einen `ValueError` und setzt die gesamte Konfiguration des Druckers auf `DEFAULT_PRINT_TASK_CONFIG` zurueck.
- **Loesungsansatz (Defensiver Fix):**
  Sowohl in OrcaSlicer (`NormalizeFilamentHexColor`) als auch in Klipper Fuehrungszeichen (`#`) vor der Validierung strikt abstreifen:
  ```python
  clean_color = color.lstrip('#').upper()
  ```

---

### [IF-08] Nicht existierende 5. und 6. Extruder sowie Koordinatenueberschreitung `X290`/`X300` in `fdm_U1.json`
- **OrcaSlicer-Datei:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L11-L183)
- **Klipper-Firmware:** [printer.cfg](file:///E:/KI%20Projekte/u1-klipper/lava/printer.cfg#L128) (`position_max: 271`), [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L9) (`PHYSICAL_EXTRUDER_NUM = 4`)
- **Schweregrad:** KRITISCH (Physischer Werkzeugkopf-Crash / Klipper-Notabschaltung)
- **Ursachenanalyse (Root Cause):**
  Das Basisprofil `fdm_U1.json` definiert 5 Extruder und enthaelt im Start-G-Code Verfahrbefehle bis `X290` und `X300` (`G0 X... 300`). Der physische Snapmaker U1 besitzt genau 4 Extruder und die X-Achse ist mechanisch auf `position_max: 271` limitiert. Fahrten ueber 271 mm fuehren zum Anschlagen des Druckkopfes oder zum Klipper-Schutzabbruch `Move out of range: 290`.
- **Loesungsansatz (Defensiver Fix):**
  Profilarrays in `fdm_U1.json` strikt auf 4 Extruder kuerzen und maximale Verfahrkoordinaten auf `X <= 270` begrenzen.

---

### [IF-09] Falscher Dateiname fuer Druckbett-Textur in `fdm_U1.json` (`Snapmaker U1_bed.svg`)
- **OrcaSlicer-Datei:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L10)
- **Vorhandene Datei:** `OrcaSlicer/resources/profiles/Snapmaker/Snapmaker U1_texture.svg`
- **Schweregrad:** MITTEL (Darstellungsfehler / Fehlende Textur)
- **Ursachenanalyse (Root Cause):**
  In `fdm_U1.json` ist `"bed_texture": "Snapmaker U1_bed.svg"` eingetragen. Die tatsaechlich im Ressourcenverzeichnis mitgelieferte Vektorgrafik heisst jedoch `Snapmaker U1_texture.svg`. OrcaSlicer kann die Textur nicht laden und das Druckbett wird ohne Gittergrafik dargestellt.
- **Loesungsansatz (Defensiver Fix):**
  In `fdm_U1.json` aendern:
  ```json
  "bed_texture": "Snapmaker U1_texture.svg"
  ```

---

### [IF-10] JSON-RPC-ID-Typ-Kollision bei String-IDs in `GatewayProtocol.cpp`
- **OrcaSlicer-Datei:** [GatewayProtocol.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/GatewayProtocol.cpp#L159-L174)
- **Moonraker/Klipper:** JSON-RPC 2.0 Spezifikation
- **Schweregrad:** MITTEL (Protokollkonflikt / Antwortverlust)
- **Ursachenanalyse (Root Cause):**
  In `classify_jsonrpc_message` wird geprueft `const bool has_id = id != message.end() && (id->is_number_integer() || id->is_string());`. Anschliessend wird jedoch `frame.id = id->is_number_integer() ? id->get<std::int64_t>() : 0;` gesetzt. Wenn Clients oder Gateways String-IDs verwenden (gemaess JSON-RPC 2.0 vollstaendig zulaessig), erhalten alle Antworten die ID 0. Dies fuehrt bei parallelen Aufrufen zu Antwortkollisionen und verworfenen Benachrichtigungen.
- **Loesungsansatz (Defensiver Fix):**
  ID im Frame als String oder `std::variant<std::int64_t, std::string>` speichern.

---

## 12. Zusammenfassung und Empfohlene Massnahmen

1. **Sicherheits-Patches:** Sofortige Schliessung der WebView-IPC-Luecke in `SSWCP.cpp` durch Whitelisting und Aktivierung der TLS-Zertifikatspruefung in `Http.cpp` und `MQTT.cpp`.
2. **Speichersicherheit und RAII:** Beseitigung von `sprintf` in `AMF.cpp`, Implementierung von `XML_ParserFree` und Ergaenzung der fehlenden `delete`-Aufrufe im `MachineObject`-Destruktor.
3. **Numerische Stabilitaet:** Absicherung der Division durch Null in `WipeTower2.cpp` fuer `n <= 1` und Einbau von Timeouts in `WebSocketClient.hpp`.
4. **Firmware- und Profil-Synchronisation:** 
   - Korrektur der Profilarrays in `fdm_U1.json` von 5 auf 4 physikalische Extruder.
   - Behebung des Indexfehlers `[0]` in `print_task_config.py:1402` fuer Duesendurchmesser.
   - Vereinheitlichung der Parameterschluessel (`nozzle_diameter` / `nozzle_diameters` sowie `filament_volume_type` / `nozzle_volume_types`).
   - Bereinigung von `#`-Praefixen bei Farbuebertragungen.
