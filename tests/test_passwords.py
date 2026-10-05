import hashlib

from passwords import hash_password, needs_upgrade, verify_password


def test_new_hashes_are_salted_and_verify():
    first = hash_password("secret123")
    second = hash_password("secret123")
    assert first != second  # random salt, so identical passwords hash differently
    assert verify_password(first, "secret123")
    assert not verify_password(first, "wrong-password")
    assert not needs_upgrade(first)


def test_legacy_sha256_hash_still_verifies_and_needs_upgrade():
    legacy = hashlib.sha256(b"oldpass").hexdigest()
    assert verify_password(legacy, "oldpass")
    assert not verify_password(legacy, "nope")
    assert needs_upgrade(legacy)
