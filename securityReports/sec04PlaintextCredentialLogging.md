# Vulnerability Advisory: SEC-04

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** SEC-04
- **Vulnerability Title:** Plaintext Logging of Sensitive TLS Certificates, CAs, and Credentials
- **Affected Components:** `src/slic3r/Utils/MQTT.cpp`
- **Vulnerability Classification:** CWE-532 (Insertion of Sensitive Information into Log File)
- **CVSS v3.1 Score:** 7.5 (HIGH) - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users connecting to MQTT brokers where log files are retained locally, exported in diagnostic bundles, or uploaded in public GitHub bug reports / crash dumps.
- **Threat Actor Profile:** Anyone gaining read access to the application log files, including third parties reviewing exported diagnostic archives.

---

## Executive Summary
In `MQTT.cpp`, diagnostic logging calls via `BOOST_LOG_TRIVIAL(info)` dump the full, unredacted plaintext strings of the Certificate Authority (`ca_content`), client certificate (`cert_content`), and broker credentials (`username_`) into standard application logs. Because users frequently attach these log files to public support tickets, forum posts, or bug reports, sensitive credentials and cryptographic keys are inadvertently leaked to unauthorized parties.

---

## Technical Root Cause Analysis
In `MqttClient::init_ssl`, the logger writes sensitive parameters into the log stream:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:74-75
BOOST_LOG_TRIVIAL(info) << "[MQTT_INFO] initializing MQTT SSL connection, server_address: " << server_address_
    << ", ca_content: " << ca_content << ", cert_content: " << cert_content << ", username: " << username_;
```

1. **Unmasked Output:** `ca_content` and `cert_content` contain the full PEM-encoded certificates.
2. **Persistent Storage:** Boost.Log writes this output to disk files located in the user's application data directory.
3. **Information Disclosure in Bug Reports:** When users generate support bundles or report connectivity problems, the full certificate strings and usernames are exposed.

---

## Steps to Reproduce
1. Launch OrcaSlicer with log level set to `info` or `debug`.
2. Connect to an MQTT printer configured with certificates and user credentials.
3. Open the log file located in the user directory (e.g., `%APPDATA%\OrcaSlicer\log\` or `~/.config/OrcaSlicer/log/`).
4. Search for `[MQTT_INFO] initializing MQTT SSL connection`.
5. Observe the complete PEM certificate text and username visible in plaintext.

---

## Attack Scenario & Threat Analysis
1. A user experiences connection trouble with their 3D printer network and opens an issue on a public repository (such as GitHub or a community forum).
2. The user attaches `orca_log.txt` as requested by standard troubleshooting instructions.
3. An attacker crawls the public issues, extracts the certificates, server addresses, and usernames from the log, and gains unauthorized administrative access to the network's printer message broker.

---

## Defensive Remediation & Verification

### Code Fix
Remove raw content strings from the log statement and record only metadata such as presence and length:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:74
BOOST_LOG_TRIVIAL(info) << "[MQTT_INFO] initializing MQTT SSL connection, server_address: " << server_address_
    << ", ca_len: " << ca_content.length() 
    << ", cert_len: " << cert_content.length() 
    << ", user_set: " << !username_.empty();
```

### Security Recommendations
- Establish an automated sanitization filter in the logging subsystem to scrub patterns matching `-----BEGIN CERTIFICATE-----`, `-----BEGIN PRIVATE KEY-----`, and passwords.
- Implement automated redaction in diagnostic bundle export wizards.
