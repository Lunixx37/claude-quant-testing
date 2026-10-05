from candidates import FINAL
V2C = {
 'C1 V only, trail':               dict(FINAL),
 'C2 V+mental>=100, trail':        dict(FINAL, mental_on=True, mental_min=100),
 'C3 V+mental>=100, TP2+trail':    dict(FINAL, mental_on=True, mental_min=100, tp_r=2.0),
 'C4 V+mental(<500 needs VWAP), TP2+trail': dict(FINAL, mental_on=True, mental_need_vwap=500, tp_r=2.0),
 'C5 V only, TP2+trail':           dict(FINAL, tp_r=2.0),
}
