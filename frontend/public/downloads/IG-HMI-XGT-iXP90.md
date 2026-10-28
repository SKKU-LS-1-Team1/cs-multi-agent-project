---
doc_id: IG-HMI-XGT-iXP90
title: "XGT iXP90 (10") (HMI-XGT-iXP90) — Installation and Commissioning Guide"
doc_type: IG
product_code: HMI-XGT-iXP90
family: HMI
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# XGT iXP90 (10") (HMI-XGT-iXP90) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: Panel cut-out per dimension drawing; 50 mm behind the unit for cable bending
- Operating temperature: 0 to +50 °C
- Degree of protection: IP66 (front)
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Check 24 V DC supply polarity
2. Download project with matching editor/OS version
3. Set PLC connection driver and station number
4. Calibrate touch panel

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| PLC communication timeout on HMI | Driver protocol or station number mismatch | TG-HMI-XGT-iXP90 §3.1 |
| Timeout when both Ethernet ports used | Firmware defect with two ports on same subnet | TG-HMI-XGT-iXP90 §3.2 |
| Touch position misaligned | Touch calibration drift | TG-HMI-XGT-iXP90 §3.3 |
| Logging stops, memory full warning | Logging storage set to internal memory without rotation | TG-HMI-XGT-iXP90 §3.6 |

On-site commissioning support can be requested through the Global CS Center. For operator panels (hmi) the request is handled by the technical support team.
