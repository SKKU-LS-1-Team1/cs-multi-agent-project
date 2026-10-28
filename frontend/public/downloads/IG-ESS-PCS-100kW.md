---
doc_id: IG-ESS-PCS-100kW
title: "ESS PCS 100kW (ESS-PCS-100kW) — Installation and Commissioning Guide"
doc_type: IG
product_code: ESS-PCS-100kW
family: ESS
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# ESS PCS 100kW (ESS-PCS-100kW) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: 1,000 mm in front for maintenance; ambient controlled by HVAC between 15 and 30 °C
- Operating temperature: -20 to +50 °C (derating above 45 °C)
- Degree of protection: IP54
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Check battery rack insulation resistance
2. Verify CAN communication between PCS and BMS
3. Select grid code profile (parameter G-01)
4. Perform pre-charge test
5. Run charge/discharge test at 20% power

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| Grid over-voltage trip | Wrong country grid profile selected | TG-ESS-PCS-100kW §3.1 |
| Frequency trip during generator operation | Firmware defect in ROCOF measurement | TG-ESS-PCS-100kW §3.2 |
| IGBT over-temperature | Air filter clogged | TG-ESS-PCS-100kW §3.3 |
| DC insulation fault | Moisture in battery rack DC cabling | TG-ESS-PCS-100kW §3.4 |

On-site commissioning support can be requested through the Global CS Center. For energy storage systems the request is handled by the technical support team.
