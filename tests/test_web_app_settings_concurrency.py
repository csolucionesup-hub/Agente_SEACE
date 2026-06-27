"""Concurrency tests for settings persistence (lock + atomic write)."""

from __future__ import annotations

import threading

from web_app import _unique_text_list, load_settings, update_settings


def test_update_settings_concurrent_no_lost_updates(tmp_path):
    """25 concurrent dismisses must all persist; without the lock some would be lost."""
    path = tmp_path / "client_settings.json"

    def add_ocid(ocid: str) -> None:
        def _mutate(settings):
            settings["ignored_ocids"] = _unique_text_list([*(settings.get("ignored_ocids") or []), ocid])
            return settings

        update_settings(_mutate, path)

    threads = [threading.Thread(target=add_ocid, args=(f"ocid-{index}",)) for index in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    final = load_settings(path)
    persisted = {item for item in final["ignored_ocids"] if item.startswith("ocid-")}
    assert persisted == {f"ocid-{index}" for index in range(25)}


def test_atomic_write_leaves_valid_json_and_no_temp_files(tmp_path):
    path = tmp_path / "client_settings.json"
    update_settings(lambda settings: {**settings, "client_name": "Concurrencia S.A.C."}, path)

    data = load_settings(path)
    assert data["client_name"] == "Concurrencia S.A.C."

    leftovers = [item.name for item in tmp_path.iterdir() if item.name.startswith(".settings-")]
    assert leftovers == []
