---
doc_id: IG-UPS-LSU-10K
title: "Online UPS 10kVA (UPS-LSU-10K) — Installation and Commissioning Guide"
doc_type: IG
product_code: UPS-LSU-10K
family: UPS
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Online UPS 10kVA (UPS-LSU-10K) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: 300 mm at the rear and 100 mm on each side for ventilation
- Operating temperature: 0 to +40 °C
- Degree of protection: IP20
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Check battery polarity and voltage
2. Connect input and close input breaker
3. Run self-test
4. Perform battery test
5. Transfer load from bypass to inverter

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| Short backup time | Battery end of life (> 3 years) | TG-UPS-LSU-10K §3.1 |
| UPS on bypass due to overload | Connected load exceeds rating | TG-UPS-LSU-10K §3.2 |
| Over-temperature alarm | Fan failure | TG-UPS-LSU-10K §3.4 |
| SNMP card not detected | Firmware defect after hot-swap | TG-UPS-LSU-10K §3.5 |

On-site commissioning support can be requested through the Global CS Center. For uninterruptible power supplies the request is handled by the technical support team.
