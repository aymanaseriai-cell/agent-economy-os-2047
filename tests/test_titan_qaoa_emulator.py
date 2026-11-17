"""No-order QAOA emulator integrity and exact-ground-state comparisons."""
import math
import unittest

from trading.titan_qaoa_emulator import (
    N_STATES, N_QUBITS, ground_energies, statevector, audit_qaoa
)


class QaoaEmulation(unittest.TestCase):
    def test_six_qubits_are_only_64_classical_basis_states(self):
        self.assertEqual((N_QUBITS,N_STATES),(6,64))

    def test_zero_angles_produce_uniform_state(self):
        energies=[float(i) for i in range(N_STATES)]
        v=statevector(energies,0,0)
        self.assertTrue(all(abs(abs(a)**2-1/64)<1e-12 for a in v))

    def test_mixing_operator_is_unitary(self):
        energies=[i*i/13 for i in range(N_STATES)]
        v=statevector(energies,.107,.71)
        self.assertAlmostEqual(sum(abs(a)**2 for a in v),1.0,places=10)

    def test_reject_invalid_parameters_and_hamiltonian(self):
        with self.assertRaises(ValueError):
            statevector([0.0],.1,.2)
        with self.assertRaises(ValueError):
            statevector([0.0]*64,float("nan"),.2)

    def test_exact_solution_is_not_misreported_as_quantum(self):
        mu=[4.,3.,2.,1.,0.,-2.]
        cov=[[0.0]*6 for _ in range(6)]
        energy=ground_energies(mu,cov)
        r=audit_qaoa(mu,cov,min(energy))
        self.assertFalse(r["physical_quantum_computer_used"])
        self.assertFalse(r["financial_edge_evidenced"])
        self.assertFalse(r["quantum_speedup_evidenced"])
        self.assertAlmostEqual(r["statevector_norm"],1,places=10)
        self.assertGreaterEqual(r["ground_state_probability_mass"],0)
        self.assertLessEqual(r["ground_state_probability_mass"],1)


if __name__=="__main__":
    unittest.main()
