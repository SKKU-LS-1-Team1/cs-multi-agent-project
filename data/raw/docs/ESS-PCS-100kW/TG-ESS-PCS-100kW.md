---
doc_id: TG-ESS-PCS-100kW
title: "ESS PCS 100kW (ESS-PCS-100kW) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: ESS-PCS-100kW
family: ESS
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ESS PCS 100kW (ESS-PCS-100kW) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| G.01 | Grid over-voltage trip | 3.1 | P2 |
| G.02 | Frequency trip during generator operation | 3.2 | P2 |
| G.04 | IGBT over-temperature | 3.3 | P3 |
| G.05 | DC insulation fault | 3.4 | P1 |
| G.06 | BMS communication loss on PCS | 3.5 | P2 |
| G.06 | Intermittent CAN errors | 3.6 | P3 |

## 3. Troubleshooting procedures

### 3.1 G.01 — Grid over-voltage trip

- **Possible cause:** Wrong country grid profile selected
- **How to check:** Check parameter G-01 grid profile
- **Corrective action:** Select correct grid profile per utility requirement

### 3.2 G.02 — Frequency trip during generator operation

- **Possible cause:** Firmware defect in ROCOF measurement
- **How to check:** Trip during genset; firmware older than 2.70
- **Corrective action:** Update PCS firmware to 2.70
- **Firmware:** fixed in version 2.70 (see RN-ESS-PCS-100kW)

### 3.3 G.04 — IGBT over-temperature

- **Possible cause:** Air filter clogged
- **How to check:** Inspect filters and fans
- **Corrective action:** Clean/replace filters
- **Replacement part:** Air filter

### 3.4 G.05 — DC insulation fault

- **Possible cause:** Moisture in battery rack DC cabling
- **How to check:** Insulation resistance test per rack
- **Corrective action:** Dry and repair cabling
- **Note:** this check normally requires a site visit by qualified personnel.
- **Safety:** isolate the equipment immediately and contact support by phone.

### 3.5 G.06 — BMS communication loss on PCS

- **Possible cause:** Firmware compatibility: BMS 3.4 heartbeat vs PCS < 2.62
- **How to check:** Check firmware versions of PCS and BMS
- **Corrective action:** Update PCS firmware to 2.62 or later
- **Firmware:** fixed in version 2.62 (see RN-ESS-PCS-100kW)

### 3.6 G.06 — Intermittent CAN errors

- **Possible cause:** CAN termination missing
- **How to check:** Measure CAN bus resistance (expect 60 Ω)
- **Corrective action:** Install 120 Ω termination

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- Event / trip log export
- Battery SOC / cell temperature at event

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
