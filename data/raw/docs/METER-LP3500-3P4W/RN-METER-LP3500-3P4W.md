---
doc_id: RN-METER-LP3500-3P4W
title: "Smart Power Meter 3P4W (METER-LP3500-3P4W) — Firmware Release Notes"
doc_type: RN
product_code: METER-LP3500-3P4W
family: METER
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Smart Power Meter 3P4W (METER-LP3500-3P4W) — Firmware Release Notes

## 1. Summary

Latest firmware: **1.80**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 1.80 (2025-12-01)

- Added: Modbus TCP gateway mode
- Fixed: R.01 no response when baud 38400 and parity even

### 2.2 Version 1.72 (2025-04-07)

- Fixed: energy register reset after power loss during flash write

### 2.3 Version 1.60 (2024-08-05)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
