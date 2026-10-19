---
doc_id: IG-RELAY-GMR-22
title: "Thermal Overload Relay 22A (RELAY-GMR-22) — Installation and Commissioning Guide"
doc_type: IG
product_code: RELAY-GMR-22
family: CONTROL
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Thermal Overload Relay 22A (RELAY-GMR-22) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: 10 mm on each side; mount vertically ±30°
- Operating temperature: -25 to +55 °C (compensated)
- Degree of protection: IP20
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Verify coil voltage against control supply
2. Set the overload relay to motor full load current
3. Check coordination with upstream protective device
4. Test start/stop sequence without load

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| Overload relay nuisance trip | Setting lower than motor full load current | TG-RELAY-GMR-22 §3.1 |
| Overload relay trips on phase loss | Upstream fuse blown on one phase | TG-RELAY-GMR-22 §3.3 |

On-site commissioning support can be requested through the Global CS Center. For motor control devices the request is handled by the technical support team.
