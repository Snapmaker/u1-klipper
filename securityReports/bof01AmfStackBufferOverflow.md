# Vulnerability Advisory: BOF-01

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** BOF-01
- **Vulnerability Title:** Stack Buffer Overflow via sprintf in AMF Archive Model Extraction
- **Affected Components:** `src/libslic3r/Format/AMF.cpp`
- **Vulnerability Classification:** CWE-121 (Stack-based Buffer Overflow), CWE-120 (Buffer Copy without Checking Size of Input)
- **CVSS v3.1 Score:** 9.8 (CRITICAL) - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users opening or importing 3D models from AMF files or compressed archive files (`.amf`, `.zip`, `.3mf`) from untrusted online sources (Printables, Thingiverse, MakerWorld, email, or USB drives).
- **Threat Actor Profile:** Remote attacker distributing malicious 3D model files.

---

## Executive Summary
A critical stack buffer overflow vulnerability exists in `AMF.cpp` within the `extract_model_from_archive` function. When extracting an AMF model from a ZIP container, error messages are formatted into a fixed-size stack buffer of 1024 bytes (`char error_buf[1024];`) using `::sprintf`. The filename read from the ZIP archive entry header (`data->stat.m_filename`) is unbounded and can measure up to 65,535 bytes under standard ZIP specifications. Opening a crafted model archive triggers a stack buffer overflow, leading to arbitrary code execution or application crash.

---

## Technical Root Cause Analysis
In `AMF.cpp`, within `extract_model_from_archive`:

```cpp
// E:/KI Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp:983-993
try
{
    res = mz_zip_reader_extract_file_to_callback(&archive, stat.m_filename, [](void* pOpaque, mz_uint64 file_ofs, const void* pBuf, size_t n)->size_t {
        CallbackData* data = (CallbackData*)pOpaque;
        if (!XML_Parse(data->parser, (const char*)pBuf, (int)n, (file_ofs + n == data->stat.m_uncomp_size) ? 1 : 0) || data->ctx.error())
        {
            char error_buf[1024];
            ::sprintf(error_buf, "Parsing file %s error at line %d: {%s}", data->stat.m_filename, (int) XML_GetCurrentLineNumber(data->parser), data->ctx.error_message());
            throw Slic3r::FileIOError(error_buf);
        }
        return n;
    }, &data, 0);
}
```

1. **Fixed Stack Buffer:** `char error_buf[1024]` allocates exactly 1,024 bytes on the stack.
2. **Unbounded Input via `stat.m_filename`:** The entry filename in `mz_zip_archive_file_stat` is controlled by the archive header and can be up to `UINT16_MAX` (65,535 bytes).
3. **Use of Unsafe `::sprintf`:** `sprintf` performs no destination buffer bounds checking. If the string representation exceeds 1,024 bytes, memory adjacent to `error_buf` on the stack frame (including saved frame pointers and return addresses) is overwritten.

---

## Steps to Reproduce
1. Generate an AMF archive file where the internal XML entry filename is padded with 2,048 characters (e.g., `AAAA...AAAA.amf`).
2. Include invalid XML content inside the file to force `XML_Parse` to return a parsing error.
3. Open or import the archive in OrcaSlicer (`File -> Import -> Import AMF/3MF`).
4. Observe a stack overflow crash (`STATUS_STACK_BUFFER_OVERRUN` / `0xC0000409` on Windows or `SIGSEGV` on Linux).

---

## Attack Scenario & Threat Analysis
1. An attacker uploads a crafted `.3mf` or `.amf` project to a popular 3D printing repository.
2. A user downloads the model file and opens it in OrcaSlicer for slicing.
3. The parser detects a syntax error and invokes the error formatting callback.
4. The oversized filename string overflows the stack, hijacking the execution flow or immediately terminating the slicer process.

---

## Defensive Remediation & Verification

### Code Fix
Replace `::sprintf` with safe string formatting or `snprintf`:

```cpp
// E:/KI Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp:989
const std::string error_msg = (boost::format("Parsing file %s error at line %d: {%s}") 
    % data->stat.m_filename 
    % (int)XML_GetCurrentLineNumber(data->parser) 
    % data->ctx.error_message()).str();
throw Slic3r::FileIOError(error_msg);
```

Or using `snprintf`:

```cpp
char error_buf[2048];
::snprintf(error_buf, sizeof(error_buf), "Parsing file %s error at line %d: {%s}",
    data->stat.m_filename, (int) XML_GetCurrentLineNumber(data->parser), data->ctx.error_message());
throw Slic3r::FileIOError(error_buf);
```

### Security Recommendations
- Ban the use of `sprintf`, `strcpy`, and `strcat` across the entire codebase via compiler warning flags (`-Wformat-security`, `/sdl`).
- Utilize RAII containers (`std::string`, `boost::format`, `std::format`) for dynamic string construction.
