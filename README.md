# Governed Analytics Platform

Este pacote fonte reúne código, contratos e documentação de governança. Entradas Olist, recortes reais, exports Power BI, relatórios pendentes e CSVs históricos de testes ficam fora da distribuição.

## Execução local e perfil público

Instale as dependências de `pyproject.toml` em um ambiente isolado e inicie a interface local com `python -m streamlit run app/main.py`. Sem os artefatos privados e o arquivo de amostra local, o perfil local pode usar dois registros sintéticos em memória. O pipeline completo requer entradas fornecidas separadamente e autorizadas para uso privado.

O perfil público, habilitado por `GAP_PUBLIC_VISITOR_MODE=true` (ou `GAP_PUBLIC_DEMO_MODE=true`), aceita a fixture sintética específica somente com autorização pública vigente para seus bytes. Sem a fixture ou a autorização, o carregamento fica bloqueado.

O navegador de documentos exige autorização de visitante, hash correspondente e ausência de revogação. A presença de um documento no ZIP não o habilita no navegador. A entrega de dados exige a autorização aplicável e o Publication Gate.


## Deploy no Streamlit Community Cloud

O repositório público é preparado para rodar no Streamlit Community Cloud sem depender do seu computador e sem usar Azure.

1. Crie/edite o app no painel do Streamlit Cloud apontando para este repositório e para a branch desejada.
2. Defina o arquivo principal como `app/main.py`.
3. Defina a variável de ambiente `GAP_PUBLIC_VISITOR_MODE=true` (compatível também com `GAP_PUBLIC_DEMO_MODE=true`).
4. Confirme que o dataset sintético autorizado está presente no caminho `data/samples/gap_public_demo_synthetic_v1.parquet`.
   - SHA-256 autorizado: `9fe727d2e5f60ac8e2a9c7e6c4d979102882a11afa7874100c5705bcaa51a1c7`
5. Mantenha o Publication Gate fail-closed: qualquer outro artefato continua bloqueado sem autorização explícita.

Se o endereço `governed-analytics-platform.streamlit.app` ainda estiver disponível, ele pode ser reutilizado ao manter o mesmo nome de app no Streamlit Cloud.

## Arquitetura e testes

A partir da raiz do pacote, consulte:

- [Camadas locais](docs/architecture/local_data_lake.md)
- [Camada semântica](docs/architecture/semantic_layer.md)
- [Contratos de dados](docs/data_contracts.md)
- [Escopo do pacote](docs/governance/public_scope.md)

Com as dependências de desenvolvimento instaladas, execute `python -m pytest tests`. Os testes incluídos usam valores sintéticos. Publicar o histórico, mudar a visibilidade do repositório ou fazer deploy exige autorização própria.
