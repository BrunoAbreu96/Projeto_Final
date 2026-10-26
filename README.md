# BRUNUS MES — Área de trabalho local

Esta é uma cópia segura para iniciar as melhorias. Os ficheiros recebidos estão preservados em `original/` e não devem ser usados como área de testes destrutivos.

## Princípios

- Desenvolvimento local, sem serviços externos.
- Manter Python, Streamlit e SQLite nesta fase.
- Não executar reset/limpeza sobre a base de dados original.
- Fazer alterações pequenas e testáveis.

## Próximo passo

Criar uma versão de desenvolvimento fora de `original/`, começando pela camada de base de dados e autenticação, depois unificar os eventos dos simuladores e do driver. Consultar `AUDITORIA_TECNICA.md` para os riscos identificados.
