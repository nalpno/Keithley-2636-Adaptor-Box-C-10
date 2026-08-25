"""baglanti_testi.py konsol betiginin duman testi (simulasyon modunda)."""

import baglanti_testi as bt


def test_kaynak_sec_prefers_keithley():
    assert bt.kaynak_sec(["ASRL1::INSTR", "USB0::0x05E6::0x2636::123::INSTR"]) == \
        "USB0::0x05E6::0x2636::123::INSTR"
    assert bt.kaynak_sec(["ASRL1::INSTR", "GPIB0::26::INSTR"]) == "GPIB0::26::INSTR"
    assert bt.kaynak_sec(["ASRL1::INSTR"]) == "ASRL1::INSTR"
    assert bt.kaynak_sec([]) == ""


def test_main_simulate_without_measurement(capsys):
    assert bt.main(["--simulate"]) == 0
    out = capsys.readouterr().out
    assert "BAGLANDI" in out
    assert "Cikis acilmadi" in out


def test_main_simulate_with_measurement(capsys):
    assert bt.main(["--simulate", "--olcum"]) == 0
    out = capsys.readouterr().out
    assert "Olcum zinciri calisiyor" in out
    assert out.count("V_ayar") == 4
    assert "Cikis kapatildi" in out


def test_kaynaklari_bul_reports_visa_ok_with_no_devices(monkeypatch):
    """VISA yuklendi ama cihaz yok: visa_ok=True, liste bos."""
    monkeypatch.setattr(bt, "try_backend", lambda lib: (True, []))
    lib, kaynaklar, visa_ok = bt.kaynaklari_bul("")
    assert visa_ok is True
    assert kaynaklar == []


def test_kaynaklari_bul_reports_visa_missing(monkeypatch):
    monkeypatch.setattr(bt, "try_backend", lambda lib: (False, "ValueError: yok"))
    lib, kaynaklar, visa_ok = bt.kaynaklari_bul("")
    assert visa_ok is False
    assert kaynaklar == []


def test_main_device_missing_prints_device_checklist(monkeypatch, capsys):
    monkeypatch.setattr(bt, "try_backend", lambda lib: (True, []))
    assert bt.main([]) == 1
    out = capsys.readouterr().out
    assert "VISA katmani CALISIYOR" in out
    assert "Aygit Yoneticisi" in out
    assert "Keithley Communicator" in out


def test_main_visa_missing_prints_visa_message(monkeypatch, capsys):
    monkeypatch.setattr(bt, "try_backend", lambda lib: (False, "ValueError: yok"))
    assert bt.main([]) == 1
    out = capsys.readouterr().out
    assert "VISA katmani yuklenemedi" in out
    assert "uvpd.visa_diag" in out


def test_main_manual_resource_is_tried_even_when_scan_empty(monkeypatch, capsys):
    """Tarama bos donse bile --kaynak ile verilen adres denenmeli."""
    monkeypatch.setattr(bt, "try_backend", lambda lib: (True, []))
    rc = bt.main(["--kaynak", "USB0::0x05E6::0x2636::123::INSTR"])
    out = capsys.readouterr().out
    assert "verilen adres dogrudan denenecek" in out
    assert "Cihaza baglaniliyor" in out
    assert rc == 1          # gercek cihaz yok, baglanti basarisiz olmali
