"""Simulador de demonstração. Cada produção é uma saída final de linha."""

import argparse
from datetime import datetime
import random
import time

from brunus_mes.database import connect, initialize_database, seed_demo_stations


def iniciar_base_dados_avancada(path=None):
    initialize_database(path)
    seed_demo_stations(path)


def ciclo_fabrica_avancado(path=None, event=None, rng=None, now=None, main_line=None):
    rng = rng if rng is not None else random
    if event not in (None, "OK", "REJEITADA", "ERRO"):
        raise ValueError("Evento inválido.")
    moment = now if now is not None else datetime.now()
    if not isinstance(moment, datetime) or moment.tzinfo is not None:
        raise ValueError("A data deve ser datetime local sem fuso horário.")
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        lines = [row[0] for row in conn.execute("SELECT DISTINCT main_line FROM cabines ORDER BY main_line")]
        if not lines:
            raise ValueError("Não existem estações. Inicialize a base com --demo.")
        line = main_line if main_line is not None else rng.choice(lines)
        if line not in lines:
            raise ValueError("Linha não configurada.")
        if conn.execute(
            """SELECT 1 FROM registo_avarias r JOIN cabines c ON c.id = r.cabine_id
               WHERE c.main_line = ? AND r.status = 'ATIVO' LIMIT 1""", (line,),
        ).fetchone():
            return {"event": "PARADA", "main_line": line, "id": None}
        selected = event or rng.choices(["OK", "REJEITADA", "ERRO"], weights=(92, 5, 3))[0]
        if selected in ("OK", "REJEITADA"):
            cycle_time = round(rng.uniform(9.5, 12.8), 2)
            cursor = conn.execute(
                "INSERT INTO historico_producao (main_line, timestamp, status_peca, tempo_ciclo) VALUES (?, ?, ?, ?)",
                (line, moment.isoformat(), selected, cycle_time),
            )
        else:
            station = rng.choice(conn.execute("SELECT id FROM cabines WHERE main_line = ? ORDER BY id", (line,)).fetchall())[0]
            robot = rng.choice(["Robô 1", "Robô 2"])
            code, description, cause = rng.choice([
                ("ERR_R_102", "Perda de sincronismo na trajetória", "Efetuar calibração do eixo J3."),
                ("ERR_R_205", "Alimentador sem stock ou obstruído", "Verificar a calha e repor parafusos."),
                ("ERR_R_308", "Falha de comunicação com controlador", "Verificar a ligação de rede."),
            ])
            conn.execute("UPDATE cabines SET status = 'ERRO' WHERE id = ?", (station,))
            cursor = conn.execute(
                """INSERT INTO registo_avarias
                   (cabine_id, robo_afetado, codigo_erro, descricao, causa_provavel, timestamp_inicio, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'ATIVO')""",
                (station, robot, code, description, cause, moment.isoformat()),
            )
        result = {"event": selected, "main_line": line, "id": cursor.lastrowid}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Simulador BRUNUS MES com dados de demonstração.")
    parser.add_argument("--db", help="Caminho da base; alternativa: BRUNUS_DB_PATH")
    parser.add_argument("--cycles", type=int, help="Número finito de ciclos; omitido: execução contínua")
    parser.add_argument("--interval", type=float, default=2.0, help="Segundos entre ciclos")
    parser.add_argument("--seed", type=int, help="Semente aleatória reproduzível")
    parser.add_argument("--event", choices=("OK", "REJEITADA", "ERRO"), help="Forçar o tipo de evento")
    parser.add_argument("--init-only", action="store_true", help="Preparar estações e terminar")
    args = parser.parse_args(argv)
    if args.cycles is not None and args.cycles < 0:
        parser.error("--cycles deve ser zero ou positivo")
    if args.interval < 0:
        parser.error("--interval deve ser zero ou positivo")
    iniciar_base_dados_avancada(args.db)
    if args.init_only:
        return 0
    rng = random.Random(args.seed)
    count = 0
    try:
        while args.cycles is None or count < args.cycles:
            result = ciclo_fabrica_avancado(args.db, event=args.event, rng=rng)
            print(f"[{result['main_line']}] {result['event']} (id={result['id']})", flush=True)
            count += 1
            if args.cycles is None or count < args.cycles:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Simulador terminado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
