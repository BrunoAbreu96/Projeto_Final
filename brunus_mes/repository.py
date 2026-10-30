"""Consultas de leitura utilizadas pela monitorização em tempo real."""
from .database import connect


def stations(path=None):
    with connect(path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id, main_line, estacao, nome_processo, status FROM cabines ORDER BY main_line, id"
        )]


def active_breakdowns(path=None):
    with connect(path) as connection:
        return [dict(row) for row in connection.execute("""
            SELECT r.*, c.main_line, c.estacao
            FROM registo_avarias r JOIN cabines c ON c.id = r.cabine_id
            WHERE r.status = 'ATIVO' ORDER BY r.timestamp_inicio, r.id
        """)]
