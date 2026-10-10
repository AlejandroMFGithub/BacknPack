from ..db import get_db
from .errors import RuleError


class Currency:
    @staticmethod
    def all():
        return get_db().execute(
            "SELECT * FROM currencies ORDER BY value_cp = 0, value_cp DESC, name"
        ).fetchall()

    @staticmethod
    def get(currency_id):
        return get_db().execute(
            "SELECT * FROM currencies WHERE id = ?", (currency_id,)
        ).fetchone()

    @staticmethod
    def create(code, name, value_cp):
        code, name = (code or "").strip(), (name or "").strip()
        if not code or not name:
            raise RuleError("La divisa necesita código y nombre.")
        if value_cp < 0:
            raise RuleError("El valor no puede ser negativo.")
        db = get_db()
        if db.execute("SELECT 1 FROM currencies WHERE code = ?", (code,)).fetchone():
            raise RuleError(f"Ya existe una divisa con código '{code}'.")
        currency_id = db.insert(
            "INSERT INTO currencies (code, name, value_cp) VALUES (?, ?, ?)", (code, name, value_cp)
        )
        db.commit()
        return currency_id

    @staticmethod
    def update(currency_id, name, value_cp):
        if not (name or "").strip():
            raise RuleError("La divisa necesita un nombre.")
        if value_cp < 0:
            raise RuleError("El valor no puede ser negativo.")
        db = get_db()
        db.execute(
            "UPDATE currencies SET name = ?, value_cp = ? WHERE id = ?",
            (name.strip(), value_cp, currency_id),
        )
        db.commit()

    @staticmethod
    def delete(currency_id):
        db = get_db()
        db.execute("DELETE FROM currencies WHERE id = ?", (currency_id,))
        db.commit()

    # --- Saldos de personajes -------------------------------------------------

    @staticmethod
    def balances(character_id):
        """Todas las divisas con la cantidad que posee el personaje (0 si no tiene)."""
        return get_db().execute(
            """
            SELECT c.*, COALESCE(cc.amount, 0) AS amount
            FROM currencies c
            LEFT JOIN character_currencies cc
                   ON cc.currency_id = c.id AND cc.character_id = ?
            ORDER BY c.value_cp = 0, c.value_cp DESC, c.name
            """,
            (character_id,),
        ).fetchall()

    @staticmethod
    def balance(character_id, currency_id):
        row = get_db().execute(
            "SELECT amount FROM character_currencies WHERE character_id = ? AND currency_id = ?",
            (character_id, currency_id),
        ).fetchone()
        return row["amount"] if row else 0

    @staticmethod
    def set_amount(character_id, currency_id, amount):
        """Fija el saldo. No hace commit: úsese dentro de transaction()."""
        if amount < 0:
            raise RuleError("Una cantidad de dinero no puede ser negativa.")
        get_db().execute(
            """
            INSERT INTO character_currencies (character_id, currency_id, amount) VALUES (?, ?, ?)
            ON CONFLICT (character_id, currency_id) DO UPDATE SET amount = excluded.amount
            """,
            (character_id, currency_id, amount),
        )

    @staticmethod
    def adjust(character_id, currency_id, delta):
        """Suma/resta al saldo. No hace commit: úsese dentro de transaction()."""
        new_amount = Currency.balance(character_id, currency_id) + delta
        if new_amount < 0:
            currency = Currency.get(currency_id)
            raise RuleError(f"Fondos insuficientes de {currency['name'] if currency else 'esa divisa'}.")
        Currency.set_amount(character_id, currency_id, new_amount)
        return new_amount
