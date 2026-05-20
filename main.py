"""
Tá Barato SC — Backend API
Agrega ofertas de supermercados de Santa Catarina
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import asyncio

from models.database import SessionLocal, Oferta, Base, engine
from scrapers.koch import scrape_ofertas_koch
from scrapers.encartes import scrape_todas_redes

Base.metadata.create_all(bind=engine)

# Scheduler para atualizar ofertas automaticamente
scheduler = AsyncIOScheduler()


async def atualizar_todas_ofertas():
    """Roda diariamente para manter ofertas atualizadas."""
    print(f'[Scheduler] Iniciando atualização — {datetime.now()}')
    db = SessionLocal()
    try:
        # Coletar Koch
        ofertas_koch = await scrape_ofertas_koch()
        # Coletar outras redes
        ofertas_outras = await scrape_todas_redes()
        todas = ofertas_koch + ofertas_outras

        # Limpar ofertas antigas e inserir novas
        if todas:
            db.query(Oferta).delete()
            for o in todas:
                oferta = Oferta(**{k: v for k, v in o.items() if k != 'atualizado_em'})
                db.add(oferta)
            db.commit()
            print(f'[Scheduler] {len(todas)} ofertas salvas')
    except Exception as e:
        print(f'[Scheduler] Erro: {e}')
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Rodar scraping ao iniciar
    asyncio.create_task(atualizar_todas_ofertas())
    # Agendar para rodar todo dia às 6h
    scheduler.add_job(atualizar_todas_ofertas, 'cron', hour=6, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title='Tá Barato SC',
    description='API de ofertas de supermercados de SC',
    version='1.0.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    return {'ok': True, 'ts': datetime.now().isoformat()}


@app.get('/ofertas')
def listar_ofertas(
    q: str = Query(None, description='Busca por nome do produto'),
    rede: str = Query(None, description='Filtrar por rede: Koch, Angeloni, Bistek...'),
    categoria: str = Query(None, description='Filtrar por categoria'),
    so_com_desconto: bool = Query(False, description='Apenas produtos com desconto'),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Lista ofertas com filtros e paginação."""
    db = SessionLocal()
    try:
        query = db.query(Oferta)

        if q:
            query = query.filter(Oferta.nome.ilike(f'%{q}%'))
        if rede:
            query = query.filter(Oferta.rede.ilike(f'%{rede}%'))
        if categoria:
            query = query.filter(Oferta.categoria.ilike(f'%{categoria}%'))
        if so_com_desconto:
            query = query.filter(Oferta.desconto_pct.isnot(None))

        total = query.count()
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
def buscar_produto(q: str = Query(..., description='Nome do produto')):
    """Busca um produto em todas as redes e retorna comparação de preços."""
    if len(q) < 2:
        raise HTTPException(400, 'Busca muito curta')
    db = SessionLocal()
    try:
        ofertas = db.query(Oferta).filter(Oferta.nome.ilike(f'%{q}%')).order_by(Oferta.preco.asc()).all()
        if not ofertas:
            return {'produto': q, 'encontrado': False, 'resultados': []}
        
        # Agrupar por rede — pegar o mais barato de cada
        por_rede = {}
        for o in ofertas:
            if o.rede not in por_rede:
                por_rede[o.rede] = o
        
        return {
            'produto': q,
            'encontrado': True,
            'melhor_preco': _oferta_dict(ofertas[0]),
            'por_rede': [_oferta_dict(o) for o in por_rede.values()],
            'todos': [_oferta_dict(o) for o in ofertas[:20]],
        }
    finally:
        db.close()


@app.get('/lista-de-compras')
def calcular_lista(produtos: str = Query(..., description='Produtos separados por vírgula')):
    """Recebe uma lista de produtos e calcula qual rede resolve mais barato."""
    items = [p.strip() for p in produtos.split(',') if p.strip()]
    if not items:
        raise HTTPException(400, 'Lista vazia')
    
    db = SessionLocal()
    try:
        resultado = {}
        total_por_rede = {}
        
        for item in items:
            ofertas = db.query(Oferta).filter(
                Oferta.nome.ilike(f'%{item}%')
            ).order_by(Oferta.preco.asc()).all()
            
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
        
        # Ordenar redes por total mais barato
        redes_ordenadas = sorted(total_por_rede.items(), key=lambda x: x[1])
        
        return {
            'lista': items,
            'por_produto': resultado,
            'total_por_rede': [
                {'rede': r, 'total': round(t, 2)}
                for r, t in redes_ordenadas
            ],
            'melhor_rede': redes_ordenadas[0][0] if redes_ordenadas else None,
        }
    finally:
        db.close()


@app.get('/redes')
def listar_redes():
    """Lista todas as redes com ofertas disponíveis."""
    db = SessionLocal()
    try:
        return {'redes': _listar_redes(db)}
    finally:
        db.close()


@app.post('/atualizar')
async def forcar_atualizacao():
    """Força atualização manual das ofertas."""
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
