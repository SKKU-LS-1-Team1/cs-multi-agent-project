---
doc_id: RN-HMI-XGT-iXP90
title: "XGT iXP90 (10") (HMI-XGT-iXP90) — Firmware Release Notes"
doc_type: RN
product_code: HMI-XGT-iXP90
family: HMI
revision: F
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGT iXP90 (10") (HMI-XGT-iXP90) — Firmware Release Notes

## 1. Summary

Latest firmware: **2.08**. Updating to the latest version is recommended for all units.

## 2. Version history

### 2.1 Version 2.08 (2026-01-26)

- Fixed: touch drift after warm restart
- Added: TLS 1.3 for web server

### 2.2 Version 2.05 (2025-05-12)

- Fixed: H.02 PLC communication timeout when two Ethernet ports on same subnet

### 2.3 Version 2.00 (2024-10-07)

- Baseline OS

## 3. Update procedure

1. Back up parameters / project before updating.
2. Connect the engineering tool (v4.6 or later).
3. Do not switch off power during the update.
4. After the update, verify the version and restore parameters if required.
5. If the update fails, do not power-cycle the unit repeatedly; contact support for the recovery procedure.

## 4. Compatibility

Parameter files from older versions can be loaded; files from newer versions cannot be loaded into older firmware.
