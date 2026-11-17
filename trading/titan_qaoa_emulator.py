#!/usr/bin/env python3
"""Six-qubit QAOA depth-1 STATEVECTOR EMULATION, not quantum hardware.

Every complex amplitude is computed classically with Python stdlib. Cost
Hamiltonian is diagonal in the bit basis. Mixing Hamiltonian is sum of Pauli X.
All optimization uses the predeclared training-only quadratic objective.
No order routing, no quantum advantage or financial-performance claim.
"""
from __future__ import annotations

import cmath
import math
from trading.titan_quantum_ising_lab import FAMILIES, COUNT_SELECTED, ising_energy

N_QUBITS = len(FAMILIES)
N_STATES = 1 << N_QUBITS


def ground_energies(mu,cov):
    return [ising_energy(tuple((state >> k) & 1 for k in range(N_QUBITS)),
                         mu,cov) for state in range(N_STATES)]


def statevector(energies, gamma, beta):
    """One QAOA layer: H_C phase then commuting single-qubit X mixers."""
    if len(energies) != N_STATES or not all(math.isfinite(float(e)) for e in energies):
        raise ValueError("Invalid QUBO Hamiltonian")
    if not all(math.isfinite(x) and 0<=x<=math.pi for x in (gamma,beta)):
        raise ValueError("Invalid variational parameters")
    amplitude = [cmath.exp(-1j*gamma*e) / math.sqrt(N_STATES)
                 for e in energies]
    c,s=math.cos(beta),math.sin(beta)
    for bit in range(N_QUBITS):
        mask=1<<bit
        for low in range(N_STATES):
            if low & mask:
                continue
            high=low|mask
            a,b=amplitude[low],amplitude[high]
            amplitude[low] = c*a - 1j*s*b
            amplitude[high] = c*b - 1j*s*a
    return amplitude


def variational_grid(energies):
    """Small, transparent, exhaustive parameter grid; no black-box miracle."""
    best=None
    for step_gamma in range(31):
        gamma=step_gamma*0.01
        for step_beta in range(13):
            beta=step_beta*math.pi/24
            amplitudes=statevector(energies,gamma,beta)
            expected=sum(abs(a)**2*e for a,e in zip(amplitudes,energies))
            candidate=(expected,gamma,beta)
            if best is None or candidate<best[:3]:
                best=(expected,gamma,beta,amplitudes)
    return best


def audit_qaoa(mu,cov,exact_minimum):
    energies=ground_energies(mu,cov)
    expectation,gamma,beta,amplitudes=variational_grid(energies)
    probs=[abs(a)**2 for a in amplitudes]
    norm=sum(probs)
    if abs(norm-1)>1e-9:
        raise ArithmeticError("Classical statevector lost probability norm")
    optimal_ids=[i for i,e in enumerate(energies) if abs(e-exact_minimum)<1e-8]
    if not optimal_ids:
        raise ValueError("Missing certified classical ground state")
    max_state=max(range(N_STATES),key=lambda i:(probs[i],-i))
    mass_valid=sum(probs[i] for i in range(N_STATES)
                   if i.bit_count()==COUNT_SELECTED)
    return {
        "method":"CLASSICAL_SIX_QUBIT_DEPTH1_QAOA_STATEVECTOR_EMULATION",
        "physical_quantum_computer_used":False,
        "depth":1,
        "states":N_STATES,
        "gamma":round(gamma,6),
        "beta":round(beta,6),
        "statevector_norm":round(norm,10),
        "minimum_energy_proven_by_exhaustive_enumeration":round(exact_minimum,8),
        "variational_expected_energy":round(expectation,8),
        "ground_state_probability_mass":round(sum(probs[i] for i in optimal_ids),6),
        "unbiased_uniform_ground_state_mass":round(len(optimal_ids)/N_STATES,6),
        "valid_three_bit_probability_mass":round(mass_valid,6),
        "most_probable_bitstring":format(max_state,"06b"),
        "most_probable_state_satisfies_three_features":
            max_state.bit_count()==COUNT_SELECTED,
        "most_probable_state_is_ground_state":max_state in optimal_ids,
        "quantum_speedup_evidenced":False,
        "financial_edge_evidenced":False,
    }
