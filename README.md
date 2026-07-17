# Instrumentacion-Biomedica-Horario-2-Grupo-5

Sistema portátil de triaje cardiopulmonar con corrección por altitud - HealthyPi 5 / RP2040

---
## Equipo — Grupo 5

| Integrante | Aporte principal |
|---|---|
| Aldo David Manturano Lopez | Seguridad eléctrica y normativa (IEC 60601-1-11) |
| David Eddy Aguilar Yahuana | Diseño de señal, energía y costo |
| Juan Raul Ramirez Mendoza | Energía, almacenamiento y costo |
| Alejandra Ivonne Gamarra Leyva | Precisión de señales, autonomía, ergonomía y electrónica |
| Davidt Brayamn Fernandez Bernaola | Diseño de señal y visualización |
| Gustavo Andre Ruiz Ortiz | Programación, firmware (Python/Zephyr), corrección por altitud, filtrado digital y validación electrónica |

Curso: Instrumentación Biomédica — Universidad Peruana Cayetano Heredia (UPCH)

---

## Tabla de contenidos

-[Equipo](#equipo)
- [Descripción del proyecto](#descripción-del-proyecto)
- [Problema que resuelve](#problema-que-resuelve)
- [Características principales](#características-principales)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Stack tecnológico](#stack-tecnológico)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Instalación y uso](#instalación-y-uso)
- [Resultados de validación](#resultados-de-validación)
- [Roadmap](#roadmap)



---

## Descripción del proyecto

Dispositivo portátil, autónomo y totalmente offline para el triaje cardiopulmonar en puestos de salud rurales de altura (>2500 msnm), desarrollado sobre la plataforma HealthyPi 5 (RP2040). Adquiere ECG, PPG/SpO2 y frecuencia respiratoria derivada, y reinterpreta automáticamente los valores según la altitud real del punto de atención, evitando falsas alarmas de hipoxia propias de los monitores calibrados a nivel del mar.

Proyecto desarrollado en el curso de Instrumentación Biomédica, Universidad Peruana Cayetano Heredia (UPCH) — Grupo 5.

## Problema que resuelve

Los puestos de salud rurales altoandinos enfrentan dos limitaciones simultáneas que ningún equipo comercial resuelve en conjunto:

| Limitación | Consecuencia |
|---|---|
| Monitores calibrados a nivel del mar | Falsas alarmas de hipoxia en población aclimatada a la altura |
| Infraestructura eléctrica y conectividad inestables/inexistentes | Los equipos dependientes de nube, WiFi o smartphone no son viables |

## Características principales

- ECG (derivación II de Einthoven) mediante chip MAX30001
- PPG / SpO2 mediante chip AFE4400 (660 nm rojo / 905 nm infrarrojo)
- Frecuencia respiratoria derivada del ECG por neumografía de impedancia transtorácica, sin sensores adicionales
- Corrección automática por altitud en tiempo real (sensor atmosférico BME280) usando percentiles poblacionales de referencia
- Operación 100% offline: visualización en pantalla TFT + almacenamiento local en MicroSD
- Plataforma web de post-análisis en Python/Streamlit con filtrado digital de señal (Notch IIR 60 Hz + Butterworth pasa-bajas) y control de acceso por token OTP
- Batería de Litio 3.7V/2500 mAh — 17 horas de autonomía (~200 sesiones de triaje)
- Diseño conforme a IEC 60601-1-11 (seguridad eléctrica en entornos sin conexión a tierra confiable)
- Enclosure diseñado en Fusion 360 e impreso en 3D (PLA)

## Arquitectura del sistema

```
┌─────────────────────────────┐
│        Sensores              │
│  MAX30001 (ECG + Resp.)      │
│  AFE4400 (PPG / SpO2)        │
│  BME280 (Altitud)            │
└──────────────┬───────────────┘
               │  I2C / Qwiic
               ▼
┌─────────────────────────────┐
│   HealthyPi 5 — RP2040       │
│   Firmware: Zephyr RTOS      │
│   Lógica de corrección       │
│   por altitud (percentiles)  │
└──────────────┬───────────────┘
       ┌────────┴────────┐
       ▼                 ▼
┌─────────────┐   ┌─────────────────┐
│ Pantalla TFT │   │  MicroSD (log)   │
└─────────────┘   └────────┬────────┘
                            │ export
                            ▼
                ┌───────────────────────┐
                │ Interfaz Python        │
                │ (Streamlit)             │
                │ Filtrado digital        │
                │ Acceso por token OTP    │
                └───────────────────────┘
```

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Microcontrolador | RP2040 (HealthyPi 5) |
| Firmware | Zephyr RTOS |
| Adquisición biopotenciales | MAX30001 |
| Adquisición PPG/SpO2 | AFE4400 |
| Sensor ambiental | BME280 (altitud) |
| Almacenamiento embebido | MicroSD |
| Post-procesamiento | Python, filtros digitales (Notch IIR, Butterworth) |
| Interfaz de usuario web | Streamlit |
| Seguridad de acceso | Tokens OTP |
| Diseño mecánico | Fusion 360 + impresión 3D (PLA) |
| Normativa | IEC 60601-1-11 |

## Estructura del repositorio

```
Instrumentacion-Biomedica-Horario-2-Grupo-5/
├── firmware/            # Código Zephyr para HealthyPi 5 (RP2040)
│   ├── src/
│   └── boards/
├── interfaz-python/     # Aplicación Streamlit de post-análisis
│   ├── app.py
│   ├── filtros.py
│   └── auth_otp.py
├── diseño-mecanico/     # Archivos Fusion 360 / STL del enclosure
├── docs/                # Informes, diagramas y datasheets
│   ├── Informe4_g5.docx
│   └── Informe5_6_Grupo5.docx
├── resultados/          # Capturas de pruebas de validación (OpenView 2)
├── .gitignore
└── README.md
```

## Instalación y uso

### Firmware (Zephyr / RP2040)

```bash
git clone https://github.com/Gustavo-Ruiz-Ortiz/Instrumentacion-Biomedica-Horario-2-Grupo-5.git
cd Instrumentacion-Biomedica-Horario-2-Grupo-5/firmware
west build -b healthypi5 .
west flash
```

### Interfaz Python (post-análisis)

```bash
cd interfaz-python
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Resultados de validación

Prueba de adquisición en banco (5 min continuos, sujeto sano, línea base a nivel del mar):

| Señal | Resultado | Método |
|---|---|---|
| ECG | 92 BPM estable | Detección de intervalo R-R, amplitud promedio 1.2 mV |
| SpO2 | 98% | PPG, sensor de pinza dactilar |
| Frecuencia respiratoria | 41 RPM | Neumografía por impedancia transtorácica derivada del ECG |

Se caracterizó además un artefacto de movimiento inducido intencionalmente, validando la etapa de filtrado digital implementada en la interfaz Python.

## Roadmap

- [ ] Filtros adicionales para artefactos de movimiento en PPG
- [ ] Validación clínica con mayor número de pacientes
- [ ] Estudio de mercado formal
- [ ] Evaluación de manufactura escalable del enclosure
- [ ] Trámite de protección de la invención ante la OPI-UPCH
