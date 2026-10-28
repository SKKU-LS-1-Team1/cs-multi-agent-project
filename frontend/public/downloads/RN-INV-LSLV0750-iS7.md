---
doc_id: RN-INV-LSLV0750-iS7
title: "iS7 75kW VFD (INV-LSLV0750-iS7) — Firmware Release Notes"
doc_type: RN
product_code: INV-LSLV0750-iS7
family: DRIVE
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# iS7 75kW VFD (INV-LSLV0750-iS7) — Firmware Release Notes

## 1. Summary

Latest firmware: **4.10**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 4.10 (2025-12-15)

- Fixed: EtherNet/IP option loses connection after 49.7 days uptime
- Added: cooling fan life warning

### 2.2 Version 4.05 (2025-03-10)

- Fixed: E.OC trip at restart after momentary power loss (speed search)

### 2.3 Version 4.00 (2024-08-19)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
