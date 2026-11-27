# Governed Analytics Platform

[Português](#governed-analytics-platform) · [English](#english)

Dados inconsistentes podem chegar a relatórios executivos quando os critérios de qualidade, privacidade e publicação ficam separados do pipeline. Construí o GAP para verificar essas condições durante o processamento e registrar a decisão antes do consumo.

**[Conheça o GAP no Streamlit](https://governed-analytics-platform.streamlit.app/)** · [Integração pública e checks](https://github.com/samuelmaia-analytics/governed-analytics-platform-public/pull/25)

## Como a plataforma funciona

O processamento implementado roda localmente em Python, SQL, dbt e DuckDB. As camadas Bronze, Silver, Gold e Quarantine separam a ingestão, a transformação, os resultados analíticos e as exceções. Contratos versionados descrevem schemas e regras. Testes de qualidade e reconciliação, lineage, controles de privacidade e evidências de execução sustentam as decisões do Publication Gate. O projeto também inclui uma aplicação Streamlit, uma API FastAPI e um assistente demonstrativo de governança com recuperação de fontes.

O GitHub Actions verifica testes, lint, segurança, política e barreira de publicação. Os cinco checks passaram na integração pública das páginas arquiteturais.

## O que explorar na aplicação

As páginas Microsoft Azure e AWS distinguem o fluxo local implementado (**AS-IS**) das arquiteturas de referência propostas (**TO-BE**). A renderização visual foi confirmada pelo responsável na aplicação oficial. A verificação automatizada dos bytes entregues ao navegador, da navegação e da responsividade e um exercício de revogação em produção permanecem pendentes.

A aplicação usa acesso de leitura com menor privilégio, valida o SHA-256 autorizado e consulta a política de revogação a cada entrega. Se o acesso, a integridade ou a política não puderem ser confirmados, a página mantém a descrição textual. A revogação bloqueia novas entregas. A visualização dos dois SVGs está autorizada exclusivamente no Streamlit oficial.

O Publication Gate de dados segue em **Needs Review**. A promoção e a distribuição de dados, os exports internos e os demais artefatos restritos permanecem bloqueados.

## Execução e documentação

Em um ambiente isolado com as dependências de `pyproject.toml`, execute `python -m streamlit run app/main.py`. A execução isolada usa somente amostras sintéticas disponíveis e autorizadas para o perfil aplicável. O pipeline completo requer insumos autorizados separadamente. Para testar o código, instale as dependências de desenvolvimento e execute `python -m pytest tests`.

- [Camadas locais](docs/architecture/local_data_lake.md)
- [Contratos de dados](docs/data_contracts.md)
- [Escopo público](docs/governance/public_scope.md)

## English

The GAP addresses a recurring analytics problem: inconsistent data can reach executive reports when quality, privacy and publication decisions are handled outside the pipeline. The implemented pipeline runs locally with Python, SQL, dbt and DuckDB. Versioned contracts, validation, reconciliation, lineage and privacy controls provide evidence for the Publication Gate. The project also includes Streamlit, FastAPI and a demonstration governance assistant.

The [official Streamlit app](https://governed-analytics-platform.streamlit.app/) presents Microsoft Azure and AWS reference architectures. Each page distinguishes the implemented local workflow (**AS-IS**) from the proposed cloud design (**TO-BE**). The project owner confirmed visual rendering. Automated verification of browser-delivered bytes, navigation and responsive layouts, and a live revocation exercise remain pending. All five [public post-merge checks](https://github.com/samuelmaia-analytics/governed-analytics-platform-public/pull/25) passed.

The app reads the two authorized SVGs with least-privilege access, checks the exact SHA-256 and consults the current revocation policy on each delivery. If access, integrity or authorization cannot be confirmed, the text alternative remains available. The data Publication Gate remains in **Needs Review**, with data promotion, distribution and restricted artifacts blocked.

To run locally, install the dependencies declared in `pyproject.toml` in an isolated environment and run `python -m streamlit run app/main.py`. See the [public scope](docs/governance/public_scope.md) for distribution boundaries and `python -m pytest tests` for the test entry point.
