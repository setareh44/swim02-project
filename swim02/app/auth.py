# -*- coding: utf-8 -*-
"""Role-based access control (RBAC) for Setargan-Darya: Admin + students.

Two roles:
  * ADMIN   (Setareh, director/master coach): one master password, full
    control - manage up to 50 students, see every athlete's analytics,
    upload videos, assign workout/meal plans, read the compliance inbox.
  * ATHLETE (student): unique username + personal password/PIN, sees only
    their own profile, plans, history, compliance tracker and quotes.

Secrets:
  * digits-only secrets of 4-12 chars are treated as a PIN (quick login);
  * anything else is a password (min 6 ASCII chars).
  Both are stored ONLY as PBKDF2-HMAC-SHA256 hashes with a per-secret
  random salt (200k iterations) + constant-time comparison.

The user database is written atomically (tmp file + os.replace) so a
crash can never leave a half-written JSON behind. All terminal output is
plain ASCII Finglish (Windows CMD compatible).

This module is Qt-free so the CLI tools and the test-suite can use it
without a display server.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import branding

STORE_VERSION = 2
USERS_FILE = "users.json"

# Academy capacity: Setareh coaches up to 50 students in this app.
MAX_ATHLETES = 50

# PBKDF2 cost: high enough to hurt brute force, low enough for instant login.
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16

MIN_ADMIN_PASSWORD_LEN = 8
MIN_PIN_LEN = 4
MAX_PIN_LEN = 12
MIN_PASSWORD_LEN = 6
MAX_SECRET_LEN = 64
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,24}$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def alog(msg: str = "") -> None:
    """Print strictly ASCII text (Finglish) for Windows CMD compatibility."""
    print(str(msg).encode("ascii", "replace").decode("ascii"))
    sys.stdout.flush()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir() -> str:
    """Writable per-user folder for the Setargan-Darya database.

    Overridable with SETARGAN_DATA_DIR (legacy SWIM_DATA_DIR still works).
    A previous SWIM-AI folder is migrated forward on first use.
    """
    return branding.user_data_dir()


class AuthError(ValueError):
    """Raised for any authentication / user-management problem."""


# ---------------------------------------------------------------------------
# roles and skill tiers
# ---------------------------------------------------------------------------
class UserRole:
    ADMIN = "admin"
    ATHLETE = "athlete"

    ALL = (ADMIN, ATHLETE)


SKILL_TIERS = ("beginner", "intermediate", "advanced", "pro")
SKILL_FA = {
    "beginner": "مبتدی",
    "intermediate": "متوسط",
    "advanced": "پیشرفته",
    "pro": "حرفه‌ای / مسابقاتی",
}
SKILL_FINGLISH = {
    "beginner": "mobtadi",
    "intermediate": "motevaset",
    "advanced": "pishrafte",
    "pro": "herfei/mosabeghati",
}


# ---------------------------------------------------------------------------
# password hashing (stdlib only)
# ---------------------------------------------------------------------------
class PasswordHasher:
    """PBKDF2-HMAC-SHA256 hashing with per-secret random salt."""

    @staticmethod
    def hash_secret(secret: str) -> Dict[str, str]:
        if not secret:
            raise AuthError("Ramz nemitavanad khali bashad.")
        salt = secrets.token_bytes(_SALT_BYTES)
        dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt,
                                 _PBKDF2_ITERATIONS)
        return {"hash": dk.hex(), "salt": salt.hex(),
                "iter": _PBKDF2_ITERATIONS, "algo": "pbkdf2-sha256"}

    @staticmethod
    def verify(secret: str, record: Optional[Dict]) -> bool:
        try:
            if not secret or not record:
                return False
            salt = bytes.fromhex(record["salt"])
            expect = bytes.fromhex(record["hash"])
            iters = int(record.get("iter", _PBKDF2_ITERATIONS))
            dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt,
                                     iters)
            return hmac.compare_digest(dk, expect)
        except (KeyError, ValueError, TypeError):
            return False


# ---------------------------------------------------------------------------
# user model
# ---------------------------------------------------------------------------
@dataclass
class User:
    user_id: str
    name: str
    role: str = UserRole.ATHLETE
    # NOTE: the storage key stays "pin_hash" for DB compatibility; since v2
    # it holds a PIN *or* password hash - see AuthService._check_secret.
    pin_hash: Dict[str, str] = field(default_factory=dict)
    username: str = ""
    age: int = 0
    experience_years: float = 0.0
    skill_tier: str = "beginner"
    created_at: str = ""
    last_login: str = ""
    active: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["age"] = int(d["age"])
        d["experience_years"] = float(d["experience_years"])
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in (data or {}).items() if k in known}
        user = cls(user_id=str(clean.get("user_id", "")),
                   name=str(clean.get("name", "")))
        for key, val in clean.items():
            if key in ("user_id", "name"):
                continue
            try:
                if key == "age":
                    setattr(user, key, int(val or 0))
                elif key == "experience_years":
                    setattr(user, key, float(val or 0.0))
                elif key == "active":
                    setattr(user, key, bool(val))
                elif key == "username":
                    setattr(user, key, str(val or "").strip().lower())
                else:
                    setattr(user, key, val)
            except (TypeError, ValueError):
                continue
        if user.role not in UserRole.ALL:
            user.role = UserRole.ATHLETE
        if user.skill_tier not in SKILL_TIERS:
            user.skill_tier = "beginner"
        if not user.username:
            # v1 databases had no username: fall back to the stable ID
            user.username = user.user_id.strip().lower()
        return user

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def display(self) -> str:
        return "%s (@%s)" % (self.name or self.user_id, self.username)


@dataclass
class Session:
    """An authenticated login session (in-memory only, never persisted)."""

    role: str
    user_id: str
    display_name: str
    login_at: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_athlete(self) -> bool:
        return self.role == UserRole.ATHLETE


# ---------------------------------------------------------------------------
# persistent store (atomic JSON)
# ---------------------------------------------------------------------------
class UserStore:
    """Loads / saves the user database with atomic writes."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(data_dir(), USERS_FILE)
        self._admin: Dict[str, str] = {}
        self._admin_set_on: str = ""
        self._users: Dict[str, User] = {}
        self._by_username: Dict[str, str] = {}
        self.load()

    # -- persistence ------------------------------------------------------
    def load(self) -> None:
        self._admin, self._admin_set_on, self._users = {}, "", {}
        self._by_username = {}
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            alog("Hoshdar: khandane database karbaran namovafagh bood.")
            return
        if not isinstance(data, dict):
            return
        admin = data.get("admin") or {}
        if isinstance(admin, dict):
            self._admin = {k: str(v) for k, v in admin.items()
                           if k in ("hash", "salt")}
            try:
                self._admin["iter"] = int(admin.get("iter", _PBKDF2_ITERATIONS))
            except (TypeError, ValueError):
                self._admin["iter"] = _PBKDF2_ITERATIONS
            self._admin["algo"] = "pbkdf2-sha256"
            self._admin_set_on = str(admin.get("set_on", ""))
        users = data.get("users") or []
        if isinstance(users, list):
            for item in users:
                if isinstance(item, dict) and item.get("user_id"):
                    user = User.from_dict(item)
                    self._users[user.user_id] = user
        self._reindex()

    def _reindex(self) -> None:
        self._by_username = {u.username: u.user_id
                             for u in self._users.values() if u.username}

    def save(self) -> None:
        folder = os.path.dirname(self.path) or "."
        os.makedirs(folder, exist_ok=True)
        payload = {
            "version": STORE_VERSION,
            "admin": dict(self._admin, set_on=self._admin_set_on),
            "users": [u.to_dict() for u in self._users.values()],
        }
        fd, tmp = tempfile.mkstemp(prefix="users_", suffix=".json",
                                   dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    # -- admin secret -----------------------------------------------------
    @property
    def admin_record(self) -> Dict[str, str]:
        return dict(self._admin)

    @property
    def admin_set_on(self) -> str:
        return self._admin_set_on

    def set_admin(self, record: Dict[str, str]) -> None:
        self._admin = dict(record)
        self._admin_set_on = utcnow_iso()
        self.save()

    # -- users ------------------------------------------------------------
    def get(self, user_id: str) -> Optional[User]:
        return self._users.get(str(user_id).strip())

    def get_by_username(self, username: str) -> Optional[User]:
        uid = self._by_username.get(str(username or "").strip().lower())
        return self._users.get(uid) if uid else None

    def get_by_login(self, login: str) -> Optional[User]:
        """Find an athlete by ID *or* username (case-insensitive)."""
        login = str(login or "").strip()
        return self.get(login) or self.get_by_username(login)

    def count_athletes(self) -> int:
        return sum(1 for u in self._users.values()
                   if u.role == UserRole.ATHLETE)

    def all(self, role: Optional[str] = None,
            active_only: bool = False) -> List[User]:
        out = list(self._users.values())
        if role is not None:
            out = [u for u in out if u.role == role]
        if active_only:
            out = [u for u in out if u.active]
        return sorted(out, key=lambda u: u.user_id)

    def put(self, user: User) -> None:
        self._users[user.user_id] = user
        self._reindex()
        self.save()

    def remove(self, user_id: str) -> bool:
        if str(user_id) in self._users:
            del self._users[str(user_id)]
            self._reindex()
            self.save()
            return True
        return False

    def next_athlete_id(self) -> str:
        best = 0
        for uid in self._users:
            if uid.startswith("ATH-"):
                try:
                    best = max(best, int(uid[4:]))
                except ValueError:
                    continue
        return "ATH-%04d" % (best + 1)


# ---------------------------------------------------------------------------
# high-level service
# ---------------------------------------------------------------------------
class AuthService:
    """All authentication and user-management operations."""

    def __init__(self, store: Optional[UserStore] = None):
        self.store = store or UserStore()

    # -- admin ------------------------------------------------------------
    def is_admin_setup(self) -> bool:
        rec = self.store.admin_record
        return bool(rec.get("hash") and rec.get("salt"))

    def _check_admin_password(self, password: str) -> str:
        pw = (password or "").strip()
        if len(pw) < MIN_ADMIN_PASSWORD_LEN:
            raise AuthError(
                "Ramz-e modir bayad hadaghal %d karakter bashad."
                % MIN_ADMIN_PASSWORD_LEN)
        try:
            pw.encode("ascii")
        except UnicodeEncodeError:
            raise AuthError("Ramz-e modir bayad faghat ASCII bashad.")
        return pw

    def setup_admin(self, password: str) -> None:
        """Define the master password (first run only)."""
        if self.is_admin_setup():
            raise AuthError("Ramz-e modir ghablan tanzim shode ast.")
        pw = self._check_admin_password(password)
        self.store.set_admin(PasswordHasher.hash_secret(pw))
        alog("Ramz-e modir (master password) ba movafaghiyat tanzim shod.")

    def verify_admin(self, password: str) -> bool:
        return PasswordHasher.verify((password or "").strip(),
                                     self.store.admin_record)

    def change_admin_password(self, old: str, new: str) -> None:
        if not self.is_admin_setup():
            raise AuthError("Ramz-e modir hanooz tanzim nashode ast.")
        if not self.verify_admin(old):
            raise AuthError("Ramz-e ghabli eshtebah ast.")
        pw = self._check_admin_password(new)
        self.store.set_admin(PasswordHasher.hash_secret(pw))
        alog("Ramz-e modir taghyir kard.")

    def login_admin(self, password: str) -> Session:
        if not self.is_admin_setup():
            raise AuthError("Ramz-e modir hanooz tanzim nashode ast.")
        if not self.verify_admin(password):
            raise AuthError("Ramz-e modir eshtebah ast.")
        alog("Vorood-e modir (admin) movafagh.")
        return Session(UserRole.ADMIN, "ADMIN", branding.ADMIN_NAME,
                       utcnow_iso())

    # -- athlete secrets --------------------------------------------------
    def _check_secret(self, secret: str) -> str:
        """Validate a student PIN (4-12 digits) or password (6+ ASCII)."""
        s = (secret or "").strip()
        if not s or len(s) > MAX_SECRET_LEN:
            raise AuthError("Ramz/PIN namotabar ast.")
        if s.isdigit():
            if not (MIN_PIN_LEN <= len(s) <= MAX_PIN_LEN):
                raise AuthError(
                    "PIN bayad %d ta %d ragham bashad."
                    % (MIN_PIN_LEN, MAX_PIN_LEN))
            return s
        if len(s) < MIN_PASSWORD_LEN:
            raise AuthError(
                "Password bayad hadaghal %d karakter bashad." % MIN_PASSWORD_LEN)
        try:
            s.encode("ascii")
        except UnicodeEncodeError:
            raise AuthError("Password bayad faghat ASCII bashad.")
        return s

    def _check_username(self, username: str,
                        ignore_id: str = "") -> str:
        uname = str(username or "").strip().lower()
        if not USERNAME_RE.match(uname):
            raise AuthError(
                "Username bayad 3 ta 24 karakter (a-z, 0-9, ., _, -) bashad.")
        clash = self.store.get_by_username(uname)
        if clash is not None and clash.user_id != ignore_id:
            raise AuthError("In username ghablan gerefte shode ast.")
        return uname

    # -- athletes ---------------------------------------------------------
    def create_athlete(self, name: str, pin: str, age: int = 0,
                       experience_years: float = 0.0,
                       skill_tier: str = "beginner",
                       user_id: Optional[str] = None,
                       username: Optional[str] = None) -> User:
        name = (name or "").strip()
        if not name:
            raise AuthError("Nam-e shenagar nemitavanad khali bashad.")
        if skill_tier not in SKILL_TIERS:
            raise AuthError("Skill-tier namotabar ast: %s" % skill_tier)
        if self.store.count_athletes() >= MAX_ATHLETES:
            raise AuthError(
                "Zarfiyat takmil ast: hadaksar %d shagerd." % MAX_ATHLETES)
        uid = (user_id or "").strip() or self.store.next_athlete_id()
        if self.store.get(uid) is not None:
            raise AuthError("In shenase ghablan vojood darad: %s" % uid)
        uname = self._check_username(username or uid)
        user = User(
            user_id=uid, name=name, role=UserRole.ATHLETE,
            pin_hash=PasswordHasher.hash_secret(self._check_secret(pin)),
            username=uname,
            age=max(0, int(age or 0)),
            experience_years=max(0.0, float(experience_years or 0.0)),
            skill_tier=skill_tier, created_at=utcnow_iso(), active=True)
        self.store.put(user)
        alog("Shenagar-e jadid sakhte shod: %s (@%s)" % (uid, uname))
        return user

    def verify_athlete(self, login: str, pin: str) -> Optional[User]:
        user = self.store.get_by_login(login)
        if user is None or user.role != UserRole.ATHLETE or not user.active:
            return None
        if not PasswordHasher.verify((pin or "").strip(), user.pin_hash):
            return None
        return user

    def login_athlete(self, login: str, pin: str) -> Session:
        user = self.verify_athlete(login, pin)
        if user is None:
            raise AuthError("Username/shenase ya ramz eshtebah ast.")
        user.last_login = utcnow_iso()
        self.store.put(user)
        alog("Vorood-e shenagar movafagh: %s" % user.user_id)
        return Session(UserRole.ATHLETE, user.user_id, user.name,
                       utcnow_iso())

    def change_athlete_secret(self, user_id: str, old_secret: str,
                              new_secret: str) -> None:
        user = self.store.get(user_id)
        if user is None or user.role != UserRole.ATHLETE:
            raise AuthError("Shenagar peyda nashod: %s" % user_id)
        if not PasswordHasher.verify((old_secret or "").strip(),
                                     user.pin_hash):
            raise AuthError("Ramz-e ghabli eshtebah ast.")
        user.pin_hash = PasswordHasher.hash_secret(
            self._check_secret(new_secret))
        self.store.put(user)
        alog("Ramz-e shenagar taghyir kard: %s" % user_id)

    # backward-compatible alias (v1 API name)
    def change_athlete_pin(self, user_id: str, old_pin: str,
                           new_pin: str) -> None:
        self.change_athlete_secret(user_id, old_pin, new_pin)

    def admin_reset_secret(self, user_id: str, new_secret: str) -> None:
        """Coach resets a student password/PIN without knowing the old one."""
        user = self.store.get(user_id)
        if user is None or user.role != UserRole.ATHLETE:
            raise AuthError("Shenagar peyda nashod: %s" % user_id)
        user.pin_hash = PasswordHasher.hash_secret(
            self._check_secret(new_secret))
        self.store.put(user)
        alog("Ramz tavasot-e modir reset shod: %s" % user_id)

    # backward-compatible alias (v1 API name)
    def admin_reset_pin(self, user_id: str, new_pin: str) -> None:
        self.admin_reset_secret(user_id, new_pin)

    def update_athlete(self, user_id: str, name: Optional[str] = None,
                       age: Optional[int] = None,
                       experience_years: Optional[float] = None,
                       skill_tier: Optional[str] = None,
                       active: Optional[bool] = None,
                       username: Optional[str] = None) -> User:
        user = self.store.get(user_id)
        if user is None or user.role != UserRole.ATHLETE:
            raise AuthError("Shenagar peyda nashod: %s" % user_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise AuthError("Nam nemitavanad khali bashad.")
            user.name = name
        if age is not None:
            user.age = max(0, int(age))
        if experience_years is not None:
            user.experience_years = max(0.0, float(experience_years))
        if skill_tier is not None:
            if skill_tier not in SKILL_TIERS:
                raise AuthError("Skill-tier namotabar ast.")
            user.skill_tier = skill_tier
        if active is not None:
            user.active = bool(active)
        if username is not None:
            user.username = self._check_username(username,
                                                 ignore_id=user.user_id)
        self.store.put(user)
        return user

    def remove_athlete(self, user_id: str) -> None:
        user = self.store.get(user_id)
        if user is None or user.role != UserRole.ATHLETE:
            raise AuthError("Shenagar peyda nashod: %s" % user_id)
        self.store.remove(user_id)
        alog("Shenagar hazf shod: %s" % user_id)

    def list_athletes(self, active_only: bool = False) -> List[User]:
        return self.store.all(role=UserRole.ATHLETE, active_only=active_only)
