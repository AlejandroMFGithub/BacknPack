class RuleError(Exception):
    """Violación de una regla de juego/negocio (fondos insuficientes, sin stock...).

    Los controladores la capturan y muestran el mensaje al usuario.
    """
