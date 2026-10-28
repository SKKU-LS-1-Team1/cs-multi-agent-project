---
doc_id: TG-METER-LP3500-3P4W
title: "Smart Power Meter 3P4W (METER-LP3500-3P4W) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: METER-LP3500-3P4W
family: METER
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Smart Power Meter 3P4W (METER-LP3500-3P4W) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| — | Negative active power reading | 3.1 | P4 |
| R.01 | No Modbus response | 3.2 | P4 |
| R.01 | No response at 38400 even parity | 3.3 | P4 |
| — | Energy register reset after power loss | 3.4 | P3 |

## 3. Troubleshooting procedures

### 3.1 Negative active power reading

- **Possible cause:** CT polarity reversed
- **How to check:** Check phase angle in meter diagnostics
- **Corrective action:** Rewire CT or set CT reverse parameter

### 3.2 R.01 — No Modbus response

- **Possible cause:** Address / baud / parity mismatch
- **How to check:** Compare master and meter comm settings
- **Corrective action:** Align communication settings

### 3.3 R.01 — No response at 38400 even parity

- **Possible cause:** Firmware defect at 38400 / even parity
- **How to check:** Firmware older than 1.80 with 38400 E
- **Corrective action:** Update firmware to 1.80
- **Firmware:** fixed in version 1.80 (see RN-METER-LP3500-3P4W)

### 3.4 Energy register reset after power loss

- **Possible cause:** Firmware defect during flash write
- **How to check:** Firmware older than 1.72
- **Corrective action:** Update firmware to 1.72 or later
- **Firmware:** fixed in version 1.72 (see RN-METER-LP3500-3P4W)

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
