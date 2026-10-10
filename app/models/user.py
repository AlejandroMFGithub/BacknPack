from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db
from .errors import RuleError


class User:
    @staticmethod
    def get(user_id):
        return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    @staticmethod
    def by_username(username):
        return get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

    @staticmethod
    def all():
        return get_db().execute("SELECT * FROM users ORDER BY role, username").fetchall()

    @staticmethod
    def create(username, password, role="player"):
        username = (username or "").strip()
        if not username or not password:
            raise RuleError("Usuario y contraseña son obligatorios.")
        if User.by_username(username):
            raise RuleError("Ese nombre de usuario ya existe.")
        db = get_db()
        user_id = db.insert(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        db.commit()
        return user_id

    @staticmethod
    def change_password(user_id, current, new, repeat):
        user = User.get(user_id)
        if not check_password_hash(user["password_hash"], current or ""):
            raise RuleError("La contraseña actual no es correcta.")
        if len(new or "") < 8:
            raise RuleError("La nueva contraseña debe tener al menos 8 caracteres.")
        if new != repeat:
            raise RuleError("Las contraseñas nuevas no coinciden.")
        db = get_db()
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), user_id)
        )
        db.commit()

    @staticmethod
    def authenticate(username, password):
        user = User.by_username((username or "").strip())
        if user and check_password_hash(user["password_hash"], password or ""):
            return user
        return None
