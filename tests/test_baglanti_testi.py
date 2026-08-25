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
