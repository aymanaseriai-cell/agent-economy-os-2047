"""Generate reproducible *mean closed equity* per relative 12h bar, no cherry picking."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

START=4.15
MODELS=("classical_momentum","quantum_walk_interference",
        "hyperquantum_commutator","beyondquantum_bayes")
COLORS=("#2563eb","#dc6b12","#16803c","#7c3aed")


def curves(report, case):
    result={}
    for model in MODELS:
        windows=[w for w in report["windows"] if w["cost"]==case and w["model"]==model]
        if not windows:
            raise ValueError("Missing fixed comparison windows")
        paths=[]
        for w in windows:
            values=[START]*49
            changes={int(t["exit_idx"]-w["start_idx"])+1:t["equity_after"] for t in w["trades"]}
            equity=START
            for i in range(1,49):
                if i in changes:
                    equity=changes[i]
                values[i]=equity
            paths.append(values)
        result[model]=[sum(row[i] for row in paths)/len(paths) for i in range(49)]
    return result


def svg(case, data):
    width,height=980,545
    left,right,top,bottom=70,30,65,95
    flat=[v for vals in data.values() for v in vals]
    lo=min(flat+[START]); hi=max(flat+[START])
    pad=max(.05,(hi-lo)*.08)
    lo=max(0,lo-pad);hi+=pad
    def xy(i,v):
        return left+(width-left-right)*i/48,top+(height-top-bottom)*(hi-v)/(hi-lo)
    s=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 545">',
       '<rect width="980" height="545" fill="white"/>',
       '<text x="70" y="34" font-family="sans-serif" font-size="20" font-weight="bold">TITAN Ω Infinite12 — '+case+' closed-equity mean</text>',
       '<text x="70" y="53" font-family="sans-serif" font-size="12">80 predeclared public historical development windows per model; no independent OOS proof</text>']
    for j in range(5):
        v=lo+(hi-lo)*j/4
        x,y=xy(0,v)
        s.append('<line x1="70" y1="'+str(round(y,2))+'" x2="950" y2="'+str(round(y,2))+'" stroke="#ddd"/>')
        s.append('<text x="8" y="'+str(round(y+3,2))+'" font-family="sans-serif" font-size="11">'+str(round(v,3))+' USDT</text>')
    base=xy(0,START)[1]
    s.append('<line x1="70" y1="'+str(round(base,2))+'" x2="950" y2="'+str(round(base,2))+'" stroke="#555" stroke-dasharray="6,5"/>')
    for j,(model,vals) in enumerate(data.items()):
        pts=" ".join(str(round(xy(i,v)[0],1))+","+str(round(xy(i,v)[1],1)) for i,v in enumerate(vals))
        s.append('<polyline points="'+pts+'" fill="none" stroke="'+COLORS[j]+'" stroke-width="2.4"/>')
        s.append('<line x1="'+str(70+225*(j%4))+'" y1="484" x2="'+str(100+225*(j%4))+'" y2="484" stroke="'+COLORS[j]+'" stroke-width="3"/>')
        s.append('<text x="'+str(105+225*(j%4))+'" y="488" font-family="sans-serif" font-size="11">'+model.replace("_"," ")+'</text>')
    s.append('<text x="455" y="448" font-family="sans-serif" font-size="12">Relative time inside window (0–12 hours)</text>')
    s.append('<text x="70" y="515" font-family="sans-serif" font-size="12">Generated from closed balances only; liquidity, funding and liquidation fills are modeled approximations.</text>')
    s.append('</svg>')
    return "\n".join(s)+"\n"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",required=True);p.add_argument("--out-dir",required=True)
    o=p.parse_args()
    report=json.loads(Path(o.report).read_text())
    root=Path(o.out_dir);root.mkdir(parents=True,exist_ok=True)
    all_curves={}
    for case in ("ordinary","stress"):
        data=curves(report,case)
        (root/("omega12_mean_equity_"+case+".svg")).write_text(svg(case,data))
        all_curves[case]=data
    (root/"omega12_mean_closed_equity_curves.json").write_text(json.dumps(all_curves,indent=2,sort_keys=True)+"\n")
    print("CURVES_CREATED: 2 SVG + 1 JSON from all 80 windows per model per cost")


if __name__=="__main__":
    main()
