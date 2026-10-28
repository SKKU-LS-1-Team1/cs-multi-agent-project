---
doc_id: TG-HMI-XGT-iXP90
title: "XGT iXP90 (10") (HMI-XGT-iXP90) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: HMI-XGT-iXP90
family: HMI
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGT iXP90 (10") (HMI-XGT-iXP90) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| H.02 | PLC communication timeout on HMI | 3.1 | P3 |
| H.02 | Timeout when both Ethernet ports used | 3.2 | P3 |
| H.01 | Touch position misaligned | 3.3 | P4 |
| H.01 | Touch not responding in one area | 3.4 | P3 |
| H.04 | Screen very dark | 3.5 | P3 |
| H.05 | Logging stops, memory full warning | 3.6 | P4 |

## 3. Troubleshooting procedures

### 3.1 H.02 — PLC communication timeout on HMI

- **Possible cause:** Driver protocol or station number mismatch
- **How to check:** Compare HMI connection settings with PLC port settings
- **Corrective action:** Correct protocol and station number

### 3.2 H.02 — Timeout when both Ethernet ports used

- **Possible cause:** Firmware defect with two ports on same subnet
- **How to check:** Firmware older than 2.05; ports on same subnet
- **Corrective action:** Update OS to 2.05 or use separate subnets
- **Firmware:** fixed in version 2.05 (see RN-HMI-XGT-iXP90)

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

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- PLC/HMI project backup

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
