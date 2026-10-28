---
doc_id: TG-ACB-AS-2000
title: "ACB 2000A (ACB-AS-2000) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: ACB-AS-2000
family: LV_BREAKER
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ACB 2000A (ACB-AS-2000) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| — | Terminal overheating / discoloration | 3.1 | P2 |
| T.LT | ACB long-time trip | 3.2 | P2 |
| T.GF | ACB ground fault trip | 3.3 | P1 |
| T.SF | ACB trip unit self-diagnosis alarm | 3.4 | P3 |
| — | ACB motor does not charge spring | 3.5 | P2 |

## 3. Troubleshooting procedures

### 3.1 Terminal overheating / discoloration

- **Possible cause:** Loose connection or undersized cable
- **How to check:** Thermographic inspection; check tightening torque
- **Corrective action:** Retighten to specified torque; replace damaged terminal
- **Note:** this check normally requires a site visit by qualified personnel.

### 3.2 T.LT — ACB long-time trip

- **Possible cause:** Sustained overload above long-time setting
- **How to check:** Read trip unit event log current
- **Corrective action:** Reduce load or adjust long-time setting per coordination study

### 3.3 T.GF — ACB ground fault trip

- **Possible cause:** Insulation fault in downstream feeder
- **How to check:** Insulation test of downstream feeders
- **Corrective action:** Repair insulation fault before re-closing
- **Note:** this check normally requires a site visit by qualified personnel.
- **Safety:** isolate the equipment immediately and contact support by phone.

### 3.4 T.SF — ACB trip unit self-diagnosis alarm

- **Possible cause:** Firmware defect after control power dip
- **How to check:** Alarm after control voltage dip below 85 V; firmware older than 1.4
- **Corrective action:** Update trip unit firmware to 1.4
- **Firmware:** fixed in version 1.4 (see RN-ACB-AS-2000)

### 3.5 ACB motor does not charge spring

- **Possible cause:** Control voltage mismatch or motor fuse blown
- **How to check:** Measure control voltage at motor terminals
- **Corrective action:** Supply correct control voltage; replace fuse

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- Load current / temperature records

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
