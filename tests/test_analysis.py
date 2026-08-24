import numpy as np
import pytest

from uvpd import analysis
from uvpd.dataset import DARK, LIGHT, Dataset


def make_ds(v, i, **kw):
    ds = Dataset(**kw)
    ds.t = np.arange(len(v), dtype=float)
    ds.v = np.asarray(v, dtype=float)
    ds.i = np.asarray(i, dtype=float)
    return ds


def test_photon_energy():
    # 365 nm -> ~3.40 eV
    assert analysis.photon_energy_ev(365.0) == pytest.approx(3.397, abs=0.01)
    assert analysis.photon_energy_ev(1239.84) == pytest.approx(1.0, abs=1e-3)


def test_compare_and_photocurrent():
    v = np.linspace(-1, 1, 21)
    dark = make_ds(v, 1e-12 * v, name="d", light_state=DARK)
    light = make_ds(v, 1e-12 * v + 5e-9, name="l", light_state=LIGHT)
    c = analysis.compare(dark, light)
    assert c.v.size == 21
    assert np.allclose(c.i_photo, 5e-9)
    at0 = c.at(0.0)
    assert at0["i_photo_A"] == pytest.approx(5e-9, rel=1e-6)


def test_compare_with_different_grids():
    dark = make_ds(np.linspace(-2, 2, 41), np.zeros(41))
    light = make_ds(np.linspace(-1, 1, 11), np.full(11, 2e-9))
    c = analysis.compare(dark, light)
    assert c.v.min() >= -1 and c.v.max() <= 1
    assert np.allclose(c.i_photo, 2e-9)


def test_detector_metrics():
    m = analysis.detector_metrics(i_dark=1e-9, i_light=101e-9,
                                  wavelength_nm=365.0, optical_power_w=1e-6,
                                  area_cm2=0.04, bias_v=1.0)
    assert m.i_photo == pytest.approx(100e-9)
    assert m.on_off_ratio == pytest.approx(101.0)
    # R = 100 nA / 1 uW = 0.1 A/W
    assert m.responsivity == pytest.approx(0.1)
    # EQE = R * E_ph(eV) = 0.1 * 3.397 -> %33.97
    assert m.eqe_percent == pytest.approx(33.97, abs=0.1)
    noise = np.sqrt(2 * analysis.Q_E * 1e-9)
    assert m.detectivity == pytest.approx(0.1 * np.sqrt(0.04) / noise, rel=1e-6)
    assert m.nep == pytest.approx(noise / 0.1, rel=1e-6)


def test_detector_metrics_without_power_warns():
    m = analysis.detector_metrics(i_dark=1e-9, i_light=2e-9)
    assert not np.isfinite(m.responsivity)
    assert any("Optik guc" in w for w in m.warnings)


def test_diode_parameters_recovers_ideality():
    n, i0, kt_q = 1.8, 1e-12, 1.380649e-23 * 300 / analysis.Q_E
    v = np.linspace(0.1, 0.5, 40)
    i = i0 * np.exp(v / (n * kt_q))
    p = analysis.diode_parameters(v, i, 0.1, 0.5, temperature_k=300.0)
    assert p["ideality"] == pytest.approx(n, rel=1e-3)
    assert p["i0"] == pytest.approx(i0, rel=1e-2)


def test_rectification_ratio():
    v = np.linspace(-1, 1, 101)
    i = np.where(v > 0, v * 1e-6, v * 1e-9)
    assert analysis.rectification_ratio(v, i, 1.0) == pytest.approx(1000.0, rel=1e-6)


def test_transient_metrics_square_wave():
    t = np.arange(0, 40, 0.01)
    tau = 0.2
    signal = np.zeros_like(t)
    state = 0.0
    on = (np.floor(t / 5) % 2 == 1)
    for k in range(1, t.size):
        target = 1.0 if on[k] else 0.0
        state = target + (state - target) * np.exp(-(t[k] - t[k - 1]) / tau)
        signal[k] = state
    i = 1e-9 + signal * 99e-9
    m = analysis.transient_metrics(t, i)
    assert m.on_off_ratio == pytest.approx(100.0, rel=0.05)
    # 10-90% suresi = tau * ln(9) ~ 2.197 * tau
    assert m.rise_time_s == pytest.approx(tau * np.log(9), rel=0.15)
    assert m.fall_time_s == pytest.approx(tau * np.log(9), rel=0.15)
    assert m.n_cycles >= 3


def test_light_spans():
    ds = make_ds(np.zeros(10), np.zeros(10))
    ds.t = np.linspace(0, 9, 10)
    ds.settings["light_events"] = [[2.0, 1], [5.0, 0], [7.0, 1]]
    spans = analysis.light_spans(ds)
    assert spans == [(2.0, 5.0), (7.0, 9.0)]


def test_subtract_generic():
    a = make_ds([0, 1, 2], [1e-9, 2e-9, 3e-9])
    b = make_ds([0, 1, 2], [1e-9, 1e-9, 1e-9])
    v, d = analysis.subtract(a, b)
    assert np.allclose(d, [0, 1e-9, 2e-9])
