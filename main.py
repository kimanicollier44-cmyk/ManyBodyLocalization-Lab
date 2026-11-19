#!/usr/bin/env python3
"""ManyBodyLocalization-Lab - educational many-body localisation lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * A disordered Heisenberg chain can fail to thermalise: at strong
    disorder its eigenstates stop looking random-matrix-like, their
    entanglement stops obeying a volume law, and a Neel pattern
    imprinted at t = 0 refuses to wash out. At weak disorder all
    three signatures point the other way.
  * This lab computes those three signatures - the adjacent-gap
    ratio <r>, the half-chain entanglement entropy S, and the
    late-time imbalance I_sat - from ONE exact diagonalisation of
    the same Hamiltonian, in the Sz = 0 sector of an N = 8 chain
    (sector dimension C(8,4) = 70), and grades each signature
    against its statistical anchor with honest tolerance BANDS.
  * HONEST SCOPE: N = 8 is a finite-size toy. The bands are
    statistical statements about 40 disorder realisations of this
    70-dimensional sector, nothing more. The many-body localisation
    transition in the thermodynamic limit is NOT located, NOT
    estimated, and NOT claimed anywhere in this file - the language
    used throughout is finite-size crossover language only.

Conventions, stated once and used everywhere:

  * H = sum_i J S_i . S_{i+1} (open chain, J = 1) + sum_i h_i S^z_i,
    with S = sigma / 2, h_i uniform in [-W, W].
  * S_i . S_{i+1} = S^z_i S^z_{i+1} + (S+_i S-_{i+1} + S-_i S+_{i+1})/2,
    so equal neighbours contribute +1/4 on the diagonal, opposite
    neighbours -1/4, and an opposite pair couples to its spin-
    exchanged partner with matrix element 1/2.
  * A basis state is an 8-bit mask; bit i = 1 means site i is up
    (S^z = +1/2). The Sz = 0 sector is the 70 masks of popcount 4.
  * Entanglement is the von Neumann entropy (natural log) of the
    left half (sites 0-3) of a mid-spectrum eigenstate.
  * Imbalance I(t) = (1/N) sum_i pattern_i * 2 <S^z_i>(t), where
    pattern is the Neel pattern (+1 on even sites, -1 on odd), so
    I(0) = 1 exactly for the Neel initial state. I_sat is I(t)
    averaged over the late times (10, 12, 14, 16, 18, 20) and over
    disorder realisations.
  * ALL randomness comes from the in-file splitmix64 PRNG. The
    disorder stream for strength W is seeded with
    SEED_BASE + round(1000 * W), SEED_BASE = 2026, and fields are
    drawn realisation by realisation, site by site.

Every real-world deployment use is a permanent HOLD gate - with
Gemini Argon 4 Extended Thinking as DECIDER (names-only,
tighten-only), Muse as advisor (never overrides HOLD), and Google
Flow plan-only seats.
"""
import cmath
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"

N_SITES = 8
SECTOR_DIM = 70  # C(8, 4)
J_COUPLING = 1.0
SEED_BASE = 2026
N_REAL_DEFAULT = 40
W_ERGODIC = 1.0
W_LOCALISED = 12.0
LATE_TIMES = (10.0, 12.0, 14.0, 16.0, 18.0, 20.0)

# Statistical anchors (textbook values, stated as anchors - the lab
# grades its finite-N averages against them with tolerance BANDS,
# it does not claim to reproduce them exactly).
GOE_R = 0.5359          # Wigner-Dyson / GOE mean adjacent-gap ratio
POISSON_R = 0.3863      # 2 ln 2 - 1, Poisson mean adjacent-gap ratio
R_BAND = 0.06           # half-width of the grading band for <r>
R_MARGIN = 0.07         # stated clear margin: <r>(W=1) - <r>(W=12)
S_MARGIN = 0.8          # stated clear margin: S(W=1) - S(W=12)
I_MARGIN = 0.4          # stated clear margin: I_sat(W=12) - I_sat(W=1)
I_ERGODIC_TOL = 0.20    # finite-size tolerance for I_sat(W=1) ~ 0

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "thermodynamic_limit_claim": "HOLD - no claim about the thermodynamic limit from an N = 8 finite-size toy",
    "phase_transition_location_claim": "HOLD - no locating, estimating, or quoting a critical disorder Wc or an MBL transition point",
    "finite_size_scaling_claim": "HOLD - no finite-size scaling, extrapolation to larger N, or critical exponent is computed or claimed",
    "real_material_localisation_claim": "HOLD - no claim that any real material, device, or sample is localised or thermalising",
    "quantum_memory_product_claim": "HOLD - no quantum memory, storage, or error-protection product claim from imbalance in a toy chain",
    "quantum_hardware_design_claim": "HOLD - no hardware design, disorder engineering, or platform specification is asserted",
    "experimental_validation_claim": "HOLD - no experimental validation; no experiment was run and no data was measured",
    "thermalisation_guarantee_claim": "HOLD - no guarantee that any real system will or will not thermalise",
    "materials_discovery_claim": "HOLD - no materials discovery, screening, or candidate claim from this model",
    "investment_claim": "HOLD - no investment claim; a lab model is not a prospectus",
    "certification_claim": "HOLD - no certification that any system meets any standard",
    "live_hardware_control": "HOLD - no control of real qubits, chains, or laboratory hardware, ever",
    "model_as_measurement_claim": "HOLD - a computed number is a statement about the model at stated inputs, never a measurement",
    "publication_phase_diagram_claim": "HOLD - no publication-grade phase diagram is produced by a 70-state sector at one system size",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. PRNG
# splitmix64: the ONLY source of randomness in the lab. Same seed,
# same stream, on every machine - the demo is byte-identical
# between runs because nothing else is allowed to be random.

MASK64 = (1 << 64) - 1


class SplitMix64:
    def __init__(self, seed):
        self.state = seed & MASK64

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def next_float(self):
        """Uniform float in [0, 1) from the top 53 bits."""
        return (self.next_u64() >> 11) / float(1 << 53)

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self.next_float()


def disorder_fields(W, n_real):
    """n_real disorder realisations at strength W.

    One splitmix64 stream per W, seeded SEED_BASE + round(1000 W);
    fields drawn realisation by realisation, site by site, each
    uniform in [-W, W]. Fully deterministic.
    """
    rng = SplitMix64(SEED_BASE + int(round(W * 1000)))
    return [[rng.uniform(-W, W) for _ in range(N_SITES)]
            for _ in range(n_real)]


# ================================================================ 2. Sector basis
# The Sz = 0 sector, built explicitly: every 8-bit mask with
# popcount 4, in increasing order. 70 states, no more, no fewer.

def _build_basis():
    return tuple(mask for mask in range(1 << N_SITES)
                 if bin(mask).count("1") == N_SITES // 2)


BASIS = _build_basis()
BASIS_INDEX = {state: i for i, state in enumerate(BASIS)}
# SZ_TABLE[b][i] = S^z eigenvalue (+1/2 up, -1/2 down) of site i
# in basis state b.
SZ_TABLE = tuple(
    tuple(0.5 if (state >> i) & 1 else -0.5 for i in range(N_SITES))
    for state in BASIS)

NEEL_STATE = sum(1 << i for i in range(0, N_SITES, 2))  # up down up down...
NEEL_INDEX = BASIS_INDEX[NEEL_STATE]
NEEL_PATTERN = tuple(1.0 if i % 2 == 0 else -1.0 for i in range(N_SITES))


# ================================================================ 3. Jacobi solver
# Real-symmetric Jacobi eigensolver, written from scratch. It is
# refereed on known spectra in CHECKS before it is trusted with
# the Hamiltonian, and its eigenvectors are checked for
# orthonormality and residuals on the Hamiltonian itself.

def jacobi_eigh(A, tol=1e-12, max_sweeps=100):
    """Eigendecomposition of a real symmetric matrix.

    Cyclic Jacobi rotations J in the (p, q) plane with
    J_pp = J_qq = c, J_pq = s, J_qp = -s, where t = s / c is the
    smaller root of t^2 + 2 tau t - 1 = 0,
    tau = (a_qq - a_pp) / (2 a_pq). Returns (eigenvalues sorted
    ascending, V) with V[row][k] the row-th component of the
    k-th eigenvector.
    """
    n = len(A)
    a = [row[:] for row in A]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for sweep in range(max_sweeps):
        off = math.sqrt(sum(a[p][q] * a[p][q]
                            for p in range(n) for q in range(p + 1, n)))
        if off < tol:
            break
        thresh = 0.2 * off / n if sweep < 4 else 0.0
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) <= thresh or abs(apq) < 1e-16:
                    continue
                app, aqq = a[p][p], a[q][q]
                tau = (aqq - app) / (2.0 * apq)
                if tau == 0.0:
                    t = 1.0
                else:
                    t = math.copysign(
                        1.0 / (abs(tau) + math.sqrt(tau * tau + 1.0)), tau)
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
                    if k != p and k != q:
                        akp, akq = a[k][p], a[k][q]
                        nkp = c * akp - s * akq
                        nkq = s * akp + c * akq
                        a[k][p] = nkp
                        a[p][k] = nkp
                        a[k][q] = nkq
                        a[q][k] = nkq
                a[p][p] = c * c * app - 2.0 * c * s * apq + s * s * aqq
                a[q][q] = s * s * app + 2.0 * c * s * apq + c * c * aqq
                a[p][q] = 0.0
                a[q][p] = 0.0
    eig = [a[i][i] for i in range(n)]
    order = sorted(range(n), key=lambda i: eig[i])
    return ([eig[i] for i in order],
            [[v[row][i] for i in order] for row in range(n)])


def jacobi_eigenvalues(A):
    return jacobi_eigh(A)[0]


# ================================================================ 4. Hamiltonian
# H = sum_i J S_i . S_{i+1} + sum_i h_i S^z_i in the Sz = 0 basis.
# Diagonal: field terms plus +-1/4 per bond. Off-diagonal: 1/2
# between masks that differ by one adjacent spin exchange.

def build_hamiltonian(fields):
    dim = len(BASIS)
    H = [[0.0] * dim for _ in range(dim)]
    for b, state in enumerate(BASIS):
        sz = SZ_TABLE[b]
        diag = sum(fields[i] * sz[i] for i in range(N_SITES))
        for i in range(N_SITES - 1):
            diag += J_COUPLING * (0.25 if sz[i] == sz[i + 1] else -0.25)
            if sz[i] != sz[i + 1]:
                partner = state ^ (1 << i) ^ (1 << (i + 1))
                H[b][BASIS_INDEX[partner]] += 0.5 * J_COUPLING
        H[b][b] = diag
    return H


def hamiltonian_trace(fields):
    H = build_hamiltonian(fields)
    return sum(H[i][i] for i in range(len(H)))


# ================================================================ 5. Level statistics
# Adjacent-gap ratio r_n = min(d_n, d_{n+1}) / max(d_n, d_{n+1})
# over the mid-spectrum window (the central half of the sorted
# spectrum). Ergodic (GOE) anchor 0.5359, Poisson anchor 0.3863.

def mid_spectrum_evals(evals):
    n = len(evals)
    return evals[n // 4: 3 * n // 4]


def adjacent_gap_ratios(evals):
    gaps = [evals[i + 1] - evals[i] for i in range(len(evals) - 1)]
    out = []
    for i in range(len(gaps) - 1):
        lo, hi = min(gaps[i], gaps[i + 1]), max(gaps[i], gaps[i + 1])
        out.append(lo / hi if hi > 0 else 0.0)
    return out


def mean_gap_ratio(evals):
    ratios = adjacent_gap_ratios(mid_spectrum_evals(evals))
    return sum(ratios) / len(ratios)


# ================================================================ 6. Entanglement
# Half-chain von Neumann entropy: reshape the eigenvector into a
# 16 x 16 matrix M[left][right] (left = sites 0-3, right = 4-7),
# form rho_L = M M^T, and take -Tr rho_L ln rho_L from the Jacobi
# eigenvalues of rho_L.

def reduced_density_matrix(vec):
    M = [[0.0] * 16 for _ in range(16)]
    for amp, state in zip(vec, BASIS):
        M[state & 15][(state >> 4) & 15] += amp
    return [[sum(M[i][k] * M[j][k] for k in range(16))
             for j in range(16)] for i in range(16)]


def von_neumann_entropy(rho):
    total = 0.0
    for p in jacobi_eigenvalues(rho):
        if p > 1e-12:
            total -= p * math.log(p)
    return total


def half_chain_entropy(vec):
    return von_neumann_entropy(reduced_density_matrix(vec))


def page_value_unrestricted():
    """Page's formula for an unrestricted 16 x 16 bipartition:
    ln(16) - 16 / (2 * 16). A formula value, fenced as approximate
    for this sector - NOT the sector's random-state average."""
    return math.log(16) - 16.0 / (2.0 * 16.0)


def page_sector_estimate(n_samples=12, seed=987654321):
    """Computed comparison: mean half-chain entropy of random
    unit vectors drawn inside the Sz = 0 sector itself (Gaussian
    entries via Box-Muller on the splitmix64 stream, normalised).
    A deterministic Monte-Carlo estimate, fenced as approximate -
    it is the sector's Page-style reference, not a theorem."""
    rng = SplitMix64(seed)
    total = 0.0
    for _ in range(n_samples):
        vals = []
        while len(vals) < SECTOR_DIM:
            u1 = max(rng.next_float(), 1e-300)
            u2 = rng.next_float()
            rad = math.sqrt(-2.0 * math.log(u1))
            vals.append(rad * math.cos(2.0 * math.pi * u2))
            if len(vals) < SECTOR_DIM:
                vals.append(rad * math.sin(2.0 * math.pi * u2))
        norm = math.sqrt(sum(v * v for v in vals))
        total += half_chain_entropy([v / norm for v in vals])
    return total / n_samples


# ================================================================ 7. Imbalance dynamics
# Neel initial state, time-evolved with the eigen-decomposition:
# psi(t) = sum_k V[:, k] <k|psi0> exp(-i E_k t). The Neel state
# is a single basis state, so <k|psi0> = V[NEEL_INDEX][k].

def probs_at_time(evals, evecs, t):
    dim = len(BASIS)
    coeffs = [evecs[NEEL_INDEX][k] for k in range(dim)]
    phases = [cmath.exp(-1j * evals[k] * t) for k in range(dim)]
    probs = []
    for b in range(dim):
        row = evecs[b]
        amp = 0j
        for k in range(dim):
            if row[k] != 0.0 and coeffs[k] != 0.0:
                amp += row[k] * coeffs[k] * phases[k]
        probs.append(abs(amp) ** 2)
    return probs


def imbalance_from_probs(probs):
    total = 0.0
    for i in range(N_SITES):
        sz_exp = sum(probs[b] * SZ_TABLE[b][i] for b in range(len(BASIS)))
        total += NEEL_PATTERN[i] * 2.0 * sz_exp
    return total / N_SITES


def imbalance_at_time(evals, evecs, t):
    return imbalance_from_probs(probs_at_time(evals, evecs, t))


def imbalance_late_average(evals, evecs):
    return sum(imbalance_at_time(evals, evecs, t)
               for t in LATE_TIMES) / len(LATE_TIMES)


# ================================================================ 8. Ensemble statistics
# One eigendecomposition per realisation yields all three
# signatures. Results are cached per (W, n_real) inside a process
# so the demo, the reports, and CHECKS share the same numbers.

def _mean(xs):
    return sum(xs) / len(xs)


def _pstd(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


_STATS_CACHE = {}


def compute_stats(W, n_real=N_REAL_DEFAULT, use_cache=True):
    key = (float(W), int(n_real))
    if use_cache and key in _STATS_CACHE:
        return _STATS_CACHE[key]
    r_list, s_list, i_list = [], [], []
    for fields in disorder_fields(W, n_real):
        evals, evecs = jacobi_eigh(build_hamiltonian(fields))
        r_list.append(mean_gap_ratio(evals))
        mid_vec = [evecs[row][len(evals) // 2] for row in range(len(BASIS))]
        s_list.append(half_chain_entropy(mid_vec))
        i_list.append(imbalance_late_average(evals, evecs))
    result = {
        "W": float(W),
        "n_real": int(n_real),
        "mean_r": _mean(r_list),
        "std_r": _pstd(r_list),
        "mean_S": _mean(s_list),
        "std_S": _pstd(s_list),
        "mean_I_sat": _mean(i_list),
        "std_I_sat": _pstd(i_list),
        "r_per_realisation": r_list,
        "S_per_realisation": s_list,
        "I_sat_per_realisation": i_list,
    }
    if use_cache:
        _STATS_CACHE[key] = result
    return result


# ================================================================ 9. kNN classifier
# Features of a disorder strength: (<r>, S_half, I_sat), the three
# computed signatures. The training grid is labelled by the lab's
# own policy (model_label below) - the classifier interpolates the
# policy, it does not replace the computed quantities. Distances
# are computed on features normalised by the stated scales
# (0.2, 2.0, 1.0), because the raw scales differ by an order of
# magnitude.

FEATURE_SCALES = (0.2, 2.0, 1.0)


def model_label(r, s_half, i_sat):
    """The phase policy distilled to three verdicts.

    Finite-size crossover language only: 'ergodic' and 'localised'
    name the two ends of the N = 8 crossover, never phases of the
    thermodynamic limit.
    """
    if r <= 0.44 and i_sat >= 0.50:
        return "localised"
    if r >= 0.47 and i_sat <= 0.30:
        return "ergodic"
    return "crossover"


def _training_grid():
    rows = []
    for r in (0.37, 0.40, 0.43, 0.46, 0.49, 0.52, 0.55):
        for s_half in (0.05, 0.3, 0.6, 1.0, 1.5, 2.0):
            for i_sat in (0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92):
                feats = (r, s_half, i_sat)
                rows.append((feats, model_label(*feats)))
    return rows


TRAINING_GRID = _training_grid()


def classify_features(features, k=5):
    """Distance-weighted kNN over the policy-labelled grid."""
    ranked = []
    for feats, label in TRAINING_GRID:
        dist = math.sqrt(sum(((a - b) / sc) ** 2
                             for a, b, sc in zip(features, feats,
                                                 FEATURE_SCALES)))
        ranked.append((dist, feats, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    votes = {}
    for dist, _, label in ranked[:k]:
        votes[label] = votes.get(label, 0.0) + 1.0 / (dist + 1e-9)
    priority = {"ergodic": 0, "crossover": 1, "localised": 2}
    return sorted(votes.items(), key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


CLASSIFIER_SCENARIOS = {
    "disorder_W1": (W_ERGODIC, N_REAL_DEFAULT),
    "disorder_W2": (2.0, 12),
    "disorder_W12": (W_LOCALISED, N_REAL_DEFAULT),
}


def classifier_report():
    rows = {}
    for name, (W, n_real) in CLASSIFIER_SCENARIOS.items():
        st = compute_stats(W, n_real=n_real)
        feats = (st["mean_r"], st["mean_S"], st["mean_I_sat"])
        rows[name] = {
            "W": W,
            "n_real": n_real,
            "features": [round(v, 6) for v in feats],
            "policy": model_label(*feats),
            "knn": classify_features(feats),
        }
    return rows


# ================================================================ 10. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="manybodylocalization-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "model_id": "gemini-argon-4",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all deployment gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="manybodylocalization-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Print the scope before the number: N = 8, sector dimension 70, 40 realisations, bands not error bars on a transition - then show the <r> band edges, the entropy margin, and the imbalance tolerance that were actually computed, and keep the words 'finite-size crossover' attached to every verdict.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["a level staircase unfolding from rigid GOE spacing into Poisson scatter as disorder grows",
                  "a chain of spins holding its Neel stripes while a thermal chain's stripes wash away",
                  "an entanglement curve bending from volume law toward area law across the crossover",
                  "seventy sector states lighting up as the Jacobi solver sorts their energies",
                  "the imbalance trace flattening near zero on one side and near one on the other"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ 11. Topic reports
def _stats_row(st):
    return {
        "W": st["W"],
        "n_real": st["n_real"],
        "mean_r": round(st["mean_r"], 6),
        "std_r": round(st["std_r"], 6),
        "mean_S": round(st["mean_S"], 6),
        "std_S": round(st["std_S"], 6),
        "mean_I_sat": round(st["mean_I_sat"], 6),
        "std_I_sat": round(st["std_I_sat"], 6),
    }


def levels_report():
    erg = compute_stats(W_ERGODIC)
    loc = compute_stats(W_LOCALISED)
    return {
        "ergodic_side": _stats_row(erg),
        "localised_side": _stats_row(loc),
        "anchors": {
            "goe_r": GOE_R,
            "poisson_r": POISSON_R,
            "band_half_width": R_BAND,
            "goe_band": [round(GOE_R - R_BAND, 6), round(GOE_R + R_BAND, 6)],
            "poisson_band": [round(POISSON_R - R_BAND, 6),
                             round(POISSON_R + R_BAND, 6)],
        },
        "mean_r_ergodic_in_goe_band": bool(
            abs(erg["mean_r"] - GOE_R) <= R_BAND),
        "mean_r_localised_in_poisson_band": bool(
            abs(loc["mean_r"] - POISSON_R) <= R_BAND),
        "mean_r_margin": round(erg["mean_r"] - loc["mean_r"], 6),
        "mean_r_margin_stated": R_MARGIN,
    }


def entropy_report():
    erg = compute_stats(W_ERGODIC)
    loc = compute_stats(W_LOCALISED)
    return {
        "ergodic_side": _stats_row(erg),
        "localised_side": _stats_row(loc),
        "page_unrestricted_formula": round(page_value_unrestricted(), 6),
        "page_sector_estimate_approx": round(page_sector_estimate(), 6),
        "page_note": "both Page numbers are approximate references, fenced as such; the sector estimate is a deterministic Monte-Carlo average over random in-sector states",
        "mean_S_margin": round(erg["mean_S"] - loc["mean_S"], 6),
        "mean_S_margin_stated": S_MARGIN,
    }


def imbalance_report():
    erg = compute_stats(W_ERGODIC)
    loc = compute_stats(W_LOCALISED)
    neel_probs = [0.0] * len(BASIS)
    neel_probs[NEEL_INDEX] = 1.0
    return {
        "ergodic_side": _stats_row(erg),
        "localised_side": _stats_row(loc),
        "I_t0_neel_exact": imbalance_from_probs(neel_probs),
        "late_times": list(LATE_TIMES),
        "mean_I_margin": round(loc["mean_I_sat"] - erg["mean_I_sat"], 6),
        "mean_I_margin_stated": I_MARGIN,
        "ergodic_tolerance_stated": I_ERGODIC_TOL,
    }


def sweep_report():
    rows = {}
    for W in (1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0):
        st = compute_stats(W, n_real=8)
        rows[f"W{W:g}"] = _stats_row(st)
    return rows


# ================================================================ checks
_ONE_CACHE = {}


def _one_realisation():
    """One shared W = 2 eigendecomposition for the referee checks."""
    if "data" not in _ONE_CACHE:
        fields = disorder_fields(2.0, 1)[0]
        H = build_hamiltonian(fields)
        evals, evecs = jacobi_eigh(H)
        _ONE_CACHE["data"] = (fields, H, evals, evecs)
    return _ONE_CACHE["data"]


def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 0. Jacobi eigensolver refereed on known spectra first
    chk("jacobi_pauli_x_spectrum",
        all(abs(a - b) < 1e-12 for a, b in
            zip(jacobi_eigenvalues([[0.0, 1.0], [1.0, 0.0]]), (-1.0, 1.0))))
    chk("jacobi_known_2x2_spectrum",
        all(abs(a - b) < 1e-12 for a, b in
            zip(jacobi_eigenvalues([[2.0, 1.0], [1.0, 2.0]]), (1.0, 3.0))))
    chk("jacobi_diagonal_3x3_spectrum",
        jacobi_eigenvalues([[3.0, 0.0, 0.0], [0.0, 1.0, 0.0],
                            [0.0, 0.0, 2.0]]) == [1.0, 2.0, 3.0])
    tri = [[2.0, 1.0, 0.0], [1.0, 2.0, 1.0], [0.0, 1.0, 2.0]]
    tri_evals, tri_evecs = jacobi_eigh(tri)
    chk("jacobi_tridiagonal_spectrum_and_orthonormality",
        all(abs(a - b) < 1e-12 for a, b in
            zip(tri_evals, (2.0 - math.sqrt(2.0), 2.0,
                            2.0 + math.sqrt(2.0))))
        and all(abs(sum(tri_evecs[k][i] * tri_evecs[k][j] for k in range(3))
                    - (1.0 if i == j else 0.0)) < 1e-12
                for i in range(3) for j in range(3)))

    # 1. Sector basis: size, Sz = 0, uniqueness, Neel membership
    chk("basis_size_70", len(BASIS) == SECTOR_DIM == 70)
    chk("basis_all_sz_zero",
        all(bin(state).count("1") == N_SITES // 2 for state in BASIS)
        and all(abs(sum(SZ_TABLE[b])) < 1e-15 for b in range(len(BASIS))))
    chk("basis_unique", len(set(BASIS)) == len(BASIS))
    chk("neel_state_in_sector",
        NEEL_STATE in BASIS_INDEX
        and bin(NEEL_STATE).count("1") == N_SITES // 2)

    # 2. Hamiltonian: symmetry, exchange-only off-diagonals, trace
    fields1 = disorder_fields(1.0, 1)[0]
    H1 = build_hamiltonian(fields1)
    chk("hamiltonian_symmetric",
        all(abs(H1[i][j] - H1[j][i]) < 1e-15
            for i in range(len(BASIS)) for j in range(len(BASIS))))
    def _offdiag_ok():
        for b, state in enumerate(BASIS):
            for j, state2 in enumerate(BASIS):
                if b == j:
                    continue
                diff = state ^ state2
                if H1[b][j] != 0.0:
                    # nonzero only for one adjacent exchange, value 1/2
                    sites = [i for i in range(N_SITES) if (diff >> i) & 1]
                    if len(sites) != 2 or sites[1] - sites[0] != 1 \
                            or abs(H1[b][j] - 0.5 * J_COUPLING) > 1e-15:
                        return False
                elif bin(diff).count("1") == 2:
                    sites = [i for i in range(N_SITES) if (diff >> i) & 1]
                    if sites[1] - sites[0] == 1 and \
                            SZ_TABLE[b][sites[0]] != SZ_TABLE[b][sites[1]]:
                        return False
        return True
    chk("hamiltonian_offdiag_exchange_only", _offdiag_ok())
    # Trace: field terms cancel (each site is up in exactly half of
    # the 70 states); each of the 7 bonds contributes
    # 0.25 * (30 equal - 40 opposite) = -2.5, so Tr H = -17.5 for
    # ANY disorder fields.
    chk("hamiltonian_trace_minus_17p5_any_fields",
        all(abs(hamiltonian_trace(disorder_fields(W, 1)[0]) + 17.5) < 1e-9
            for W in (0.0, 1.0, 5.0, 12.0)))
    chk("hamiltonian_rebuild_deterministic",
        build_hamiltonian(fields1) == H1)

    # 3. Eigendecomposition refereed on the Hamiltonian itself
    _, _, evals1, evecs1 = _one_realisation()
    chk("eigenvalues_sum_equals_trace",
        abs(sum(evals1) - hamiltonian_trace(
            disorder_fields(2.0, 1)[0])) < 1e-8)
    chk("eigenvectors_orthonormal_hamiltonian",
        all(abs(sum(evecs1[k][i] * evecs1[k][j] for k in range(len(BASIS)))
                - (1.0 if i == j else 0.0)) < 1e-9
            for i in range(0, len(BASIS), 7)
            for j in range(0, len(BASIS), 7)))
    _, H2, _, _ = _one_realisation()
    chk("eigenvector_residual_hamiltonian",
        max(abs(sum(H2[row][k] * evecs1[k][i] for k in range(len(BASIS)))
                - evals1[i] * evecs1[row][i])
            for i in (0, 17, 35, 52, 69) for row in range(len(BASIS)))
        < 1e-8)

    # 4. PRNG + disorder: deterministic, in range
    s_a = SplitMix64(123)
    s_b = SplitMix64(123)
    chk("splitmix_deterministic_and_unit_range",
        [s_a.next_float() for _ in range(50)]
        == [s_b.next_float() for _ in range(50)])
    chk("splitmix_stream_values_in_range",
        all(0.0 <= v < 1.0 for v in
            [SplitMix64(7).next_float() for _ in range(1)])
        and all(-3.0 <= f <= 3.0
                for row in disorder_fields(3.0, 4) for f in row))
    chk("disorder_fields_shape_and_determinism",
        disorder_fields(4.0, 3) == disorder_fields(4.0, 3)
        and len(disorder_fields(4.0, 3)) == 3
        and all(len(row) == N_SITES for row in disorder_fields(4.0, 3)))

    # 5. Level statistics: definition, window, bands, margin
    chk("gap_ratio_synthetic_spectrum",
        abs(_mean(adjacent_gap_ratios([0.0, 1.0, 3.0, 6.0, 10.0]))
            - (0.5 + 2.0 / 3.0 + 0.75) / 3.0) < 1e-12)
    chk("mid_spectrum_window_size",
        len(mid_spectrum_evals(list(range(70)))) == 35
        and len(adjacent_gap_ratios(mid_spectrum_evals(
            [float(i) for i in range(70)]))) == 33)
    erg = compute_stats(W_ERGODIC)
    loc = compute_stats(W_LOCALISED)
    chk("r_per_realisation_in_unit_interval",
        all(0.0 <= v <= 1.0 for v in erg["r_per_realisation"])
        and all(0.0 <= v <= 1.0 for v in loc["r_per_realisation"]))
    chk("mean_r_ergodic_in_goe_band",
        abs(erg["mean_r"] - GOE_R) <= R_BAND)
    chk("mean_r_localised_in_poisson_band",
        abs(loc["mean_r"] - POISSON_R) <= R_BAND)
    chk("mean_r_margin_ergodic_above_localised",
        erg["mean_r"] - loc["mean_r"] >= R_MARGIN)

    # 6. Entanglement: RDM referee cases, bounds, margin
    neel_vec = [0.0] * len(BASIS)
    neel_vec[NEEL_INDEX] = 1.0
    rho_neel = reduced_density_matrix(neel_vec)
    chk("rdm_trace_one_eigenstate",
        abs(sum(reduced_density_matrix(
            [evecs1[row][35] for row in range(len(BASIS))])[i][i]
            for i in range(16)) - 1.0) < 1e-9)
    chk("entropy_product_state_zero",
        abs(half_chain_entropy(neel_vec)) < 1e-12
        and abs(sum(rho_neel[i][i] for i in range(16)) - 1.0) < 1e-12)
    bell_vec = [0.0] * len(BASIS)
    bell_vec[BASIS_INDEX[0b00111100]] = 1.0 / math.sqrt(2.0)
    bell_vec[BASIS_INDEX[0b11000011]] = 1.0 / math.sqrt(2.0)
    chk("entropy_two_state_superposition_ln2",
        abs(half_chain_entropy(bell_vec) - math.log(2.0)) < 1e-9)
    chk("entropy_bounds_per_realisation",
        all(0.0 - 1e-9 <= v <= math.log(16) + 1e-9
            for v in erg["S_per_realisation"])
        and all(0.0 - 1e-9 <= v <= math.log(16) + 1e-9
                for v in loc["S_per_realisation"]))
    chk("page_unrestricted_formula",
        abs(page_value_unrestricted() - (math.log(16) - 0.5)) < 1e-12)
    chk("page_sector_estimate_in_range",
        1.8 < page_sector_estimate() < 2.3)
    chk("mean_entropy_margin",
        erg["mean_S"] - loc["mean_S"] >= S_MARGIN)
    chk("mean_entropy_sides_separated",
        erg["mean_S"] > 1.0 and loc["mean_S"] < 0.5)

    # 7. Imbalance: exact start, bounds, late-time verdicts
    neel_probs = [0.0] * len(BASIS)
    neel_probs[NEEL_INDEX] = 1.0
    chk("imbalance_t0_exactly_one",
        abs(imbalance_from_probs(neel_probs) - 1.0) < 1e-12)
    chk("imbalance_bounds_over_time",
        all(abs(imbalance_at_time(evals1, evecs1, t)) <= 1.0 + 1e-9
            for t in (0.0, 1.0, 5.0, 10.0, 20.0)))
    chk("imbalance_probabilities_normalised",
        abs(sum(probs_at_time(evals1, evecs1, 7.0)) - 1.0) < 1e-9)
    chk("imbalance_late_localised_high", loc["mean_I_sat"] > 0.6)
    chk("imbalance_late_ergodic_near_zero",
        abs(erg["mean_I_sat"]) <= I_ERGODIC_TOL)
    chk("imbalance_margin", loc["mean_I_sat"] - erg["mean_I_sat"] >= I_MARGIN)

    # 8. Determinism of the full pipeline at small size
    st_a = compute_stats(3.0, n_real=3, use_cache=False)
    st_b = compute_stats(3.0, n_real=3, use_cache=False)
    chk("stats_deterministic_small",
        st_a["mean_r"] == st_b["mean_r"]
        and st_a["mean_S"] == st_b["mean_S"]
        and st_a["mean_I_sat"] == st_b["mean_I_sat"])

    # 9. Classifier: labels come from the lab's own policy
    rep = classifier_report()
    chk("classifier_scenario_labels",
        rep["disorder_W1"]["knn"] == "ergodic"
        and rep["disorder_W2"]["knn"] == "crossover"
        and rep["disorder_W12"]["knn"] == "localised")
    chk("classifier_knn_matches_policy_scenarios",
        all(row["knn"] == row["policy"] for row in rep.values()))
    chk("classifier_knn_matches_policy_grid",
        all(classify_features(feats) == label
            for feats, label in TRAINING_GRID))
    chk("classifier_headline_phases",
        model_label(erg["mean_r"], erg["mean_S"], erg["mean_I_sat"])
        == "ergodic"
        and model_label(loc["mean_r"], loc["mean_S"], loc["mean_I_sat"])
        == "localised")

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_model_as_measurement_hold",
        gate("model_as_measurement_claim") == "HOLD")
    chk("gate_live_hardware_hold", gate("live_hardware_control") == "HOLD")
    chk("gate_thermodynamic_limit_hold",
        gate("thermodynamic_limit_claim") == "HOLD")
    chk("gate_phase_transition_location_hold",
        gate("phase_transition_location_claim") == "HOLD")
    chk("gate_investment_hold", gate("investment_claim") == "HOLD")
    chk("gate_certification_hold", gate("certification_claim") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"]
        == "Gemini Argon 4 Extended Thinking"
        and brains["decider"]["model_id"] == "gemini-argon-4")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("ManyBodyLocalization-Lab - disordered Heisenberg chain, N = 8")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - a finite-size toy, crossover language only")
    print("    Exact diagonalisation in the Sz = 0 sector (dim 70) of a")
    print("    disordered Heisenberg chain. Three signatures - level")
    print("    statistics, entanglement, imbalance - are graded against")
    print("    statistical anchors with tolerance BANDS. N = 8 does NOT")
    print("    locate the MBL transition; nothing here is a measurement.")
    print("\n[2] Sector + Hamiltonian")
    print(f"    basis states {len(BASIS)} (C(8,4) = 70) | Neel state "
          f"mask {NEEL_STATE:08b} at sector index {NEEL_INDEX}")
    print(f"    Tr H = {hamiltonian_trace(disorder_fields(1.0, 1)[0]):.6f} "
          f"for any fields (analytic -17.5: fields cancel, each bond "
          f"-2.5)")
    erg = compute_stats(W_ERGODIC)
    loc = compute_stats(W_LOCALISED)
    print(f"\n[3] Level statistics - adjacent-gap ratio <r>, "
          f"{N_REAL_DEFAULT} realisations")
    print(f"    W = 1:  <r> = {erg['mean_r']:.6f} (std "
          f"{erg['std_r']:.6f}) | GOE anchor {GOE_R} band "
          f"[{GOE_R - R_BAND:.4f}, {GOE_R + R_BAND:.4f}] -> "
          f"{'IN BAND' if abs(erg['mean_r'] - GOE_R) <= R_BAND else 'OUT OF BAND'}")
    print(f"    W = 12: <r> = {loc['mean_r']:.6f} (std "
          f"{loc['std_r']:.6f}) | Poisson anchor {POISSON_R} band "
          f"[{POISSON_R - R_BAND:.4f}, {POISSON_R + R_BAND:.4f}] -> "
          f"{'IN BAND' if abs(loc['mean_r'] - POISSON_R) <= R_BAND else 'OUT OF BAND'}")
    print(f"    margin <r>(W=1) - <r>(W=12) = "
          f"{erg['mean_r'] - loc['mean_r']:.6f} (stated >= {R_MARGIN})")
    print("\n[4] Entanglement - half-chain entropy of a mid-spectrum state")
    print(f"    W = 1:  S = {erg['mean_S']:.6f} (std {erg['std_S']:.6f})")
    print(f"    W = 12: S = {loc['mean_S']:.6f} (std {loc['std_S']:.6f})")
    print(f"    margin S(W=1) - S(W=12) = {erg['mean_S'] - loc['mean_S']:.6f} "
          f"(stated >= {S_MARGIN})")
    print(f"    Page references (approximate, fenced): unrestricted "
          f"formula {page_value_unrestricted():.6f}; in-sector "
          f"random-state estimate {page_sector_estimate():.6f}")
    print("\n[5] Imbalance dynamics - Neel start, late-time average")
    print(f"    I(0) = 1 exactly by construction; late times "
          f"{list(LATE_TIMES)}")
    print(f"    W = 1:  I_sat = {erg['mean_I_sat']:.6f} (std "
          f"{erg['std_I_sat']:.6f}) | near zero within stated "
          f"tolerance {I_ERGODIC_TOL} (finite-size residual, not zero)")
    print(f"    W = 12: I_sat = {loc['mean_I_sat']:.6f} (std "
          f"{loc['std_I_sat']:.6f}) | the Neel pattern largely survives")
    print(f"    margin I_sat(W=12) - I_sat(W=1) = "
          f"{loc['mean_I_sat'] - erg['mean_I_sat']:.6f} "
          f"(stated >= {I_MARGIN})")
    print("\n[6] Phase classifier (TinyML kNN, labels from the lab policy)")
    for name, row in classifier_report().items():
        print(f"    {name:16s} W = {row['W']:<5g} features "
              f"{row['features']} -> {row['knn']}")
    print("\n[7] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[8] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "levels":
        print(json.dumps(levels_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "entropy":
        print(json.dumps(entropy_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "imbalance":
        print(json.dumps(imbalance_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "sweep":
        print(json.dumps(sweep_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "thermodynamic_limit_claim"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
