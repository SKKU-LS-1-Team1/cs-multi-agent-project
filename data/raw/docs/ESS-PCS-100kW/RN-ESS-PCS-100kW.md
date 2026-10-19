---
doc_id: RN-ESS-PCS-100kW
title: "ESS PCS 100kW (ESS-PCS-100kW) — Firmware Release Notes"
doc_type: RN
product_code: ESS-PCS-100kW
family: ESS
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ESS PCS 100kW (ESS-PCS-100kW) — Firmware Release Notes

## 1. Summary

Latest firmware: **2.70**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 2.70 (2026-03-30)

- Added: frequency-watt response curve for new grid codes
- Fixed: G.02 nuisance trip on ROCOF measurement during genset operation

### 2.2 Version 2.62 (2025-07-07)

- Fixed: G.06 BMS communication loss with BMS FW 3.4 heartbeat change

### 2.3 Version 2.50 (2024-11-11)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

PCS firmware 2.62 or later is required with BMS firmware 3.40 or later (CAN heartbeat change).
