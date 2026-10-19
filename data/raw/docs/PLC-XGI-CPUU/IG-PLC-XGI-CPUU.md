---
doc_id: IG-PLC-XGI-CPUU
title: "XGI PLC CPU Universal (PLC-XGI-CPUU) — Installation and Commissioning Guide"
doc_type: IG
product_code: PLC-XGI-CPUU
family: PLC
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGI PLC CPU Universal (PLC-XGI-CPUU) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: 50 mm above and below the base for ventilation; keep 100 mm from power cables
- Operating temperature: 0 to +55 °C
- Degree of protection: IP20
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Check power supply and base grounding (FG)
2. Download I/O parameter and program
3. Verify each input and output point
4. Check communication settings
5. Back up the final project

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| CPU stops with watchdog error | Scan time exceeds watchdog due to program loop | TG-PLC-XGI-CPUU §3.1 |
| Random watchdog error in noisy environment | Electrical noise due to improper grounding | TG-PLC-XGI-CPUU §3.2 |
| I/O configuration mismatch after module replacement | Replacement module type differs from I/O parameter | TG-PLC-XGI-CPUU §3.3 |
| Battery low warning | Backup battery end of life | TG-PLC-XGI-CPUU §3.4 |

On-site commissioning support can be requested through the Global CS Center. For programmable logic controllers the request is handled by the technical support team.
