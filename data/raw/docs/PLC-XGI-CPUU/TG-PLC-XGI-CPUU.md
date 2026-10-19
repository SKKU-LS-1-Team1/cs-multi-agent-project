---
doc_id: TG-PLC-XGI-CPUU
title: "XGI PLC CPU Universal (PLC-XGI-CPUU) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: PLC-XGI-CPUU
family: PLC
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGI PLC CPU Universal (PLC-XGI-CPUU) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| P.01 | CPU stops with watchdog error | 3.1 | P2 |
| P.01 | Random watchdog error in noisy environment | 3.2 | P2 |
| P.02 | I/O configuration mismatch after module replacement | 3.3 | P3 |
| P.03 | Battery low warning | 3.4 | P4 |
| P.04 | Program lost repeatedly | 3.5 | P2 |
| P.05 | Ethernet communication timeout | 3.6 | P3 |
| P.05 | Ethernet timeout during broadcast storm | 3.7 | P2 |
| P.06 | Base power fault, CPU does not start | 3.8 | P2 |
| — | Relay output stuck ON | 3.9 | P3 |

## 3. Troubleshooting procedures

### 3.1 P.01 — CPU stops with watchdog error

- **Possible cause:** Scan time exceeds watchdog due to program loop
- **How to check:** Check max scan time in CPU status; review FOR/JMP loops
- **Corrective action:** Fix program loop or increase watchdog setting

### 3.2 P.01 — Random watchdog error in noisy environment

- **Possible cause:** Electrical noise due to improper grounding
- **How to check:** Check FG grounding and cable shielding; correlate with contactor switching
- **Corrective action:** Separate grounding and add surge suppressors
- **Note:** this check normally requires a site visit by qualified personnel.

### 3.3 P.02 — I/O configuration mismatch after module replacement

- **Possible cause:** Replacement module type differs from I/O parameter
- **How to check:** Compare I/O parameter with installed module list
- **Corrective action:** Update I/O parameter and download

### 3.4 P.03 — Battery low warning

- **Possible cause:** Backup battery end of life
- **How to check:** Check battery voltage in CPU status
- **Corrective action:** Replace backup battery (keep power on during replacement)
- **Replacement part:** Backup battery

### 3.5 P.04 — Program lost repeatedly

- **Possible cause:** Flash memory failure in CPU
- **How to check:** Checksum error recurs after re-download
- **Corrective action:** Replace CPU under RMA
- **Replacement part:** CPU module
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.6 P.05 — Ethernet communication timeout

- **Possible cause:** IP address conflict on plant network
- **How to check:** ARP scan shows duplicate IP
- **Corrective action:** Assign unique IP address

### 3.7 P.05 — Ethernet timeout during broadcast storm

- **Possible cause:** Firmware defect under broadcast storm > 2,000 frames/s
- **How to check:** Packet capture shows broadcast storm; firmware older than 4.40
- **Corrective action:** Update firmware to 4.40 and configure switch storm control
- **Firmware:** fixed in version 4.40 (see RN-PLC-XGI-CPUU)

### 3.8 P.06 — Base power fault, CPU does not start

- **Possible cause:** Power supply module output degraded
- **How to check:** Measure 5 V DC output of power module
- **Corrective action:** Replace power supply module
- **Replacement part:** Power supply module
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.9 Relay output stuck ON

- **Possible cause:** Relay contact welded by inrush of capacitive/lamp load
- **How to check:** Output stays ON with CPU in STOP; check load type
- **Corrective action:** Replace output module and add interposing relay
- **Replacement part:** Relay output module
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- Event / trip log export
- PLC/HMI project backup

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
