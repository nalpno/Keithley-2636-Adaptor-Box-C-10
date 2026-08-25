import uvpd.visa_diag as vd


def test_python_bits_is_sane():
    assert vd.python_bits() in (32, 64)


def test_module_version_known_and_unknown():
    assert vd.module_version("json") is not None
    assert vd.module_version("bu_paket_yok_12345") is None


def test_has_gpib_resource():
    assert vd.has_gpib_resource(["ASRL1::INSTR", "GPIB0::26::INSTR"])
    assert not vd.has_gpib_resource(["USB0::0x05E6::0x2636::1234::INSTR"])
    assert not vd.has_gpib_resource([])


def test_diagnose_report_has_sections(monkeypatch):
    monkeypatch.setattr(vd, "try_backend", lambda lib: (False, "ValueError: yok"))
    d = vd.diagnose()
    assert "=== SISTEM ===" in d.text
    assert "=== PAKETLER ===" in d.text
    assert "=== BACKEND DENEMELERI ===" in d.text
    assert d.suggestion
    # VISA yokken uc baglanti yolu da anlatilmali
    assert "USB" in d.suggestion and "LAN" in d.suggestion and "GPIB" in d.suggestion


def test_diagnose_recommends_pyvisa_py_when_it_sees_gpib(monkeypatch):
    def fake(lib):
        if lib == vd.BACKEND_PY:
            return True, ["GPIB0::26::INSTR"]
        return False, "ValueError: Could not locate a VISA implementation."

    monkeypatch.setattr(vd, "try_backend", fake)
    d = vd.diagnose()
    assert d.recommended_library == vd.BACKEND_PY
    assert d.working_resources == ["GPIB0::26::INSTR"]


def test_diagnose_recommends_system_visa_when_usb_device_present(monkeypatch):
    usb = "USB0::0x05E6::0x2636::4037576::INSTR"
    monkeypatch.setattr(vd, "try_backend",
                        lambda lib: (True, [usb]) if lib == vd.BACKEND_DEFAULT
                        else (False, "yok"))
    d = vd.diagnose()
    assert d.recommended_library == vd.BACKEND_DEFAULT
    assert usb in d.working_resources


def test_diagnose_reports_missing_pyvisa(monkeypatch):
    monkeypatch.setattr(vd, "module_version",
                        lambda name: None if name == "pyvisa" else None)
    monkeypatch.setattr(vd, "try_backend", lambda lib: (False, "pyvisa kurulu degil"))
    d = vd.diagnose()
    assert "pip install pyvisa" in d.suggestion


def test_try_backend_returns_error_for_bogus_library():
    ok, result = vd.try_backend("bu-kutuphane-yok.dll")
    assert ok is False
    assert isinstance(result, str)


def test_suggestion_when_system_visa_blind_but_pyvisapy_sees_gpib(monkeypatch):
    """NI-VISA calisiyor ama bos donuyor, @py cihazi goruyor (ADLINK durumu)."""
    def fake(lib):
        if lib == vd.BACKEND_PY:
            return True, ["GPIB0::26::INSTR"]
        return True, []

    monkeypatch.setattr(vd, "try_backend", fake)
    d = vd.diagnose()
    assert d.recommended_library == vd.BACKEND_PY
    assert d.working_resources == ["GPIB0::26::INSTR"]
    # sistem VISA'nin calistigi, ama adaptoru goremedigi dogru anlatilmali
    assert "yuklu ve calisiyor" in d.suggestion
    assert "ADLINK" in d.suggestion
    assert "@py" in d.suggestion
    assert "GPIB0::26::INSTR" in d.suggestion


def test_in_virtualenv_returns_bool():
    assert isinstance(vd.in_virtualenv(), bool)
