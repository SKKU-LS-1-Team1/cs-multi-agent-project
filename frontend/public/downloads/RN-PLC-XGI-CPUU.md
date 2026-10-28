---
doc_id: RN-PLC-XGI-CPUU
title: "XGI PLC CPU Universal (PLC-XGI-CPUU) — Firmware Release Notes"
doc_type: RN
product_code: PLC-XGI-CPUU
family: PLC
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGI PLC CPU Universal (PLC-XGI-CPUU) — Firmware Release Notes

## 1. Summary

Latest firmware: **4.50**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 4.50 (2026-02-23)

- Added: online change for structured data types
- Fixed: watchdog false trip during online change of large FB

### 2.2 Version 4.40 (2025-06-02)

- Fixed: P.05 Ethernet timeout under broadcast storm > 2,000 frames/s

### 2.3 Version 4.20 (2024-09-23)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
