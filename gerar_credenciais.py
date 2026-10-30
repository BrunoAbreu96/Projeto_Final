import hashlib
import secrets
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog, messagebox

root = tk.Tk()
root.withdraw()

hashes = []

for perfil in ("operador", "tecnico", "master"):
    palavra = simpledialog.askstring(
        f"Perfil: {perfil}",
        f"Nova palavra-passe para {perfil}:",
        show="*",
        parent=root
    )

    if palavra is None:
        break

    confirmacao = simpledialog.askstring(
        f"Perfil: {perfil}",
        "Repete a palavra-passe:",
        show="*",
        parent=root
    )

    if confirmacao is None:
        break

    if palavra != confirmacao:
        messagebox.showerror("Erro", "As palavras-passe não coincidem.")
        break

    if len(palavra) < 6:
        messagebox.showerror(
            "Erro",
            "A palavra-passe deve ter pelo menos 6 caracteres."
        )
        break

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        palavra.encode("utf-8"),
        bytes.fromhex(salt),
        600000
    ).hex()

    hashes.append(
        f'{perfil}_hash = "pbkdf2_sha256$600000${salt}${digest}"'
    )

if len(hashes) == 3:
    resultado = "[credenciais]\n" + "\n".join(hashes) + "\n"

    caminho = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    caminho.parent.mkdir(parents=True, exist_ok=True)

    with open(
        caminho,
        "w",
        encoding="utf-8",
        newline="\n"
    ) as ficheiro:
        ficheiro.write(resultado)

    messagebox.showinfo(
        "Concluído",
        "Os três hashes foram guardados no secrets.toml."
    )
else:
    messagebox.showwarning(
        "Incompleto",
        "Os hashes não foram alterados. Executa novamente para recomeçar."
    )

root.destroy()
