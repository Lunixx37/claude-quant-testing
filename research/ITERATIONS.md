# Iteration log (Training 2023-02..2024-06, Validation 2024-07..2024-12; net of costs)

| # | Hypothesis / change | Data used | Result | Decision |
|---|---|---|---|---|
| 1 | Baseline: VWAP/band/mult levels, sweep, absorption (relvol + wick/close location), A = sweep + displacement, B = touch or no displacement, trigger = close beyond absorption bar, stop 100/50, trail lag 1.0 | Train | n=331, PF 0.83, E -0.09R. B-tier PF 0.49, A-tier PF 1.15 | fails |
| 1a | Engine audit: trade limit, window, next-open fills, no overnight, truncation (no-lookahead) test | Train | all PASS | - |
| 2 | Diagnosis: entry sits a median 103 ticks from the sweep extreme, so the 100-tick stop lands inside the liquidity pool. H2a reclaim trigger, H2b structure rule (stop beyond manipulation extreme), H2c trail lag 1.0/1.25/1.5 | Train | A-only + structure rule is positive in all 6 trigger x lag combinations (PF 1.20-1.45). B-tier always dilutes | adopt structure rule, A-only default |
| 2a | Sensitivity: stop 80/120 negative, 100 positive (cliff). Root cause: the stop size also changed the structure filter. With the structure reference fixed at 100t, every stop from 60 to 150t is positive and peaks at 90-110 | Train | no cliff | struct_ref fixed at 100t |
| 2b | Pre-declared candidates C1-C5 on validation | Train+Valid | C1 valid PF 1.09 (n=29); window to 11:30 fails valid (PF 0.80); HP 50t never better | C1 kept; window 9:30-11:00 |
| 2c | Edge decay / direction-flip / random control | Train+Valid | 2023 strong, 2024 ~flat; flipped direction +0.04R, random -0.01R, signal +0.19R, t=1.45 | evidence weak, continue |
| 3a | Absorption effort-vs-result: relrange/relvol <= 1.0 | Train | PF 1.43 -> 1.47, DD 9.6 -> 6.9R, plateau 0.8-1.5 | adopt (1.0) |
| 3b | Liquidity levels ONH/ONL/PDH/PDL | Train | worse in 2024H1 | rejected |
| 3c | Regime analysis: counter-trend trades positive in all 4 half-years | Train+Valid | post-hoc, halves the trade count | NOT adopted (mining risk), noted |
| 4 | Final candidate C1 + er_max 1.0 on validation | Valid | n=27, PF 1.24, E +0.13R | frozen as FINAL |
| 4a | Full robustness grid (93 variants) | Train, IS | all variants PF > 1; +-1 step PF > 1.05; 2-tick slippage E +0.15R | IS criteria met |
| 5 | **One-time forward run** (2025-01-01..2025-12-11) with the frozen FINAL | Forward | n=35, PF 1.70, E +0.36R, DD 6.1R; 2/3-tick slippage PF 1.50/1.21 | profitable, but n < 60 (pre-registered) -> not statistically confirmed. No changes made after the forward run |
