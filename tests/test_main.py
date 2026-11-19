"""Tests for ManyBodyLocalization-Lab. Every test grades a computed
number against a statistical anchor band, a closed form, or an
independent referee in main.py. Headline ensemble tests use the
full 40 realisations; referee tests use one realisation or fewer
realisations via the n_real parameter so the suite stays sane."""
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as mbl

_ONE = {}


def one_realisation():
    if "data" not in _ONE:
        fields = mbl.disorder_fields(2.0, 1)[0]
        H = mbl.build_hamiltonian(fields)
        evals, evecs = mbl.jacobi_eigh(H)
        _ONE["data"] = (fields, H, evals, evecs)
    return _ONE["data"]


def test_basis_sector():
    assert len(mbl.BASIS) == 70
    assert all(bin(s).count("1") == 4 for s in mbl.BASIS)
    assert len(set(mbl.BASIS)) == 70
    assert mbl.NEEL_STATE in mbl.BASIS_INDEX


def test_splitmix_deterministic():
    a = mbl.SplitMix64(99)
    b = mbl.SplitMix64(99)
    assert [a.next_float() for _ in range(20)] == \
        [b.next_float() for _ in range(20)]


def test_disorder_fields_range_and_shape():
    rows = mbl.disorder_fields(3.0, 4)
    assert len(rows) == 4 and all(len(r) == 8 for r in rows)
    assert all(-3.0 <= f <= 3.0 for r in rows for f in r)
    assert rows == mbl.disorder_fields(3.0, 4)


def test_hamiltonian_symmetric_and_trace():
    for W in (0.0, 1.0, 12.0):
        fields = mbl.disorder_fields(W, 1)[0]
        H = mbl.build_hamiltonian(fields)
        assert all(abs(H[i][j] - H[j][i]) < 1e-15
                   for i in range(70) for j in range(70))
        # analytic trace: fields cancel, 7 bonds x -2.5
        assert abs(mbl.hamiltonian_trace(fields) + 17.5) < 1e-9


def test_hamiltonian_offdiag_exchange_only():
    fields = mbl.disorder_fields(1.0, 1)[0]
    H = mbl.build_hamiltonian(fields)
    for b, state in enumerate(mbl.BASIS):
        for j, state2 in enumerate(mbl.BASIS):
            if b != j and H[b][j] != 0.0:
                assert abs(H[b][j] - 0.5) < 1e-15
                diff = state ^ state2
                sites = [i for i in range(8) if (diff >> i) & 1]
                assert len(sites) == 2 and sites[1] - sites[0] == 1


def test_jacobi_known_spectra():
    assert all(abs(a - b) < 1e-12 for a, b in zip(
        mbl.jacobi_eigenvalues([[0.0, 1.0], [1.0, 0.0]]), (-1.0, 1.0)))
    assert all(abs(a - b) < 1e-12 for a, b in zip(
        mbl.jacobi_eigenvalues([[2.0, 1.0], [1.0, 2.0]]), (1.0, 3.0)))
    tri = [[2.0, 1.0, 0.0], [1.0, 2.0, 1.0], [0.0, 1.0, 2.0]]
    assert all(abs(a - b) < 1e-12 for a, b in zip(
        mbl.jacobi_eigenvalues(tri),
        (2.0 - math.sqrt(2.0), 2.0, 2.0 + math.sqrt(2.0))))


def test_eigendecomposition_refereed_on_hamiltonian():
    fields, H, evals, evecs = one_realisation()
    assert abs(sum(evals) - mbl.hamiltonian_trace(fields)) < 1e-8
    for i in range(0, 70, 7):
        for j in range(0, 70, 7):
            dot = sum(evecs[k][i] * evecs[k][j] for k in range(70))
            assert abs(dot - (1.0 if i == j else 0.0)) < 1e-9
    for i in (0, 35, 69):
        for row in range(70):
            hv = sum(H[row][k] * evecs[k][i] for k in range(70))
            assert abs(hv - evals[i] * evecs[row][i]) < 1e-8


def test_gap_ratio_synthetic_and_window():
    ratios = mbl.adjacent_gap_ratios([0.0, 1.0, 3.0, 6.0, 10.0])
    expect = (0.5 + 2.0 / 3.0 + 0.75) / 3.0
    assert abs(sum(ratios) / len(ratios) - expect) < 1e-12
    assert len(mbl.mid_spectrum_evals(list(range(70)))) == 35


def test_entropy_referees():
    neel_vec = [0.0] * 70
    neel_vec[mbl.NEEL_INDEX] = 1.0
    assert abs(mbl.half_chain_entropy(neel_vec)) < 1e-12
    bell = [0.0] * 70
    bell[mbl.BASIS_INDEX[0b00111100]] = 1.0 / math.sqrt(2.0)
    bell[mbl.BASIS_INDEX[0b11000011]] = 1.0 / math.sqrt(2.0)
    assert abs(mbl.half_chain_entropy(bell) - math.log(2.0)) < 1e-9
    _, _, _, evecs = one_realisation()
    mid = [evecs[row][35] for row in range(70)]
    rho = mbl.reduced_density_matrix(mid)
    assert abs(sum(rho[i][i] for i in range(16)) - 1.0) < 1e-9
    S = mbl.half_chain_entropy(mid)
    assert 0.0 <= S <= math.log(16)


def test_page_references():
    assert abs(mbl.page_value_unrestricted() - (math.log(16) - 0.5)) < 1e-12
    assert 1.8 < mbl.page_sector_estimate() < 2.3


def test_imbalance_t0_bounds_and_normalisation():
    probs = [0.0] * 70
    probs[mbl.NEEL_INDEX] = 1.0
    assert abs(mbl.imbalance_from_probs(probs) - 1.0) < 1e-12
    _, _, evals, evecs = one_realisation()
    assert abs(sum(mbl.probs_at_time(evals, evecs, 7.0)) - 1.0) < 1e-9
    for t in (0.0, 1.0, 5.0, 20.0):
        assert abs(mbl.imbalance_at_time(evals, evecs, t)) <= 1.0 + 1e-9


def test_stats_headline_bands():
    erg = mbl.compute_stats(1.0)
    loc = mbl.compute_stats(12.0)
    assert abs(erg["mean_r"] - mbl.GOE_R) <= mbl.R_BAND
    assert abs(loc["mean_r"] - mbl.POISSON_R) <= mbl.R_BAND
    assert erg["mean_r"] - loc["mean_r"] >= mbl.R_MARGIN
    assert erg["mean_S"] - loc["mean_S"] >= mbl.S_MARGIN
    assert erg["mean_S"] > 1.0 and loc["mean_S"] < 0.5
    assert loc["mean_I_sat"] > 0.6
    assert abs(erg["mean_I_sat"]) <= mbl.I_ERGODIC_TOL
    assert loc["mean_I_sat"] - erg["mean_I_sat"] >= mbl.I_MARGIN


def test_stats_deterministic_small():
    a = mbl.compute_stats(3.0, n_real=3, use_cache=False)
    b = mbl.compute_stats(3.0, n_real=3, use_cache=False)
    assert a["mean_r"] == b["mean_r"]
    assert a["mean_S"] == b["mean_S"]
    assert a["mean_I_sat"] == b["mean_I_sat"]


def test_policy_labels_synthetic():
    assert mbl.model_label(0.53, 1.6, 0.10) == "ergodic"
    assert mbl.model_label(0.39, 0.10, 0.80) == "localised"
    assert mbl.model_label(0.45, 0.70, 0.30) == "crossover"


def test_classifier_scenarios():
    rep = mbl.classifier_report()
    assert rep["disorder_W1"]["knn"] == "ergodic"
    assert rep["disorder_W2"]["knn"] == "crossover"
    assert rep["disorder_W12"]["knn"] == "localised"
    assert all(row["knn"] == row["policy"] for row in rep.values())


def test_classifier_grid_consistency():
    for feats, label in mbl.TRAINING_GRID:
        assert mbl.classify_features(feats) == label


def test_reports_match_bands():
    lev = mbl.levels_report()
    assert lev["mean_r_ergodic_in_goe_band"] is True
    assert lev["mean_r_localised_in_poisson_band"] is True
    ent = mbl.entropy_report()
    assert ent["mean_S_margin"] >= mbl.S_MARGIN
    imb = mbl.imbalance_report()
    assert abs(imb["I_t0_neel_exact"] - 1.0) < 1e-12
    assert imb["mean_I_margin"] >= mbl.I_MARGIN


def test_hold_gates():
    assert len(mbl.HOLD_GATES) == 14
    assert mbl.gate("model_as_measurement_claim") == "HOLD"
    assert mbl.gate("live_hardware_control") == "HOLD"
    assert mbl.gate("thermodynamic_limit_claim") == "HOLD"
    assert mbl.gate("phase_transition_location_claim") == "HOLD"
    assert mbl.gate("investment_claim") == "HOLD"
    assert mbl.gate("certification_claim") == "HOLD"
    assert mbl.gate("run_simulation") == "PROCEED"


def test_seats_never_override():
    brains = mbl.brains_report()
    assert brains["decider"]["can_override_hold"] is False
    assert brains["decider"]["model_id"] == "gemini-argon-4"
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_checks_all_pass():
    checks = mbl.run_checks()
    assert all(ok for _, ok in checks), [n for n, ok in checks if not ok]
    assert len(checks) == 54


def test_cli_hold_demo_exit_2():
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent
                             / "main.py"), "hold-demo"],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "HOLD" in proc.stdout


def test_cli_checks_command():
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent
                             / "main.py"), "checks"],
        capture_output=True, text=True)
    assert proc.returncode == 0
    assert "CHECKS 54/54" in proc.stdout
