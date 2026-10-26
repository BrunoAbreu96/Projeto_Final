-- BRUNUS MES
-- Script de criação da estrutura da base de dados SQLite
-- Este script cria as tabelas; não insere dados de produção.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cabines (
    id INTEGER PRIMARY KEY,
    main_line TEXT,
    estacao TEXT,
    nome_processo TEXT,
    status TEXT DEFAULT 'OK'
);

CREATE TABLE IF NOT EXISTS historico_producao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    main_line TEXT,
    timestamp TEXT,
    status_peca TEXT,
    tempo_ciclo REAL
);

CREATE TABLE IF NOT EXISTS registo_avarias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cabine_id INTEGER,
    robo_afetado TEXT,
    codigo_erro TEXT,
    descricao TEXT,
    causa_provavel TEXT,
    timestamp_inicio TEXT,
    timestamp_fim TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS sessao_ativa (
    id INTEGER PRIMARY KEY,
    perfil TEXT,
    timestamp TEXT
);
