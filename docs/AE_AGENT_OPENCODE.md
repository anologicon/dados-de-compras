# Memória AE neste projeto via OpenCode

Instalação local do piloto: `opencode.json` conecta o servidor `ae-memory` ao
binário `.ae-agent-go/bin/ae-agent-go`. Não há configuração global, modelo
conversacional adicional nem alteração do MCP `compras` já existente no código.

Abra o projeto:

```sh
opencode ~/Documents/dados_de_compras
```

Dentro do OpenCode, `/mcps` mostra o servidor. Configurações são recarregadas
automaticamente; `/reload` força recarga se necessário. No terminal deste projeto,
`opencode mcp list` deve mostrar `ae-memory connected`.

## Primeiro teste

Uma observação foi registrada localmente a partir de evidência literal do README,
sem consultar os bancos ou serviços externos. Prompt sugerido:

> Use a ferramenta memory_search do servidor ae-memory para buscar a regra sobre
> preservação do Bronze. Mostre a citação, source_ref, status e confirmation.
> Se precisar conferir a fonte, use source_read com path README.md. Não execute
> coleta, SQL ou alterações no código ou nos bancos.

Encerre a sessão, abra novamente e repita. O conhecimento armazenado deve permanecer.
O teste não altera nem conclui a tarefa PNCP ativa do projeto.

## Escopo

- Seis ferramentas de memória: store, search, update, link, invalidate e history.
- Uma ferramenta de fonte: `source_read`, somente para `README.md` nesta configuração.
  Ela retorna snapshot e referência verificável antes de registrar uma memória.
- O servidor não observa a conversa do OpenCode nem pode autenticar afirmações
  atribuídas ao usuário. Memórias ficam `unconfirmed`; `active` não significa verdade.
- Conteúdo é negado por padrão no executável. A configuração deste projeto inclui
  `-allow-content`: ao usar as ferramentas, o modelo escolhido no OpenCode pode
  receber o conteúdo retornado. Respeite as permissões do cliente e os dados do projeto.
- `.env`, DuckDB, SQLite, caminhos externos, symlinks e documentos não permitidos
  são negados. O servidor não executa shell, SQL, dbt, sincronizações ou chamadas de rede.
- A memória está em `.ae-agent-go/memory.sqlite3`, com arquivos privados e ignorada
  pelo Git. Não é um dos bancos do crawler e não substitui Bronze ou os estados PNCP.
- Este MCP usa busca textual com fallback explícito `SEMANTIC_UNAVAILABLE`.
  O provedor de embeddings da CLI independente não é herdado automaticamente.
- Fontes são snapshots: editar o README não invalida automaticamente as memórias.
  É necessário revisar/recriar as evidências e usar update/invalidate quando pertinente.

O binário e a memória são locais. A configuração contém caminhos absolutos desta
máquina: revise antes de compartilhar/versionar. Para atualizar o binário, compile
o projeto `ae-context-agent`, substitua apenas a cópia em `.ae-agent-go/bin/` e
reconecte o MCP; não apague o banco de memória. Este piloto não foi commitado aqui.
