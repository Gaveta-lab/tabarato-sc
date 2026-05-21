from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class Oferta(Base):
    __tablename__ = 'ofertas'
    id            = Column(Integer, primary_key=True)
    rede          = Column(String(100), index=True)
    nome          = Column(String(500), index=True)
    preco         = Column(Float)
    preco_original= Column(Float, nullable=True)
    desconto_pct  = Column(Integer, nullable=True)
    imagem        = Column(Text, nullable=True)
    categoria     = Column(String(200), nullable=True)
    validade      = Column(String(100), nullable=True)
    url_produto   = Column(Text, nullable=True)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# PostgreSQL via DATABASE_URL do Railway, fallback SQLite local
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///./tabarato.db')

# Railway injeta postgres:// mas SQLAlchemy 2.x precisa de postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # reconecta se conexão cair
    pool_size=5,
    max_overflow=10,
)

Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine)
