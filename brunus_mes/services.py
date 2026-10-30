"""Operações autorizadas e atómicas sobre o estado da fábrica."""

from datetime import datetime

from .database import connect


def _authorize(profile, allowed):
    if profile not in allowed:
        raise PermissionError("O perfil não tem permissão para esta operação.")


def _timestamp(now):
    value = now if now is not None else datetime.now()
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise ValueError("A data deve ser datetime local sem fuso horário.")
    return value.isoformat()


def resolve_breakdown(breakdown_id, profile, path=None, now=None) -> bool:
    _authorize(profile, {"tecnico", "master"})
    timestamp = _timestamp(now)
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT cabine_id FROM registo_avarias WHERE id = ? AND status = 'ATIVO'", (breakdown_id,)
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE registo_avarias SET status = 'RESOLVIDO', timestamp_fim = ? WHERE id = ? AND status = 'ATIVO'",
            (timestamp, breakdown_id),
        )
        conn.execute(
            """UPDATE cabines SET status = CASE WHEN EXISTS (
                SELECT 1 FROM registo_avarias WHERE cabine_id = ? AND status = 'ATIVO'
            ) THEN 'ERRO' ELSE 'OK' END WHERE id = ?""", (row[0], row[0]),
        )
    return True


def reset_active_breakdowns(profile, path=None, now=None) -> int:
    _authorize(profile, {"master"})
    timestamp = _timestamp(now)
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        count = conn.execute(
            "UPDATE registo_avarias SET status = 'RESOLVIDO', timestamp_fim = ? WHERE status = 'ATIVO'",
            (timestamp,),
        ).rowcount
        conn.execute("UPDATE cabines SET status = 'OK'")
    return count


def clear_demo_data(profile, confirmed=False, path=None) -> None:
    _authorize(profile, {"master"})
    if confirmed is not True:
        raise ValueError("É necessária confirmação explícita para eliminar dados de demonstração.")
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM historico_producao")
        conn.execute("DELETE FROM registo_avarias")
        conn.execute("UPDATE cabines SET status = 'OK'")
