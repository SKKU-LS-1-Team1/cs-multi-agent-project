---
doc_id: RN-INV-LSLV0220-H100
title: "LSLV H100 22kW VFD (INV-LSLV0220-H100) — Firmware Release Notes"
doc_type: RN
product_code: INV-LSLV0220-H100
family: DRIVE
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# LSLV H100 22kW VFD (INV-LSLV0220-H100) — Firmware Release Notes

## 1. Summary

Latest firmware: **2.40**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 2.40 (2026-02-02)

- Fixed: MMC auxiliary motor not staging when PID feedback noisy
- Improved: fire mode event log with timestamp

### 2.2 Version 2.31 (2025-05-26)

- Fixed: BACnet MS/TP token loss on networks with > 32 nodes (E.CO)
- Added: pump clean function

### 2.3 Version 2.20 (2024-10-14)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
