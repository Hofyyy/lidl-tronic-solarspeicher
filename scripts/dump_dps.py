#!/usr/bin/env python3
"""Dump aller DataPoints des Lidl TRONIC Solarspeichers via lokalem tinytuya-Zugriff.

Gibt die numerischen DP-IDs + aktuelle Werte aus, spuert via
detect_available_dps() zusaetzliche DPs auf (die Base64-DPs fehlen im
Standard-Status) und dekodiert die bekannten Base64-DPs (automatische
Klassifizierung nach Byte-Länge).

Voraussetzungen:
    pip3 install tinytuya

Aufruf (Local Key NICHT im Repo hinterlegen -> per Umgebungsvariable):
    export SPEICHER_DEVICE_ID="bf..."
    export SPEICHER_LOCAL_KEY="...."
    python3 scripts/dump_dps.py

Optional:
    SPEICHER_IP        (sonst beim Lauf abfragen)
    SPEICHER_VERSION   (Default: 3.3 -- bei Fehler 3.4 probieren)
"""
import base64
import json
import os
import struct
import sys
import time

import tinytuya

DEVICE_IP = os.environ.get("SPEICHER_IP", "")  # keine IP im Repo -> beim Lauf eingeben
DEVICE_ID = os.environ.get("SPEICHER_DEVICE_ID", "")
LOCAL_KEY = os.environ.get("SPEICHER_LOCAL_KEY", "")
VERSION = float(os.environ.get("SPEICHER_VERSION", "3.3"))


def _d(s: str) -> bytes:
    s = s.rstrip("=")
    return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4))


def decode_battery_parameters(raw: bytes) -> dict:
    return {
        "voltage_v": struct.unpack(">H", raw[0:2])[0] / 10,
        "current_a": struct.unpack(">H", raw[2:4])[0] / 10,
        "power_w":   struct.unpack(">H", raw[4:6])[0],   # x1, nicht /10
    }


def decode_pv_parameters(raw: bytes) -> dict:
    return {
        "flag":          raw[0],
        "pv1_voltage_v": struct.unpack(">H", raw[1:3])[0] / 10,
        "pv1_current_a": struct.unpack(">H", raw[3:5])[0] / 10,
        "pv1_power_w":   struct.unpack(">H", raw[5:7])[0],
        "pv2_voltage_v": struct.unpack(">H", raw[7:9])[0] / 10,
        "pv2_current_a": struct.unpack(">H", raw[9:11])[0] / 100,
        "pv2_power_w":   struct.unpack(">H", raw[11:13])[0],
    }


def decode_dc_message(raw: bytes) -> dict:
    return {
        "flag":          raw[0],
        "dc1_voltage_v": struct.unpack(">H", raw[1:3])[0] / 10,
        "dc1_current_a": struct.unpack(">H", raw[3:5])[0] / 100,
        "dc1_power_w":   struct.unpack(">H", raw[5:7])[0],
        "dc2_voltage_v": struct.unpack(">H", raw[7:9])[0] / 10,
        "dc2_current_a": struct.unpack(">H", raw[9:11])[0] / 10,
        "dc2_power_w":   struct.unpack(">H", raw[11:13])[0],
        "total_power_w": struct.unpack(">H", raw[5:7])[0]
        + struct.unpack(">H", raw[11:13])[0],
    }


def decode_discharge_schedule(raw: bytes) -> list:
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


def try_decode_b64(value: str):
    """Dekodiert einen String als Base64 und klassifiziert nach Byte-Länge."""
    try:
        raw = _d(value)
    except Exception:
        return None
    if len(raw) < 6:
        return None
    info = {"len": len(raw), "bytes": list(raw)}
    if len(raw) == 6:
        info["battery_parameters?"] = decode_battery_parameters(raw)
    elif len(raw) == 13:
        # 13 Bytes -> dc_message ODER pv_canshu; beide zeigen, Werte entscheiden
        info["dc_message?"] = decode_dc_message(raw)
        info["pv_canshu?"] = decode_pv_parameters(raw)
    elif len(raw) == 36:
        info["discharge_schedule?"] = decode_discharge_schedule(raw)
    return info


def listen(d, minutes: float):
    """Persistente Verbindung: lauscht auf asynchrone Push-Updates (Base64-DPs).

    Die Base64-DPs antworten lokal nicht auf Abfragen, werden aber asynchron
    gepusht (~alle 10 min). Hier sehen wir ihre numerischen IDs.
    """
    print(f"\n=== Listen-Modus: {minutes:g} Min auf Push-Updates lauschen (Strg+C beendet) ===")
    d.set_socketPersistent(True)
    seen = {}
    deadline = time.time() + minutes * 60
    try:
        while time.time() < deadline:
            data = d.receive()
            if isinstance(data, dict) and "dps" in data:
                for k, v in data["dps"].items():
                    first = k not in seen
                    seen[k] = v
                    print(f"  DP {k:>4}: {v!r}{' <- NEU' if first else ''}")
                    if isinstance(v, str) and len(v) >= 8:
                        decoded = try_decode_b64(v)
                        if decoded and len(decoded) > 2:
                            pretty = {kk: vv for kk, vv in decoded.items() if kk != "bytes"}
                            print(f"        ({decoded['len']} Bytes) "
                                  + json.dumps(pretty, ensure_ascii=False))
            d.heartbeat()
    except KeyboardInterrupt:
        print("\n  Abgebrochen.")
    ids = sorted(seen, key=lambda k: int(k) if str(k).isdigit() else 1e9)
    print(f"\n  Im Listen-Modus gesehene DP-IDs: {ids}")


def _ask(label: str, default: str = "") -> str:
    """Fragt einen Wert interaktiv ab; Enter uebernimmt den Default."""
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"{label}{hint}: ").strip()
    except EOFError:
        val = ""
    return val or default


def main():
    # Werte aus Umgebungsvariablen verwenden, fehlende bei Ausfuehrung abfragen.
    device_id = DEVICE_ID or _ask("Device ID")
    local_key = LOCAL_KEY or _ask("Local Key")
    ip = _ask("Geraete-IP", DEVICE_IP)
    version = float(_ask("Protokoll-Version", str(VERSION)))

    if not device_id or not local_key or not ip:
        sys.exit("Abbruch: Device ID, Local Key und Geraete-IP sind erforderlich.")

    d = tinytuya.Device(device_id, ip, local_key)
    d.set_version(version)
    status = d.status()

    if not isinstance(status, dict) or "dps" not in status:
        print("Keine gueltige Antwort erhalten:", status)
        if version == 3.3:
            print("Tipp: bei der Versions-Abfrage 3.4 eingeben und erneut versuchen.")
        return

    dps = dict(status["dps"])

    # Base64-DPs fehlen oft im Standard-Status -> alle DP-IDs aktiv aufspueren.
    print("\nSuche zusaetzliche DPs via detect_available_dps() ... (kann ein paar Sekunden dauern)")
    try:
        detected = d.detect_available_dps() or {}
    except Exception as exc:  # noqa: BLE001
        detected = {}
        print(f"  detect_available_dps() fehlgeschlagen: {exc}")
    extra = {k: v for k, v in detected.items() if k not in dps}
    dps.update(extra)

    print(f"\n=== Alle DPs ({ip}, v{version}) ===")
    for dp_id in sorted(dps, key=lambda k: int(k) if str(k).isdigit() else 1e9):
        tag = "   <- neu via detect" if dp_id in extra else ""
        print(f"  DP {dp_id:>4}: {dps[dp_id]!r}{tag}")

    print("\n=== Dekodierte Base64-DPs ===")
    found_b64 = False
    for dp_id, value in dps.items():
        if isinstance(value, str) and len(value) >= 8:
            decoded = try_decode_b64(value)
            if decoded and len(decoded) > 2:  # mehr als nur len + bytes
                found_b64 = True
                print(f"\n  DP {dp_id} ({decoded['len']} Bytes)  raw={value}")
                pretty = {k: v for k, v in decoded.items() if k not in ("bytes",)}
                print(json.dumps(pretty, indent=4, ensure_ascii=False))
    if not found_b64:
        print("  (keine Base64-DPs gefunden -- evtl. push-only, siehe Listen-Modus)")

    minutes = float(_ask("\nListen-Modus starten? Minuten (0 = ueberspringen)", "10"))
    if minutes > 0:
        listen(d, minutes)


if __name__ == "__main__":
    main()
