"""
Scraper Koch Supermercados
O Koch usa a plataforma Osuper que expõe uma API interna.
Fazemos requisições direto à API deles.
"""
import httpx
import re
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Referer': 'https://www.superkoch.com.br/',
}

# API interna da plataforma Osuper usada pelo Koch
# Descoberta via DevTools do browser
KOCH_API = 'https://www.superkoch.com.br/api/catalog/products'
KOMPRAO_API = 'https://www.kompraokoch.com.br/api/catalog/products'


async def scrape_ofertas_koch() -> list[dict]:
    """Busca ofertas do Koch via API interna da Osuper."""
    ofertas = []
    page = 1
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        while True:
            try:
                resp = await client.get(KOCH_API, params={
                    'sort': 'relevance',
                    'page': page,
                    'per_page': 48,
                    'filters': 'offer:true',
                })
                if resp.status_code != 200:
                    break
                data = resp.json()
                produtos = data.get('products', data.get('items', data.get('data', [])))
                if not produtos:
                    break
                for p in produtos:
                    oferta = _parse_produto_osuper(p, 'Koch')
                    if oferta:
                        ofertas.append(oferta)
                # Checar se tem mais páginas
                total = data.get('total', data.get('count', 0))
                if page * 48 >= total or len(produtos) < 48:
                    break
                page += 1
            except Exception as e:
                print(f'[Koch] Erro página {page}: {e}')
                break

    # Fallback: scraping HTML se API não retornar nada
    if not ofertas:
        ofertas = await _scrape_html_koch(client if 'client' in dir() else None)

    print(f'[Koch] {len(ofertas)} ofertas coletadas')
    return ofertas


async def _scrape_html_koch(client=None) -> list[dict]:
    """Fallback: scraping via HTML da página de ofertas."""
    from bs4 import BeautifulSoup
    ofertas = []
    urls = [
        'https://www.superkoch.com.br/promocoes',
        'https://www.superkoch.com.br/ofertas',
    ]
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as c:
        for url in urls:
            try:
                resp = await c.get(url)
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Buscar cards de produto (estrutura comum do Osuper)
                cards = soup.select('[class*="product-card"], [class*="ProductCard"], [class*="product-item"]')
                for card in cards:
                    nome_el = card.select_one('[class*="name"], [class*="title"], h2, h3')
                    preco_el = card.select_one('[class*="price-offer"], [class*="special-price"], [class*="promo"]')
                    preco_orig_el = card.select_one('[class*="price-original"], [class*="old-price"], s, del')
                    img_el = card.select_one('img')
                    if not nome_el or not preco_el:
                        continue
                    nome = nome_el.get_text(strip=True)
                    preco = _parse_preco(preco_el.get_text(strip=True))
                    preco_orig = _parse_preco(preco_orig_el.get_text(strip=True)) if preco_orig_el else None
                    imagem = img_el.get('src') or img_el.get('data-src') if img_el else None
                    if nome and preco:
                        ofertas.append({
                            'rede': 'Koch',
                            'nome': nome,
                            'preco': preco,
                            'preco_original': preco_orig,
                            'desconto_pct': _calc_desconto(preco, preco_orig),
                            'imagem': imagem,
                            'categoria': None,
                            'validade': None,
                            'url_produto': url,
                            'atualizado_em': datetime.now().isoformat(),
                        })
            except Exception as e:
                print(f'[Koch HTML] Erro em {url}: {e}')
    return ofertas


def _parse_produto_osuper(p: dict, rede: str) -> dict | None:
    """Converte produto da API Osuper para nosso formato."""
    try:
        nome = p.get('name') or p.get('title') or p.get('product_name')
        if not nome:
            return None
        preco = float(p.get('special_price') or p.get('price') or p.get('sale_price') or 0)
        preco_orig = float(p.get('price') or p.get('original_price') or p.get('regular_price') or 0)
        if preco == 0:
            return None
        if preco_orig and preco_orig <= preco:
            preco_orig = None
        imagem = (p.get('images') or [{}])[0].get('url') if p.get('images') else p.get('image')
        return {
            'rede': rede,
            'nome': nome,
            'preco': preco,
            'preco_original': preco_orig if preco_orig and preco_orig != preco else None,
            'desconto_pct': _calc_desconto(preco, preco_orig),
            'imagem': imagem,
            'categoria': p.get('category') or p.get('department'),
            'validade': p.get('promotion_end') or p.get('valid_until'),
            'url_produto': p.get('url') or p.get('link'),
            'atualizado_em': datetime.now().isoformat(),
        }
    except Exception:
        return None


def _parse_preco(texto: str) -> float | None:
    try:
        nums = re.findall(r'[\d,\.]+', texto.replace(',', '.'))
        return float(nums[-1]) if nums else None
    except Exception:
        return None


def _calc_desconto(preco: float, preco_orig: float | None) -> int | None:
    try:
        if preco_orig and preco_orig > preco:
            return int((1 - preco / preco_orig) * 100)
    except Exception:
        pass
    return None
