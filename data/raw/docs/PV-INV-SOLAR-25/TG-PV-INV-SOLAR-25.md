---
doc_id: TG-PV-INV-SOLAR-25
title: "Solar Inverter 25kW (PV-INV-SOLAR-25) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: PV-INV-SOLAR-25
family: PV
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Solar Inverter 25kW (PV-INV-SOLAR-25) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| S.01 | Insulation fault at sunrise | 3.1 | P3 |
| S.01 | Insulation fault after rain | 3.2 | P3 |
| S.02 | Grid lost alarm | 3.3 | P2 |
| S.03 | PV over-voltage alarm in winter | 3.4 | P2 |
| S.04 | Power derating at noon | 3.5 | P3 |
| S.05 | Residual current trip | 3.6 | P2 |
| — | Yield lower than expected | 3.7 | P3 |

## 3. Troubleshooting procedures

### 3.1 S.01 — Insulation fault at sunrise

- **Possible cause:** Firmware defect at humidity > 95%
- **How to check:** Fault only at sunrise; firmware older than 1.82
- **Corrective action:** Update firmware to 1.82
- **Firmware:** fixed in version 1.82 (see RN-PV-INV-SOLAR-25)

### 3.2 S.01 — Insulation fault after rain

- **Possible cause:** Water ingress in PV connector
- **How to check:** IR test per string
- **Corrective action:** Replace damaged connectors
- **Note:** this check normally requires a site visit by qualified personnel.

### 3.3 S.02 — Grid lost alarm

- **Possible cause:** AC breaker tripped / grid outage
- **How to check:** Measure AC voltage at inverter terminals
- **Corrective action:** Restore AC supply; check breaker rating

### 3.4 S.03 — PV over-voltage alarm in winter

- **Possible cause:** String too long for low temperature Voc
- **How to check:** Recalculate Voc at minimum temperature
- **Corrective action:** Reduce modules per string

### 3.5 S.04 — Power derating at noon

- **Possible cause:** Installed in direct sunlight with poor airflow
- **How to check:** Check heat sink temperature log
- **Corrective action:** Relocate or add shading

### 3.6 S.05 — Residual current trip

- **Possible cause:** Damaged DC cable insulation
- **How to check:** Locate fault by string isolation
- **Corrective action:** Repair cable
- **Note:** this check normally requires a site visit by qualified personnel.

### 3.7 Yield lower than expected

- **Possible cause:** One string disconnected
- **How to check:** Compare string currents
- **Corrective action:** Reconnect string; check fuse

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- Event / trip log export
- PV string configuration (modules per string)

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
