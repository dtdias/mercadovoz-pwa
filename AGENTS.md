# MercadoVoz PWA

## Agent Rules
- UI/design: use `antd-components` MCP first; consult component docs, API, and examples before choosing or implementing Ant Design components.
- Before any repository action: consult `graphify` first. If `graphify-out/graph.json` is absent, build graphify before continuing.
- At the end of each implementation, commit changes on branch `dev`.

## Structure
- No package manifest, test runner, linter, formatter, or build step is configured. Do not assume `npm test` or a bundler exists.
- `index.html` contains all UI, CSS, and application JavaScript. It stores lists in `localStorage` key `mercadovoz_clean_v4` and loads product data from `/precos.json`.
- Personal list data stays in `localStorage`; `sw.js` caches app/catalog assets only, never user lists.
- `sw.js` is active: `index.html` registers it at `/sw.js`. If offline assets change, update `SHELL_ASSETS` and bump `CACHE_NAME`. `service-worker.js` is not registered by current app.
- `manifest.json` points icons at Vercel serverless handler `api/icon.js`; a plain static server cannot exercise `/api/icon`.

## Price Data Automation
- `.github/workflows/atualizar_precos.yml` runs weekly and manually with Python 3.10, scrapes configured public sources, validates `precos.json`, then commits the catalog only.
- `scripts/atualizar_precos.py` reads `scripts/fontes_precos.json`, performs bounded public-page scraping, preserves the last valid catalog on source errors, and writes normalized `precos.json`. Use `--no-scrape` only to normalize existing data; do not run casually because it can update generated prices.

## Verification
- Validate JSON: `python -m json.tool manifest.json` and `python -m json.tool precos.json`.
- Validate inline application JavaScript: `node -e "const fs=require('fs');const h=fs.readFileSync('index.html','utf8');new Function(h.slice(h.indexOf('<script>')+8,h.lastIndexOf('</script>')));"`.
- Validate scraper: `python scripts/atualizar_precos.py --check`.
- Validate service worker syntax: `node --check sw.js`.
