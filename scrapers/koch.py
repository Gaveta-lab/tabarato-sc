"""
Scraper Koch Supermercados
Usa a API interna da Osuper (sense.osuper.com.br) — sem autenticação.
IDs: plataforma=295, loja=1415 (Camboriú Centro)
Busca o catálogo completo de produtos com preços.
"""
import httpx
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Origin': 'https://www.superkoch.com.br',
    'Referer': 'https://www.superkoch.com.br/',
}

OSUPER_SEARCH = 'https://sense.osuper.com.br/295/1415/search'
PAGE_SIZE = 48


async def scrape_ofertas_koch() -> list[dict]:
    """Busca catálogo completo do Koch via API Osuper."""
    ofertas = []
    from_idx = 0

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        while True:
            try:
                resp = await client.get(OSUPER_SEARCH, params={
                    'promotion': 'false',   # catálogo completo
                    'brands': '',
                    'categories': '',
                    'tags': '',
                    'onlyPersonas': 'false',
                    'cashback': 'false',
                    'hidePersonas': '690',
                    'size': PAGE_SIZE,
                    'from': from_idx,
                    'search': '',
                    'sortField': 'sales_count',
                    'sortOrder': 'desc',
                })
                if resp.status_code != 200:
                    print(f'[Koch] HTTP {resp.status_code}')
                    break

                data = resp.json()
                hits = data.get('hits', [])
                if not hits:
                    break

                for p in hits:
                    oferta = _parse_produto(p)
                    if oferta:
                        ofertas.append(oferta)

                has_more = hits[-1].get('hasMore', False) if hits else False
                if not has_more or len(hits) < PAGE_SIZE:
                    break
                from_idx += PAGE_SIZE

                print(f'[Koch] {from_idx} produtos carregados...')

            except Exception as e:
                print(f'[Koch] Erro offset {from_idx}: {e}')
                break

    print(f'[Koch] Total: {len(ofertas)} produtos coletados')
    return ofertas


def _parse_produto(p: dict) -> dict | None:
    try:
        nome = p.get('name', '').strip()
        if not nome:
            return None

        pricing = p.get('pricing', {})
        preco_original = pricing.get('price')
        preco_promo    = pricing.get('promotionalPrice')
        desconto       = pricing.get('discount')
        em_promocao    = pricing.get('promotion', False)

        # Preço atual: promocional se disponível, senão normal
        preco = preco_promo if (em_promocao and preco_promo) else preco_original
        if not preco:
            return None

        # Categoria — pegar a mais específica
        categorias = p.get('categories', [])
        categoria = None
        if categorias:
            partes = categorias[0].replace('store1415:', '').split(' > ')
            categoria = partes[-1] if partes else None

        return {
            'rede': 'Koch',
            'nome': nome,
            'preco': float(preco),
            'preco_original': float(preco_original) if em_promocao and preco_original and preco_original != preco else None,
            'desconto_pct': int(desconto) if em_promocao and desconto else None,
            'imagem': p.get('image'),
            'categoria': categoria,
            'validade': None,
            'url_produto': f'https://www.superkoch.com.br/produto/{p.get("slug", "")}',
            'atualizado_em': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f'[Koch] Erro parse: {e}')
        return None
