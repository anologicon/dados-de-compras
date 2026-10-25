# Compras · Observatório local

Frontend React/TypeScript. A aplicação usa apenas `/api` da mesma origem; nenhum token ou caminho de banco é enviado pelo navegador.

## Build

A partir da raiz do repositório:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/compras-crawler web
```

O build gera `src/compras_crawler/web/static/` (ignorado no Git e incluído como package data quando presente). Node não é necessário em runtime. Execute o build antes de empacotar um wheel que deva conter a UI.

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

Os testes de navegador sobem um serviço isolado na porta 8765, com dados sintéticos temporários e **sem workers ou chamadas à API pública**. Eles não aprovam a coleta real de Brusque.
