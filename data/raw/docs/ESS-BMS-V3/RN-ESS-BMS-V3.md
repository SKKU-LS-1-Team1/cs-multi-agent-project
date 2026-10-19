---
doc_id: RN-ESS-BMS-V3
title: "ESS BMS Controller V3 (ESS-BMS-V3) — Firmware Release Notes"
doc_type: RN
product_code: ESS-BMS-V3
family: ESS
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ESS BMS Controller V3 (ESS-BMS-V3) — Firmware Release Notes

## 1. Summary

Latest firmware: **3.50**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 3.50 (2026-01-19)

- Fixed: SOC jump of up to 15% after long rest period
- Fixed: contactor status mismatch alarm on cold start

### 2.2 Version 3.40 (2025-05-19)

- Changed: CAN heartbeat period from 100 ms to 200 ms
- Improved: passive balancing threshold 30 mV → 20 mV

### 2.3 Version 3.30 (2024-10-28)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

PCS firmware 2.62 or later is required with BMS firmware 3.40 or later (CAN heartbeat change).
