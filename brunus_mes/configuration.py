"""Configuração das estações, reservada ao master e sem apagar histórico."""

from .database import check_database, connect


def _require_master(profile):
    if profile != "master":
        raise PermissionError("Só o perfil master pode configurar linhas e estações.")


def _text(value, label, maximum):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} é obrigatório.")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{label} deve ter no máximo {maximum} caracteres.")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} deve ser escrito numa única linha, sem caracteres de controlo.")
    return value


def _identity(value):
    return value.strip().casefold()


def _station_id(value):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("Selecione uma estação válida.")
    return value


def _fields(main_line, station, process):
    return (_text(main_line, "Linha", 128), _text(station, "Estação", 128),
            _text(process, "Processo", 200))


def _canonical_line(conn, main_line):
    # Reutiliza a grafia existente: "main a" não cria outra linha "Main A".
    for row in conn.execute("SELECT DISTINCT main_line FROM cabines ORDER BY main_line"):
        if _identity(row[0]) == _identity(main_line):
            return row[0]
    return main_line


def _check_duplicate(conn, main_line, station, exclude_id=None):
    for row in conn.execute("SELECT id, main_line, estacao FROM cabines"):
        if row["id"] != exclude_id and _identity(row["main_line"]) == _identity(main_line) and _identity(row["estacao"]) == _identity(station):
            raise ValueError("Já existe uma estação com esse nome nesta linha.")


def _get_station(conn, station_id):
    row = conn.execute("SELECT * FROM cabines WHERE id = ?", (station_id,)).fetchone()
    if row is None:
        raise ValueError("A estação selecionada já não existe.")
    return row


def _has_history(conn, station):
    return (conn.execute("SELECT 1 FROM registo_avarias WHERE cabine_id = ? LIMIT 1", (station["id"],)).fetchone() is not None
            or conn.execute("SELECT 1 FROM historico_producao WHERE main_line = ? LIMIT 1", (station["main_line"],)).fetchone() is not None)


def add_station(main_line, station, process, profile, path=None) -> int:
    """Adiciona uma estação; uma linha nova surge com a sua primeira estação."""
    _require_master(profile)
    main_line, station, process = _fields(main_line, station, process)
    check_database(path)
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        main_line = _canonical_line(conn, main_line)
        _check_duplicate(conn, main_line, station)
        cursor = conn.execute(
            "INSERT INTO cabines (main_line, estacao, nome_processo) VALUES (?, ?, ?)",
            (main_line, station, process),
        )
        return cursor.lastrowid


def update_station(station_id, main_line, station, process, profile, path=None) -> None:
    """Edita o processo; protege linha/nome quando já identificam histórico."""
    _require_master(profile)
    station_id = _station_id(station_id)
    main_line, station, process = _fields(main_line, station, process)
    check_database(path)
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _get_station(conn, station_id)
        main_line = _canonical_line(conn, main_line)
        if (main_line != existing["main_line"] or station != existing["estacao"]) and _has_history(conn, existing):
            raise ValueError("A estação ou a sua linha já têm histórico. Preserve a linha e o nome; pode editar o processo.")
        _check_duplicate(conn, main_line, station, exclude_id=station_id)
        conn.execute("UPDATE cabines SET main_line = ?, estacao = ?, nome_processo = ? WHERE id = ?",
            (main_line, station, process, station_id))


def delete_station(station_id, profile, confirmed=False, path=None) -> None:
    """Remove apenas configuração sem produção na linha nem avarias associadas."""
    _require_master(profile)
    station_id = _station_id(station_id)
    if confirmed is not True:
        raise ValueError("É necessária confirmação explícita para remover uma estação.")
    check_database(path)
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _get_station(conn, station_id)
        if _has_history(conn, existing):
            raise ValueError("A estação ou a sua linha já têm histórico e não podem ser removidas.")
        conn.execute("DELETE FROM cabines WHERE id = ?", (station_id,))
