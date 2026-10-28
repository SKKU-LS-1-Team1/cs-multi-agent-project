---
doc_id: TG-HMI-XGT-eXP60
title: "XGT Panel eXP60 (6") (HMI-XGT-eXP60) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: HMI-XGT-eXP60
family: HMI
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGT Panel eXP60 (6") (HMI-XGT-eXP60) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| H.02 | PLC communication timeout on HMI | 3.1 | P3 |
| H.03 | Project download fails | 3.2 | P3 |
| H.01 | Touch position misaligned | 3.3 | P4 |
| H.01 | Touch not responding in one area | 3.4 | P3 |
| H.04 | Screen very dark | 3.5 | P3 |
| H.05 | Logging stops, memory full warning | 3.6 | P4 |
| — | Screen freezes after weeks of operation | 3.7 | P3 |

## 3. Troubleshooting procedures

### 3.1 H.02 — PLC communication timeout on HMI

- **Possible cause:** Driver protocol or station number mismatch
- **How to check:** Compare HMI connection settings with PLC port settings
- **Corrective action:** Correct protocol and station number

### 3.2 H.03 — Project download fails

- **Possible cause:** Editor version newer than HMI OS
- **How to check:** Compare editor version with OS version
- **Corrective action:** Update HMI OS to 1.62 or later
- **Firmware:** fixed in version 1.62 (see RN-HMI-XGT-eXP60)

### 3.3 H.01 — Touch position misaligned

- **Possible cause:** Touch calibration drift
- **How to check:** Run touch test in system menu
- **Corrective action:** Recalibrate touch panel

### 3.4 H.01 — Touch not responding in one area

- **Possible cause:** Touch panel physically damaged
- **How to check:** Visual inspection; touch test dead zone
- **Corrective action:** Replace touch panel under RMA
- **Replacement part:** Touch panel
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.5 H.04 — Screen very dark

- **Possible cause:** Backlight end of life
- **How to check:** Check operating hours (> 50,000 h)
- **Corrective action:** Replace backlight / unit under RMA
- **Replacement part:** Backlight unit
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.6 H.05 — Logging stops, memory full warning

- **Possible cause:** Logging storage set to internal memory without rotation
- **How to check:** Check logging configuration
- **Corrective action:** Enable ring buffer or log to USB

### 3.7 Screen freezes after weeks of operation

- **Possible cause:** Firmware defect after ~30 days uptime
- **How to check:** Freeze reproducible after ~30 days; OS older than 1.58
- **Corrective action:** Update OS to 1.58 or later
- **Firmware:** fixed in version 1.58 (see RN-HMI-XGT-eXP60)

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- PLC/HMI project backup

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
