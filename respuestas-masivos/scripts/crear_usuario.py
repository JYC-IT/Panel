"""Crear o restablecer usuarios del panel desde la terminal.

Uso:
  python crear_usuario.py                      (modo interactivo)
  python crear_usuario.py francisco "Francisco" admin
  python crear_usuario.py hernan "Hernán" lector
  python crear_usuario.py --reset hernan       (cambiar contraseña)
"""
import getpass
import os
import sys

from dotenv import load_dotenv

# Asegurar que los módulos y .env del proyecto se encuentren desde la raíz
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

import auth  # noqa: E402
import db  # noqa: E402


def _ask_password():
    while True:
        p1 = getpass.getpass("Contraseña (mín. 8 caracteres): ")
        p2 = getpass.getpass("Repite la contraseña: ")
        if p1 != p2:
            print("No coinciden, intenta de nuevo.")
        elif len(p1) < 8:
            print("Muy corta.")
        else:
            return p1


def main(argv):
    db.init_db()
    if argv[:1] == ["--reset"]:
        username = (argv[1] if len(argv) > 1 else input("Usuario: ")).strip().lower()
        user = next((u for u in auth.list_users() if u["username"] == username), None)
        if not user:
            sys.exit(f"No existe el usuario «{username}».")
        auth.set_password(user["id"], _ask_password())
        print(f"✅ Contraseña de «{username}» actualizada.")
        return

    username = argv[0] if len(argv) > 0 else input("Usuario (ej. hernan): ")
    name = argv[1] if len(argv) > 1 else input("Nombre visible (ej. Hernán): ")
    role = argv[2] if len(argv) > 2 else (input("Rol [admin/lector] (lector): ") or "lector")
    try:
        auth.create_user(username, name, _ask_password(), role.strip().lower())
    except ValueError as e:
        sys.exit(f"❌ {e}")
    print(f"✅ Usuario «{username.strip().lower()}» creado con rol {role}.")


if __name__ == "__main__":
    main(sys.argv[1:])
