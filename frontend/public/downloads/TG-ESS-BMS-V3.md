---
doc_id: TG-ESS-BMS-V3
title: "ESS BMS Controller V3 (ESS-BMS-V3) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: ESS-BMS-V3
family: ESS
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ESS BMS Controller V3 (ESS-BMS-V3) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| G.05 | DC insulation fault | 3.1 | P1 |
| G.06 | BMS communication loss on PCS | 3.2 | P2 |
| G.06 | Intermittent CAN errors | 3.3 | P3 |
| B.01 | Cell over-voltage alarm | 3.4 | P2 |
| B.03 | Cell over-temperature | 3.5 | P1 |
| B.04 | Cell imbalance alarm | 3.6 | P3 |
| B.06 | Main contactor welded alarm | 3.7 | P1 |
| — | SOC jumps after long rest | 3.8 | P3 |

## 3. Troubleshooting procedures

### 3.1 G.05 — DC insulation fault

- **Possible cause:** Moisture in battery rack DC cabling
- **How to check:** Insulation resistance test per rack
- **Corrective action:** Dry and repair cabling
- **Note:** this check normally requires a site visit by qualified personnel.
- **Safety:** isolate the equipment immediately and contact support by phone.

### 3.2 G.06 — BMS communication loss on PCS

- **Possible cause:** Firmware compatibility: BMS 3.4 heartbeat vs PCS < 2.62
- **How to check:** Check firmware versions of PCS and BMS
- **Corrective action:** Update PCS firmware to 2.62 or later

### 3.3 G.06 — Intermittent CAN errors

- **Possible cause:** CAN termination missing
- **How to check:** Measure CAN bus resistance (expect 60 Ω)
- **Corrective action:** Install 120 Ω termination

### 3.4 B.01 — Cell over-voltage alarm

- **Possible cause:** Defective battery module cell
- **How to check:** Cell voltage trend shows single cell drift
- **Corrective action:** Replace battery module under RMA
- **Replacement part:** Battery module
- **Note:** this check normally requires a site visit by qualified personnel.
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.5 B.03 — Cell over-temperature

- **Possible cause:** Container HVAC failure
- **How to check:** Check HVAC alarm and room temperature
- **Corrective action:** Stop operation; repair HVAC
- **Note:** this check normally requires a site visit by qualified personnel.
- **Safety:** isolate the equipment immediately and contact support by phone.

### 3.6 B.04 — Cell imbalance alarm

- **Possible cause:** Insufficient balancing after long partial cycling
- **How to check:** Max-min cell voltage difference > 50 mV
- **Corrective action:** Perform full charge balancing maintenance

### 3.7 B.06 — Main contactor welded alarm

- **Possible cause:** Pre-charge circuit failure
- **How to check:** Pre-charge resistor measurement
- **Corrective action:** Replace contactor and pre-charge resistor
- **Replacement part:** DC contactor
- **Note:** this check normally requires a site visit by qualified personnel.
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).
- **Safety:** isolate the equipment immediately and contact support by phone.

### 3.8 SOC jumps after long rest

- **Possible cause:** Firmware defect in SOC estimation
- **How to check:** SOC trend shows jump; firmware older than 3.50
- **Corrective action:** Update BMS firmware to 3.50 and perform calibration
- **Firmware:** fixed in version 3.50 (see RN-ESS-BMS-V3)

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
