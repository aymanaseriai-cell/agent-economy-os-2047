#!/usr/bin/env python3
"""NEXUS-7 2047: seven REAL open-source research libraries combined in one experiment.

Research-only. Uses real public OKX depth geometry plus explicitly SYNTHETIC
causal/outcome labels. It DOES NOT model historical TITAN trade profitability,
run NVIDIA, access trading credentials, authorize trades, or enable the bot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request,urlopen
from datetime import datetime,timezone

REPOSITORIES={
 "z3":"https://github.com/Z3Prover/z3",
 "gudhi":"https://github.com/GUDHI/gudhi-devel",
 "openspiel":"https://github.com/google-deepmind/open_spiel",
 "cleanlab":"https://github.com/cleanlab/cleanlab",
 "dowhy":"https://github.com/py-why/dowhy",
 "causal_learn":"https://github.com/py-why/causal-learn",
 "art":"https://github.com/Trusted-AI/adversarial-robustness-toolbox",
}
# No paths under /api/v5/trade or /api/v5/account are ever used.
OKX_PUBLIC_BOOK="https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz=20"
SAMPLE_COUNT=300
RNG_SEED=2037

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                      allow_nan=False).encode("utf-8")

def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def fetch_public_book():
    with urlopen(Request(OKX_PUBLIC_BOOK,headers={
        "Accept":"application/json","User-Agent":"Nexus7-Research-NoTrades/1.0"}),timeout=18) as r:
        obj=json.load(r)
    if obj.get("code")!="0" or len(obj.get("data",[]))!=1:
        raise RuntimeError("OKX public book unavailable")
    return {"source":"OKX_PUBLIC_BOOK_ONLY",
            "captured_utc":datetime.now(timezone.utc).isoformat(),
            "symbol":"BTC-USDT-SWAP","book":obj["data"][0]}

def validate_public_book(capture):
    if capture.get("source")!="OKX_PUBLIC_BOOK_ONLY":
        raise ValueError("Market source is not approved public OKX orderbook")
    book=capture["book"]
    for side in ("bids","asks"):
        levels=book.get(side,[])
        if len(levels)<10:
            raise ValueError("Insufficient book depth")
        for row in levels[:20]:
            price,volume=float(row[0]),float(row[1])
            if not (math.isfinite(price) and math.isfinite(volume) and
                    price>0 and volume>=0):
                raise ValueError("Invalid L2 book level")
    if float(book["bids"][0][0])>=float(book["asks"][0][0]):
        raise ValueError("Crossed or nonstandard public book")
    return True

def simulate_confounded_decisions(seed=RNG_SEED,n=SAMPLE_COUNT):
    """Controlled fabricated labels: never infer TITAN trading performance from them."""
    import numpy as np
    if n<100:raise ValueError("Need at least 100 synthetic observations")
    rng=np.random.default_rng(seed)
    regime=rng.normal(size=n)
    tape=.6*regime+rng.normal(size=n)
    treatment=(tape+.6*regime+rng.normal(scale=.6,size=n)>0).astype(int)
    outcome=.65*treatment+.4*regime+rng.normal(scale=.25,size=n)
    observed_label=(outcome>0.3).astype(int)
    corrupt=observed_label.copy()
    positions=np.array([2,12,33,71,89,121,177,221],dtype=int)
    positions=positions[positions<n]
    corrupt[positions]=1-corrupt[positions]
    return {"regime":regime,"tape":tape,"treatment":treatment,
            "outcome":outcome,"true_label":observed_label,
            "noisy_label":corrupt,"injected_label_errors":positions.tolist(),
            "synthetic":True}

def lab_cleanlab(data):
    """Label QA on held-out synthetic predictions; no returns claimed."""
    import numpy as np
    from cleanlab.filter import find_label_issues
    from sklearn.model_selection import cross_val_predict, StratifiedKFold
    from sklearn.linear_model import LogisticRegression
    x=np.stack([data["regime"],data["tape"]],axis=1)
    labels=data["noisy_label"]
    clf=LogisticRegression(max_iter=300,random_state=23)
    pred=cross_val_predict(clf,x,labels,cv=StratifiedKFold(
        n_splits=5,shuffle=True,random_state=13),method="predict_proba")
    suspects=find_label_issues(labels=labels,pred_probs=pred,
                               return_indices_ranked_by="self_confidence")
    injected=set(data["injected_label_errors"])
    return {"status":"executed","source":"SYNTHETIC_WITH_INJECTED_LABEL_ERRORS",
            "suspect_count":int(len(suspects)),
            "detected_injected_count":int(sum(int(i) in injected for i in suspects)),
            "first_suspects":[int(i) for i in suspects[:12]],
            "observations":int(len(labels))}

def lab_causal_graph(data):
    """PC gives observed conditional independence candidate graph, NOT market causality."""
    import numpy as np
    from causallearn.search.ConstraintBased.PC import pc
    x=np.column_stack([data["regime"],data["treatment"],data["outcome"]])
    graph=pc(x,alpha=.05,indep_test="fisherz",show_progress=False)
    adjacency=graph.G.graph
    return {"status":"executed","source":"CONTROLLED_SYNTHETIC_STRUCTURAL_DATA",
            "variables":["regime","candidate_trade","future_outcome"],
            "nonzero_adjacency_entries":int(np.count_nonzero(adjacency)),
            "not_proof_of_observed_market_causality":True}

def lab_dowhy(data):
    """Backdoor-adjusted effect, on known synthetic confounder only."""
    import pandas as pd
    from dowhy import CausalModel
    df=pd.DataFrame({"candidate_trade":data["treatment"],
                     "future_outcome":data["outcome"],
                     "known_regime":data["regime"]})
    model=CausalModel(data=df,treatment="candidate_trade",
                      outcome="future_outcome",common_causes=["known_regime"])
    estimand=model.identify_effect(proceed_when_unidentifiable=False)
    result=model.estimate_effect(estimand,method_name="backdoor.linear_regression")
    return {"status":"executed","source":"SYNTHETIC_KNOWN_GENERATING_PROCESS",
            "estimated_adjusted_effect":round(float(result.value),5),
            "true_synthetic_effect":.65,
            "not_estimated_from_real_trade_outcomes":True}

def lab_art(data):
    """Attack a synthetic sklearn surrogate, NOT NVIDIA nor the deterministic council."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from art.estimators.classification import SklearnClassifier
    from art.attacks.evasion import FastGradientMethod
    x=np.column_stack([data["regime"],data["tape"]]).astype("float32")
    labels=data["noisy_label"]
    train_x,probe_x=x[:250],x[250:]
    train_y=labels[:250]
    clf=LogisticRegression(max_iter=300,random_state=13).fit(train_x,train_y)
    art_clf=SklearnClassifier(model=clf)
    attacker=FastGradientMethod(estimator=art_clf,eps=.2)
    adv=attacker.generate(x=probe_x)
    before=clf.predict(probe_x)
    after=clf.predict(adv)
    return {"status":"executed","source":"SYNTHETIC_CLASSIFICATION_SURROGATE",
            "attacked_points":int(len(probe_x)),
            "predictions_flipped":int(np.count_nonzero(before!=after)),
            "flip_rate":round(float(np.mean(before!=after)),5),
            "max_feature_perturbation":round(float(np.max(np.abs(adv-probe_x))),5),
            "not_attack_on_actual_NVIDIA_or_core_trading_bot":True}

def lab_gudhi(capture):
    """Topology of ONE REAL public L2 snapshot, not a proven alpha signal."""
    import numpy as np
    import gudhi
    validate_public_book(capture)
    book=capture["book"]
    bid,ask=(float(book["bids"][0][0]),float(book["asks"][0][0]))
    mid=(bid+ask)/2
    points=[]
    for side in ("bids","asks"):
        for level in book[side][:20]:
            price,qty=map(float,level[:2])
            points.append([(price/mid-1)*1e4/100,
                           math.log1p(qty)])
    pts=np.asarray(points)
    scale=np.maximum(pts.std(axis=0),1e-6)
    pts=(pts-pts.mean(axis=0))/scale
    st=gudhi.RipsComplex(points=pts,max_edge_length=2.0).create_simplex_tree(max_dimension=2)
    bars=st.persistence()
    finite_h1=[d-b for dim,(b,d) in bars if dim==1 and math.isfinite(d)]
    return {"status":"executed","source":"REAL_OKX_PUBLIC_BOOK_SNAPSHOT",
            "symbol":capture["symbol"],"depth_points":len(points),
            "finite_one_dimensional_cycles":len(finite_h1),
            "max_cycle_lifetime":round(max(finite_h1,default=0),6),
            "not_predictive_without_historical_validation":True}

def lab_open_spiel(dowhy_report,art_report):
    """Use REAL OpenSpiel game engine; all payoffs come from SYNTHETIC model."""
    import pyspiel
    e=float(dowhy_report["estimated_adjusted_effect"])
    f=float(art_report["flip_rate"])
    row_payoffs=[[e, e-2*max(.20,f)],[0.,0.]]
    game=pyspiel.create_matrix_game("nexus2047","synthetic adversarial decision game",
          ["ENTER","WAIT"],["NORMAL","DATA_ATTACK"],row_payoffs,
          [[-v for v in row] for row in row_payoffs])
    utilities=[]
    for row in range(2):
        cases=[]
        for col in range(2):
            state=game.new_initial_state()
            state.apply_actions([row,col])
            cases.append(float(state.returns()[0]))
        utilities.append(cases)
    worst=[min(row) for row in utilities]
    return {"status":"executed","source":"SYNTHETIC_PAYOFF_ASSUMPTIONS_NOT_MARKET",
            "defender_actions":["ENTER","WAIT"],
            "adversary_actions":["NORMAL","DATA_ATTACK"],
            "payoff_matrix":utilities,
            "maximin_research_action":["ENTER","WAIT"][max(range(2),key=lambda i:worst[i])],
            "not_authorized_trade":True}

def lab_z3():
    """Proof only of an ABSTRACT policy, NOT the existing Python order executor."""
    from z3 import Bool, Solver, And, Not, unsat
    enable=Bool("real_trading_enabled")
    user_arm=Bool("user_explicit_arm")
    nvidia=Bool("nvidia_approved")
    fresh=Bool("all_feeds_fresh")
    risk=Bool("risk_policy_pass")
    send=Bool("may_submit_order")
    s=Solver()
    s.add(send==And(enable,user_arm,nvidia,fresh,risk))
    s.add(Not(enable),send)
    stop_proof=s.check()==unsat
    s2=Solver()
    s2.add(send==And(enable,user_arm,nvidia,fresh,risk))
    s2.add(Not(nvidia),send)
    veto_proof=s2.check()==unsat
    if not(stop_proof and veto_proof):
        raise AssertionError("Abstract research safety policy invalid")
    return {"status":"executed","source":"ABSTRACT_FORMAL_SPEC_NOT_EXISTING_CODE",
            "disabled_cannot_authorize":bool(stop_proof),
            "missing_nvidia_cannot_authorize":bool(veto_proof),
            "does_not_formally_verify_existing_live_executor":True}

def run(capture,seed=RNG_SEED):
    validate_public_book(capture)
    data=simulate_confounded_decisions(seed)
    reports={}
    reports["cleanlab"]=lab_cleanlab(data)
    reports["causal_learn"]=lab_causal_graph(data)
    reports["dowhy"]=lab_dowhy(data)
    reports["art"]=lab_art(data)
    reports["gudhi"]=lab_gudhi(capture)
    reports["openspiel"]=lab_open_spiel(reports["dowhy"],reports["art"])
    reports["z3"]=lab_z3()
    if set(reports)!=set(REPOSITORIES) or any(z["status"]!="executed" for z in reports.values()):
        raise ValueError("Not all seven distinct GitHub projects actually executed")
    return {"experiment":"NEXUS_7_2047",
            "mode":"RESEARCH_ONLY_ZERO_TRADING_AUTHORITY",
            "seven_imported_and_exercised":True,
            "trading_enabled":False,"orders_placed":0,
            "public_book_sha256":digest(capture),
            "public_book_timestamp_utc":capture["captured_utc"],
            "synthetic_data":{"rows":SAMPLE_COUNT,"seed":seed,
                              "known_treatment_effect":.65,
                              "real_future_outcomes":0},
            "real_market_data_used_only_for":["gudhi"],
            "projects":REPOSITORIES,
            "modules":reports,
            "hard_limitations":[
               "Seven project calls compose one controlled research demonstration.",
               "Synthetic treatment labels and model predictions are NOT real trading alpha.",
               "OpenSpiel payoffs are hypothetical; no profit expectations inferred.",
               "DoWhy and PC cannot establish causality from limited market snapshots.",
               "Z3 proves only an abstract policy, not the production order executor.",
               "GUDHI sees one public L2 snapshot, not time-series stability.",
               "No NVIDIA calls, private endpoints, orders, portfolio or future PnL.",
               "Novel integration is not evidence of being first in the world."
            ]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--public-book",help="Frozen public OKX book capture JSON")
    p.add_argument("--out",default="reports/nexus7_research.json")
    p.add_argument("--seed",type=int,default=RNG_SEED)
    args=p.parse_args()
    book=json.loads(Path(args.public_book).read_text()) if args.public_book else fetch_public_book()
    output=run(book,args.seed)
    f=Path(args.out);f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(json.dumps(output,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print("NEXUS-7 RESEARCH",json.dumps({
        "all_seven_executed":output["seven_imported_and_exercised"],
        "trading_enabled":output["trading_enabled"],
        "real_book_sha":output["public_book_sha256"],
        "synthetic_causal_effect":output["modules"]["dowhy"]["estimated_adjusted_effect"],
        "synthetic_art_flip_rate":output["modules"]["art"]["flip_rate"],
        "real_book_topology_points":output["modules"]["gudhi"]["depth_points"],
        "abstract_policy_unsat":output["modules"]["z3"]["disabled_cannot_authorize"]
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
