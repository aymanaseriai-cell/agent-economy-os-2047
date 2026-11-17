#!/usr/bin/env python3
"""TITAN Ω Infinite Frontier Gen2: genuine finite-dimensional learning.

A research implementation, NOT marketing: Gaussian Kalman state-space,
finite-state hidden semi-Markov regime duration, ridge Koopman lifted
conditional return, Bayesian online changepoint evidence, conformal
absolute-error intervals, distributionally robust selection, and a tiny
quantum-walk/annealing asset chooser contrasted against exact enumeration.
CPU-only. No historical holdout used in model fitting.
"""
from __future__ import annotations
import cmath, math, random, statistics

MODEL_VERSION="FRONTIER-V2-FROZEN-20261117"
Z_DIM=7

def safe_std(v):
    if len(v)<2:return .001
    return max(1e-5,statistics.pstdev(v))

def lift(f):
    if len(f)!=10 or not all(math.isfinite(float(x)) for x in f):
        raise ValueError("Ten finite 4h causal features required")
    # Koopman EDMD observables; exponential dimension 7, ridge regularized.
    return (1., f[0],f[1],f[2],f[3], f[0]*f[2],f[4])

def solve_ridge(samples,targets,ridge=25.):
    """Dual independent small matrix solver, no sklearn dependency."""
    if len(samples)!=len(targets) or not samples:
        raise ValueError("Labeled training pairs mandatory")
    n=len(samples[0])
    a=[[0.]*n for _ in range(n)]
    b=[0.]*n
    for row,y in zip(samples,targets):
        for i in range(n):
            b[i]+=row[i]*y
            for j in range(n):a[i][j]+=row[i]*row[j]
    for i in range(n):a[i][i]+=ridge
    for i in range(n):
        pivot=max(range(i,n),key=lambda j:abs(a[j][i]))
        a[i],a[pivot]=a[pivot],a[i]
        if abs(a[i][i])<1e-12:raise ArithmeticError("Ill-conditioned Koopman matrix")
        scale=a[i][i]
        for k in range(i,n):a[i][k]/=scale
        b[i]/=scale
        for j in range(n):
            if j==i:continue
            factor=a[j][i]
            for k in range(i,n):a[j][k]-=factor*a[i][k]
            b[j]-=factor*b[i]
    return b

def fit(train):
    """Train [(feature10,next_4h_log_return,sym,clock)] only before embargo."""
    if len(train)<500:raise ValueError("500 causal training pairs required")
    samples=[lift(f) for f,_,_,_ in train]
    targets=[y for _,y,_,_ in train]
    weights=solve_ridge(samples,targets)
    mean=sum(targets)/len(targets)
    sigma=safe_std(targets)
    # Koopman predictive residual variability is determined on TRAIN.
    residual=[y-sum(a*b for a,b in zip(weights,v)) for v,y in zip(samples,targets)]
    res_sigma=safe_std(residual)
    # Train-only persistence and volatility parameters; no holdout tuning.
    x=[f[0] for f,_,_,_ in train]
    x_sigma=max(.35,statistics.pstdev(x))
    p_ac=sum(x[i]*x[i-1] for i in range(1,len(x)))
    den=sum(x[i-1]**2 for i in range(1,len(x)))
    phi=max(.15,min(.9,p_ac/max(1e-6,den)))
    return {"koopman_weights":weights,"y_mean":mean,"y_sigma":sigma,
            "residual_sigma":res_sigma,"x_sigma":x_sigma,"kalman_phi":phi,
            "fit_count":len(train)}

class BayesianKalman:
    """Causal local Gaussian return Kalman state-space filter x_t=phi*x_{t-1}+w.
    Observation is the just-completed 4h log return, not next return.
    """
    def __init__(self,phi,scale):
        self.phi=phi;self.q=max(1e-8,.12*scale*scale)
        self.r=max(1e-8,.7*scale*scale)
        self.mu=0.;self.var=scale*scale
    def update(self,observed):
        pred=self.phi*self.mu
        variance=self.phi*self.phi*self.var+self.q
        gain=variance/(variance+self.r)
        self.mu=pred+gain*(observed-pred)
        self.var=(1-gain)*variance
        return self.phi*self.mu,math.sqrt(self.var+self.q+self.r)

class DurationHSMM:
    """2-state explicit-duration hidden semi-Markov filter, not HMM label.
    48 possible run lengths per state. Likelihoods are Gaussian observed
    4h return with signs, transition hazard grows with duration.
    """
    def __init__(self,scale,max_age=48):
        self.sd=max(1e-5,scale)
        self.n=max_age
        self.probs={(1,1):.5,(-1,1):.5}
    def update(self,observed):
        new={}
        for (sign,age),weight in self.probs.items():
            h=min(.6,.015+.004*age)
            stay=(sign,min(self.n,age+1))
            flip=(-sign,1)
            new[stay]=new.get(stay,0.)+weight*(1-h)
            new[flip]=new.get(flip,0.)+weight*h
        scaled={}
        for (sign,age),prior in new.items():
            mu=sign*.42*self.sd
            z=(observed-mu)/self.sd
            scaled[sign,age]=prior*math.exp(-.5*z*z)
        norm=sum(scaled.values())
        if norm<=0:raise ArithmeticError("HSMM underflow")
        self.probs={k:v/norm for k,v in scaled.items()}
        bullish=sum(p for (sign,_),p in self.probs.items() if sign==1)
        expected=(2*bullish-1)*.42*self.sd
        return expected,bullish

class BOCPD:
    """Bayesian online changepoint run-length filter, truncated at 32 steps.
    Gaussian likelihood with run-conditioned predictive mean, fixed variance
    calibrated on historical training. Changepoint hazard 1/36 each 4h bar.
    """
    def __init__(self,scale):
        self.sd=max(1e-5,scale)
        self.weights=[1.]
        self.means=[0.]
        self.max_age=32
    def update(self,observed):
        def likelihood(x,mu):
            z=(x-mu)/(self.sd*1.3)
            return math.exp(-.5*z*z)
        hazard=1/36
        change=0.;survivors=[0.]*(min(self.max_age,len(self.weights)+1))
        means=[0.]*len(survivors)
        for age,weight in enumerate(self.weights):
            prob=weight*likelihood(observed,self.means[age])
            change+=prob*hazard
            j=min(self.max_age-1,age+1)
            v=prob*(1-hazard)
            survivors[j]+=v
            means[j]+=v*(self.means[age]*age+observed)/(age+1)
        probabilities=[change]+survivors[1:]
        predicted_means=[observed]+[
            means[k]/survivors[k] if survivors[k]>1e-15 else 0.
            for k in range(1,len(survivors))]
        norm=sum(probabilities)
        if norm<=0:raise ArithmeticError("BOCPD underflow")
        self.weights=[v/norm for v in probabilities]
        self.means=predicted_means
        return self.weights[0]

def conformal_threshold(nonconformity,alpha=.10):
    """Split conformal finite-sample rank; exchangeability not guaranteed for
    market time-series. Dev calibration ONLY, no final labels.
    """
    if not .01<=alpha<=.5 or len(nonconformity)<50:
        raise ValueError("Need at least 50 development calibration residuals")
    ordered=sorted(abs(x) for x in nonconformity)
    rank=min(len(ordered),math.ceil((len(ordered)+1)*(1-alpha)))
    return ordered[rank-1]

def koopman_forecast(f,fit_params):
    return sum(a*b for a,b in zip(lift(f),fit_params["koopman_weights"]))

def robust_edge(mu,sigma,cost=0.002,robust_factor=1.):
    """DRO lower bound E[direction*return]-k sigma-execution-cost.
    Positive only if robust forecast dominates conservative transaction cost.
    """
    return max(0.,abs(mu)-robust_factor*max(1e-6,sigma)-cost)

def softmax_anneal(utility,temperature=.15):
    """Small-complex-amplitude quantum-inspired energy phase mixer.
    No quantum speedup or superiority claim; compare same energy with exact.
    State 0 is abstention, states 1..6 are one-asset decisions.
    """
    if len(utility)!=7 or any(not math.isfinite(float(x)) for x in utility):
        raise ValueError("Seven finite asset+abstention utility states")
    state=[complex(1/math.sqrt(8)) for _ in range(8)]
    energy=[-float(x) for x in utility]+[10.]
    for t in range(3):
        for i in range(8):
            state[i]*=cmath.exp(-1j*energy[i]*(.8+t*.3))
        # Unitary Hadamard mixing controlled by a fixed angle.
        for bit in range(3):
            c=math.cos(temperature);s=math.sin(temperature);mask=1<<bit
            nxt=state[:]
            for i in range(8):
                if i&mask:continue
                a,b=state[i],state[i|mask]
                nxt[i]=c*a-1j*s*b
                nxt[i|mask]=-1j*s*a+c*b
            state=nxt
    norm=sum(abs(a)**2 for a in state)
    if abs(norm-1)>1e-9:raise ArithmeticError("Nonunitary quantum-inspired annealer")
    return max(range(7),key=lambda j:abs(state[j])**2)

def exact_enumeration(utility):
    """Classic exhaustive maximizer of the IDENTICAL objective."""
    if len(utility)!=7:raise ValueError("Expected abstention and six assets")
    return max(range(7),key=lambda j:utility[j])

def conditionally_score(f,model,fitted,kalman,hsmm,change_prob,conformal_q):
    """Only completed 4h features are allowed; no future return labels."""
    mu_k,sigma_k=kalman
    mu_h,prob_h=hsmm
    mu_o=koopman_forecast(f,fitted)
    sigma=max(1e-5,fitted["residual_sigma"])
    if model=="koopman":return mu_o/sigma
    if model=="kalman":return mu_k/max(sigma_k,1e-5)
    if model=="hsmm":return (2*prob_h-1)*1.2
    if model=="conformal":
        edge=max(0.,abs(mu_o)-conformal_q-.002)
        return math.copysign(edge/max(1e-5,sigma),mu_o) if edge else 0.
    if model=="distribution_robust":
        edge=robust_edge(mu_o,sigma,.002,1.25)
        return math.copysign(edge/sigma,mu_o) if edge else 0.
    if model=="changepoint":
        if change_prob<.065:return 0.
        return math.copysign(min(1.,change_prob*5),f[0])
    if model=="regime_ensemble":
        if change_prob>.30:return 0.
        opinions=[mu_o/sigma,mu_k/max(1e-5,sigma_k),2*prob_h-1]
        if max(opinions)*min(opinions)<=0:return 0.
        return sum(opinions)/3
    if model=="classic":
        return .6*f[2]+.4*f[0]
    raise ValueError("Unknown frontier model")
