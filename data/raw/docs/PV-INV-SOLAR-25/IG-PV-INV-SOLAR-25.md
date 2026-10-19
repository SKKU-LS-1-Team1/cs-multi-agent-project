---
doc_id: IG-PV-INV-SOLAR-25
title: "Solar Inverter 25kW (PV-INV-SOLAR-25) — Installation and Commissioning Guide"
doc_type: IG
product_code: PV-INV-SOLAR-25
family: PV
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Solar Inverter 25kW (PV-INV-SOLAR-25) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: 500 mm above, 300 mm below and on each side; avoid direct sunlight on the heat sink
- Operating temperature: -25 to +60 °C (derating above 45 °C)
- Degree of protection: IP66
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Measure Voc of each string at the lowest expected temperature
2. Check DC polarity and insulation
3. Select grid code / country setting
4. Verify communication and monitoring
5. Check MPPT operation at noon

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| Insulation fault at sunrise | Firmware defect at humidity > 95% | TG-PV-INV-SOLAR-25 §3.1 |
| Insulation fault after rain | Water ingress in PV connector | TG-PV-INV-SOLAR-25 §3.2 |
| Grid lost alarm | AC breaker tripped / grid outage | TG-PV-INV-SOLAR-25 §3.3 |
| PV over-voltage alarm in winter | String too long for low temperature Voc | TG-PV-INV-SOLAR-25 §3.4 |

On-site commissioning support can be requested through the Global CS Center. For pv inverters the request is handled by the technical support team.
