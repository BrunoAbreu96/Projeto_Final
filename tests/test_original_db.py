import sqlite3
from pathlib import Path


def test_base_original_integra():
    caminho = Path("original/visteon_porsche_line.db").resolve()
    assert caminho.exists(), "Base de dados original não encontrada."

    ligacao = sqlite3.connect(
        caminho.as_uri() + "?mode=ro",
        uri=True
    )

    try:
        resultado = ligacao.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        assert resultado == "ok", f"Integridade: {resultado}"

        tabelas = {
            linha[0]
            for linha in ligacao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        essenciais = {
            "cabines",
            "historico_producao",
            "registo_avarias",
            "sessao_ativa",
        }

        assert essenciais.issubset(tabelas), (
            f"Tabelas em falta: {essenciais - tabelas}"
        )
    finally:
        ligacao.close()
