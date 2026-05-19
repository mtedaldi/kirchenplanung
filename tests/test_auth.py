"""
Tests für Authentifizierung: Passwort-Hashing, JWT, Stärkeprüfung.
"""
import pytest
from jose import JWTError

from app.auth import (
    check_password_strength,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "KircheHerisau2026!"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("richtig")
        assert not verify_password("falsch", hashed)

    def test_hash_is_not_plaintext(self):
        pw = "geheim"
        assert hash_password(pw) != pw


class TestPasswordStrength:
    def test_strong_password_passes(self):
        result = check_password_strength("KircheHerisau2026!")
        assert result["ok"] is True
        assert result["score"] >= 3

    def test_weak_password_fails(self):
        result = check_password_strength("passwort")
        assert result["ok"] is False

    def test_common_password_fails(self):
        result = check_password_strength("password123")
        assert result["ok"] is False


class TestJWT:
    def test_access_token_roundtrip(self):
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        roles = ["requester", "approver"]
        token = create_access_token(user_id, roles)
        payload = decode_access_token(token)
        assert payload["sub"] == user_id
        assert payload["roles"] == roles
        assert payload["type"] == "access"

    def test_refresh_token_roundtrip(self):
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        token = create_refresh_token(user_id)
        payload = decode_refresh_token(token)
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"

    def test_wrong_token_type_rejected(self):
        user_id = "123e4567-e89b-12d3-a456-426614174000"
        # Refresh-Token als Access-Token verwenden → Fehler
        refresh = create_refresh_token(user_id)
        with pytest.raises(JWTError):
            decode_access_token(refresh)

    def test_invalid_token_rejected(self):
        with pytest.raises(JWTError):
            decode_access_token("das.ist.kein.token")
