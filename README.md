# Lidl TRONIC Solarspeicher 2.2 kWh — Tuya DP Reverse Engineering & Home Assistant Integration

Reverse-engineertes Tuya-DataPoint-Mapping für den **Lidl TRONIC Solarspeicher 2.2 kWh** (Marstek-Klon, Tuya Product Category `bxsdy`), inkl. Dekodierung der Base64-DPs (PV, Batterie, DC-Ausgang, Entlade-Zeitfenster) und einer YAML-Gerätedefinition für [`make-all/tuya-local`](https://github.com/make-all/tuya-local).

> ⚠️ Community-Reverse-Engineering. Nicht von Lidl, Marstek oder Tuya autorisiert. Keine Garantie auf Korrektheit. Nutzung auf eigenes Risiko — Schreib-DPs können das Gerät unerwartet beeinflussen.

**Status:** Numerische DPs überwiegend verifiziert (DP 37 als Solarerzeugung via lokalem tinytuya-Dump bestätigt), Base64-Dekodierung der wichtigsten DPs durch Messreihen bestätigt. Noch offen: DP 113 (immer 0, unklar) und `逆変器類型`. Korrekturen und Beiträge via Issue oder PR willkommen.

---

## Kontext

- **Gerät:** Lidl TRONIC Solarspeicher 2.2 kWh (Marstek-Klon)
- **App:** Tuya (nicht Lidl Home)
- **Device ID:** `<DEVICE_ID>` (eigene ID einsetzen)
- **Product Category:** `bxsdy` (solarpowerstorage)
- **Tuya IoT Platform:** Central Europe Data Center
- **Ziel:** Lokale Integration in Home Assistant via **tuya-local** (HACS)

---

## Infrastruktur

### Tuya IoT Platform
- Account: `<TUYA_EMAIL>`
- Projekt: "Home"
- API Access ID & Secret: bereits konfiguriert

### Home Assistant
- **tuya-local** via HACS installiert ([github.com/make-all/tuya-local](https://github.com/make-all/tuya-local))
- Benötigt noch: **Local Key** des Geräts

### Local Key abrufen
1. [iot.tuya.com](https://iot.tuya.com) → Cloud → Projekt → API Explorer
2. Smart Home Basic Service → Device Management → **Get Device Information**
3. Device ID: `<DEVICE_ID>`
4. Im Response: Feld `local_key` notieren

---

## DP Mapping – Vollständige Übersicht

### Numerische DPs – bestätigt ✅

| DP ID | Wert | Beschreibung | Einheit | Skalierung | Validierung |
|---|---|---|---|---|---|
| **1** | 100 | Ladestand | % | ×1 | App + Device Log übereinstimmend |
| **2** | 21504 | Restzeit | min | ×1 | 21504 = 358h 24min, App bestätigt |
| **4** | 0 | Fehler | — | ×1 | 0 = kein Fehler, Tuya Standard |
| **10** | 32 | Batterietemperatur | °C | ×1 | App zeigt 32°C, DP-Name temp_current |
| **37** | 1369 | Solarerzeugung gesamt (Lifetime, „Reverse Energy Total") | kWh | ÷100 | 1369÷100=13.69 kWh = App „Solarenergie/Stromerzeugung" + lokaler DP-Dump ✓ |
| **102** | 750 | Gesamtladung Lifetime | kWh | ÷100 | 750÷100=7.50 kWh, App: 7.5 kWh ✓ |
| **103** | 683 | Gesamtentladung Lifetime | kWh | ÷100 | 683÷100=6.83 kWh, App: 6.83 kWh ✓ |
| **104** | 1171 | Gesamtausgang/Verbrauch (Lifetime, „Electric Total") | kWh | ÷100 | 1171÷100=11.71 kWh = App „Ausgangsleistung/Stromverbrauch" + lokaler DP-Dump ✓ |
| **105** | charge_first | Lademodus | Enum | — | Toggle in App → Log zeigte charge_discharge ✓ |
| **107** | 80 | Entladetiefe (DoD) | % | ×1 | Device Log = 80%, App bestätigt ✓ |
| **109** | discharge | Ladestatus | Enum | — | standby / charge / discharge im Log beobachtet ✓ |
| **111** | True | Daten-Refresh Befehl (mbeb: evtl. WR aktiv/inaktiv) | Bool | — | App Client sendet on → Device antwortet ✓ |
| **115** | 600 | WR-Leistungslimit (Sollwert, max 600W; ≠ Momentan-Ausgang) | W | ×1 | Log konstant 600 bei Live-Ausgang 320W → Limit, nicht Istwert ✓ |

---

### Numerische DPs – plausibel, noch nicht 100% bestätigt ⚠️

| DP ID | Wert | Beschreibung | Einheit | Skalierung | Was noch fehlt |
|---|---|---|---|---|---|
| **108** | 80 | Mindestausgangsleistung (WR-Abschaltgrenze) | W | ×1 | Keine Logs vorhanden, logisch aus WR-Verhalten abgeleitet – Änderung in App noch nicht getestet |

---

### Numerische DPs – ungeklärt ❓

| DP ID | Wert | Hypothese | Was zu tun |
|---|---|---|---|
| **113** | 0 | Unklar – auch bei aktiver Entladung (DP 109 = discharge) weiter 0. mbeb-Hypothese „WR-Ausgangsleistung" damit **widerlegt** (wäre ~320W). Echte Ausgangsleistung steckt in `dc_message` | niedrige Priorität |

---

### Base64 DPs – bestätigt ✅

> ⚠️ Hinweis: Die Base64-DPs sind lokal **„push-only"** — sie erscheinen **nicht** in `tinytuya status()`, **nicht** über `detect_available_dps()` und **nicht** im Cloud-Standard-Status. Das Gerät pusht sie nur asynchron (~alle 10 min) bzw. an die Cloud (Device-Logs). localtuya/tuya-local fangen sie über ihre **persistente Verbindung** ab; ein Einzel-Abruf reicht nicht.

#### `dc_message` – DC Ausgang (AUS1 + AUS2) ✅

**Format:** 13 Bytes

```
byte[0]       = Status/Flag:
                  0 = normaler Betrieb / Stand-by
                  3 = Zeitfenster-gesteuerte Entladung aktiv
byte[1:3] ÷10  = DC1 Spannung (V)   → AUS1
byte[3:5] ÷100 = DC1 Strom (A)      → AUS1
byte[5:7]      = DC1 Leistung (W)   → AUS1
byte[7:9] ÷10  = DC2 Spannung (V)   → AUS2
byte[9:11] ÷10 = DC2 Strom (A)      → AUS2
byte[11:13]    = DC2 Leistung (W)   → AUS2
```

**Verifikation über 12 Timestamps:**

| Zeit | Flag | DC1-V | DC1-A | DC1-W | DC2-V | DC2-A | DC2-W | Total |
|---|---|---|---|---|---|---|---|---|
| 20:52 | **3** | 35.5V | 4.25A | 160W | 28.1V | 5.2A | 157W | **317W** |
| 20:48 | **3** | 32.8V | 4.73A | 160W | 32.1V | 4.8A | 160W | **320W** |
| 20:38 | 0 | 6.5V | 0A | 0W | 6.5V | 0A | 0W | 0W |
| 20:28 | 0 | 32.4V | 0.83A | 27W | 32.7V | 0.7A | 25W | 52W |
| 20:18 | 0 | 30.5V | 1.26A | 38W | 29.0V | 1.2A | 35W | 73W |
| 20:08 | 0 | 30.5V | 1.65A | 50W | 29.6V | 1.6A | 48W | 98W |
| 19:58 | 0 | 30.4V | 2.01A | 61W | 29.5V | 1.9A | 58W | 119W |
| 19:48 | 0 | 30.3V | 2.31A | 70W | 30.0V | 2.2A | 68W | 138W |
| 19:38 | 0 | 30.3V | 2.70A | 81W | 29.6V | 2.6A | 79W | 160W |
| 19:28 | 0 | 30.4V | 2.97A | 90W | 30.0V | 2.9A | 88W | 178W |
| 16:40 | 0 | 28.5V | 7.01A | 200W | 28.9V | 7.0A | 204W | 404W |
| 15:53 | 0 | 0.2V | 0A | 0W | 0.2V | 0A | 0W | 0W |

> **Beobachtungen:**
> - Abend 19:28–20:28: PV nimmt ab, Ausgang sinkt von 178W auf 0W (Akku leer / Pause)
> - 20:48–20:52: Flag springt auf **3**, Zeitfenster-Slot 1 aktiv (20:30–23:59, 320W)
> - Bei Charge (15:53): Ausgänge 0W, PV-Energie fließt direkt in Batterie
> - V×A ≈ W bei **flag 0** (gemessene Leistung) → Dekodierung bestätigt ✅
> - Bei **flag 3** (Zeitfenster) meldet das Leistungs-Byte den **kommandierten Slot-Sollwert** (320W ÷ 2 = 160W je Kanal), nicht die gemessene V×A (~150W) — bestätigt 27.05.2026

---

#### `pv_canshu` (PV参数) – Solar PV Eingang ✅

**Format:** 13 Bytes

```
byte[0]        = Flag/Version
byte[1:3] ÷10  = PV1 Spannung (V)
byte[3:5] ÷10  = PV1 Strom (A)
byte[5:7]      = PV1 Leistung (W)
byte[7:9] ÷10  = PV2 Spannung (V)
byte[9:11] ÷100 = PV2 Strom (A)
byte[11:13]    = PV2 Leistung (W)
```

**Verifikation:**
- `AAEWAEgAyQESAtwAyQ==` → PV1: 27.8V / 7.2A / **201W** ✅ | PV2: 27.4V / 7.32A / **201W** ✅
- Messreihe 27.05.2026 (Sonnenuntergang, flag 3): PV gesamt 62 → 11 → 8 → 4 W, V×A bei allen Samples konsistent ✅

> Hinweis: Skalierungsunterschied PV1 Strom ÷10, PV2 Strom ÷100. byte[0] im Entladebetrieb = 3.

---

#### `battery_parameters` – Batterie V/A/W ✅

**Format:** 6 Bytes

```
byte[0:2] ÷10 = Batteriespannung (V)
byte[2:4] ÷10 = Batteriestrom (A)
byte[4:6]     = Batterieleistung (W)   ← ×1 (KEIN Teiler!)
```

**Verifikation:**
- `AdwALwDj` → 47.6V / 4.7A / **227W** ✅ (Ladebetrieb; 47.6×4.7 = 224 ≈ 227)
- `Ad4AAgAA` → 47.8V / 0.2A / 0W ✅ (Standby, Akku voll)
- `Ac4ARgFF` → 46.2V / 7.0A / **325W** ✅ (Entladung 27.05.2026; 46.2×7.0 = 323 ≈ 325)

> ⚠️ Korrektur 27.05.2026: Leistung ist `byte[4:6]` **×1**, nicht ÷10 (frühere Annahme war falsch — V×A-Gegenprobe **und** Live-Entladung bei 325W bestätigen ×1).

---

### Base64 DPs – plausibel, noch nicht 100% bestätigt ⚠️

#### `放电模式` – Entlademodus Zeitfenster

**Format:** 36 Bytes = 1B Header + 5× 7B Slots

```
byte[0]     = Header/Flag (immer 0)

Pro Slot (7 Bytes, Offset = 1 + slot_index * 7):
  byte[0]   = Aktiv: 1=aktiv, 0=inaktiv
  byte[1]   = Start Stunde (0–23)
  byte[2]   = Start Minute (0–59)
  byte[3]   = End Stunde (0–23)
  byte[4]   = End Minute (0–59)
  byte[5:7] = Leistung uint16 Big-Endian (W)
```

**Aktuelle Konfiguration:**

| Slot | Offset | Aktiv | Start | Ende | Leistung |
|---|---|---|---|---|---|
| 1 | 1 | ✅ | 20:30 | 23:59 | 320W |
| 2 | 8 | ✅ | 00:00 | 05:00 | 320W |
| 3 | 15 | ❌ | 05:00 | 20:30 | 80W |
| 4 | 22 | ❌ | 00:00 | 23:59 | 80W |
| 5 | 29 | ❌ | 00:00 | 23:59 | 80W |

> Slot 1 (20:30–23:59, 320W) indirekt bestätigt: am 27.05.2026 20:49–21:09 `dc_message` flag 3 + 320W WR-Ausgang während dieses Fensters.

---

### Base64 DPs – ungeklärt ❓

#### `逆変器類型` – WR-Konfiguration

**Format:** 8 Bytes – **Struktur und Bedeutung unklar**

Dekodierte uint16-BE-Werte: **1004, 360, 30, 600**. Hypothese: WR-Limits (30W min, 360W default?, 600W max) – nicht bestätigt. Wahrscheinlich read-only, niedrige Priorität.

---

### Steuerbare DPs

| DP ID | String-Name | Typ | Beschreibung | Werte |
|---|---|---|---|---|
| 105 | `充电模式` | Enum | Lademodus | `charge_first` / `charge_discharge` |
| 107 | `放电深度` | Integer | Entladetiefe (DoD) | 1–100 % |
| 111 | `主动更新数据` | Boolean | Daten-Refresh auslösen (mbeb: ggf. WR an/aus) | `true` |
| 115 | `微逆功率` | Integer | WR-Leistungslimit (Sollwert) | W (0–600W) |
| — | `放电模式` | Base64 | Entladezeitfenster (5 Slots) | siehe Struktur oben |

---

### Ungeklärte DPs

| DP ID | Wert | Bemerkung |
|---|---|---|
| 108 | 80 | `电池启动阈值` – Mindestausgangsleistung in W, unter diesem Wert schaltet WR ab |
| 113 | 0 | Unklar – 0 auch bei aktiver Entladung; mbeb-Hypothese „WR-Leistung" widerlegt |
| dc_message byte[2] | 1–2 bei Charge | Bedeutung bei Ladestatus unklar |

---

## Python Hilfsfunktionen

```python
import base64
import struct


def _d(s: str) -> bytes:
    s = s.rstrip('=')
    return base64.b64decode(s + '=' * ((4 - len(s) % 4) % 4))


def decode_battery_parameters(b64: str) -> dict:
    """battery_parameters → Spannung, Strom, Leistung der Batterie."""
    raw = _d(b64)
    return {
        "voltage_v": struct.unpack(">H", raw[0:2])[0] / 10,
        "current_a": struct.unpack(">H", raw[2:4])[0] / 10,
        "power_w":   struct.unpack(">H", raw[4:6])[0],   # ×1, nicht ÷10
    }


def decode_pv_parameters(b64: str) -> dict:
    """pv_canshu → PV1 und PV2 Spannung, Strom, Leistung."""
    raw = _d(b64)
    return {
        "pv1_voltage_v":  struct.unpack(">H", raw[1:3])[0] / 10,
        "pv1_current_a":  struct.unpack(">H", raw[3:5])[0] / 10,
        "pv1_power_w":    struct.unpack(">H", raw[5:7])[0],
        "pv2_voltage_v":  struct.unpack(">H", raw[7:9])[0] / 10,
        "pv2_current_a":  struct.unpack(">H", raw[9:11])[0] / 100,
        "pv2_power_w":    struct.unpack(">H", raw[11:13])[0],
    }


def decode_dc_message(b64: str) -> dict:
    """dc_message → DC1 (AUS1) und DC2 (AUS2) Spannung, Strom, Leistung.

    Flag-Werte:
        0 = normaler Betrieb / Stand-by
        3 = Zeitfenster-gesteuerte Entladung aktiv
    """
    raw = _d(b64)
    return {
        "flag":          raw[0],
        "dc1_voltage_v": struct.unpack(">H", raw[1:3])[0] / 10,
        "dc1_current_a": struct.unpack(">H", raw[3:5])[0] / 100,
        "dc1_power_w":   struct.unpack(">H", raw[5:7])[0],
        "dc2_voltage_v": struct.unpack(">H", raw[7:9])[0] / 10,
        "dc2_current_a": struct.unpack(">H", raw[9:11])[0] / 10,
        "dc2_power_w":   struct.unpack(">H", raw[11:13])[0],
        "total_power_w": struct.unpack(">H", raw[5:7])[0] +
                         struct.unpack(">H", raw[11:13])[0],
    }


def decode_discharge_schedule(b64: str) -> list:
    """放电模式 → Liste der 5 Zeitfenster."""
    raw = _d(b64)
    slots = []
    for i in range(5):
        o = 1 + i * 7
        s = raw[o:o + 7]
        slots.append({
            "enabled": bool(s[0]),
            "start":   f"{s[1]:02d}:{s[2]:02d}",
            "end":     f"{s[3]:02d}:{s[4]:02d}",
            "power_w": struct.unpack(">H", s[5:7])[0],
        })
    return slots


def encode_discharge_schedule(slots: list, header: int = 0) -> str:
    """5 Zeitfenster → Base64 String für 放电模式."""
    raw = bytes([header])
    for slot in slots:
        sh, sm = map(int, slot["start"].split(":"))
        eh, em = map(int, slot["end"].split(":"))
        pw = slot["power_w"]
        raw += bytes([
            1 if slot["enabled"] else 0,
            sh, sm, eh, em,
            (pw >> 8) & 0xFF,
            pw & 0xFF,
        ])
    return base64.b64encode(raw).decode()
```

---

## tuya-local Konfiguration

### Gerät hinzufügen
1. HA → Einstellungen → Geräte & Dienste → Integration hinzufügen → **tuya-local**
2. Host: feste IP des Speichers (im Router DHCP-Reservation einrichten!)
3. Device ID: `<DEVICE_ID>`
4. Local Key: (aus API Explorer abrufen)
5. Protocol: `3.3` oder `3.4`

### Custom Device YAML
Pfad: `/config/custom_components/tuya_local/devices/solarspeicher_bxsdy.yaml`

```yaml
name: Solarspeicher bxsdy
primary_entity:
  entity: sensor
  name: Batterie
  dps:
    - id: 1
      type: integer
      name: sensor
      unit: "%"
      class: battery
    - id: 10
      type: integer
      name: current_temperature
      unit: "°C"
      class: temperature
    - id: 2
      type: integer
      name: remain_time
      unit: "min"
    - id: 4
      type: bitfield
      name: fault
    - id: 109
      type: string
      name: charge_status

secondary_entities:
  - entity: sensor
    name: Energie
    dps:
      - id: 102
        type: integer
        name: total_energy_charged
        unit: "kWh"
        class: energy
        mapping:
          - scale: 0.01
      - id: 103
        type: integer
        name: total_energy_discharged
        unit: "kWh"
        class: energy
        mapping:
          - scale: 0.01
      - id: 104
        type: integer
        name: total_output_energy
        unit: "kWh"
        class: energy
        mapping:
          - scale: 0.01

  - entity: select
    name: Lademodus
    dps:
      - id: 105
        type: string
        name: option
        mapping:
          - dps_val: charge_first
            value: "Akku zuerst laden"
          - dps_val: charge_discharge
            value: "Laden und Entladen"

  - entity: number
    name: WR Ausgangsleistung
    dps:
      - id: 115
        type: integer
        name: value
        unit: "W"
        range:
          min: 0
          max: 600

  - entity: number
    name: Entladetiefe DoD
    dps:
      - id: 107
        type: integer
        name: value
        unit: "%"
        range:
          min: 1
          max: 100

  - entity: button
    name: Daten aktualisieren
    dps:
      - id: 111
        type: boolean
        name: button
```

---

## Base64 DPs in HA dekodieren

Da localtuya die Base64-DPs nicht direkt anzeigt, gibt es zwei Wege:

### Option A: AppDaemon (empfohlen)

```python
# apps/solarspeicher.py
import appdaemon.plugins.hass.hassapi as hass
import base64, struct

def _d(s):
    s = s.rstrip('=')
    return base64.b64decode(s + '=' * ((4 - len(s) % 4) % 4))

class Solarspeicher(hass.Hass):
    def initialize(self):
        self.listen_state(self.on_dc_message,        "sensor.solarspeicher_dc_message")
        self.listen_state(self.on_pv_params,         "sensor.solarspeicher_pv_canshu")
        self.listen_state(self.on_battery_params,    "sensor.solarspeicher_battery_parameters")

    def on_dc_message(self, entity, attribute, old, new, kwargs):
        if not new or new in ('unavailable', 'unknown'):
            return
        raw = _d(new)
        flag   = raw[0]
        dc1_w  = struct.unpack(">H", raw[5:7])[0]
        dc2_w  = struct.unpack(">H", raw[11:13])[0]
        self.set_state("sensor.solarspeicher_aus1_leistung",
                       state=dc1_w,
                       attributes={"unit_of_measurement": "W",
                                   "device_class": "power",
                                   "flag": flag})
        self.set_state("sensor.solarspeicher_aus2_leistung",
                       state=dc2_w,
                       attributes={"unit_of_measurement": "W",
                                   "device_class": "power"})
        self.set_state("sensor.solarspeicher_ausgang_gesamt",
                       state=dc1_w + dc2_w,
                       attributes={"unit_of_measurement": "W",
                                   "device_class": "power",
                                   "zeitfenster_aktiv": flag == 3})

    def on_pv_params(self, entity, attribute, old, new, kwargs):
        if not new or new in ('unavailable', 'unknown'):
            return
        raw = _d(new)
        pv1_w = struct.unpack(">H", raw[5:7])[0]
        pv2_w = struct.unpack(">H", raw[11:13])[0]
        self.set_state("sensor.solarspeicher_pv1_leistung",
                       state=pv1_w, attributes={"unit_of_measurement": "W"})
        self.set_state("sensor.solarspeicher_pv2_leistung",
                       state=pv2_w, attributes={"unit_of_measurement": "W"})
        self.set_state("sensor.solarspeicher_pv_gesamt",
                       state=pv1_w + pv2_w, attributes={"unit_of_measurement": "W"})

    def on_battery_params(self, entity, attribute, old, new, kwargs):
        if not new or new in ('unavailable', 'unknown'):
            return
        raw = _d(new)
        v = struct.unpack(">H", raw[0:2])[0] / 10
        a = struct.unpack(">H", raw[2:4])[0] / 10
        w = struct.unpack(">H", raw[4:6])[0]   # ×1, nicht ÷10
        self.set_state("sensor.solarspeicher_batterie_spannung",
                       state=v, attributes={"unit_of_measurement": "V"})
        self.set_state("sensor.solarspeicher_batterie_strom",
                       state=a, attributes={"unit_of_measurement": "A"})
        self.set_state("sensor.solarspeicher_batterie_leistung",
                       state=w, attributes={"unit_of_measurement": "W"})
```

### Option B: Node-RED Function Node

```javascript
const b64 = msg.payload;
const buf = Buffer.from(b64, 'base64');
msg.payload = {
    flag:          buf[0],
    dc1_voltage_v: buf.readUInt16BE(1) / 10,
    dc1_current_a: buf.readUInt16BE(3) / 100,
    dc1_power_w:   buf.readUInt16BE(5),
    dc2_voltage_v: buf.readUInt16BE(7) / 10,
    dc2_current_a: buf.readUInt16BE(9) / 10,
    dc2_power_w:   buf.readUInt16BE(11),
    total_power_w: buf.readUInt16BE(5) + buf.readUInt16BE(11),
    zeitfenster_aktiv: buf[0] === 3,
};
return msg;
```

---

## Nächste Schritte

### Sofort machbar
- [ ] **Local Key abrufen** (iot.tuya.com → API Explorer → Get Device Information)
- [ ] **Feste IP** für Solarspeicher im Router vergeben (DHCP-Reservation)
- [ ] **tuya-local Gerät hinzufügen** (IP + Device ID + Local Key)
- [ ] **Custom YAML** anlegen und testen
- [ ] Basis-Sensoren (%, Temp, kWh-Werte) verifizieren

### Base64 Dekodierung implementieren
- [ ] Methode wählen: AppDaemon / Node-RED
- [ ] `battery_parameters` → Batterie V, A, W
- [ ] `pv_canshu` → PV1 + PV2 Leistung
- [ ] `dc_message` → AUS1 + AUS2 Leistung + Flag
- [ ] `放电模式` → Zeitfenster lesen und schreiben

### Ungeklärtes verifizieren
- [x] **DP 37** – via lokalem DP-Dump als **Solarerzeugung gesamt** identifiziert (1369 = 13.69 kWh) ✓
- [x] **DP 113** – mbeb-Hypothese „WR-Ausgangsleistung" widerlegt (0 trotz aktiver Entladung); bleibt unklar
- [ ] **DP 111** – mbeb-Hypothese „WR aktiv/inaktiv" gegen beobachtetes Refresh-Verhalten abgrenzen
- [ ] **Base64-DP-IDs** über persistente Verbindung mitschneiden (push-only; `detect_available_dps()` findet sie nicht)
- [ ] `dc_message` byte[2] bei Charge-Status klären

### Optional / Erweitert
- [ ] Energy Dashboard einrichten (Solar, Batterie, Netz)
- [ ] Automatisierung: Lademodus nach Tageszeit / PV-Prognose steuern
- [ ] WR-Leistung dynamisch anpassen (Überschusssteuerung)
- [ ] tuya-local YAML als PR einreichen → [make-all/tuya-local](https://github.com/make-all/tuya-local)

---

## Referenzen
- tuya-local: https://github.com/make-all/tuya-local
- Tuya IoT Platform: https://iot.tuya.com

---

## Lizenz

[MIT](LICENSE) — frei nutzbar inkl. Übernahme der YAML-Definition in [tuya-local](https://github.com/make-all/tuya-local) oder andere Projekte.
