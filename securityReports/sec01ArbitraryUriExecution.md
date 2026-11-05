# Vulnerability Advisory: SEC-01

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** SEC-01
- **Vulnerability Title:** Arbitrary URI Scheme Execution and Remote Code Execution via WebView IPC
- **Affected Components:** `src/slic3r/GUI/SSWCP.cpp`, `src/slic3r/GUI/PrinterWebView.cpp`
- **Vulnerability Classification:** CWE-20 (Improper Input Validation), CWE-78 (OS Command Injection), CWE-937 (Using Components with Known Vulnerabilities)
- **CVSS v3.1 Score:** 9.6 (CRITICAL) - `CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users utilizing the integrated printer web view feature on Windows, macOS, or Linux, connecting to local or remote printer interfaces (Klipper/Fluidd, Mainsail, OctoPrint, or external web endpoints).
- **Threat Actor Profile:** Remote or local network attacker capable of serving or manipulating web content loaded inside `PrinterWebView` (e.g., via compromised printer web interfaces, MitM attacks on HTTP connections, or malicious redirects).

---

## Executive Summary
A critical security vulnerability exists in the inter-process communication (IPC) layer between the embedded `PrinterWebView` and the native OrcaSlicer desktop process. Script messages dispatched by JavaScript inside the embedded browser are forwarded without origin validation or URI scheme filtering to `SSWCP_Instance::sw_OpenBrowser()`. The method subsequently invokes `wxLaunchDefaultBrowser()`, which delegates directly to the operating system shell (`ShellExecuteEx` on Windows). An attacker can supply arbitrary protocol schemes (`file:///`, `smb://`, `ms-msdt:`, `calculator:`, `powershell:`) to execute local applications or trigger remote code execution.

---

## Technical Root Cause Analysis
In `PrinterWebView::OnScriptMessage`, all script messages dispatched from the embedded browser instance are accepted unconditionally:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/PrinterWebView.cpp:244
void PrinterWebView::OnScriptMessage(wxWebViewEvent& evt) {
    SSWCP::handle_web_message(evt.GetString().ToUTF8().data(), m_browser);
}
```

The message is routed to `SSWCP_Instance::sw_OpenBrowser()` in `SSWCP.cpp`:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp:692
void SSWCP_Instance::sw_OpenBrowser() {
    try {
        std::string url = m_param_data.count("url") ? m_param_data["url"].get<std::string>() : "";
        wxString wx_url  = wxString::FromUTF8(url);

        std::weak_ptr<SSWCP_Instance> weak_self = shared_from_this();
        wxGetApp().CallAfter([wx_url, weak_self]() {
            auto self = weak_self.lock();
            if (!self) {
                return;
            }
            bool res = wxLaunchDefaultBrowser(wx_url);
            if (!res) {
                self->handle_general_fail(-1, "Open browser failed");
            } else {
                self->send_to_js();
                self->finish_job();
            }
        });
    }
    catch (std::exception& e) {
        handle_general_fail();
    }
}
```

1. **Missing Origin Verification:** No check verifies that the event originates from a trusted local domain or trusted printer interface.
2. **Missing Scheme Sanitization:** The URL string is parsed directly without validating the protocol against an allowlist.
3. **Execution of Dangerous Protocol Handlers:** Under Windows, passing non-HTTP protocol handlers to `wxLaunchDefaultBrowser` invokes whatever application is registered for that scheme.

---

## Steps to Reproduce
1. Configure an internal printer web address or proxy server serving an HTML test document.
2. From within the web document's JavaScript execution context, dispatch a message to the native host container:
   ```javascript
   window.chrome.webview.postMessage(JSON.stringify({
       cmd: "sw_OpenBrowser",
       param_data: {
           url: "calculator://"
       }
   }));
   ```
3. Observe that OrcaSlicer's main thread receives the IPC event and immediately launches the registered system calculator application without prompt or warning.

---

## Attack Scenario & Threat Analysis
1. An attacker on the local network (or hosting a shared printer interface accessed by an engineer) serves an interface page.
2. The user navigates to the "Device" tab in OrcaSlicer to monitor printing progress.
3. The page executes JavaScript in the background that issues a message containing a dangerous URI handler (such as a crafted protocol triggering a binary download from an SMB share, or invoking local tools with argument injection).
4. The host operating system executes the external command under the privileges of the active desktop user.

---

## Defensive Remediation & Verification

### Code Fix
Implement strict protocol allowlisting allowing only `http://` and `https://` URLs, and restrict target domains where appropriate:

```cpp
void SSWCP_Instance::sw_OpenBrowser() {
    try {
        std::string url = m_param_data.value("url", "");
        
        // Enforce strict protocol allowlist
        const bool is_http  = (url.rfind("http://", 0) == 0);
        const bool is_https = (url.rfind("https://", 0) == 0);
        if (!is_http && !is_https) {
            BOOST_LOG_TRIVIAL(error) << "[Security] Blocked unauthorized URL scheme in sw_OpenBrowser: " << url;
            handle_general_fail(-1, "Unauthorized URL scheme");
            return;
        }

        wxString wx_url = wxString::FromUTF8(url);
        std::weak_ptr<SSWCP_Instance> weak_self = shared_from_this();
        wxGetApp().CallAfter([wx_url, weak_self]() {
            auto self = weak_self.lock();
            if (!self) return;
            bool res = wxLaunchDefaultBrowser(wx_url);
            if (!res) {
                self->handle_general_fail(-1, "Open browser failed");
            } else {
                self->send_to_js();
                self->finish_job();
            }
        });
    }
    catch (const std::exception& e) {
        handle_general_fail();
    }
}
```

### Security Recommendations
- Validate all IPC command parameters received across WebView boundaries.
- Restrict WebView origin access to configured printer IP addresses or loopback interfaces.
