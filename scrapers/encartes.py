"""
Scraper genérico para redes que publicam encartes em imagem/PDF.
Usa catalogosofertas.com.br que lista as ofertas em HTML estruturado.
Redes suportadas: Angeloni, Bistek, Fort Atacadista, Giassi, Cooper, Hipermais
"""
import httpx
from bs4 import BeautifulSoup
import re
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

REDES = {
    'angeloni':      'https://www.catalogosofertas.com.br/lojas/angeloni/ofertas-catalogos',
    'bistek':        'https://www.catalogosofertas.com.br/lojas/bistek-supermercados/ofertas-catalogos',
    'fort':          'https://www.catalogosofertas.com.br/lojas/fort-atacadista/ofertas-catalogos',
    'giassi':        'https://www.catalogosofertas.com.br/lojas/giassi-supermercados/ofertas-catalogos',
    'cooper':        'https://www.catalogosofertas.com.br/lojas/cooper-supermercados/ofertas-catalogos',
    'hipermais':     'https://www.catalogosofertas.com.br/lojas/hipermais/ofertas-catalogos',
    'komprao':       'https://www.catalogosofertas.com.br/lojas/komprao-koch/ofertas-catalogos',
}

NOMES_DISPLAY = {
    'angeloni': 'Angeloni',
    'bistek': 'Bistek',
    'fort': 'Fort Atacadista',
    'giassi': 'Giassi',
    'cooper': 'Cooper',
    'hipermais': 'Hipermais',
    'komprao': 'Komprão Koch',
}


async def scrape_encarte(rede_key: str) -> list[dict]:
    """Scrapa ofertas de uma rede via catalogosofertas."""
    url = REDES.get(rede_key)
    nome_rede = NOMES_DISPLAY.get(rede_key, rede_key.title())
    if not url:
        return []

    ofertas = []
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Estrutura do catalogosofertas — cards de produto
            cards = soup.select('.product-card, [class*="product"], article[class*="offer"]')
            for card in cards:
                nome_el = card.select_one('[class*="name"], [class*="title"], h2, h3, p.name')
                preco_el = card.select_one('[class*="price"], [class*="valor"], .price')
                img_el = card.select_one('img')

                if not nome_el:
                    continue
                nome = nome_el.get_text(strip=True)
                preco_txt = preco_el.get_text(strip=True) if preco_el else ''
                preco = _parse_preco(preco_txt)
                imagem = img_el.get('src') or img_el.get('data-src') if img_el else None

                if nome and len(nome) > 3:
                    ofertas.append({
                        'rede': nome_rede,
                        'nome': nome,
                        'preco': preco,
                        'preco_original': None,
                        'desconto_pct': None,
                        'imagem': imagem,
                        'categoria': None,
                        'validade': _extrair_validade(soup),
                        'url_produto': url,
                        'atualizado_em': datetime.now().isoformat(),
                    })
        except Exception as e:
            print(f'[{nome_rede}] Erro: {e}')

    print(f'[{nome_rede}] {len(ofertas)} ofertas coletadas')
    return ofertas


async def scrape_todas_redes() -> list[dict]:
    """Scrapa todas as redes em paralelo."""
    import asyncio
    tasks = [scrape_encarte(k) for k in REDES.keys()]
    resultados = await asyncio.gather(*tasks, return_exceptions=True)
    todas = []
    for r in resultados:
        if isinstance(r, list):
            todas.extend(r)
    return todas


def _parse_preco(texto: str) -> float | None:
    try:
        clean = texto.replace('R$', '').replace(' ', '').replace(',', '.')
        nums = re.findall(r'\d+\.\d+|\d+', clean)
        return float(nums[0]) if nums else None
    except Exception:
        return None


def _extrair_validade(soup) -> str | None:
    try:
        el = soup.select_one('[class*="valid"], [class*="period"], [class*="data"]')
        if el:
            txt = el.get_text(strip=True)
            if re.search(r'\d{2}/\d{2}', txt):
                return txt
    except Exception:
        pass
    return None
