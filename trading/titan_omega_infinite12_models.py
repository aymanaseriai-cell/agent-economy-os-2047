"""Causal CPU-only mathematical research prototypes, not quantum hardware."""
from __future__ import annotations
import cmath
import math
from statistics import pstdev

NAMES = ("classical_momentum", "quantum_walk_interference",
         "hyperquantum_commutator", "beyondquantum_bayes")


def _returns(bars, index, length=32):
    if index < length or index >= len(bars):
        raise ValueError("Insufficient completed causal history")
    closes = [float(bars[j]["close"]) for j in range(index-length, index+1)]
    if min(closes) <= 0:
        raise ValueError("Nonpositive price")
    return [math.log(b/a) for a,b in zip(closes, closes[1:])]


def _sign(score, cutoff):
    return 1 if score > cutoff else (-1 if score < -cutoff else 0)


def classical_momentum(bars, index):
    r = _returns(bars, index)
    slow = sum(r[-12:])
    fast = sum(r[-4:])
    vol = max(1e-5, pstdev(r[-20:]))
    return _sign((0.6*slow + 0.4*fast)/(vol*math.sqrt(12)), 0.8)


def quantum_walk_interference(bars, index):
    """Two-state discrete-time unitary coined walk; Born readout on CPU.

    psi_(t+1) = D(phi_t) R_y(2 theta_t) psi_t, each step uses old returns.
    No entanglement, no hardware speed advantage.
    """
    r = _returns(bars, index)[-20:]
    a, b = complex(1/math.sqrt(2)), complex(1/math.sqrt(2))
    for k, v in enumerate(r):
        theta = math.atan(50*v)
        phase = math.atan(30*(v-r[k-1] if k else 0))
        c, s = math.cos(theta), math.sin(theta)
        a, b = (c*a-s*b)*cmath.exp(1j*phase), (s*a+c*b)*cmath.exp(-1j*phase)
    p = abs(a)**2 + abs(b)**2
    if abs(p-1) > 1e-9:
        raise ArithmeticError("Nonunitary simulated state")
    # Hadamard-style interference readout, not a forecasting guarantee.
    score = 2*(a.conjugate()*b).real
    return _sign(score, 0.22)


def hyperquantum_commutator(bars, index):
    """Invented noncommutative/Koopman inspired *name*, not new physics.

    Observables A = momentum*sigma_x, B=shock*sigma_z.
    [A,B] / (2i) has a sigma_y coefficient; its signed proxy is
    momentum*shock, added to a causal spectral response.
    """
    r = _returns(bars, index)
    vol = max(1e-5,pstdev(r[-20:]))
    m = math.tanh(sum(r[-8:])/(vol*math.sqrt(8)))
    shock = math.tanh((r[-1]-sum(r[-9:-1])/8)/vol)
    spectral = math.tanh((sum(r[-4:])-sum(r[-12:-4])/2)/(vol*4))
    noncommuting = m*shock
    return _sign(0.55*m+0.30*spectral+0.15*noncommuting, 0.27)


def beyondquantum_bayes(bars, index):
    """Robust Kalman-like state update with innovation-dependent hazard."""
    r = _returns(bars,index)
    mu, var = 0.0, 1e-4
    for value in r:
        process = 2e-6 + min(1e-3, 0.1*value*value)
        pred = var + process
        observation = max(2e-6, pstdev(r[-20:])**2)
        gain = pred/(pred+observation)
        innovation = value-mu
        hazard = min(0.5,abs(innovation)/(10*math.sqrt(pred+observation)))
        mu = (1-hazard)*(mu+gain*innovation)
        var = max(1e-9,(1-gain)*pred+hazard*process)
    # Abstain unless posterior confidence exceeds minimum 20bp move estimate.
    edge = max(0.002, 1.0*math.sqrt(var))
    return _sign(mu, edge)


STRATEGIES = {
    "classical_momentum": classical_momentum,
    "quantum_walk_interference": quantum_walk_interference,
    "hyperquantum_commutator": hyperquantum_commutator,
    "beyondquantum_bayes": beyondquantum_bayes,
}
