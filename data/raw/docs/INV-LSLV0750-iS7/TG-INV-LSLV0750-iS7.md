---
doc_id: TG-INV-LSLV0750-iS7
title: "iS7 75kW VFD (INV-LSLV0750-iS7) — Troubleshooting and Error Code Guide"
doc_type: TG
product_code: INV-LSLV0750-iS7
family: DRIVE
revision: D
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# iS7 75kW VFD (INV-LSLV0750-iS7) — Troubleshooting and Error Code Guide

## 1. How to use this guide

Find the error code or symptom in section 2, then follow the detailed procedure in section 3. If the problem persists, contact support with the information listed in section 4.

## 2. Error code and symptom list

| Code | Symptom | Section | Severity |
|---|---|---|---|
| E.OC | Over-current trip during acceleration | 3.1 | P2 |
| E.OC | Over-current trip immediately at run command | 3.2 | P2 |
| E.OC | Over-current trip even with motor disconnected | 3.3 | P2 |
| E.OC | Over-current trip at restart after momentary power loss | 3.4 | P2 |
| E.OV | Over-voltage trip during deceleration | 3.5 | P2 |
| E.OV | Over-voltage trip at standstill | 3.6 | P3 |
| E.LV | Low-voltage trip during operation | 3.7 | P2 |
| E.LV | Low-voltage trip on one phase loss | 3.8 | P2 |
| E.OL | Motor stops with overload trip | 3.9 | P3 |
| E.OL | Overload trip after several minutes of operation | 3.10 | P2 |
| E.OH | Inverter overheat trip | 3.11 | P3 |
| E.OH | Overheat trip in summer afternoons | 3.12 | P3 |
| E.GF | Ground fault trip | 3.13 | P2 |
| E.PO | Output phase open trip | 3.14 | P3 |
| E.CO | Communication error trip from PLC/BMS network | 3.15 | P3 |
| — | Motor does not run on remote command | 3.16 | P4 |

## 3. Troubleshooting procedures

### 3.1 E.OC — Over-current trip during acceleration

- **Possible cause:** Acceleration time too short for load inertia
- **How to check:** Check trip log: output current at trip > 200% of rated during ACC
- **Corrective action:** Increase acceleration time and enable stall prevention

### 3.2 E.OC — Over-current trip immediately at run command

- **Possible cause:** Motor cable insulation breakdown (phase-to-phase short)
- **How to check:** Disconnect motor cable, megger test cable and motor at 1,000 V
- **Corrective action:** Replace damaged motor cable section
- **Note:** this check normally requires a site visit by qualified personnel.

### 3.3 E.OC — Over-current trip even with motor disconnected

- **Possible cause:** Output IGBT module damaged
- **How to check:** Diode test on output terminals U/V/W shows short circuit
- **Corrective action:** Replace power module under RMA
- **Replacement part:** IGBT power module
- **Note:** hardware replacement is required; request an RMA (see POL-WARRANTY).

### 3.4 E.OC — Over-current trip at restart after momentary power loss

- **Possible cause:** Firmware defect in speed search at restart
- **How to check:** Trip log shows E.OC within 50 ms after power restoration; reproducible with speed search enabled
- **Corrective action:** Update firmware to 4.05 or later
- **Firmware:** fixed in version 4.05 (see RN-INV-LSLV0750-iS7)

### 3.5 E.OV — Over-voltage trip during deceleration

- **Possible cause:** Regenerative energy from load; deceleration time too short
- **How to check:** Trip log shows DC link voltage > 820 V during DEC
- **Corrective action:** Increase deceleration time or install braking resistor

### 3.6 E.OV — Over-voltage trip at standstill

- **Possible cause:** Supply voltage above tolerance (> 528 V)
- **How to check:** Measure line voltage at drive input terminals
- **Corrective action:** Adjust transformer tap or install input reactor

### 3.7 E.LV — Low-voltage trip during operation

- **Possible cause:** Loose input power terminal causing voltage drop
- **How to check:** Measure input voltage under load; inspect terminal torque and discoloration
- **Corrective action:** Retighten input terminals to specified torque

### 3.8 E.LV — Low-voltage trip on one phase loss

- **Possible cause:** Input fuse blown on one phase
- **How to check:** Measure phase-to-phase input voltages
- **Corrective action:** Replace input fuse and check upstream protection

### 3.9 E.OL — Motor stops with overload trip

- **Possible cause:** Motor rated current parameter set lower than motor nameplate
- **How to check:** Compare motor rated current parameter with motor nameplate; check overload trip log
- **Corrective action:** Correct motor rated current parameter and overload level

### 3.10 E.OL — Overload trip after several minutes of operation

- **Possible cause:** Mechanical jam / bearing failure in driven load
- **How to check:** Load current trend rising over time; manual rotation check of load
- **Corrective action:** Repair mechanical load; resume operation

### 3.11 E.OH — Inverter overheat trip

- **Possible cause:** Cooling fan failure
- **How to check:** Check fan rotation and fan run-hour monitor
- **Corrective action:** Replace cooling fan
- **Replacement part:** Cooling fan

### 3.12 E.OH — Overheat trip in summer afternoons

- **Possible cause:** Panel ventilation insufficient; ambient > 50 °C
- **How to check:** Measure panel internal temperature; check heat sink temperature monitor
- **Corrective action:** Improve panel ventilation or apply derating

### 3.13 E.GF — Ground fault trip

- **Possible cause:** Motor winding insulation degradation
- **How to check:** Megger test motor winding to ground (< 1 MΩ)
- **Corrective action:** Repair or replace motor
- **Note:** this check normally requires a site visit by qualified personnel.

### 3.14 E.PO — Output phase open trip

- **Possible cause:** Loose motor terminal or contactor between drive and motor opened during run
- **How to check:** Inspect motor wiring; check sequence of output contactor
- **Corrective action:** Fix wiring and correct output contactor sequence

### 3.15 E.CO — Communication error trip from PLC/BMS network

- **Possible cause:** RS-485 termination missing or baud rate mismatch
- **How to check:** Check communication parameters and termination resistor at both ends
- **Corrective action:** Set matching baud rate and enable termination

### 3.16 Motor does not run on remote command

- **Possible cause:** Command source parameter set to keypad instead of terminal
- **How to check:** Check run command source and frequency reference source parameters
- **Corrective action:** Set command source to terminal/fieldbus

## 4. Information required when contacting support

- Product model / ordering code
- Serial number (nameplate)
- Error code or symptom displayed
- Operating condition at failure (load, speed, temperature)
- Photos of product and nameplate
- Event / trip log export
- Parameter backup file
- Motor nameplate data

## 5. Returning a unit

Hardware failures are handled under an RMA number issued by the Warranty & RMA Desk. Do not ship units without an RMA number.
