"""
Tá Barato SC — Backend API
Agrega ofertas de supermercados de Santa Catarina
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from contextlib import asynccontextmanager
from sqlalchemy import or_, func
import asyncio

from models.database import SessionLocal, Oferta, Base, engine
from scrapers.koch import scrape_ofertas_koch
from scrapers.bistek import scrape_ofertas_bistek
from scrapers.encartes import scrape_todas_redes

Base.metadata.create_all(bind=engine)

scheduler = AsyncIOScheduler()


async def atualizar_todas_ofertas():
    print(f'[Scheduler] Iniciando atualização — {datetime.now()}')
    db = SessionLocal()
    try:
        ofertas_koch   = await scrape_ofertas_koch()
        ofertas_bistek = await scrape_ofertas_bistek()
        ofertas_outras = await scrape_todas_redes()
        todas = ofertas_koch + ofertas_bistek + ofertas_outras
        if todas:
            db.query(Oferta).delete()
            for o in todas:
                oferta = Oferta(**{k: v for k, v in o.items() if k != 'atualizado_em'})
                db.add(oferta)
            db.commit()
            print(f'[Scheduler] {len(todas)} produtos salvos')
    except Exception as e:
        print(f'[Scheduler] Erro: {e}')
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(atualizar_todas_ofertas())
    scheduler.add_job(atualizar_todas_ofertas, 'cron', hour=6, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title='Tá Barato SC',
    description='API de ofertas de supermercados de SC',
    version='1.1.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def _filtro_palavras(q: str):
    """
    Gera filtros para busca por múltiplas palavras.
    Ex: 'arroz 5kg' → busca registros que contenham 'arroz' E '5kg' no nome.
    """
    palavras = [p.strip() for p in q.split() if len(p.strip()) >= 2]
    if not palavras:
        return [Oferta.nome.ilike(f'%{q}%')]
    return [Oferta.nome.ilike(f'%{p}%') for p in palavras]


@app.get('/health')
def health():
    return {'ok': True, 'ts': datetime.now().isoformat()}


@app.get('/sugerir')
def sugerir(q: str = Query(..., min_length=2)):
    """Retorna sugestões rápidas de nomes para autocomplete."""
    db = SessionLocal()
    try:
        filtros = _filtro_palavras(q)
        nomes = (
            db.query(Oferta.nome)
            .filter(*filtros)
            .order_by(Oferta.nome)
            .limit(10)
            .all()
        )
        # Deduplicar por nome normalizado (sem tamanho/embalagem)
        vistos = set()
        sugestoes = []
        for (nome,) in nomes:
            chave = nome[:30].lower()
            if chave not in vistos:
                vistos.add(chave)
                sugestoes.append(nome)
        return {'sugestoes': sugestoes[:8]}
    finally:
        db.close()


@app.get('/ofertas')
def listar_ofertas(
    q: str = Query(None),
    rede: str = Query(None),
    categoria: str = Query(None),
    so_com_desconto: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    db = SessionLocal()
    try:
        query = db.query(Oferta)
        if q:
            filtros = _filtro_palavras(q)
            query = query.filter(*filtros)
        if rede:
            query = query.filter(Oferta.rede.ilike(f'%{rede}%'))
        if categoria:
            query = query.filter(Oferta.categoria.ilike(f'%{categoria}%'))
        if so_com_desconto:
            query = query.filter(Oferta.desconto_pct.isnot(None))

        total   = query.count()
        ofertas = query.order_by(Oferta.preco.asc()).offset((page-1)*per_page).limit(per_page).all()

        return {
            'total': total,
            'page': page,
            'per_page': per_page,
            'redes_disponiveis': _listar_redes(db),
            'ofertas': [_oferta_dict(o) for o in ofertas],
        }
    finally:
        db.close()


@app.get('/buscar')
def buscar_produto(
    q: str = Query(...),
    por_rede: int = Query(5, ge=1, le=20),
):
    """
    Busca por múltiplas palavras e retorna resultados balanceados por rede.
    Ex: 'arroz 5kg' → encontra produtos com 'arroz' E '5kg' no nome.
    """
    if len(q.strip()) < 2:
        raise HTTPException(400, 'Busca muito curta')

    db = SessionLocal()
    try:
        filtros = _filtro_palavras(q)
        todas = (
            db.query(Oferta)
            .filter(*filtros)
            .order_by(Oferta.preco.asc())
            .all()
        )

        # Se não encontrou com todas as palavras, tenta só a primeira
        if not todas and len(q.split()) > 1:
            primeira = q.split()[0]
            todas = (
                db.query(Oferta)
                .filter(Oferta.nome.ilike(f'%{primeira}%'))
                .order_by(Oferta.preco.asc())
                .all()
            )

        if not todas:
            return {'produto': q, 'encontrado': False, 'todos': [], 'por_rede': []}

        # Balancear: até `por_rede` produtos de cada rede
        contagem = {}
        balanceados = []
        for o in todas:
            cnt = contagem.get(o.rede, 0)
            if cnt < por_rede:
                balanceados.append(o)
                contagem[o.rede] = cnt + 1

        # Melhor preço geral
        com_preco = [o for o in todas if o.preco is not None]
        melhor = com_preco[0] if com_preco else todas[0]

        # Melhor por rede (mais barato de cada)
        por_rede_dict = {}
        for o in todas:
            if o.rede not in por_rede_dict and o.preco is not None:
                por_rede_dict[o.rede] = o

        return {
            'produto': q,
            'encontrado': True,
            'total': len(todas),
            'melhor_preco': _oferta_dict(melhor),
            'por_rede': [_oferta_dict(o) for o in por_rede_dict.values()],
            'todos': [_oferta_dict(o) for o in balanceados],
        }
    finally:
        db.close()


@app.get('/produto/{produto_id}')
def detalhe_produto(produto_id: int):
    """Retorna um produto e mostra o mesmo produto em outras redes."""
    db = SessionLocal()
    try:
        produto = db.query(Oferta).filter(Oferta.id == produto_id).first()
        if not produto:
            raise HTTPException(404, 'Produto não encontrado')

        # Buscar produto similar em outras redes (primeiras 3 palavras do nome)
        palavras = produto.nome.split()[:3]
        filtros  = [Oferta.nome.ilike(f'%{p}%') for p in palavras if len(p) >= 3]

        similares = []
        if filtros:
            por_rede = {}
            todos = (
                db.query(Oferta)
                .filter(*filtros, Oferta.id != produto_id)
                .order_by(Oferta.preco.asc())
                .all()
            )
            for o in todos:
                if o.rede not in por_rede:
                    por_rede[o.rede] = o
            similares = list(por_rede.values())

        return {
            'produto': _oferta_dict(produto),
            'em_outras_redes': [_oferta_dict(o) for o in similares],
        }
    finally:
        db.close()


@app.get('/categorias')
def listar_categorias():
    """Lista todas as categorias disponíveis."""
    db = SessionLocal()
    try:
        from sqlalchemy import distinct
        cats = [
            r[0] for r in
            db.query(distinct(Oferta.categoria))
            .filter(Oferta.categoria.isnot(None))
            .order_by(Oferta.categoria)
            .all()
        ]
        return {'categorias': cats}
    finally:
        db.close()


@app.get('/lista-de-compras')
def calcular_lista(produtos: str = Query(...)):
    """
    Recebe lista de produtos separados por vírgula.
    Busca com múltiplas palavras e calcula qual rede sai mais barato no total.
    """
    items = [p.strip() for p in produtos.split(',') if p.strip()]
    if not items:
        raise HTTPException(400, 'Lista vazia')

    db = SessionLocal()
    try:
        resultado      = {}
        total_por_rede = {}

        for item in items:
            filtros = _filtro_palavras(item)
            ofertas = (
                db.query(Oferta)
                .filter(*filtros)
                .order_by(Oferta.preco.asc())
                .all()
            )

            # Fallback para primeira palavra se não encontrou
            if not ofertas and len(item.split()) > 1:
                primeira = item.split()[0]
                ofertas = (
                    db.query(Oferta)
                    .filter(Oferta.nome.ilike(f'%{primeira}%'))
                    .order_by(Oferta.preco.asc())
                    .all()
                )

            por_rede = {}
            for o in ofertas:
                if o.rede not in por_rede and o.preco:
                    por_rede[o.rede] = _oferta_dict(o)
                    total_por_rede[o.rede] = total_por_rede.get(o.rede, 0) + o.preco

            resultado[item] = {
                'encontrado': bool(por_rede),
                'mais_barato': list(por_rede.values())[0] if por_rede else None,
                'por_rede': por_rede,
            }

        redes_ordenadas = sorted(total_por_rede.items(), key=lambda x: x[1])

        return {
            'lista': items,
            'por_produto': resultado,
            'total_por_rede': [{'rede': r, 'total': round(t, 2)} for r, t in redes_ordenadas],
            'melhor_rede': redes_ordenadas[0][0] if redes_ordenadas else None,
        }
    finally:
        db.close()


@app.get('/redes')
def listar_redes():
    db = SessionLocal()
    try:
        return {'redes': _listar_redes(db)}
    finally:
        db.close()


@app.post('/atualizar')
async def forcar_atualizacao():
    asyncio.create_task(atualizar_todas_ofertas())
    return {'ok': True, 'msg': 'Atualização iniciada em background'}


def _oferta_dict(o: Oferta) -> dict:
    return {
        'id': o.id,
        'rede': o.rede,
        'nome': o.nome,
        'preco': o.preco,
        'preco_original': o.preco_original,
        'desconto_pct': o.desconto_pct,
        'imagem': o.imagem,
        'categoria': o.categoria,
        'validade': o.validade,
        'url_produto': o.url_produto,
        'atualizado_em': o.atualizado_em.isoformat() if o.atualizado_em else None,
    }


def _listar_redes(db) -> list[str]:
    from sqlalchemy import distinct
    return [r[0] for r in db.query(distinct(Oferta.rede)).all()]
