---
doc_id: TG-UPS-LSU-10K
title: "Online UPS 10kVA (UPS-LSU-10K) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: UPS-LSU-10K
family: UPS
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Online UPS 10kVA (UPS-LSU-10K) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| U.01 | Short backup time | 3.1 | P3 |
| U.02 | UPS on bypass due to overload | 3.2 | P2 |
| U.03 | Inverter fault, load on bypass | 3.3 | P2 |
| U.05 | Over-temperature alarm | 3.4 | P3 |
| — | SNMP card not detected | 3.5 | P4 |
| — | Frequent transfer to battery on generator | 3.6 | P3 |

## 3. Troubleshooting procedures

### 3.1 U.01 — Short backup time

- **Possible cause:** Battery end of life (> 3 years)
- **How to check:** Run battery test; check battery age
- **Corrective action:** Replace battery set
- **Replacement part:** Battery set

### 3.2 U.02 — UPS on bypass due to overload

- **Possible cause:** Connected load exceeds rating
- **How to check:** Read load % log
- **Corrective action:** Redistribute load

### 3.3 U.03 — Inverter fault, load on bypass

- **Possible cause:** Inverter board failure
- **How to check:** Event log U.03; self-test fails
- **Corrective action:** Repair inverter board under RMA
- **Replacement part:** Inverter board
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.4 U.05 — Over-temperature alarm

- **Possible cause:** Fan failure
- **How to check:** Check fan operation
- **Corrective action:** Replace fan
- **Replacement part:** Fan

### 3.5 SNMP card not detected

- **Possible cause:** Firmware defect after hot-swap
- **How to check:** Firmware older than 2.30
- **Corrective action:** Update UPS firmware to 2.30
- **Firmware:** fixed in version 2.30 (see RN-UPS-LSU-10K)

### 3.6 Frequent transfer to battery on generator

- **Possible cause:** Generator frequency outside default window
- **How to check:** Frequency log during genset operation
- **Corrective action:** Enable generator mode (firmware 2.20 or later)
- **Firmware:** fixed in version 2.20 (see RN-UPS-LSU-10K)

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- Event / trip log export
- Battery installation date / age

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
