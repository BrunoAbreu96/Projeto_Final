# Relatório Técnico — BRUNUS MES

**Projeto:** BRUNUS MES — Manufacturing Execution System
**Data:** 26 de outubro de 2026

## 1. Introdução

O BRUNUS MES é um projeto de software destinado à monitorização e ao acompanhamento de processos de produção industrial. O sistema utiliza Python e Streamlit, com uma base de dados SQLite para armazenar informação.

## 2. Objetivos

- Desenvolver uma aplicação de monitorização da produção.
- Organizar e consultar registos de produção e avarias.
- Implementar autenticação por perfis de utilizador.
- Documentar a estrutura da base de dados e as decisões técnicas.
- Preparar o projeto para controlo de versões através do Git e publicação no GitHub.

## 3. Tecnologias utilizadas

- Python — linguagem de programação.
- Streamlit — interface da aplicação.
- SQLite — sistema de gestão de base de dados.
- Pandas — tratamento de dados.
- ReportLab — geração de relatórios PDF.
- Git e GitHub — controlo de versões e alojamento do código.
- Pytest — execução de testes automatizados.

## 4. Justificação do sistema de base de dados

Foi escolhido o SQLite por ser um sistema relacional leve, que não exige um servidor de base de dados separado e permite trabalhar com um ficheiro local. Esta opção é adequada ao desenvolvimento e à demonstração do projeto.

Para uma futura instalação industrial com vários utilizadores e requisitos de elevada disponibilidade, deverá ser avaliada a necessidade de um sistema de base de dados servidor.

## 5. Estrutura da base de dados

O projeto utiliza as seguintes tabelas:

- `cabines`: identifica linhas, estações, processos e estados.
- `historico_producao`: regista eventos de produção, estados das peças e tempos de ciclo.
- `registo_avarias`: armazena informação sobre avarias, equipamentos afetados, causas e períodos de ocorrência.
- `sessao_ativa`: tabela existente no esquema da base de dados para informação de sessão.

O script de criação da estrutura está disponível em `sql/criar_base_dados.sql`.

## 6. Autenticação e proteção de credenciais

A aplicação foi preparada para utilizar três perfis: operador, técnico e master.

A verificação das palavras-passe utiliza hashes PBKDF2-HMAC-SHA256 e comparação segura dos resultados. Os hashes são obtidos a partir da configuração local do Streamlit, em `.streamlit/secrets.toml`.

O ficheiro de credenciais e as bases de dados locais devem permanecer fora do repositório Git. A configuração local não deve ser publicada no GitHub.

A autenticação implementada constitui uma melhoria de segurança, mas não representa, por si só, uma certificação para utilização industrial. Devem ser avaliadas medidas adicionais, incluindo políticas de palavras-passe e permissões específicas para cada perfil.

## 7. Controlo de versões

O projeto utiliza Git para acompanhar as alterações ao código. O ficheiro `.gitignore` exclui ambientes virtuais, bases de dados locais, ficheiros de configuração sensível e cópias de segurança.

O estado do repositório e os ficheiros preparados para cada commit devem ser verificados antes de qualquer publicação.

## 8. Testes e validação

Foram anteriormente realizados testes ao esquema da base de dados, à integridade dos dados e ao funcionamento manual da autenticação.

O script SQL foi testado numa base de dados temporária em memória, tendo sido confirmada a criação das tabelas previstas.

Os testes devem voltar a ser executados após as alterações mais recentes, para confirmar o estado final do projeto. Os resultados registados neste documento devem corresponder aos testes efetivamente executados.

## 9. Dificuldades e correções

Durante o desenvolvimento e a preparação do ambiente foram identificadas dificuldades relacionadas com a configuração de credenciais, a codificação de ficheiros e a interpretação de aspas em comandos PowerShell.

Foram também revistas as regras de exclusão do Git, a autenticação e a necessidade de disponibilizar um script SQL independente para a criação da base de dados.

## 10. Requisitos da formação

| Requisito | Evidência no projeto |
|---|---|
| Escolha e justificação do SGBD | Secção 4 deste relatório |
| Script SQL de criação da base de dados | `sql/criar_base_dados.sql` |
| Código-fonte organizado | Ficheiros Python do projeto |
| Controlo de versões | Repositório Git |
| Proteção de configurações sensíveis | `.gitignore` e configuração local |
| Instruções de instalação e execução | `README.md` |
| Relatório técnico | Este documento |

A existência dos ficheiros no repositório local não significa que todas as alterações já tenham sido publicadas no GitHub. A publicação deverá ser confirmada separadamente.

## 11. Trabalho pendente

- Reexecutar os testes automatizados.
- Validar a sintaxe dos ficheiros Python.
- Confirmar o funcionamento do simulador.
- Rever as permissões dos perfis.
- Inspecionar os ficheiros preparados para o próximo commit.
- Confirmar a documentação e as instruções de instalação num ambiente limpo.
- Publicar as alterações no GitHub, após validação e autorização.

## 12. Conclusão

O BRUNUS MES dispõe de uma base de trabalho para a monitorização da produção, com estrutura de dados relacional, autenticação por perfis e documentação técnica em preparação. A conclusão da entrega depende da validação final dos testes, da revisão dos ficheiros e da confirmação da publicação da versão final.

## 13. Registo das atividades por período horário

**Data:** 26 de outubro de 2026
**Período:** 09h00–13h00

### 09h00–10h00 — Revisão do ambiente e autenticação

- Revisão do estado do projeto e dos ficheiros existentes.
- Análise das alterações ao mecanismo de autenticação.
- Verificação manual dos perfis e do logout.

### 10h00–11h00 — Proteção dos ficheiros e controlo de versões

- Revisão das regras do `.gitignore`.
- Verificação da exclusão de configurações sensíveis e bases de dados locais.
- Análise das alterações pendentes no repositório.

### 11h00–12h00 — Base de dados e script SQL

- Análise da estrutura da base de dados SQLite.
- Identificação das tabelas existentes.
- Criação e teste do script SQL numa base de dados temporária.

### 12h00–13h00 — Documentação técnica

- Preparação do README com instruções do projeto.
- Organização do relatório técnico.
- Identificação dos testes e tarefas ainda necessários.
