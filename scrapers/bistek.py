"""
Scraper Bistek Supermercados
Usa a API REST pública do VTEX — sem autenticação.
"""
import httpx
import re
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
    'Accept': 'application/json',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Referer': 'https://www.bistek.com.br/',
}

BISTEK_API = 'https://www.bistek.com.br/api/catalog_system/pub/products/search'
PAGE_SIZE  = 50


async def scrape_ofertas_bistek() -> list[dict]:
    """Busca catálogo completo do Bistek via API VTEX."""
    ofertas  = []
    from_idx = 0

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        while True:
            try:
                to_idx = from_idx + PAGE_SIZE - 1
                resp = await client.get(BISTEK_API, params={
                    '_from': from_idx,
                    '_to':   to_idx,
                    'O':     'OrderByTopSaleDESC',
                })

                if resp.status_code not in (200, 304):
                    print(f'[Bistek] HTTP {resp.status_code}')
                    break

                produtos = resp.json()
                if not produtos:
                    break

                for p in produtos:
                    oferta = _parse_produto(p)
                    if oferta:
                        ofertas.append(oferta)

                # VTEX retorna header 'resources' com total ex: "0-49/1500"
                resources = resp.headers.get('resources', '')
                total = _parse_total(resources)
                print(f'[Bistek] {from_idx + len(produtos)}/{total} produtos...')

                if len(produtos) < PAGE_SIZE or (total and from_idx + PAGE_SIZE >= total):
                    break
                from_idx += PAGE_SIZE

            except Exception as e:
                print(f'[Bistek] Erro offset {from_idx}: {e}')
                break

    print(f'[Bistek] Total: {len(ofertas)} produtos coletados')
    return ofertas


def _parse_produto(p: dict) -> dict | None:
    try:
        nome = p.get('productName', '').strip()
        if not nome:
            return None

        # Pegar o primeiro SKU disponível
        items = p.get('items', [])
        if not items:
            return None

        item = items[0]
        sellers = item.get('sellers', [])
        if not sellers:
            return None

        offer = sellers[0].get('commertialOffer', {})
        preco          = offer.get('Price')
        preco_original = offer.get('ListPrice')

        if not preco:
            return None

        # Calcular desconto
        desconto = None
        if preco_original and preco_original > preco:
            desconto = int((1 - preco / preco_original) * 100)
        else:
            preco_original = None

        # Imagem
        imagens = item.get('images', [])
        imagem = imagens[0].get('imageUrl') if imagens else None

        # Categoria
        categorias = p.get('categories', [])
        categoria = None
        if categorias:
            partes = categorias[0].strip('/').split('/')
            categoria = partes[-1] if partes else None

        return {
            'rede': 'Bistek',
            'nome': nome,
            'preco': float(preco),
            'preco_original': float(preco_original) if preco_original else None,
            'desconto_pct': desconto,
            'imagem': imagem,
            'categoria': categoria,
            'validade': None,
            'url_produto': p.get('link'),
            'atualizado_em': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f'[Bistek] Erro parse: {e}')
        return None


def _parse_total(resources: str) -> int | None:
    try:
        m = re.search(r'/(\d+)', resources)
        return int(m.group(1)) if m else None
    except Exception:
        return None
