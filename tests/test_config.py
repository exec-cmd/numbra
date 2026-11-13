from pathlib import Path

import pytest

from numbra.config import ConfigError, ConfigManager, ConfigPaths


def test_config_manager_creates_defaults(tmp_path: Path) -> None:
    manager = ConfigManager(ConfigPaths.from_root(tmp_path))
    settings = manager.load_or_create()
    assert settings.challenge.duration_minutes == 6
    assert settings.challenge.brackets is True
    assert {
        level.value: (profile.min_terms, profile.max_terms)
        for level, profile in settings.challenge.profiles.items()
    } == {"easy": (2, 3), "normal": (2, 6), "hard": (3, 8)}
    assert settings.language == "auto"
    paths = manager.paths
    assert all(p.exists() for p in (paths.main, paths.templates, paths.design))


@pytest.mark.parametrize("value", ["false", "true"])
def test_generation_brackets_can_be_configured(tmp_path: Path, value: str) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(f"[challenge]\n[generation]\nbrackets = {value}\n", encoding="utf-8")

    assert manager.load_or_create().challenge.brackets is (value == "true")


@pytest.mark.parametrize("value", ["1", '"yes"'])
def test_generation_brackets_rejects_non_boolean(tmp_path: Path, value: str) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(f"[challenge]\n[generation]\nbrackets = {value}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"numbra\.toml: generation\.brackets"):
        manager.load_or_create()


@pytest.mark.parametrize(
    ("level", "old_pair", "new_pair"),
    [
        ("easy", (2, 2), (2, 3)),
        ("normal", (2, 3), (2, 6)),
        ("hard", (3, 4), (3, 8)),
    ],
)
def test_old_default_term_pairs_map_without_rewriting(
    tmp_path: Path, level: str, old_pair: tuple[int, int], new_pair: tuple[int, int]
) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    original = (
        f"[challenge]\n[difficulties.{level}]\n"
        f"min_terms = {old_pair[0]}\nmax_terms = {old_pair[1]}\n"
    )
    paths.main.write_text(original, encoding="utf-8")

    profile = manager.load_or_create().challenge.profiles[level]

    assert (profile.min_terms, profile.max_terms) == new_pair
    assert paths.main.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("level", "max_terms", "new_pair"),
    [("easy", 2, (2, 3)), ("normal", 3, (2, 6)), ("hard", 4, (3, 8))],
)
def test_partial_old_term_pair_maps_after_fallback(
    tmp_path: Path, level: str, max_terms: int, new_pair: tuple[int, int]
) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        f"[challenge]\n[difficulties.{level}]\nmax_terms = {max_terms}\n", encoding="utf-8"
    )

    profile = manager.load_or_create().challenge.profiles[level]

    assert (profile.min_terms, profile.max_terms) == new_pair


def test_custom_term_pair_is_kept(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        "[challenge]\n[difficulties.normal]\nmin_terms = 3\nmax_terms = 4\n", encoding="utf-8"
    )

    profile = manager.load_or_create().challenge.profiles["normal"]

    assert (profile.min_terms, profile.max_terms) == (3, 4)


def test_ui_language_setting_and_validation(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    settings = manager.load_or_create()
    assert settings.language == "auto"
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace('language = "auto"', 'language = "ru"'),
        encoding="utf-8",
    )
    assert manager.load_or_create().language == "ru"
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace('language = "ru"', 'language = "de"'),
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigError, match=r"numbra\.toml: ui\.language must be one of auto, en, ru"
    ):
        manager.load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace('language = "de"', "other = true"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"unknown field ui\.other"):
        manager.load_or_create()


def test_config_without_ui_uses_auto(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace('\n[ui]\nlanguage = "auto"\n', "\n"),
        encoding="utf-8",
    )
    assert manager.load_or_create().language == "auto"


def test_unknown_toml_field_mentions_file_and_field(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text("[challenge]\nunknown = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"numbra\.toml.*challenge\.unknown"):
        manager.load_or_create()


def test_invalid_json_is_user_facing_error(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.templates.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="temps.json"):
        manager.load_or_create()


def test_new_difficulty_profiles_and_operation_timing_are_loaded(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.difficulty.value == "normal"
    assert settings.challenge.profiles["easy"].max_value == 20
    assert settings.challenge.profiles["hard"].max_value == 999
    assert settings.challenge.profiles["easy"].max_result == 400
    assert settings.challenge.profiles["hard"].max_result == 10_000
    assert settings.challenge.operation_timing.enabled is True
    assert settings.challenge.operation_timing.bonus_seconds["*"] == 1.0
    assert settings.challenge.features == {topic: False for topic in settings.challenge.features}
    assert settings.warnings == ()


def test_legacy_difficulty_maps_to_easy_and_warns_without_rewriting(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    text = paths.main.read_text(encoding="utf-8")
    paths.main.write_text(
        text.replace('difficulty = "normal"', 'difficulty = "very-easy"'), encoding="utf-8"
    )

    settings = manager.load_or_create()

    assert settings.challenge.difficulty.value == "easy"
    assert any("very-easy" in warning and "easy" in warning for warning in settings.warnings)
    assert 'difficulty = "very-easy"' in paths.main.read_text(encoding="utf-8")


def test_legacy_very_easy_profile_is_ignored_and_warned(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    with paths.main.open("a", encoding="utf-8") as file:
        file.write("\n[difficulties.very-easy]\nmax_value = 5\n")
    original = paths.main.read_text(encoding="utf-8")

    settings = manager.load_or_create()

    assert "very-easy" not in {level.value for level in settings.challenge.profiles}
    assert any("very-easy" in warning for warning in settings.warnings)
    assert paths.main.read_text(encoding="utf-8") == original


def test_legacy_very_hard_difficulty_maps_to_hard(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    text = paths.main.read_text(encoding="utf-8")
    paths.main.write_text(
        text.replace('difficulty = "normal"', 'difficulty = "very-hard"'), encoding="utf-8"
    )

    settings = manager.load_or_create()

    assert settings.challenge.difficulty.value == "hard"
    assert any(
        "numbra.toml" in warning and "'very-hard' is deprecated; using 'hard'" in warning
        for warning in settings.warnings
    )
    assert 'difficulty = "very-hard"' in paths.main.read_text(encoding="utf-8")


def test_legacy_very_hard_profile_is_ignored(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    with paths.main.open("a", encoding="utf-8") as file:
        file.write("\n[difficulties.very-hard]\nmax_value = 5\n")

    settings = manager.load_or_create()

    assert "very-hard" not in {level.value for level in settings.challenge.profiles}
    assert any(
        "difficulties.very-hard is deprecated and ignored" in warning
        for warning in settings.warnings
    )


def test_feature_flags_load_and_validate_with_filename_and_field(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace("sqrt = false", "sqrt = true"),
        encoding="utf-8",
    )

    settings = manager.load_or_create()

    assert {topic.value for topic, enabled in settings.challenge.features.items() if enabled} == {
        "sqrt",
    }
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace(
            "identities = false", "identities = false\nunknown = true"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"numbra\.toml.*features\.unknown"):
        manager.load_or_create()


def test_feature_flag_must_be_boolean(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace("sqrt = false", "sqrt = 1"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"numbra\.toml.*features\.sqrt.*boolean"):
        manager.load_or_create()


def test_operation_timing_can_be_disabled(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    ConfigManager(paths).load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace("enabled = true", "enabled = false"),
        encoding="utf-8",
    )
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.operation_timing.enabled is False


def test_operation_timing_disable_can_omit_bonus_table(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    ConfigManager(paths).load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace(
            '[timing]\noperation_bonus_enabled = true\n[timing.operation_bonus_seconds]\n"+" = 0\n"-" = 0\n"*" = 1\n"/" = 2\n"^" = 3\n',
            "[timing]\noperation_bonus_enabled = false\n",
        ),
        encoding="utf-8",
    )
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.operation_timing.enabled is False


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("[challenge]\nduration_minutes = true", "challenge.duration_minutes"),
        ("[challenge]\nduration_minutes = 1.9", "challenge.duration_minutes"),
        ('[challenge]\nstages = "3"', "challenge.stages"),
        ("[challenge]\nseed = false", "challenge.seed"),
        ('[challenge]\noperations = "+-"', "challenge.operations"),
        ('[challenge]\noperations = ["+", 1]', "challenge.operations"),
        ("stages = []\n[challenge]", "stages"),
        ("[challenge]\n[difficulties.typo]\nmax_result = 2", "difficulties.typo"),
        ("[challenge]\n[difficulties.easy]\nmin_value = true", "difficulties.easy.min_value"),
        ("[challenge]\n[difficulties.normal]\nmax_terms = 3.5", "difficulties.normal.max_terms"),
        ("[challenge]\n[stages.slow]\nlimit_seconds = true", "stages.slow.limit_seconds"),
        (
            '[challenge]\n[timing.operation_bonus_seconds]\n"+" = "1"',
            "timing.operation_bonus_seconds",
        ),
    ],
)
def test_invalid_config_types_report_filename_and_field(
    tmp_path: Path, text: str, field: str
) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError) as error:
        manager.load_or_create()

    assert paths.main.name in str(error.value)
    assert field in str(error.value)


@pytest.mark.parametrize(
    ("seed", "valid"),
    [(-(1 << 63), True), ((1 << 63) - 1, True), (-(1 << 63) - 1, False), (1 << 63, False)],
)
def test_config_seed_must_fit_sqlite_integer_range(tmp_path: Path, seed: int, valid: bool) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(f"[challenge]\nseed = {seed}\n", encoding="utf-8")

    if valid:
        assert manager.load_or_create().challenge.seed == seed
    else:
        with pytest.raises(ConfigError, match=r"numbra\.toml.*challenge\.seed"):
            manager.load_or_create()


@pytest.mark.parametrize("filename", ["numbra.toml", "temps.json", "design.toml"])
def test_invalid_file_encoding_is_a_config_error(tmp_path: Path, filename: str) -> None:
    manager = ConfigManager(ConfigPaths.from_root(tmp_path))
    manager.load_or_create()
    (tmp_path / filename).write_bytes(b"\xff")

    with pytest.raises(ConfigError, match=filename):
        manager.load_or_create()


def test_config_directory_creation_error_is_user_facing(tmp_path: Path) -> None:
    root = tmp_path / "blocked-config"
    root.write_text("a file occupies the directory", encoding="utf-8")

    with pytest.raises(ConfigError, match="blocked-config"):
        ConfigManager(ConfigPaths.from_root(root)).load_or_create()


def test_config_file_creation_error_mentions_filename(tmp_path: Path, monkeypatch) -> None:
    from pathlib import Path

    original = Path.open

    def deny_main_file(self, *args, **kwargs):
        if self.name == "numbra.toml":
            raise PermissionError("read-only config")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_main_file)

    with pytest.raises(ConfigError, match="numbra.toml"):
        ConfigManager(ConfigPaths.from_root(tmp_path)).load_or_create()


def test_config_without_tricks_key_loads_with_tricks_off(tmp_path: Path) -> None:
    from numbra.core.models import Topic

    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    text = paths.main.read_text(encoding="utf-8")
    assert "tricks = false\n" in text
    paths.main.write_text(text.replace("tricks = false\n", ""), encoding="utf-8")

    settings = manager.load_or_create()

    assert settings.challenge.features[Topic.TRICKS] is False
    assert settings.warnings == ()


def test_funbox_modes_load_in_canonical_order_and_reject_unknown(tmp_path: Path) -> None:
    from numbra.core.funbox import FunboxMode

    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    assert manager.load_or_create().challenge.funbox_modes == ()
    text = paths.main.read_text(encoding="utf-8")
    paths.main.write_text(
        text.replace("modes = []", 'modes = ["logic", "equations"]'), encoding="utf-8"
    )

    assert manager.load_or_create().challenge.funbox_modes == (
        FunboxMode.EQUATIONS,
        FunboxMode.LOGIC,
    )

    paths.main.write_text(text.replace("modes = []", 'modes = ["nope"]'), encoding="utf-8")
    with pytest.raises(ConfigError, match=r"numbra\.toml.*funbox\.modes.*nope"):
        manager.load_or_create()
