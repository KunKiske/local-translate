from pathlib import Path
import pytest
from translator.dictionary import DATA_FILE, Dictionary, senses, split_gloss


def test_pos_parsing_uses_dictionary_labels():
    assert list(senses("n. 银行; 岸\\nvt. 存款\\n[网络] 未分类")) == [
        ("名词", "银行; 岸"), ("及物动词", "存款"), ("词性未标注", "[网络] 未分类")]
    assert list(split_gloss("覆盖, 使(马,鹰等)戴头罩; 围住")) == ["覆盖", "使(马,鹰等)戴头罩", "围住"]


@pytest.mark.skipif(not DATA_FILE.exists(), reason="Run scripts/build_dictionary.py first")
def test_offline_bidirectional_multiple_senses_and_no_match():
    dictionary = Dictionary()
    bank = dictionary.lookup("BANK")
    assert len(bank) > 1
    assert any(c["name"] == "银行" and "名词" in c["label"] for c in bank)
    speed = dictionary.lookup("速度")
    assert len(speed) > 1
    assert any(c["name"] == "speed" for c in speed)
    assert all("速度" in c["detail"] for c in speed)
    assert dictionary.lookup("zzzznonexistentword") == []
    assert dictionary.lookup("\" OR *") == []
    with pytest.raises(InterruptedError):
        dictionary.lookup("bank", lambda: True)
    with pytest.raises(ValueError, match="80"):
        dictionary.lookup("x" * 81)


def test_dictionary_missing_file_is_clear(tmp_path):
    with pytest.raises(ValueError, match="离线词典"):
        Dictionary(tmp_path / "missing.db").lookup("bank")
