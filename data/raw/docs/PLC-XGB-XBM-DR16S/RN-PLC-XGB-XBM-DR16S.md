---
doc_id: RN-PLC-XGB-XBM-DR16S
title: "XGB PLC CPU 16 I/O (PLC-XGB-XBM-DR16S) — Firmware Release Notes"
doc_type: RN
product_code: PLC-XGB-XBM-DR16S
family: PLC
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGB PLC CPU 16 I/O (PLC-XGB-XBM-DR16S) — Firmware Release Notes

## 1. Summary

Latest firmware: **3.20**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 3.20 (2025-11-03)

- Added: Modbus RTU master up to 64 blocks
- Fixed: RTC drift > 30 s/month at high ambient temperature

### 2.2 Version 3.10 (2025-02-17)

- Fixed: P.04 program checksum error after repeated power cycling within 1 s

### 2.3 Version 3.00 (2024-07-01)

- Baseline release

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
