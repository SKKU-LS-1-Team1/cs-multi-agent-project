---
doc_id: IG-METER-LPB-DIN
title: "DIN Rail Energy Meter (METER-LPB-DIN) — Installation and Commissioning Guide"
doc_type: IG
product_code: METER-LPB-DIN
family: METER
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# DIN Rail Energy Meter (METER-LPB-DIN) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: Panel cut-out 92 x 92 mm (panel type) or 35 mm DIN rail
- Operating temperature: -25 to +55 °C
- Degree of protection: IP51 (front)
- Above 1,000 m altitude, apply derating per the datasheet.

## 4. Wiring and tightening torques

- Terminal tightening torque: see dimension drawing
- Use copper conductors rated for at least 75 °C.
- Separate power and signal cables by at least 200 mm.

## 5. Commissioning procedure

1. Check CT polarity and phase sequence
2. Set CT and VT ratios
3. Set communication address and baud rate
4. Verify readings against a reference meter

## 6. Pre-energisation checklist

- [ ] Product rating matches the drawing
- [ ] All terminals tightened to specified torque
- [ ] Protective earth connected
- [ ] Insulation resistance measured and recorded
- [ ] Settings / parameters recorded

## 7. Common commissioning issues

| Symptom | Likely cause | See |
|---|---|---|
| Negative active power reading | CT polarity reversed | TG-METER-LPB-DIN §3.1 |
| No Modbus response | Address / baud / parity mismatch | TG-METER-LPB-DIN §3.2 |
| Pulse output not counted by PLC | Open-collector output polarity reversed | TG-METER-LPB-DIN §3.3 |

On-site commissioning support can be requested through the Global CS Center. For power & energy meters the request is handled by the technical support team.
