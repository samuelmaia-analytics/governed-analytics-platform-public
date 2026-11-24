# Governed Analytics Platform

Este pacote fonte reúne código, contratos e documentação de governança. Entradas Olist, recortes reais, exports Power BI, relatórios pendentes e CSVs históricos de testes ficam fora da distribuição.

## Execução local e perfil público

Instale as dependências de `pyproject.toml` em um ambiente isolado e inicie a interface local com `python -m streamlit run app/main.py`. Sem os artefatos privados e o arquivo de amostra local, o perfil local pode usar dois registros sintéticos em memória. O pipeline completo requer entradas fornecidas separadamente e autorizadas para uso privado.

O perfil público, habilitado por `GAP_PUBLIC_DEMO_MODE=true`, aceita a fixture sintética específica somente com autorização pública vigente para seus bytes. Sem a fixture ou a autorização, o carregamento fica bloqueado.

O navegador de documentos exige autorização de visitante, hash correspondente e ausência de revogação. A presença de um documento no ZIP não o habilita no navegador. A entrega de dados exige a autorização aplicável e o Publication Gate.

## Arquitetura e testes

A partir da raiz do pacote, consulte:

- [Camadas locais](docs/architecture/local_data_lake.md)
- [Camada semântica](docs/architecture/semantic_layer.md)
- [Contratos de dados](docs/data_contracts.md)
- [Escopo do pacote](docs/governance/public_scope.md)

Com as dependências de desenvolvimento instaladas, execute `python -m pytest tests`. Os testes incluídos usam valores sintéticos. Publicar o histórico, mudar a visibilidade do repositório ou fazer deploy exige autorização própria.
