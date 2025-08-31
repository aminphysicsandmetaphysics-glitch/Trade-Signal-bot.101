from profiles import ChannelProfile, ProfileStore


def test_profile_crud(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    profile = ChannelProfile(
        id="p1",
        name="Profile 1",
        parse_options={"lang": "en"},
        member_channels=["channel_a", "channel_b"],
        templates={"welcome": "hello"},
        destinations=["dest_a"]
    )

    store.create_profile(profile)
    loaded = store.get_profile("p1")
    assert loaded == profile

    store.update_profile("p1", name="Updated")
    assert store.get_profile("p1").name == "Updated"

    assert store.delete_profile("p1") is True
    assert store.get_profile("p1") is None
