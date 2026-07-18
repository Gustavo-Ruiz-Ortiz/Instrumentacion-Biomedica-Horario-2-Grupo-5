import matplotlib
matplotlib.use('Qt5Agg')

import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

import serial
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import struct
import threading
import csv
import os
from datetime import datetime

# ============================================================
# CONFIGURACIÓN
# ============================================================
PORT        = 'COM14'
BAUD        = 115200
FS          = 128
WINDOW_SECS = 6
BUFFER_SIZE = FS * WINDOW_SECS

# ============================================================
# CSV — archivo nuevo por cada sesión
# ============================================================
csv_filename = f"healthypi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
csv_folder   = r"C:\Users\Administrador 1\Desktop\Presentación fianal"
os.makedirs(csv_folder, exist_ok=True)
csv_filepath = os.path.join(csv_folder, csv_filename)
csv_file     = open(csv_filepath, 'w', newline='', encoding='utf-8')
csv_writer   = csv.writer(csv_file)
csv_writer.writerow(['timestamp', 'ecg_raw', 'ecg_filtrado',
                     'bioz', 'ppg_ir', 'hr_bpm', 'rr_rpm',
                     'spo2_pct', 'altitud_m', 'estado_spo2'])
print(f"Guardando datos en: {csv_filepath}")

# ============================================================
# TABLA DE PERCENTILES SpO2 vs ALTITUD
# Fuente: Rojas-Camayo et al., Thorax 2018
# Columnas: altitud_m, p2_5, p10, p25, p75, p97_5
# ============================================================
SPO2_TABLA = [
    (    0,  95,  96,  97,  99, 100),
    (  500,  94,  95,  97,  99, 100),
    ( 1000,  93,  95,  96,  98,  99),
    ( 1500,  92,  94,  95,  98,  99),
    ( 2000,  90,  92,  94,  97,  98),
    ( 2500,  88,  90,  92,  96,  98),
    ( 3000,  85,  88,  91,  95,  97),
    ( 3500,  82,  85,  88,  93,  96),
    ( 4000,  78,  82,  86,  91,  94),
    ( 4500,  74,  78,  83,  89,  93),
    ( 5000,  70,  75,  80,  87,  91),
]

def interpolar_percentiles(alt_m):
    """Interpola percentiles SpO2 para una altitud dada."""
    if alt_m <= SPO2_TABLA[0][0]:
        return SPO2_TABLA[0][1:]
    if alt_m >= SPO2_TABLA[-1][0]:
        return SPO2_TABLA[-1][1:]
    for i in range(len(SPO2_TABLA) - 1):
        a0, *p0 = SPO2_TABLA[i]
        a1, *p1 = SPO2_TABLA[i+1]
        if a0 <= alt_m < a1:
            frac = (alt_m - a0) / (a1 - a0)
            return tuple(int(p0[j] + frac * (p1[j] - p0[j])) for j in range(5))
    return SPO2_TABLA[-1][1:]

def evaluar_spo2(spo2, alt_m):
    """Devuelve etiqueta de estado según percentil poblacional."""
    if alt_m < 0:
        return "SIN DATO"
    p2_5, p10, p25, p75, p97_5 = interpolar_percentiles(alt_m)
    if spo2 < p2_5:  return "CRITICO"
    if spo2 < p10:   return "BAJO"
    if spo2 < p25:   return "NORMAL-BAJO"
    if spo2 <= p75:  return "NORMAL"
    return "NORMAL-ALTO"

# Presión de referencia al nivel del mar (Pa)
PRESION_NM = 101325.0

def calcular_altitud(presion_hpa):
    """Fórmula barométrica ISA: altitud en metros desde presión en hPa."""
    presion_pa = presion_hpa * 100.0
    return 44330.0 * (1.0 - (presion_pa / PRESION_NM) ** (1.0 / 5.255))

# ============================================================
# FILTROS IIR MANUALES (sin scipy)
# ============================================================
class NotchFilter:
    def __init__(self, fs=128, f0=60, Q=30):
        w0    = 2 * np.pi * f0 / fs
        alpha = np.sin(w0 / Q) / 2
        a0    = 1 + alpha
        self.b = [1/a0, -2*np.cos(w0)/a0, 1/a0]
        self.a = [1,    -2*np.cos(w0)/a0, (1-alpha)/a0]
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def process(self, x):
        y = (self.b[0]*x + self.b[1]*self.x1 + self.b[2]*self.x2
             - self.a[1]*self.y1 - self.a[2]*self.y2)
        self.x2 = self.x1; self.x1 = x
        self.y2 = self.y1; self.y1 = y
        return y

class BandpassFilter:
    def __init__(self, fs=128, low=0.5, high=40.0):
        w    = 2 * np.pi * low / fs
        k    = np.tan(w / 2)
        norm = 1 / (1 + np.sqrt(2)*k + k*k)
        self.b1 = [norm, -2*norm, norm]
        self.a1 = [1, 2*(k*k-1)*norm, (1-np.sqrt(2)*k+k*k)*norm]
        w = 2 * np.pi * high / fs
        k = np.tan(w / 2)
        d = 1 + np.sqrt(2)*k + k*k
        self.b2 = [k*k/d, 2*k*k/d, k*k/d]
        self.a2 = [1, 2*(k*k-1)/d, (1-np.sqrt(2)*k+k*k)/d]
        self.x1_1=self.x2_1=self.y1_1=self.y2_1=0.0
        self.x1_2=self.x2_2=self.y1_2=self.y2_2=0.0

    def process(self, x):
        y1 = (self.b1[0]*x  + self.b1[1]*self.x1_1 + self.b1[2]*self.x2_1
              - self.a1[1]*self.y1_1 - self.a1[2]*self.y2_1)
        self.x2_1=self.x1_1; self.x1_1=x
        self.y2_1=self.y1_1; self.y1_1=y1
        y2 = (self.b2[0]*y1 + self.b2[1]*self.x1_2 + self.b2[2]*self.x2_2
              - self.a2[1]*self.y1_2 - self.a2[2]*self.y2_2)
        self.x2_2=self.x1_2; self.x1_2=y1
        self.y2_2=self.y1_2; self.y1_2=y2
        return y2

notch = NotchFilter()
bpf   = BandpassFilter()

# ============================================================
# BUFFERS
# ============================================================
ecg_raw  = deque([0]*BUFFER_SIZE, maxlen=BUFFER_SIZE)
ecg_filt = deque([0]*BUFFER_SIZE, maxlen=BUFFER_SIZE)
ppg_buf  = deque([0]*BUFFER_SIZE, maxlen=BUFFER_SIZE)
bioz_buf = deque([0]*BUFFER_SIZE, maxlen=BUFFER_SIZE)

hr_value     = [0]
spo2_value   = [0]
rr_value     = [0]
alt_value    = [-1.0]   # -1 = sin dato aún
estado_value = ["--"]

running = True

# ============================================================
# PARSER — Formato legacy OpenView (tipo 0x02, 22 bytes)
# [0-3]  ECG int32  [4-7]  BioZ int32  [8] skip
# [9-12] Red int32  [13-16] IR int32
# [17-18] temp      [19] spo2  [20] hr  [21] rr
# ============================================================
def parse_legacy_packet(payload):
    if len(payload) < 22:
        return None
    try:
        ecg  = struct.unpack('<i', bytes(payload[0:4]))[0]
        bioz = struct.unpack('<i', bytes(payload[4:8]))[0]
        red  = struct.unpack('<i', bytes(payload[9:13]))[0]
        ir   = struct.unpack('<i', bytes(payload[13:17]))[0]
        spo2 = payload[19]
        hr   = payload[20]
        rr   = payload[21]
        return ecg, bioz, red, ir, hr, rr, spo2
    except:
        return None

# ============================================================
# PARSER — Paquete de altitud (tipo 0x05, 4 bytes)
# int32 little-endian en centímetros (alt_cm = altitud_m * 100)
# Definido en data_module.c: CES_CMDIF_TYPE_ALTITUDE_DATA / send_altitude_packet()
# ============================================================
def parse_altitude_packet(payload):
    if len(payload) < 4:
        return None
    try:
        alt_cm = struct.unpack('<i', bytes(payload[0:4]))[0]
        return alt_cm / 100.0
    except:
        return None

# ============================================================
# HILO DE LECTURA SERIAL
# ============================================================
def read_serial():
    global running
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        print(f"Conectado a {PORT}")
    except Exception as e:
        print(f"Error abriendo puerto: {e}")
        running = False
        return

    buf = bytearray()

    while running:
        try:
            incoming = ser.read(ser.in_waiting or 1)
            if incoming:
                buf.extend(incoming)

            while len(buf) >= 7:
                idx = -1
                for i in range(len(buf) - 1):
                    if buf[i] == 0x0A and buf[i+1] == 0xFA:
                        idx = i
                        break
                if idx == -1:
                    buf = buf[-1:]
                    break
                if idx > 0:
                    buf = buf[idx:]
                if len(buf) < 5:
                    break

                pkt_len   = buf[2] | (buf[3] << 8)
                pkt_type  = buf[4]
                total_len = 5 + pkt_len + 2

                if len(buf) < total_len:
                    break

                if buf[total_len - 1] == 0x0B:
                    payload = buf[5:5 + pkt_len]

                    if pkt_type == 0x02:
                        result = parse_legacy_packet(payload)
                        if result:
                            ecg, bioz, red, ir, hr, rr, spo2 = result

                            # Filtrar ECG
                            f = notch.process(float(ecg))
                            f = bpf.process(f)
                            ecg_raw.append(ecg)
                            ecg_filt.append(f)
                            bioz_buf.append(bioz)
                            ppg_buf.append(ir)

                            if hr   > 0: hr_value[0]   = hr
                            if rr   > 0: rr_value[0]   = rr
                            if spo2 > 0: spo2_value[0] = spo2

                            # Evaluación SpO2 por altitud
                            alt   = alt_value[0]
                            estado = evaluar_spo2(spo2, alt) if spo2 > 0 else "--"
                            estado_value[0] = estado

                            # Guardar en CSV
                            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                            csv_writer.writerow([
                                ts, ecg, round(f, 2),
                                bioz, ir, hr, rr,
                                spo2,
                                round(alt, 1) if alt >= 0 else '',
                                estado
                            ])

                    elif pkt_type == 0x05:
                        alt_m = parse_altitude_packet(payload)
                        if alt_m is not None:
                            alt_value[0] = alt_m

                buf = buf[total_len:]

        except Exception as e:
            print(f"Error serial: {e}")
            break

    ser.close()

# ============================================================
# VISUALIZACIÓN
# ============================================================
fig, axes = plt.subplots(3, 1, figsize=(14, 8))
fig.patch.set_facecolor('#1a1a2e')
fig.suptitle('HealthyPi 5 — Monitor en Tiempo Real', color='white', fontsize=14)

for ax in axes:
    ax.set_facecolor('#16213e')
    ax.tick_params(colors='white')
    for spine in ax.spines.values():
        spine.set_color('#444')

line_ecg,  = axes[0].plot([], [], color='#00ff88', lw=1)
line_ppg,  = axes[1].plot([], [], color='#ff6b35', lw=1)
line_bioz, = axes[2].plot([], [], color='#4ecdc4', lw=1)

axes[0].set_ylabel('ECG (filtrado)', color='white')
axes[1].set_ylabel('PPG / IR',       color='white')
axes[2].set_ylabel('BioZ / Resp',    color='white')
axes[2].set_xlabel('Muestras',       color='white')

txt_hr    = axes[0].text(0.01, 0.85, 'HR: -- bpm',
                         transform=axes[0].transAxes, color='#00ff88', fontsize=12)
txt_spo2  = axes[1].text(0.01, 0.85, 'SpO2: -- %',
                         transform=axes[1].transAxes, color='#ff6b35', fontsize=12)
txt_rr    = axes[2].text(0.01, 0.85, 'RR: -- rpm',
                         transform=axes[2].transAxes, color='#4ecdc4', fontsize=12)
txt_alt   = axes[1].text(0.75, 0.85, 'Alt: -- m',
                         transform=axes[1].transAxes, color='#f0e68c', fontsize=11)
txt_estado= axes[1].text(0.50, 0.85, 'SpO2: --',
                         transform=axes[1].transAxes, color='#ffffff', fontsize=11)

# Colores por estado SpO2
ESTADO_COLOR = {
    "CRITICO":     '#ff0000',
    "BAJO":        '#ff6600',
    "NORMAL-BAJO": '#ffcc00',
    "NORMAL":      '#00ff88',
    "NORMAL-ALTO": '#00ccff',
    "--":          '#ffffff',
}

x_data = np.arange(BUFFER_SIZE)

def update(frame):
    ecg_arr  = np.array(ecg_filt)
    ppg_arr  = np.array(ppg_buf)
    bioz_arr = np.array(bioz_buf)

    line_ecg.set_data(x_data,  ecg_arr)
    line_ppg.set_data(x_data,  ppg_arr)
    line_bioz.set_data(x_data, bioz_arr)

    for ax, arr in zip(axes, [ecg_arr, ppg_arr, bioz_arr]):
        ax.set_xlim(0, BUFFER_SIZE)
        if arr.max() != arr.min():
            margin = (arr.max() - arr.min()) * 0.1
            ax.set_ylim(arr.min() - margin, arr.max() + margin)

    txt_hr.set_text(f'HR: {hr_value[0]} bpm')
    txt_spo2.set_text(f'SpO2: {spo2_value[0]} %')
    txt_rr.set_text(f'RR: {rr_value[0]} rpm')

    alt = alt_value[0]
    txt_alt.set_text(f'Alt: {alt:.0f} m' if alt >= 0 else 'Alt: -- m')

    estado = estado_value[0]
    txt_estado.set_text(f'Estado: {estado}')
    txt_estado.set_color(ESTADO_COLOR.get(estado, '#ffffff'))

    return (line_ecg, line_ppg, line_bioz,
            txt_hr, txt_spo2, txt_rr, txt_alt, txt_estado)

# ============================================================
# ZOOM CON RUEDA DEL MOUSE
# ============================================================
def on_scroll(event):
    ax = event.inaxes
    if ax is None:
        return
    scale = 0.8 if event.button == 'up' else 1.2
    ylim  = ax.get_ylim()
    mid   = (ylim[0] + ylim[1]) / 2
    half  = (ylim[1] - ylim[0]) / 2 * scale
    ax.set_ylim(mid - half, mid + half)
    fig.canvas.draw_idle()

fig.canvas.mpl_connect('scroll_event', on_scroll)

# ============================================================
# INICIO
# ============================================================
t = threading.Thread(target=read_serial, daemon=True)
t.start()

ani = animation.FuncAnimation(fig, update, interval=50, blit=True,
                               cache_frame_data=False)
plt.tight_layout()
try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    running = False
    csv_file.close()
    print(f"\nSesión finalizada. Datos guardados en:\n  {csv_filepath}")