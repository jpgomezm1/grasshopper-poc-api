"""Base declarativa compartida por todos los modelos del paquete.

Re-exporta `Base` desde `app.db.database` para que los módulos del paquete
importen desde aquí (evita importar database.py directamente en cada módulo).
"""
from app.db.database import Base

__all__ = ["Base"]
