---
doc_id: IG-INV-LSLV0075-S100
title: "LSLV S100 7.5kW VFD (INV-LSLV0075-S100) — Installation and Commissioning Guide"
doc_type: IG
product_code: INV-LSLV0075-S100
family: DRIVE
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# LSLV S100 7.5kW VFD (INV-LSLV0075-S100) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: 100 mm above and below, 50 mm on each side; mount vertically for cooling airflow
- Operating temperature: -10 to +50 °C (derating above 40 °C)
- Degree of protection: IP20 (IP66 option)
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: STO, SIL3 / PLe
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Enter motor nameplate data (rated power, current, voltage, frequency, speed)
2. Select command source and frequency reference
3. Perform auto-tuning (rotational if possible)
4. Set acceleration/deceleration times for the load
5. Test run at low speed and check rotation direction

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| Over-current trip during acceleration | Acceleration time too short for load inertia | TG-INV-LSLV0075-S100 §3.1 |
| Over-current trip immediately at run command | Motor cable insulation breakdown (phase-to-phase short) | TG-INV-LSLV0075-S100 §3.2 |
| Over-voltage trip during deceleration | Regenerative energy from load; deceleration time too short | TG-INV-LSLV0075-S100 §3.4 |
| Over-voltage trip at standstill | Supply voltage above tolerance (> 528 V) | TG-INV-LSLV0075-S100 §3.5 |

On-site commissioning support can be requested through the Global CS Center. For variable frequency drives the request is handled by the technical support team.
