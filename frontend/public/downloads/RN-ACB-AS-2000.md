---
doc_id: RN-ACB-AS-2000
title: "ACB 2000A (ACB-AS-2000) — Firmware Release Notes"
doc_type: RN
product_code: ACB-AS-2000
family: LV_BREAKER
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ACB 2000A (ACB-AS-2000) — Firmware Release Notes

## 1. Summary

Latest firmware: **1.4**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 1.4 (2026-03-09)

- Fixed: false T.SF self-diagnosis alarm after control power dip below 85 V
- Improved: event log capacity from 64 to 256 entries

### 2.2 Version 1.3 (2025-06-16)

- Fixed: ground fault (G) pickup delay ignored when set to 0.1 s
- Added: Modbus register for contact wear percentage

### 2.3 Version 1.2 (2024-11-04)

- Initial release of trip unit firmware for AS series

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
