"""
Scraper Koch Supermercados
Usa a API interna da Osuper (sense.osuper.com.br) — sem autenticação.
IDs: plataforma=295, loja=1415 (Camboriú Centro)
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
    """Busca todas as ofertas do Koch via API Osuper."""
    ofertas = []
    from_idx = 0

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        while True:
            try:
                resp = await client.get(OSUPER_SEARCH, params={
                    'promotion': 'true',
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

                # Checar se tem mais páginas
                has_more = hits[-1].get('hasMore', False) if hits else False
                if not has_more or len(hits) < PAGE_SIZE:
                    break
                from_idx += PAGE_SIZE

            except Exception as e:
                print(f'[Koch] Erro offset {from_idx}: {e}')
                break

    print(f'[Koch] {len(ofertas)} ofertas coletadas')
    return ofertas


def _parse_produto(p: dict) -> dict | None:
    try:
        nome = p.get('name', '').strip()
        if not nome:
            return None

        pricing = p.get('pricing', {})
        preco_original = pricing.get('price')
        preco_promo    = pricing.get('promotionalPrice')
        desconto       = pricing.get('discount')  # já vem em % (ex: 22)

        # Usar preço promocional se disponível, senão preço normal
        preco = preco_promo if preco_promo else preco_original
        if not preco:
            return None

        # Categoria — pegar a mais específica
        categorias = p.get('categories', [])
        categoria = None
        if categorias:
            partes = categorias[0].replace(f'store1415:', '').split(' > ')
            categoria = partes[-1] if partes else None

        return {
            'rede': 'Koch',
            'nome': nome,
            'preco': float(preco),
            'preco_original': float(preco_original) if preco_original and preco_original != preco else None,
            'desconto_pct': int(desconto) if desconto else None,
            'imagem': p.get('image'),
            'categoria': categoria,
            'validade': None,
            'url_produto': f'https://www.superkoch.com.br/produto/{p.get("slug", "")}',
            'atualizado_em': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f'[Koch] Erro parse: {e}')
        return None
