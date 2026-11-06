# Vulnerability Advisory: BOF-04

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** BOF-04
- **Vulnerability Title:** Character Buffer Length Under-Read and Boundary Desynchronization with Multi-Byte UTF-8 in WCP_Logger
- **Affected Components:** `src/slic3r/GUI/SSWCP.cpp`
- **Vulnerability Classification:** CWE-125 (Out-of-bounds Read), CWE-135 (Length Calculation Inconsistency with Multi-Byte Characters)
- **CVSS v3.1 Score:** 5.3 (MEDIUM) - `CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:L`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users generating logs containing non-ASCII characters (e.g., German umlauts `ä, ö, ü`, accented characters, Chinese/Japanese paths or filenames) communicating with local logging or daemon endpoints.
- **Threat Actor Profile:** User or process causing multi-byte characters to be written to the logging queue.

---

## Executive Summary
In `WCP_Logger::worker` within `SSWCP.cpp`, log messages are transmitted over a TCP socket via `asio::write`. The code converts a `wxString` to UTF-8 using `log.ToUTF8()`, but computes the buffer length using `log.length() + 1`. In wxWidgets under Windows, `log.length()` returns the number of UTF-16 code units (character count), whereas `log.ToUTF8()` returns a buffer of UTF-8 encoded bytes. Because multi-byte UTF-8 characters require between 2 and 4 bytes per character, the byte length supplied to `asio::buffer` is shorter than the actual encoded payload. This causes truncated network writes, corrupted multi-byte sequences, or parsing boundary desynchronization on the receiving socket.

---

## Technical Root Cause Analysis
In `WCP_Logger::worker`:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp:189-196
wxString log = m_log_que.front();
m_log_que.pop();
m_log_mtx.unlock();

log += "\n";
boost::system::error_code ec;
std::size_t bytes_transferred = asio::write(*socket, asio::buffer(log.ToUTF8().data(), log.length() + 1), ec);
```

1. **Length Mismatch:** For an ASCII string of 10 characters, `log.length()` is 10 and `log.ToUTF8().length()` is 10. For a string containing 10 multi-byte characters (e.g., 10 German umlauts or Chinese characters), `log.length()` is 10, but the UTF-8 byte length is 20 to 30 bytes.
2. **Buffer Truncation:** Passing `log.length() + 1` sends only 11 bytes of a 20-30 byte buffer, truncating characters mid-sequence and sending corrupted byte streams to the receiver.
3. **Temporary Buffer Binding:** `log.ToUTF8()` creates a temporary `wxScopedCharBuffer`. While valid in the immediate expression, binding length from a different property invites boundary desynchronization.

---

## Steps to Reproduce
1. Log a message containing multi-byte characters (e.g., `Druckerüberwachung für Modell "Würfel.stl"`).
2. Inspect the received socket stream on the listening TCP port (e.g., `127.0.0.1:50000`).
3. Observe that the payload is truncated mid-message and multi-byte characters at the end are split or dropped.

---

## Defensive Remediation & Verification

### Code Fix
Extract the `wxScopedCharBuffer` into a local variable and use its exact byte length:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp:193
log += "\n";
boost::system::error_code ec;
const wxScopedCharBuffer utf8_buf = log.ToUTF8();
std::size_t bytes_transferred = asio::write(*socket, asio::buffer(utf8_buf.data(), utf8_buf.length()), ec);
if (ec) {
    BOOST_LOG_TRIVIAL(error) << "[WCP_Logger] Write failed: " << ec.message();
}
```

### Security Recommendations
- Never mix character counts (`length()`) with byte buffer sizes when dealing with Unicode encodings.
- Store UTF-8 encoded byte arrays in intermediate queues rather than re-encoding repeatedly across threads.
