# gen_dynamic_model_header.py
# ============================================================
# Generate dynamic_model.h from:
#   - dynamic_gestures.json
#   - labels_default.json
#
# Place this script in the SAME directory and just run:
#   python gen_dynamic_model_header.py
# ============================================================

import json
from pathlib import Path

# ---------------- Path Config ----------------

BASE_DIR   = Path(__file__).resolve().parent
DYN_JSON   = BASE_DIR / "dynamic_gestures.json"
LABEL_JSON = BASE_DIR / "labels_default.json"
OUT_H      = BASE_DIR / "dynamic_model.h"

DEFAULT_COOLDOWN_S = 1.0   # seconds
WINDOW_SCALE = 3           # ★ 只放大 time_window_ms

# ---------------- Utils ----------------

def load_json(p: Path):
    if not p.exists():
        raise FileNotFoundError(f"Missing file: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

def load_label_map(label_json):
    """
    labels_default.json:
    {
      "label_defs": [
        { "id": 0, "name": "idle" },
        { "id": 10, "name": "ok" }
      ]
    }
    """
    m = {}
    for it in label_json.get("label_defs", []):
        name = str(it.get("name", "")).strip()
        idx  = int(it.get("id"))
        if name:
            m[name] = idx
    return m

def token_to_id(tok, label_map):
    # int
    if isinstance(tok, int):
        return tok

    s = str(tok).strip()

    # numeric string
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return int(s)

    # label string
    if s in label_map:
        return label_map[s]

    raise ValueError(f"[ERROR] Unknown token '{tok}'")

def normalize_sequence(seq, name):
    """
    Accept:
      - [1,3,5,0]
      - ["ok","peace"]
      - "1,3,5,0"
      - "ok,peace"
    """
    if isinstance(seq, list):
        return seq

    if isinstance(seq, str):
        return [s.strip() for s in seq.split(",") if s.strip()]

    raise ValueError(f"[ERROR] Unsupported sequence type in {name}: {type(seq)}")

def normalize_dynamic_items(dyn_raw):
    """
    Supported formats:

    1) { "dynamic_gestures": [ {name, ...}, ... ] }
    2) [ {name, ...}, ... ]
    3) { "FL": {...}, "love": {...} }
    """
    items = []

    # case 1
    if isinstance(dyn_raw, dict) and "dynamic_gestures" in dyn_raw:
        lst = dyn_raw["dynamic_gestures"]
        if not isinstance(lst, list):
            raise ValueError("dynamic_gestures must be list")
        for it in lst:
            if not isinstance(it, dict):
                continue
            if "name" not in it:
                raise ValueError("dynamic_gestures item missing 'name'")
            items.append(it)
        return items

    # case 2
    if isinstance(dyn_raw, list):
        for it in dyn_raw:
            if not isinstance(it, dict):
                continue
            if "name" not in it:
                raise ValueError("dynamic_gestures list item missing 'name'")
            items.append(it)
        return items

    # case 3
    if isinstance(dyn_raw, dict):
        for k, v in dyn_raw.items():
            if not isinstance(v, dict):
                continue
            item = {"name": k}
            item.update(v)
            items.append(item)
        return items

    raise ValueError("Unsupported dynamic_gestures.json format")

# ---------------- Main ----------------

def main():
    dyn_raw    = load_json(DYN_JSON)
    label_raw  = load_json(LABEL_JSON)

    label_map = load_label_map(label_raw)
    dyn_items = normalize_dynamic_items(dyn_raw)

    if not dyn_items:
        raise RuntimeError("[FATAL] No dynamic gestures found")

    # sort: longer sequence first (PC behavior)
    dyn_items.sort(
        key=lambda x: len(normalize_sequence(x.get("sequence", []), x["name"])),
        reverse=True
    )

    flat_tokens = []
    gestures    = []
    max_tw_ms   = 0

    for cfg in dyn_items:
        name = cfg["name"]

        seq_raw = (
            cfg.get("sequence")
            or cfg.get("seq")
            or cfg.get("steps")
            or cfg.get("gestures")
        )

        if not seq_raw:
            print(f"[SKIP] {name}: no sequence")
            continue

        seq_list = normalize_sequence(seq_raw, name)
        ids = [token_to_id(t, label_map) for t in seq_list]

        max_gap = int(cfg.get("max_gap", 0))

        tw_s = float(cfg.get("time_window",
                 cfg.get("time_window_s", 0.0)))
        cd_s = float(cfg.get("cooldown",
                 cfg.get("cooldown_s", DEFAULT_COOLDOWN_S)))

        # ★★★ 只放大 time window ★★★
        tw_ms = int(round(tw_s * 1000.0 * WINDOW_SCALE))
        cd_ms = int(round(cd_s * 1000.0))

        max_tw_ms = max(max_tw_ms, tw_ms)

        off = len(flat_tokens)
        flat_tokens.extend(ids)

        gestures.append({
            "name": name,
            "seq_off": off,
            "seq_len": len(ids),
            "max_gap": max_gap,
            "time_window_ms": tw_ms,
            "cooldown_ms": cd_ms,
        })

    # ---------------- Emit Header ----------------

    out = []
    out.append("// AUTO-GENERATED FILE. DO NOT EDIT.\n")
    out.append("// Generated by gen_dynamic_model_header.py\n\n")
    out.append("#pragma once\n\n")
    out.append("#include <stdint.h>\n\n")
    out.append("#ifdef __cplusplus\nextern \"C\" {\n#endif\n\n")

    out.append(
        "typedef struct {\n"
        "    const char*  name;\n"
        "    uint16_t     seq_off;\n"
        "    uint16_t     seq_len;\n"
        "    uint16_t     max_gap;\n"
        "    uint32_t     time_window_ms;\n"
        "    uint32_t     cooldown_ms;\n"
        "} dyn_gesture_t;\n\n"
    )

    out.append("static const uint16_t g_dyn_seq_tokens[] = {\n")
    for i, v in enumerate(flat_tokens):
        out.append(f"    {v},")
        if (i + 1) % 16 == 0:
            out.append("\n")
    if flat_tokens and len(flat_tokens) % 16 != 0:
        out.append("\n")
    out.append("};\n\n")

    out.append(f"static const uint32_t g_dyn_seq_tokens_count = {len(flat_tokens)}u;\n\n")

    out.append("static const dyn_gesture_t g_dyn_gestures[] = {\n")
    for g in gestures:
        out.append(
            f"    {{ \"{g['name']}\", {g['seq_off']}, {g['seq_len']}, "
            f"{g['max_gap']}, {g['time_window_ms']}u, {g['cooldown_ms']}u }},\n"
        )
    out.append("};\n\n")

    out.append(f"static const uint16_t g_dyn_gestures_count = {len(gestures)}u;\n")
    out.append(f"static const uint32_t g_dyn_global_max_time_window_ms = {max_tw_ms}u;\n\n")

    out.append("#ifdef __cplusplus\n}\n#endif\n")

    OUT_H.write_text("".join(out), encoding="utf-8")

    print("[OK] dynamic_model.h generated")
    print(f"     gestures = {len(gestures)}")
    print(f"     tokens   = {len(flat_tokens)}")
    print(f"     max TW   = {max_tw_ms} ms")
    print(f"     output   = {OUT_H}")

# ---------------- Entry ----------------

if __name__ == "__main__":
    main()
