# Vulnerability Advisory: SEC-03

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** SEC-03
- **Vulnerability Title:** Insecure Temporary File Creation for Private Keys in MQTT Client
- **Affected Components:** `src/slic3r/Utils/MQTT.cpp`
- **Vulnerability Classification:** CWE-377 (Insecure Temporary File), CWE-59 (Improper Link Resolution Before File Access)
- **CVSS v3.1 Score:** 7.8 (HIGH) - `CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** Multi-user desktop systems or shared workstations running OrcaSlicer where printer communication takes place over MQTT with mutual TLS (mTLS) or certificate authentication.
- **Threat Actor Profile:** Local unprivileged user or malicious background process running on the same host machine.

---

## Executive Summary
In `MQTT.cpp`, when configuring TLS/SSL client authentication, certificate data and cryptographic private keys are written out to files in the global system temporary directory (`/tmp` on Linux/macOS or `%TEMP%` on Windows). The filenames are constructed using predictable patterns (`"key_" + client_id + std::to_string(int64_t(this)) + ".key"`), and files are created using standard file streams without restrictive access control lists (ACLs) or exclusive file creation flags (`O_EXCL`). This allows local attackers to harvest private keys or launch symlink attacks to overwrite arbitrary files owned by the user running OrcaSlicer.

---

## Technical Root Cause Analysis
In `MqttClient::init_ssl`, the application creates disk files for cryptographic secrets:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:84-118
boost::filesystem::path temp_dir = boost::filesystem::temp_directory_path();
boost::filesystem::path ca_path = temp_dir / ("ca_" + client_id + std::to_string(int64_t(this)) + ".crt");
...
boost::filesystem::path key_path = temp_dir / ("key_" + client_id + std::to_string(int64_t(this)) + ".key");
if (!key_content.empty()) {
    boost::filesystem::ofstream key_file(key_path);
    key_file << key_content;
    key_file.close();
    if (!key_file) {
        throw std::runtime_error("Failed to write private key temporary file");
    }
}
```

1. **Predictable Filenames:** The path is derived solely from the client identifier and memory address of `this`, both of which can be inferred or brute-forced by local processes.
2. **Missing Permissions Restriction:** `boost::filesystem::ofstream` creates files under the default process umask. On standard systems, this yields permissions `0644` or `0666`, allowing any local user to read the file.
3. **No Symlink Protection:** Existing files or symlinks at the target path are opened and truncated rather than failing atomically.

---

## Steps to Reproduce
1. Launch OrcaSlicer on a multi-user Linux or macOS system.
2. Connect to an MQTT-enabled printer requiring TLS client certificate authentication.
3. In a separate terminal session under a different unprivileged user account:
   ```bash
   ls -la /tmp/key_*.key
   cat /tmp/key_*.key
   ```
4. Observe that the private key file is world-readable and contains the full RSA/EC private key.

---

## Attack Scenario & Threat Analysis
1. A multi-user laboratory, makerspace, or enterprise workstation runs OrcaSlicer to control high-value additive manufacturing machines.
2. A low-privileged local user creates pre-crafted symbolic links in `/tmp` pointing to a target file owned by the victim (e.g., `~/.bashrc` or configuration files).
3. When OrcaSlicer initializes an MQTT connection, it follows the symlink and overwrites the target file with the certificate data.
4. Concurrently, the attacker copies the printer's private keys, granting them unauthorized access to impersonate the printer or client on the local MQTT message broker.

---

## Defensive Remediation & Verification

### Code Fix
Avoid writing private keys to disk altogether by passing them directly into the SSL/TLS context in memory, or use secure temporary file creation with exclusive mode (`0600` permissions):

```cpp
#ifdef _WIN32
// Windows: Ensure restrictive DACL or use secure temp directory within user profile
boost::filesystem::path temp_dir = boost::filesystem::path(wxStandardPaths::Get().GetUserConfigDir().ToStdString());
#else
// POSIX: Use mkstemp() with umask 077
char temp_template[] = "/tmp/orca_key_XXXXXX";
int fd = mkstemp(temp_template);
if (fd != -1) {
    fchmod(fd, 0600);
    write(fd, key_content.data(), key_content.size());
    close(fd);
    key_path = temp_template;
}
#endif
```

Ideally, leverage Paho MQTT C++ memory-based SSL options (`ssl_options::set_key_store_memory`) if supported by the underlying OpenSSL build to completely prevent plaintext disk writes.
