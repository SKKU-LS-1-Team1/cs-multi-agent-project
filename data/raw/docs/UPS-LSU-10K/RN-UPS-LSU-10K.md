---
doc_id: RN-UPS-LSU-10K
title: "Online UPS 10kVA (UPS-LSU-10K) — Firmware Release Notes"
doc_type: RN
product_code: UPS-LSU-10K
family: UPS
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Online UPS 10kVA (UPS-LSU-10K) — Firmware Release Notes

## 1. Summary

Latest firmware: **2.30**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 2.30 (2025-11-17)

- Fixed: SNMP card not detected after hot-swap
- Fixed: battery test result not logged when load < 10%

### 2.2 Version 2.20 (2025-03-03)

- Added: generator mode with wider frequency window (45-65 Hz)

### 2.3 Version 2.10 (2024-07-15)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
