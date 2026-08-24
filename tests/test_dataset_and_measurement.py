import numpy as np
import pytest

from uvpd.dataset import DARK, LIGHT, Dataset, suggest_filename
from uvpd.instrument import SmuConfig
from uvpd.measurement import SampleInfo, SweepConfig, TransientConfig, run_sweep, run_transient
from uvpd.simulator import SimulatedKeithley2636


def test_dataset_roundtrip(tmp_path):
    ds = Dataset(name="ZnO-1", kind="iv", light_state=LIGHT, wavelength_nm=365.0,
                 optical_power_w=1.5e-6, area_cm2=0.04, notes="deneme")
    for k in range(5):
        ds.append(k * 0.1, k * 0.5, k * 1e-9)
    path = ds.to_csv(tmp_path / "test.csv")
    back = Dataset.from_csv(path)
    assert back.name == "ZnO-1"
    assert back.light_state == LIGHT
    assert back.wavelength_nm == 365.0
    assert back.optical_power_w == pytest.approx(1.5e-6)
    assert back.notes == "deneme"
    assert np.allclose(back.v, ds.v)
    assert np.allclose(back.i, ds.i)
    assert len(back) == 5


def test_effective_power_from_irradiance():
    ds = Dataset(irradiance_w_cm2=1e-4, area_cm2=0.5)
    assert ds.effective_power_w() == pytest.approx(5e-5)
    ds2 = Dataset()
    assert ds2.effective_power_w() is None


def test_suggest_filename_is_safe():
    ds = Dataset(name="numune 1/2", light_state=DARK, kind="iv")
    name = suggest_filename(ds, "/tmp")
    assert name.endswith(".csv")
    assert "/" not in name.split("/tmp/")[1]


def test_sweep_levels_dual():
    cfg = SweepConfig(start=-1, stop=1, points=5, dual=True)
    lv = cfg.levels()
    assert len(lv) == 9
    assert lv[0] == -1 and lv[4] == 1 and lv[-1] == -1
    assert cfg.step == pytest.approx(0.5)


def test_run_sweep_with_simulator():
    inst = SimulatedKeithley2636()
    inst.connect()
    smu = SmuConfig(source_func="voltage", compliance=1e-3)
    cfg = SweepConfig(start=-1.0, stop=1.0, points=21, settle_time=0.0, hold_time=0.0)
    ds = run_sweep(inst, smu, cfg, SampleInfo(name="sim", light_state=DARK))
    assert len(ds) == 21
    assert ds.v.min() < -0.9 and ds.v.max() > 0.9
    # ileri beslemede akim ters besleme akimindan buyuk olmali
    assert abs(ds.i[-1]) > abs(ds.i[0])


def test_run_sweep_dark_vs_light_photocurrent():
    inst = SimulatedKeithley2636()
    inst.connect()
    inst.noise_floor = 0.0
    smu = SmuConfig(source_func="voltage", compliance=1e-3)
    cfg = SweepConfig(start=-1.0, stop=0.0, points=11, settle_time=0.0, hold_time=0.0)

    inst.set_uv(False)
    dark = run_sweep(inst, smu, cfg, SampleInfo(name="sim", light_state=DARK))
    inst.set_uv(True)
    inst._photo_state = 1.0
    inst._uv_changed_at -= 10.0  # gecis tamamlanmis kabul et
    light = run_sweep(inst, smu, cfg, SampleInfo(name="sim", light_state=LIGHT,
                                                 wavelength_nm=365.0,
                                                 optical_power_w=2e-6))
    from uvpd.analysis import compare
    c = compare(dark, light)
    # UV altinda ters bias akimi (negatif yonde) buyumeli
    assert np.nanmean(c.i_photo) < 0
    assert abs(np.nanmean(c.i_photo)) == pytest.approx(
        inst.responsivity * inst.optical_power, rel=0.1)


def test_run_sweep_stop_callback():
    inst = SimulatedKeithley2636()
    inst.connect()
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 5

    ds = run_sweep(inst, SmuConfig(), SweepConfig(points=50, settle_time=0.0, hold_time=0.0),
                   SampleInfo(), should_stop=should_stop)
    assert 0 < len(ds) < 50


def test_run_transient_with_auto_cycle():
    inst = SimulatedKeithley2636()
    inst.connect()
    inst.rise_tau = inst.fall_tau = 0.05
    events = []
    cfg = TransientConfig(bias=-1.0, duration=1.2, interval=0.02, hold_time=0.0,
                          cycle_enabled=True, cycle_delay=0.3,
                          cycle_on=0.3, cycle_off=0.3)
    ds = run_transient(inst, SmuConfig(compliance=1e-3), cfg,
                       SampleInfo(light_state=LIGHT),
                       light_control=lambda on: inst.set_uv(on),
                       light_events=events)
    assert len(ds) > 30
    assert "light_events" in ds.settings
    assert ds.settings["light_events"][0][1] == 1
    assert ds.kind == "transient"
    # isik acikken akim buyumeli
    assert np.abs(ds.i).max() > np.abs(ds.i[:5]).max()
