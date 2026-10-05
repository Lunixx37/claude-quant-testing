from engine import Params
BASE = dict(trigger='reclaim', struct_filter=True, struct_ref_ticks=100, trail_lag=1.25, allow_b=False, use_hp=False)
CANDIDATES = {
    'C1 base (9:30-11:00)': dict(BASE),
    'C2 window to 11:30':   dict(BASE, win_end=690),
    'C3 abs_break trigger': dict(BASE, trigger='abs_break'),
    'C4 with B-tier':       dict(BASE, allow_b=True),
    'C5 with HP 50t stop':  dict(BASE, use_hp=True),
}

# Frozen final version (selected on train+valid only; forward untouched)
FINAL = dict(BASE, er_max=1.0)

# V2 (mental levels instead of GEX), frozen before the single 2025 run - see PROTOCOL_V2.md
V2_FINAL = dict(FINAL, mental_on=True, mental_min=100, tp_r=2.0)
