---
doc_id: IG-METER-LP3500-3P4W
title: "Smart Power Meter 3P4W (METER-LP3500-3P4W) — Installation and Commissioning Guide"
doc_type: IG
product_code: METER-LP3500-3P4W
family: METER
revision: B
language: en
synthetic: true
---

> SYNTHETIC DATA — 교육용 가상 데이터이며 실제 제품 사양·운영 기준과 무관합니다.

# Smart Power Meter 3P4W (METER-LP3500-3P4W) — Installation and Commissioning Guide

## 1. Safety

Installation, wiring and commissioning must be performed by qualified personnel. Disconnect and lock out all power sources before work. Verify absence of voltage.

## 2. Receiving and storage

Inspect the packaging on arrival and report damage within 7 days (see POL-RETURN). Store indoors in a dry place between -25 and +55 °C, relative humidity below 85% without condensation.

## 3. Mounting and clearances

- Required clearances: Panel cut-out 92 x 92 mm (panel type) or 35 mm DIN rail
- Operating temperature: -10 to +55 °C
- Degree of protection: IP54 (front)
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
| Negative active power reading | CT polarity reversed | TG-METER-LP3500-3P4W §3.1 |
| No Modbus response | Address / baud / parity mismatch | TG-METER-LP3500-3P4W §3.2 |
| No response at 38400 even parity | Firmware defect at 38400 / even parity | TG-METER-LP3500-3P4W §3.3 |
| Energy register reset after power loss | Firmware defect during flash write | TG-METER-LP3500-3P4W §3.4 |

On-site commissioning support can be requested through the Global CS Center. For power & energy meters the request is handled by the technical support team.
