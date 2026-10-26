# BRUNUS MES — Manufacturing Execution System

Sistema de apoio à monitorização e gestão da produção industrial, desenvolvido no âmbito de um projeto de formação profissional.

## 1. Apresentação

O BRUNUS MES é uma aplicação destinada a apoiar o acompanhamento de processos produtivos industriais, centralizando informação sobre linhas de produção, cabines, qualidade das peças e registo de avarias.

O projeto procura demonstrar a aplicação prática de programação, bases de dados, visualização de indicadores e organização de informação industrial.

## 2. Objetivos

- Monitorizar o estado das cabines e dos processos produtivos.
- Consultar o histórico de produção e os resultados de qualidade.
- Registar e acompanhar avarias.
- Apresentar indicadores de eficiência e qualidade, incluindo métricas OEE.
- Disponibilizar acesso através de perfis de utilizador.
- Organizar a aplicação para permitir manutenção e evolução futuras.

## 3. Funcionalidades

A versão atual inclui componentes para:

- Monitorização da produção.
- Consulta de indicadores de eficiência e qualidade.
- Histórico e análise de avarias.
- Registo do estado das peças produzidas.
- Autenticação por perfil, com verificação de palavras-passe através de hashes.
- Geração de relatórios de turno em PDF.
- Simulação contínua de dados para apoiar testes e demonstrações.

A disponibilidade e o comportamento de cada funcionalidade dependem da configuração e dos dados existentes no ambiente de execução.

## 4. Tecnologias

- **Python** — linguagem de programação.
- **Streamlit** — interface da aplicação.
- **SQLite** — sistema de gestão de base de dados relacional.
- **Pandas** — tratamento e análise de dados.
- **ReportLab** — geração de documentos PDF.
- **streamlit-autorefresh** — atualização periódica da interface.
- **pytest** — execução de testes automatizados.
- **Git e GitHub** — controlo de versões e disponibilização do código.

## 5. Base de dados

O projeto utiliza SQLite, uma solução relacional adequada ao desenvolvimento local e à demonstração de um sistema desta dimensão, por dispensar a instalação de um servidor de base de dados independente.

As tabelas principais são:

- `cabines` — informação sobre linhas, estações, processos e estados.
- `historico_producao` — registos de produção e tempos de ciclo.
- `registo_avarias` — informação sobre avarias e respetiva duração.
- `sessao_ativa` — estrutura histórica existente na base de dados.

O script de criação da estrutura encontra-se em:

`sql/criar_base_dados.sql`

Para reproduzir a estrutura da base de dados num ambiente SQLite vazio, pode executar-se o script através de uma ferramenta SQLite ou do módulo `sqlite3` do Python.

## 6. Requisitos

- Windows, Linux ou outro sistema compatível com Python.
- Python 3.10 ou superior, sujeito à compatibilidade das dependências instaladas.
- Git, caso pretenda clonar o repositório.

## 7. Instalação

### 7.1. Obter o projeto

```bash
git clone https://github.com/BrunoAbreu96/Projeto_Final.git
cd Projeto_Final
```

Se estiver a trabalhar numa cópia local já existente, entre na pasta do projeto em vez de voltar a cloná-lo.

### 7.2. Criar um ambiente virtual

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 7.3. Configurar as credenciais

A autenticação utiliza hashes guardados no ficheiro local:

`.streamlit/secrets.toml`

Este ficheiro não deve ser publicado no GitHub.

O ficheiro tem de conter a secção `[credenciais]` e as chaves de hash correspondentes aos perfis `operador`, `tecnico` e `master`. Os hashes devem ser gerados localmente através do utilitário `gerar_credenciais.py`.

Executar o utilitário:

```powershell
.\.venv\Scripts\python.exe .\gerar_credenciais.py
```

O utilitário utiliza uma interface gráfica para introduzir e confirmar as palavras-passe. Não partilhe o ficheiro de credenciais nem os valores dos hashes.

### 7.4. Preparar a base de dados

Confirme que a base de dados local utilizada pela aplicação está no caminho esperado pelo código. O script SQL disponibilizado cria a estrutura das tabelas, mas não inclui dados de produção nem substitui eventuais dados de demonstração.

## 8. Executar a aplicação

Com o ambiente virtual e a configuração preparados:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\dashboard.py
```

O Streamlit apresenta o endereço local no terminal. Abra esse endereço no navegador e autentique-se com um dos perfis configurados.

## 9. Testes

Os testes automatizados encontram-se na pasta `tests`.

Para executar a suite:

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -v
```

Durante o desenvolvimento foram também realizados testes de compilação Python, verificação da configuração de credenciais, testes manuais de autenticação e logout e validação do script SQL numa base de dados temporária.

Consulte o `RELATORIO_TECNICO.md` para conhecer os testes efetuados, os problemas encontrados e as limitações ainda identificadas.

## 10. Segurança e controlo de versões

- As credenciais são mantidas fora do código-fonte.
- O ficheiro `.streamlit/secrets.toml` deve permanecer excluído do Git.
- As bases de dados locais, ambientes virtuais e cópias de segurança não devem ser publicados.
- As alterações devem ser registadas através de commits com mensagens claras.
- Antes de cada publicação, deve confirmar-se quais os ficheiros que serão incluídos.

A autenticação atual constitui uma melhoria face à utilização de palavras-passe fixas no código, mas não representa, por si só, uma auditoria de segurança completa nem certifica a aplicação para utilização industrial real.

## 11. Documentação técnica

O relatório técnico encontra-se em `RELATORIO_TECNICO.md` e documenta a arquitetura, a base de dados, as decisões técnicas, os testes, os problemas resolvidos e o trabalho futuro.

## 12. Estado do projeto

O BRUNUS MES encontra-se em desenvolvimento. As funcionalidades existentes estão a ser verificadas e a estrutura do projeto está a ser preparada para facilitar a manutenção, a documentação e a evolução.

## 13. Autor e repositório

**Projeto:** BRUNUS MES
**Autor:** Bruno Abreu
**Repositório GitHub:** https://github.com/BrunoAbreu96/Projeto_Final

---

*Projeto desenvolvido para fins de formação e demonstração técnica. A utilização num ambiente industrial real exige validação funcional, testes de segurança, controlo de acessos e avaliação da infraestrutura de implementação.*
