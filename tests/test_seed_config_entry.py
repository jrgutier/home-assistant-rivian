"""The devcontainer seeder writes credentials into HA's .storage by hand.

Two things can go wrong and both are expensive. It can write a shape Home
Assistant will not load, which costs a container rebuild to discover. Or it can
leak a credential -- into stdout, into a world-readable file, or into a path that
is not gitignored.

The shape test is deliberately built against homeassistant.config_entries.ConfigEntry
itself rather than a copy of its field list, so an HA upgrade that changes the
schema fails here instead of at boot. That is the exact hazard the pin in
requirements.txt exists for: a .storage written for one HA version and read by
another.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent

# Not importable as a package -- scripts/ has no __init__.py and is not on the path.
_spec = importlib.util.spec_from_file_location(
    "seed_config_entry", REPO / "scripts" / "seed_config_entry.py"
)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

# Values are shaped like the real ones (long opaque strings) but are not real.
FAKE_ENV = """
RIVIAN_USERNAME=someone@example.invalid
RIVIAN_ACCESS_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
RIVIAN_REFRESH_TOKEN=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
RIVIAN_USER_SESSION_TOKEN=cccccccccccccccccccccccccccccccccccccccc
RIVIAN_PUBLIC_KEY=dddddddddddddddddddddddddddddddddddddddd
RIVIAN_PRIVATE_KEY=eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
RIVIAN_VEHICLE_CONTROL_DEVICES=0123456789abcdef0123456789abcdef
RIVIAN_VEHICLE_ID=01-276948064
"""
SECRETS = [
    line.split("=", 1)[1]
    for line in FAKE_ENV.strip().splitlines()
    if line.split("=", 1)[0] != "RIVIAN_USERNAME"
]


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(FAKE_ENV)
    return path


def run(env_file: Path, config: Path, *extra: str) -> int:
    argv = ["seed", "--env", str(env_file), "--config", str(config), *extra]
    old, sys.argv = sys.argv, argv
    try:
        return seed.main()
    finally:
        sys.argv = old


def read_entry(config: Path) -> dict:
    blob = json.loads((config / ".storage" / "core.config_entries").read_text())
    return next(e for e in blob["data"]["entries"] if e["domain"] == "rivian")


class TestHomeAssistantWillLoadIt:
    def test_the_entry_constructs_as_a_real_config_entry(
        self, env_file: Path, tmp_path: Path
    ) -> None:
        """The point of the whole script. Built against HA's own class so an HA
        schema change fails here, not on the next container boot."""
        from homeassistant.config_entries import ConfigEntry, ConfigEntryState

        run(env_file, tmp_path / "config")
        entry = read_entry(tmp_path / "config")

        # HA's store maps subentries -> subentries_data and supplies state itself.
        kwargs = {k: v for k, v in entry.items() if k != "subentries"}
        kwargs["subentries_data"] = entry["subentries"]
        kwargs["state"] = ConfigEntryState.NOT_LOADED
        built = ConfigEntry(**kwargs)

        assert built.domain == "rivian"
        assert built.title == "Rivian (Unofficial)"

    def test_it_carries_every_field_the_integration_reads(
        self, env_file: Path, tmp_path: Path
    ) -> None:
        """config_flow writes data in _async_create_entry and options in
        validate_vehicle_control; an entry missing either is loadable but inert."""
        run(env_file, tmp_path / "config")
        entry = read_entry(tmp_path / "config")

        assert set(entry["data"]) == {
            "username",
            "access_token",
            "refresh_token",
            "user_session_token",
        }
        assert set(entry["options"]) == {
            "public_key",
            "private_key",
            "vehicle_control",
            "vehicle_image_style",
        }
        # A bare string here would make HA iterate it per character.
        assert entry["options"]["vehicle_control"] == [
            "0123456789abcdef0123456789abcdef"
        ]


class TestItDoesNotLeak:
    def test_no_secret_reaches_stdout(
        self, env_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(env_file, tmp_path / "config")
        out = capsys.readouterr().out
        for secret in SECRETS:
            assert secret not in out

    def test_the_missing_key_error_names_keys_not_values(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        partial = tmp_path / ".env"
        partial.write_text("RIVIAN_USERNAME=someone@example.invalid\n")
        with pytest.raises(SystemExit) as exc:
            run(partial, tmp_path / "config")
        message = str(exc.value)
        assert "RIVIAN_ACCESS_TOKEN" in message
        assert "aaaa" not in message

    def test_the_file_is_not_world_readable(
        self, env_file: Path, tmp_path: Path
    ) -> None:
        run(env_file, tmp_path / "config")
        mode = os.stat(tmp_path / "config" / ".storage" / "core.config_entries").st_mode
        assert not mode & stat.S_IRGRP
        assert not mode & stat.S_IROTH

    def test_both_ends_are_gitignored(self) -> None:
        """A seeded entry that can be committed is worse than no seeder at all."""
        ignored = (REPO / ".gitignore").read_text().splitlines()
        assert any(line.strip() in {".env", "/.env"} for line in ignored)
        assert any(line.strip() in {"config/", "/config/"} for line in ignored)


class TestRerunning:
    def test_it_refuses_to_clobber_without_force(
        self, env_file: Path, tmp_path: Path
    ) -> None:
        config = tmp_path / "config"
        run(env_file, config)
        with pytest.raises(SystemExit):
            run(env_file, config)

    def test_force_keeps_the_entry_id(self, env_file: Path, tmp_path: Path) -> None:
        """Device and entity registry rows reference entry_id. A fresh id on every
        reseed orphans every entity the user has renamed or automated."""
        config = tmp_path / "config"
        run(env_file, config)
        first = read_entry(config)["entry_id"]
        run(env_file, config, "--force")
        assert read_entry(config)["entry_id"] == first

    def test_entries_for_other_domains_survive(
        self, env_file: Path, tmp_path: Path
    ) -> None:
        config = tmp_path / "config"
        (config / ".storage").mkdir(parents=True)
        (config / ".storage" / "core.config_entries").write_text(
            json.dumps(
                {
                    "version": 1,
                    "minor_version": 5,
                    "key": "core.config_entries",
                    "data": {"entries": [{"domain": "sun", "entry_id": "keepme"}]},
                }
            )
        )
        run(env_file, config)
        blob = json.loads((config / ".storage" / "core.config_entries").read_text())
        domains = {e["domain"] for e in blob["data"]["entries"]}
        assert domains == {"sun", "rivian"}


class TestEnvParsing:
    def test_quotes_are_stripped(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            FAKE_ENV.replace("RIVIAN_PRIVATE_KEY=e", 'RIVIAN_PRIVATE_KEY="e')
        )
        # closing quote
        text = env.read_text().replace("eeee\n", 'eeee"\n')
        env.write_text(text)
        run(env, tmp_path / "config")
        assert not read_entry(tmp_path / "config")["options"]["private_key"].startswith(
            '"'
        )

    def test_comments_and_blanks_are_skipped(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("# a comment\n\n" + FAKE_ENV)
        run(env, tmp_path / "config")
        assert read_entry(tmp_path / "config")["data"]["username"] == (
            "someone@example.invalid"
        )

    def test_a_missing_env_file_is_a_clear_error(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            run(tmp_path / "nope.env", tmp_path / "config")
        assert "not found" in str(exc.value)
