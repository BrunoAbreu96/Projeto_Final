-- Esquema único do BRUNUS MES. Datas ISO locais, sem fuso horário.
-- A produção representa a saída final de uma linha, não uma cabine.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cabines (
    id INTEGER PRIMARY KEY,
    main_line TEXT NOT NULL CHECK (length(trim(main_line)) > 0),
    estacao TEXT NOT NULL CHECK (length(trim(estacao)) > 0),
    nome_processo TEXT NOT NULL CHECK (length(trim(nome_processo)) > 0),
    status TEXT NOT NULL DEFAULT 'OK' CHECK (status IN ('OK', 'ERRO'))
);

CREATE TABLE IF NOT EXISTS historico_producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    main_line TEXT NOT NULL CHECK (length(trim(main_line)) > 0),
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) BETWEEN 19 AND 26
        AND substr(timestamp, 1, 19) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][T ][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
        AND substr(timestamp, 1, 4) BETWEEN '0001' AND '9999'
        AND substr(timestamp, 12, 2) BETWEEN '00' AND '23'
        AND substr(timestamp, 15, 2) BETWEEN '00' AND '59'
        AND substr(timestamp, 18, 2) BETWEEN '00' AND '59'
        AND (length(timestamp) = 19 OR (
            length(timestamp) BETWEEN 21 AND 26 AND substr(timestamp, 20, 1) = '.'
            AND substr(timestamp, 21) NOT GLOB '*[^0-9]*'
        ))
        AND date(substr(timestamp, 1, 10), '+0 days') IS NOT NULL
        AND date(substr(timestamp, 1, 10), '+0 days') = substr(timestamp, 1, 10)
    ),
    status_peca TEXT NOT NULL CHECK (status_peca IN ('OK', 'REJEITADA')),
    tempo_ciclo REAL NOT NULL CHECK (
        typeof(tempo_ciclo) IN ('real', 'integer') AND tempo_ciclo > 0
        AND tempo_ciclo <= 1.7976931348623157e308
    )
);

CREATE TABLE IF NOT EXISTS registo_avarias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cabine_id INTEGER NOT NULL REFERENCES cabines(id) ON DELETE RESTRICT,
    robo_afetado TEXT NOT NULL CHECK (length(trim(robo_afetado)) > 0),
    codigo_erro TEXT NOT NULL CHECK (length(trim(codigo_erro)) > 0),
    descricao TEXT NOT NULL CHECK (length(trim(descricao)) > 0),
    causa_provavel TEXT NOT NULL CHECK (length(trim(causa_provavel)) > 0),
    timestamp_inicio TEXT NOT NULL CHECK (
        length(timestamp_inicio) BETWEEN 19 AND 26
        AND substr(timestamp_inicio, 1, 19) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][T ][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
        AND substr(timestamp_inicio, 1, 4) BETWEEN '0001' AND '9999'
        AND substr(timestamp_inicio, 12, 2) BETWEEN '00' AND '23'
        AND substr(timestamp_inicio, 15, 2) BETWEEN '00' AND '59'
        AND substr(timestamp_inicio, 18, 2) BETWEEN '00' AND '59'
        AND (length(timestamp_inicio) = 19 OR (
            length(timestamp_inicio) BETWEEN 21 AND 26 AND substr(timestamp_inicio, 20, 1) = '.'
            AND substr(timestamp_inicio, 21) NOT GLOB '*[^0-9]*'
        ))
        AND date(substr(timestamp_inicio, 1, 10), '+0 days') IS NOT NULL
        AND date(substr(timestamp_inicio, 1, 10), '+0 days') = substr(timestamp_inicio, 1, 10)
    ),
    timestamp_fim TEXT CHECK (
        timestamp_fim IS NULL OR (
            length(timestamp_fim) BETWEEN 19 AND 26
            AND substr(timestamp_fim, 1, 19) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][T ][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
            AND substr(timestamp_fim, 1, 4) BETWEEN '0001' AND '9999'
            AND substr(timestamp_fim, 12, 2) BETWEEN '00' AND '23'
            AND substr(timestamp_fim, 15, 2) BETWEEN '00' AND '59'
            AND substr(timestamp_fim, 18, 2) BETWEEN '00' AND '59'
            AND (length(timestamp_fim) = 19 OR (
                length(timestamp_fim) BETWEEN 21 AND 26 AND substr(timestamp_fim, 20, 1) = '.'
                AND substr(timestamp_fim, 21) NOT GLOB '*[^0-9]*'
            ))
            AND date(substr(timestamp_fim, 1, 10), '+0 days') IS NOT NULL
            AND date(substr(timestamp_fim, 1, 10), '+0 days') = substr(timestamp_fim, 1, 10)
            -- Comparação exata de microssegundos; julianday arredonda a milissegundos.
            AND substr(replace(timestamp_fim, ' ', 'T') || CASE WHEN length(timestamp_fim) = 19 THEN '.' ELSE '' END || '000000', 1, 26)
                >= substr(replace(timestamp_inicio, ' ', 'T') || CASE WHEN length(timestamp_inicio) = 19 THEN '.' ELSE '' END || '000000', 1, 26)
        )
    ),
    status TEXT NOT NULL CHECK (status IN ('ATIVO', 'RESOLVIDO')),
    CHECK ((status = 'ATIVO' AND timestamp_fim IS NULL)
        OR (status = 'RESOLVIDO' AND timestamp_fim IS NOT NULL))
);

-- Tabela histórica; a autenticação atual utiliza a sessão do Streamlit.
CREATE TABLE IF NOT EXISTS sessao_ativa (
    id INTEGER PRIMARY KEY,
    perfil TEXT NOT NULL CHECK (perfil IN ('operador', 'tecnico', 'master')),
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) BETWEEN 19 AND 26
        AND substr(timestamp, 1, 19) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][T ][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
        AND substr(timestamp, 1, 4) BETWEEN '0001' AND '9999'
        AND substr(timestamp, 12, 2) BETWEEN '00' AND '23'
        AND substr(timestamp, 15, 2) BETWEEN '00' AND '59'
        AND substr(timestamp, 18, 2) BETWEEN '00' AND '59'
        AND (length(timestamp) = 19 OR (
            length(timestamp) BETWEEN 21 AND 26 AND substr(timestamp, 20, 1) = '.'
            AND substr(timestamp, 21) NOT GLOB '*[^0-9]*'
        ))
        AND date(substr(timestamp, 1, 10), '+0 days') IS NOT NULL
        AND date(substr(timestamp, 1, 10), '+0 days') = substr(timestamp, 1, 10)
    )
);

CREATE INDEX IF NOT EXISTS idx_producao_timestamp ON historico_producao(timestamp);
CREATE INDEX IF NOT EXISTS idx_avarias_cabine_status ON registo_avarias(cabine_id, status);
CREATE INDEX IF NOT EXISTS idx_avarias_intervalo ON registo_avarias(timestamp_inicio, timestamp_fim);
PRAGMA user_version = 1;
