# Vulnerability Advisory: SEC-05

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** SEC-05
- **Vulnerability Title:** Disabled TLS Server Certificate Verification in MQTT Client
- **Affected Components:** `src/slic3r/Utils/MQTT.cpp`
- **Vulnerability Classification:** CWE-295 (Improper Certificate Validation)
- **CVSS v3.1 Score:** 7.4 (HIGH) - `CVSS:3.1/AV:A/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users communicating with 3D printers via MQTT over TLS/SSL (port 8883 / secure websockets).
- **Threat Actor Profile:** Adjacent network attacker on the same local area network or Wi-Fi network.

---

## Executive Summary
In `MQTT.cpp`, during the construction of SSL/TLS connection options for the Paho MQTT C++ client, certificate verification is explicitly disabled via `ssl_opts.set_verify(false)`. Even though a CA certificate path may be specified via `set_trust_store()`, the client is explicitly told not to verify the broker's certificate identity or authenticity. This allows rogue MQTT brokers to intercept control commands, telemetry, and G-code streams transmitted between the slicer and printer.

---

## Technical Root Cause Analysis
In `MqttClient::init_ssl`, the SSL options are set as follows:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:122-124
mqtt::ssl_options ssl_opts;
ssl_opts.set_verify(false);
ssl_opts.set_enable_server_cert_auth(true);
```

1. **Explicit Bypass:** `ssl_opts.set_verify(false)` overrides certificate validation behavior in Eclipse Paho MQTT C.
2. **Conflicting Configuration:** While `set_enable_server_cert_auth(true)` is set, passing `false` to `set_verify` suppresses validation errors, accepting any TLS certificate presented by the server regardless of trust status.

---

## Steps to Reproduce
1. Start an MQTT broker with an untrusted, self-signed certificate on a local IP.
2. Direct OrcaSlicer's MQTT client to connect to that broker.
3. Observe that the client connects cleanly without warning, verifying that no root-of-trust check was enforced.

---

## Attack Scenario & Threat Analysis
1. An attacker on the local network initiates ARP cache poisoning targeting the 3D printer IP address.
2. The attacker runs a rogue MQTT broker with an arbitrary TLS certificate.
3. OrcaSlicer connects to the rogue broker, accepting the counterfeit certificate without error.
4. The attacker issues unauthorized printer control commands, cancels active prints, or injects malicious G-code into print tasks.

---

## Defensive Remediation & Verification

### Code Fix
Enable certificate verification in `MQTT.cpp`:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:122
mqtt::ssl_options ssl_opts;
ssl_opts.set_verify(true);
ssl_opts.set_enable_server_cert_auth(true);
```

If self-signed certificates must be supported for local network printers, require the user to explicitly upload or trust the printer's specific root certificate rather than disabling verification globally.
