import tempfile
import time
import unittest
from pathlib import Path

from app import security as s


class Passwords(unittest.TestCase):
    def test_hash_and_verify(self):
        h = s.hash_password("a very long passphrase")
        self.assertTrue(h.startswith("scrypt$"))
        self.assertTrue(s.verify_password("a very long passphrase", h))
        self.assertFalse(s.verify_password("a very long passphrasE", h))
        self.assertNotEqual(h, s.hash_password("a very long passphrase"))   # random salt

    def test_garbage_hash(self):
        self.assertFalse(s.verify_password("x", "not-a-hash"))

    def test_policy(self):
        self.assertTrue(s.password_problems("short"))
        self.assertTrue(s.password_problems("armin-is-my-password", "armin"))
        self.assertFalse(s.password_problems("purple-tram-garden-42"))


class Totp(unittest.TestCase):
    SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"

    def test_rfc6238_vector(self):
        # RFC 6238 test vector (SHA1, secret "12345678901234567890", T=59 → 94287082 → last 6 digits)
        import base64
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(s.totp_now(secret, at=59), "287082")

    def test_verify_and_replay(self):
        now = time.time()
        code = s.totp_now(self.SECRET, at=now)
        counter = s.verify_totp(self.SECRET, code, 0, at=now)
        self.assertIsNotNone(counter)
        self.assertIsNone(s.verify_totp(self.SECRET, code, counter, at=now))   # replay blocked
        self.assertIsNone(s.verify_totp(self.SECRET, "000000" if code != "000000" else "111111", 0, at=now))
        self.assertIsNone(s.verify_totp(self.SECRET, "12345", 0, at=now))


class Limits(unittest.TestCase):
    def test_rate_limiter(self):
        with tempfile.TemporaryDirectory() as d:
            rl = s.RateLimiter(Path(d) / "db.sqlite")
            for _ in range(5):
                self.assertFalse(rl.blocked("k", 5, 60))
                rl.hit("k")
            self.assertTrue(rl.blocked("k", 5, 60))
            rl.clear("k")
            self.assertFalse(rl.blocked("k", 5, 60))
