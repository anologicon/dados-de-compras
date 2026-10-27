# Compras · Observatório local

Frontend React/TypeScript. A aplicação usa apenas `/api` da mesma origem; nenhum token ou caminho de banco é enviado pelo navegador.

## Panorama e linguagem visual

A UI usa tema claro editorial, fontes do sistema (sem downloads externos), navegação responsiva e indicadores de cobertura sempre separados do preenchimento dos campos.

O panorama usa a projeção local já publicada, sem novas coletas ou migração:
- evolução mensal alternável entre quantidade, estimado e homologado, com seleção por teclado/toque e tabela de valores exatos;
- distribuição por modalidade (cinco principais + outras), ranking de órgãos por quantidade ou valor e acesso às compras correspondentes;
- preenchimento dos campos e participação PNCP/legado no consolidado;
- filtros compartilhados e exportações CSV/JSON do recorte inteiro, inclusive pelo panorama.

Valores ausentes permanecem “Não informado”, diferentes de zero. Meses sem registros não são artificialmente preenchidos. Os valores financeiros são agrupados pelo mês de publicação, não de pagamento; somatórios incluem somente os campos conhecidos. A cobertura exibida pertence ao snapshot, não a uma certificação dos filtros selecionados.

## Fichas conectadas

Em **Compras**, abra o objeto de uma compra para navegar pelos itens, resultados e fornecedor. A ficha mostra os identificadores que comprovam os vínculos; referências ambíguas e cadastros ausentes não são resolvidos por nome. CPF fica mascarado por padrão, e cada registro mantém acesso explícito ao JSON e à proveniência.

As páginas são vinculadas ao mesmo snapshot. Se ele mudar, use **Atualizar ficha**. O fluxo usa apenas dados locais e não dispara coleta ou consulta cadastral externa. Backend anterior mantém resumo/origem acessíveis, com aviso de que as rotas novas exigem reiniciar o serviço após concluir as coletas.

Regras, endpoints, limites e validação: [`docs/ENTITY_EXPLORER.md`](../docs/ENTITY_EXPLORER.md).

## Build

A partir da raiz do repositório:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/compras-crawler web
```

O build gera `src/compras_crawler/web/static/` (ignorado no Git e incluído como package data quando presente). Node não é necessário em runtime. Execute o build antes de empacotar um wheel que deva conter a UI.

### Atualização de um serviço já aberto

Compilar os arquivos estáticos não recarrega o código Python do processo em execução. O frontend reconhece a resposta anterior da API e mantém indicadores básicos, evolução mensal, ranking por quantidade, filtros, exportações e navegação disponíveis, com aviso de compatibilidade. Detalhes que a API anterior não fornece não são inventados nem tratados como zero.

Para liberar todas as análises novas, conclua as coletas em execução e então pare/inicie o serviço local. Atualizar a página carrega os novos arquivos estáticos, mas não atualiza o backend. Não reinicie automaticamente o serviço apenas para aplicar o build enquanto houver coleta em andamento.

## Desenvolvimento

```bash
.venv/bin/compras-crawler web
npm --prefix frontend run dev
```

O Vite escuta somente no loopback e encaminha `/api` para a porta 8000, reescrevendo Host/Origin para o backend local. Mantenha o header `X-Compras-UI` nas mutações; não habilite CORS público para contornar essa proteção.

```bash
cd frontend
npx prettier --write src tests *.ts
npx playwright install chromium
npm run build
npm run test:e2e
```

Os testes de navegador sobem um serviço isolado na porta 8765, com dados sintéticos temporários (panorama simples e recorte multianual com valores ausentes/zero, sete modalidades e doze órgãos) e **sem workers ou chamadas à API pública**. Eles não aprovam a coleta real de Brusque.
