from test_providers import BrokenFingerprint, FakeFingerprint, FakeProvider

from framewise.providers import resolve_analyzer


def session_providers(review, providers, config_path=None) -> dict:
    analyzer = resolve_analyzer(config_path, providers=providers)
    return review(provider_lineup=analyzer.provider_lineup).get("/api/session").json()["providers"]


def test_the_session_names_the_provider_picked_automatically_for_a_capability(review):
    providers = session_providers(
        review,
        [
            FakeFingerprint(id="low", priority=1),
            FakeFingerprint(id="top", priority=5, version=3),
        ],
    )

    assert providers["fingerprint"]["active"] == {
        "id": "top",
        "version": 3,
        "source": "automatic",
    }


def test_the_session_names_the_provider_chosen_in_the_config(review, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[providers]\nfingerprint = "low"\n')

    providers = session_providers(
        review,
        [FakeFingerprint(id="low", priority=1), FakeFingerprint(id="top", priority=5)],
        config_path=config,
    )

    assert providers["fingerprint"]["active"] == {"id": "low", "version": 1, "source": "config"}


def test_an_optional_capability_without_a_provider_has_none_in_use(review):
    providers = session_providers(
        review,
        [FakeFingerprint(), FakeProvider(capability="eye-state", id="dozy", available=False)],
    )

    assert providers["eye-state"]["active"] is None


def test_the_session_lists_every_capability_in_the_fixed_order(review):
    providers = session_providers(review, [FakeFingerprint()])

    assert list(providers) == [
        "fingerprint",
        "face-detection",
        "eye-state",
        "face-quality",
        "expression",
        "aesthetics",
        "subject",
    ]


def test_the_session_lists_the_alternatives_in_descending_priority(review):
    providers = session_providers(
        review,
        [
            FakeFingerprint(id="low", priority=1, version=2),
            FakeFingerprint(id="top", priority=9),
            FakeFingerprint(id="elsewhere", priority=5, available=False),
        ],
    )

    assert providers["fingerprint"]["alternatives"] == [
        {"id": "elsewhere", "version": 1, "available": False},
        {"id": "low", "version": 2, "available": True},
    ]


def test_an_alternative_whose_availability_check_raises_is_listed_as_unavailable(review):
    providers = session_providers(
        review, [FakeFingerprint(id="fallback"), BrokenFingerprint(id="broken", version=4)]
    )

    assert providers["fingerprint"]["alternatives"] == [
        {"id": "broken", "version": 4, "available": False}
    ]


def test_the_session_gives_the_config_path_whether_or_not_the_file_exists(review, tmp_path):
    config = tmp_path / "missing" / "config.toml"

    session = review(config_path=config).get("/api/session").json()

    assert session["config_path"] == str(config)


def test_a_provider_whose_availability_check_raises_is_warned_about_once(review, capsys):
    session_providers(review, [FakeFingerprint(id="fallback"), BrokenFingerprint(id="broken")])

    assert capsys.readouterr().err.count("skipped the Provider broken") == 1
