#!/usr/bin/env python3
"""OMEGA 25M: 20 explicit hypothesis families + classical control.

17 executable OHLCV approximations, 3 fail-closed requiring unavailable data.
All machine learning / search / priors fit only on an explicitly supplied
development data set. Four-qubit complex wavefunction is CPU simulated.
NO LIVE ORDERS.
"""
import cmath, math, random

MODELS = (
 "quantum_inspired", "path_integral", "nonlinear_chaos",
 "hierarchical_bayes", "information_geometry", "hawkes_trade_flow",
 "hidden_markov", "risk_constrained_rl", "causal_invariance",
 "multihorizon_representation", "orderbook_imbalance",
 "genetic_programming", "volatility_surface", "meta_learning",
 "multiagent_decision", "multiscale_wavelet", "uncertainty_ensemble",
 "structural_breakout", "dynamic_portfolio", "hybrid_controller",
 "classical_trend",
)
UNAVAILABLE = {
 "hawkes_trade_flow":"individual trade event timestamps are not available",
 "orderbook_imbalance":"historical synchronized L2 bid/ask depths unavailable",
 "volatility_surface":"historical option strikes and implied volatilities unavailable",
}
ACTIVE = tuple(m for m in MODELS if m not in UNAVAILABLE)
SEED = 25_000_000_2047

def logistic(x):
    return 1/(1+math.exp(-max(-20,min(20,x))))

def _rot(y,b,a):
    mask=1<<b;co=math.cos(a/2);si=math.sin(a/2);out=y[:]
    for i in range(16):
        if i&mask:continue
        v,w=y[i],y[i|mask]
        out[i]=co*v-si*w;out[i|mask]=si*v+co*w
    return out

def _had(y,b):
    mask=1<<b;out=y[:];root=math.sqrt(.5)
    for i in range(16):
        if i&mask:continue
        v,w=y[i],y[i|mask]
        out[i]=(v+w)*root;out[i|mask]=(v-w)*root
    return out

def quantum_probability(features,phase=1.):
    if len(features)!=10 or any(not math.isfinite(float(x)) for x in features):
        raise ValueError("Ten finite observed feature inputs required")
    x=tuple(math.tanh(z) for z in
           (features[0],features[2],features[4],
            .5*features[5]+.5*features[7]))
    y=[0j]*16;y[0]=1+0j
    for b in range(4):y=_rot(y,b,1.5*x[b])
    for i in range(16):
        z=[1 if i&(1<<b) else -1 for b in range(4)]
        zz=.31*z[0]*z[1]-.42*z[1]*z[2]+.29*z[2]*z[3]+.23*z[3]*z[0]
        y[i]*=cmath.exp(1j*phase*(zz+.1*sum(z[b]*x[b] for b in range(4))))
    for b in range(4):y=_had(y,b)
    for b in (0,2):y=_had(y,b)
    norm=sum(abs(a)**2 for a in y)
    if abs(norm-1)>1e-9:raise ArithmeticError("Quantum-like circuit nonunitary")
    return min(1.,max(0.,sum(abs(y[i])**2 for i in range(16) if i&8)))

def fit(train):
    """List (10 causal features, next 4h return, symbol, 4h clock)."""
    if len(train)<200:raise ValueError("Insufficient true historical train labels")
    n=10;weights=[0.]*(n+1)
    for epoch in range(3):
        for f,y,_,_ in train:
            p=logistic(sum(weights[i]*f[i] for i in range(n))+weights[-1])
            err=(1 if y>0 else 0)-p
            for k in range(n):
                weights[k]+=.008*(err*f[k]-.01*weights[k])
            weights[-1]+=.008*err
    rng=random.Random(SEED)
    genomes=[[rng.uniform(-1,1) for _ in range(n)] for _ in range(16)]
    sample=train[::max(1,len(train)//240)]
    def fitness(g):
        return sum((1 if sum(a*b for a,b in zip(g,f))>=0 else -1)*y-.002
                   for f,y,_,_ in sample)
    for epoch in range(4):
        genomes.sort(key=fitness,reverse=True);best=genomes[:4]
        genomes=[row[:] for row in best]
        while len(genomes)<16:
            row=best[rng.randrange(len(best))]
            genomes.append([max(-2,min(2,v+rng.gauss(0,.21))) for v in row])
    gene=max(genomes,key=fitness)
    glob=sum(y for _,y,_,_ in train)/len(train)
    asset={}
    state={}
    for f,y,s,_ in train:
        if s not in asset:asset[s]=[0.,0]
        asset[s][0]+=y;asset[s][1]+=1
        key=(f[2]>0,f[4]>0)
        if key not in state:state[key]=[0.,0]
        state[key][0]+=y;state[key][1]+=1
    asset={s:(a+50*glob)/(n+50) for s,(a,n) in asset.items()}
    thirds=(train[:len(train)//3],train[len(train)//3:2*len(train)//3],
            train[2*len(train)//3:])
    corr=[sum(f[0]*y for f,y,_,_ in t)/max(1,len(t)) for t in thirds]
    causal=1 if all(v>0 for v in corr) else -1 if all(v<0 for v in corr) else 0
    return {"weights":weights,"gene":gene,"asset":asset,"global":glob,
            "state":{str(k):v for k,v in state.items()},"causal":causal,
            "n_train":len(train)}

def score(f,s,p):
    """F = momentum short/long, EMA trend, ATR compression, REAL quote vol
    ratio, candle pressure, range break, cross-asset breadth, up fraction,
    EMA distance. Returns bounded signed preference or abstention zero.
    Names describe testable approximations, not exact Hawkes/HMM/GP.
    """
    if len(f)!=10:raise ValueError("Wrong causal features")
    a,b,t,v,q,pressure,br,breadth,up,dist=f
    w=p["weights"];g=p["gene"]
    ml=2*logistic(sum(wi*fi for wi,fi in zip(w,f))+w[-1])-1
    gene=math.tanh(sum(gi*fi for gi,fi in zip(g,f))/5)
    prior=p["asset"].get(s,p["global"])
    state=p["state"].get(str((t>0,q>0)),[0.,0])
    bandit=state[0]/state[1] if state[1] else 0
    quantum=2*quantum_probability(f,1.)-1
    pathnum=sum(x*math.exp(-abs(x-y)) for x in (a,b,t) for y in (a,b,t))
    pathden=sum(math.exp(-abs(x-y)) for x in (a,b,t) for y in (a,b,t))
    path=math.tanh(pathnum/pathden)
    chaos=math.tanh(1.7*a-.32*a**3-.3*v)
    bayes=2*logistic(a+.4*t+5*prior)-1
    info=math.tanh((up-breadth)/(1.01-up*up)+.25*q)
    hmm=math.tanh(t*(1-.3*abs(v))+.4*up)
    rl=math.tanh(15*bandit+.3*t) if abs(v)<1.1 else 0.
    causal=math.tanh(p["causal"]*a) if p["causal"] else 0.
    represent=math.tanh(.4*a+.6*b+.35*t)
    meta=math.tanh(10*prior+.3*a)
    agents=math.tanh(.4*bayes+.35*hmm+.25*ml)
    wave=math.tanh(.6*(a-b)+.5*(b-t)+.3*t)
    spread=(abs(bayes-ml)+abs(quantum-bayes)+abs(ml-gene))/3
    unc=math.tanh(.4*ml+.4*bayes+.2*quantum) if spread<.8 else 0.
    breaks=math.tanh(1.6*br+.3*v) if abs(br)>.1 else 0.
    portfolio=math.tanh((t+.5*b)/(1+abs(v))) if abs(q)<2.4 else 0.
    hybrid=math.tanh(.35*bayes+.25*ml+.2*quantum+.2*gene) if abs(v)<1.1 else 0.
    return {
        "quantum_inspired":quantum,
        "path_integral":path,
        "nonlinear_chaos":chaos,
        "hierarchical_bayes":bayes,
        "information_geometry":info,
        "hidden_markov":hmm,
        "risk_constrained_rl":rl,
        "causal_invariance":causal,
        "multihorizon_representation":represent,
        "genetic_programming":gene,
        "meta_learning":meta,
        "multiagent_decision":agents,
        "multiscale_wavelet":wave,
        "uncertainty_ensemble":unc,
        "structural_breakout":breaks,
        "dynamic_portfolio":portfolio,
        "hybrid_controller":hybrid,
        "classical_trend":math.tanh(.6*t+.4*a),
    }
