# Explorador conectado — primeiro ciclo

## Escopo entregue

Exploração de **um município por vez**, a partir de uma compra conciliada:

**Compra → itens PNCP → resultados PNCP → fornecedor observado → cadastro de referência**.

A ficha se abre pelo objeto da compra ou pelo botão de detalhes em **Compras**. Inclui resumo legível, abas de itens/resultados, paginação, valores exatos, evidências dos vínculos, registro original e proveniência. O retorno do fornecedor mantém o item e a página de resultados selecionados. CPF é mascarado na apresentação padrão; o conteúdo original pode ser consultado explicitamente.

Não há nova coleta, consulta externa, migração de armazenamento ou reconstrução obrigatória dos snapshots. A implementação consulta `purchases`, `purchase_candidates`, `records` e `snapshot_metadata` existentes, em modo somente leitura, sem abrir o Bronze.

## Regras de vínculo

- Compra: identificadores `idCompra` e controles PNCP compatíveis com a compra conciliada e seus aliases seguros.
- Item: mesmos identificadores explícitos da compra. Um município explícito divergente ou controle associado a outra compra torna a relação ambígua.
- Resultado: associação direta à compra ou, na ausência dela, referência a um `idCompraItem` único com compra confirmada.
- Resultado → item: `idCompraItem` único, sem contradição com a compra ou com `numeroItemPncp`. Sem `idCompraItem`, somente a composição de compra confirmada + `numeroItemPncp` único permite o vínculo.
- Identificadores contraditórios não são substituídos por um candidato conveniente. Resultado com item não confirmado permanece visível na aba geral, mas não é associado automaticamente a um item.
- Fornecedor: documento informado em `niFornecedor`, com formatação normalizada, sem completar dígitos. Tipo e documento precisam ser compatíveis. Não há associação por nome, catálogo, descrição ou posição na resposta.
- Cadastro de referência: CNPJ/CPF completo e tipo compatível. Ausência de cadastro, múltiplas referências ou documentos conflitantes são situações distintas; nenhum candidato ambíguo é escolhido automaticamente.
- Resultado cancelado continua visível e identificado. A interface não o chama de pagamento ou de contrato ativo.
- Registros sem identidade de negócio estável no snapshot são sinalizados: versões podem aparecer como registros distintos. Não são apresentados como entidades de negócio únicas.

Valores nulos permanecem ausentes, diferentes de zero. As contagens descrevem registros observados. Falta de filhos não prova que não existam itens/resultados na fonte. O nome observado no resultado e o nome do cadastro são apresentados separadamente; situação cadastral e endereço são referências datadas, não comprovação da situação atual ou do município da compra.

## API local

Todos os endpoints são GET e respeitam a fronteira localhost existente:

- `/api/cities/{city_id}/purchase-detail?purchase_key=...`: compra, resumo dos vínculos, cobertura e token `snapshot`.
- `/api/cities/{city_id}/purchase-items?purchase_key=...&snapshot=...&page=1&page_size=20`.
- `/api/cities/{city_id}/purchase-results?purchase_key=...&snapshot=...&item_record_id=...&page=1&page_size=20`: omitir `item_record_id` para ver todos os resultados candidatos da compra, inclusive ambíguos e sem item.
- `/api/cities/{city_id}/supplier-detail?purchase_key=...&snapshot=...&result_id=...&page=1&page_size=10`.

`item_record_id` e `result_id` são IDs de registros da projeção, não documentos de pessoa física. O fornecedor é acessado a partir de um resultado com compra confirmada, não por pesquisa arbitrária de nome/documento.

As páginas seguintes e o fornecedor exigem o token obtido na ficha. Se a projeção atual mudar, a API retorna **409**, orientando atualizar a ficha em vez de misturar versões. Limites de paginação e IDs são validados; parâmetros SQL permanecem vinculados.

## Compatibilidade de atualização

Compilar os arquivos estáticos não atualiza o código Python de um serviço já aberto. Se o endpoint novo ainda não existir, a ficha mantém resumo, JSON original e rastreabilidade disponíveis, desabilita a navegação conectada e informa a necessidade de atualizar o serviço.

**Não reiniciar automaticamente com coleta em andamento.** Após concluir as coletas, reiniciar o backend habilita as rotas novas. A publicação desta UI não foi usada como autorização para iniciar, parar ou reiniciar workers.

## Validação desta entrega

- **241 testes Python e 20 testes Chromium passando**, além de build TypeScript/Vite.
- Casos de vínculo por ID/composição, contradições de compra/município/item, órfãos, documentos formatados, CPF mascarado, cadastro ausente/ambíguo, cancelamento, identidade instável, paginação e mudança de snapshot.
- Navegação completa em navegador, permanência do contexto ao voltar do fornecedor, compatibilidade com backend anterior e isolamento ao trocar de município.
- Inspeção visual desktop e móvel; verificação de ausência de overflow a 320 e 390 px.
- Leitura do snapshot real de Joinville: **28 compras conciliadas, 273 itens e 234 resultados**. Todos os itens/resultados desse conjunto tiveram vínculo confirmado. O fluxo compra → item → resultado → cadastro também foi percorrido no navegador, usando um serviço temporário sem workers e com startup desativado, apenas GET, sem erros JavaScript ou mutações HTTP. O serviço temporário foi encerrado. Essa verificação não certifica cobertura completa da fonte, ausência de problemas no conteúdo ou pagamentos.

## Fora deste ciclo

Perfis agregados de fornecedores/órgãos, comparação de preços, navegação por catálogos, atas/contratos, PGC/OCDS, alertas, buscas salvas, links compartilháveis e exportação própria da ficha. As exportações completas de compras filtradas continuam disponíveis como antes.

A pesquisa de materiais atualmente coletada pelo endpoint de **detalhe** não deve ser tratada como base pronta de preços unitários. Complementar essa coleta e validar comparabilidade é trabalho posterior, não uma funcionalidade implícita desta navegação.
