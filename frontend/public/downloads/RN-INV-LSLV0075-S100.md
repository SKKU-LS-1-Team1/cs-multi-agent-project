---
doc_id: RN-INV-LSLV0075-S100
title: "LSLV S100 7.5kW VFD (INV-LSLV0075-S100) — Firmware Release Notes"
doc_type: RN
product_code: INV-LSLV0075-S100
family: DRIVE
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# LSLV S100 7.5kW VFD (INV-LSLV0075-S100) — Firmware Release Notes

## 1. Summary

Latest firmware: **3.10**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 3.10 (2026-01-12)

- Fixed: E.EP parameter write error when copying from 3.00 keypad
- Improved: stall prevention during fast acceleration
- Added: fan run-hour counter (monitor parameter)

### 2.2 Version 3.05 (2025-04-21)

- Fixed: Modbus RTU response timeout when polling interval < 20 ms (E.CO)
- Added: parameter copy compatibility check on keypad

### 2.3 Version 3.00 (2024-09-02)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
