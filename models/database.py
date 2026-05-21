from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class Oferta(Base):
    __tablename__ = 'ofertas'
    id = Column(Integer, primary_key=True)
    rede = Column(String, index=True)
    nome = Column(String, index=True)
    preco = Column(Float)
    preco_original = Column(Float, nullable=True)
    desconto_pct = Column(Integer, nullable=True)
    imagem = Column(String, nullable=True)
    categoria = Column(String, nullable=True)
    validade = Column(String, nullable=True)
    url_produto = Column(String, nullable=True)
    atualizado_em = Column(DateTime, default=datetime.now, onupdate=datetime.now)

engine = create_engine('sqlite:///./tabarato.db', connect_args={'check_same_thread': False})
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(bind=engine)
