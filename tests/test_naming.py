import re
from pathlib import Path

import pytest

from translator.config import Settings
from translator.engine import TranslationEngine
from translator.naming import STYLES, RESERVED, clean_request, generate_names, suggest


class NoTranslation:
    def translate(self, *args):
        raise AssertionError("Known development terms and English should not need translation")


@pytest.mark.parametrize("style,expected", [
    ("camel", "playerMoveSpeed"), ("pascal", "PlayerMoveSpeed"),
    ("private", "_playerMoveSpeed"), ("snake", "player_move_speed"),
    ("constant", "PLAYER_MOVE_SPEED"),
])
def test_code_styles_and_distinct_candidates(style, expected):
    result = generate_names(NoTranslation(), "玩家移动速度", style, Settings())
    assert result[0]["name"] == expected
    assert len(result) >= 3
    assert len({c["name"] for c in result}) == len(result)


@pytest.mark.parametrize("text,expected", [
    ("用于记录玩家最大生命值的字段", "playerMaxHealth"),
    ("最大重试次数", "maxRetryCount"),
    ("用于管理订单缓存的类", "orderCacheManager"),
    ("用户名称", "userName"),
    ("玩家是否死亡", "isPlayerDead"),
    ("HTTPServerURL", "httpServerUrl"),
])
def test_short_description_meaning(text, expected):
    assert generate_names(NoTranslation(), text, "camel", Settings())[0]["name"] == expected


def test_unknown_chinese_uses_local_model_and_checks_cancellation():
    calls = []
    class Model:
        def translate(self, text, direction, settings, cancelled):
            calls.append((text, direction))
            return "Astronomy observation data panel"
    result = generate_names(Model(), "天文观测数据面板", "pascal", Settings())
    assert calls == [("天文观测数据面板", "zh-en")]
    assert result[0]["name"] == "AstronomyObservationDataPanel"
    with pytest.raises(InterruptedError):
        generate_names(Model(), "天文观测数据面板", "pascal", Settings(), lambda: True)


def test_reserved_words_numbers_and_negation():
    for _, style in STYLES:
        for text in ("class", "123 cache entries", "HTTP server URL", "not enabled"):
            for candidate in suggest(text, style):
                name = candidate["name"]
                assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                assert name not in RESERVED
        assert "not" in suggest("not enabled", style)[0]["name"].lower()
    assert suggest("speed of the player", "camel")[0]["name"] == "playerSpeed"


def test_empty_and_long_description():
    with pytest.raises(ValueError):
        generate_names(NoTranslation(), "", "camel", Settings())
    with pytest.raises(ValueError):
        generate_names(NoTranslation(), "😀", "camel", Settings())
    with pytest.raises(ValueError, match="300"):
        clean_request("长" * 301)


@pytest.mark.skipif(not Path(Settings().model_path).is_dir(), reason="Local model not installed")
def test_real_model_fallback_for_naming():
    names = generate_names(TranslationEngine(), "天文观测数据面板", "pascal", Settings())
    assert len(names) >= 2
    assert all(re.fullmatch(r"[A-Z][a-zA-Z0-9]*", name["name"]) for name in names)
