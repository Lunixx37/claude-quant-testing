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

# V3 (high-frequency ICT/level search), frozen before Test A: best min(E_train, E_valid) of the 8 configs
# positive in both (see v3_grid_train.csv / v3_grid_valid.csv)
V3_FINAL = dict(setup='S10 Absorption', stop_mode='fixed', tp_r=3.0, trail=False)

# V4 candidate (did NOT pass the pre-registered neighbour rule, but is positive on all test years):
# FVG rejection (single confluence), fixed 40-pt stop, TP 3R, 09:30-11:00 NY, max 2/day, no VWAP / order flow
V4_CANDIDATE = dict(combo=('fvg',), stop_pts=40.0, tp_r=3.0, trail=False)

# V5 (refined FVG candidate), frozen before its test run: no filters (none improved Train AND Validation),
# fixed 60-pt stop, TP 2R, hold up to 2 sessions (plateau choice, all neighbours positive) - see v5_selection.txt
V5_FINAL = dict(filters=(), stop=('fixed', 60.0), tp_r=2.0, trail=False, hold=2)
