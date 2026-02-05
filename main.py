# =========================
# IMPORTS
# =========================

from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from jose import JWTError, jwt
import cloudinary
import cloudinary.uploader
import os, uuid, logging

# =========================
# ENV
# =========================

ROOT_DIR = Path(__file__).parent
load_dotenv()


MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME")

JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 24))

ADMIN_USER = os.getenv("ADMIN_USERNAME")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD")
if not MONGO_URL or not DB_NAME:
    raise RuntimeError("MongoDB não configurado")

if not JWT_SECRET or not JWT_ALGORITHM:
    raise RuntimeError("JWT não configurado")


# =========================
# CLOUDINARY
# =========================

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# =========================
# DATABASE
# =========================

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# =========================
# APP
# =========================

app = FastAPI()
api = APIRouter(prefix="/api")
security = HTTPBearer()

# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# AUTH
# =========================

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

# =========================
# MODELS — HOME CONTENT
# =========================

class HomeBranding(BaseModel):
    nome_loja: str = ""
    slogan: str = ""
    logo_url: str = ""

class HomeHero(BaseModel):
    imagem: str = ""
    titulo: str = ""
    texto: List[str] = []
    frase_impacto: str = ""
    cta_texto: str = ""
    cta_link: str = ""

class HomeSobre(BaseModel):
    titulo: str = ""
    mensagens: List[str] = []
    textos: List[str] = []
    fotos: List[str] = []

class HomeContato(BaseModel):
    titulo: str = ""
    subtitulo: str = ""
    instagram_url: str = ""
    lojas: List[dict] = []

class HomeFooter(BaseModel):
    institucional: str = ""
    cnpj: str = ""
    selo_texto: str = ""
    lojas: List[dict] = []
    certificados: List[str] = []

class HomeContent(BaseModel):
    slug: str = "home"
    branding: HomeBranding = HomeBranding()
    hero: HomeHero = HomeHero()
    sobre: HomeSobre = HomeSobre()
    contato: HomeContato = HomeContato()
    footer: HomeFooter = HomeFooter()

# =========================
# MODELS — CATEGORIES
# =========================

class Category(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    slug: str
    ativo: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# =========================
# MODELS — PRODUCTS
# =========================

class ProductSpec(BaseModel):
    label: str
    value: str

class ProductCarousel(BaseModel):
    home: bool = False
    promo: bool = False
    destaque: bool = False
    order: int = 0

class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    name: str
    category: str

    price: float

    # 🔥 PROMOÇÃO (ADICIONADO)
    promo_active: bool = False
    promo_price: Optional[float] = None

    images: List[str] = []
    specs: List[ProductSpec] = []

    carousel: ProductCarousel = ProductCarousel()

    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# =========================
# AUTH — ADMIN LOGIN
# =========================

class AdminLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

@api.post("/admin/login", response_model=Token)
async def admin_login(data: AdminLogin):
    if data.username != ADMIN_USER or data.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)

    token = jwt.encode(
        {"sub": data.username, "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    return {"access_token": token, "token_type": "bearer"}

# =========================
# HOME CONTENT
# =========================

@api.get("/home-content")
async def get_home_content():
    data = await db.home_content.find_one({"slug": "home"}, {"_id": 0})
    return data or HomeContent().model_dump()

@api.put("/home-content")
async def update_home_content(
    data: dict,
    user: str = Depends(verify_token)
):
    await db.home_content.update_one(
        {"slug": "home"},
        {"$set": data},
        upsert=True
    )
    return {"ok": True}

# =========================
# CATEGORIES
# =========================

@api.get("/categories")
async def get_categories():
    return await db.categories.find(
        {"ativo": True},
        {"_id": 0}
    ).to_list(1000)

@api.post("/categories")
async def create_category(
    category: Category,
    user: str = Depends(verify_token)
):
    await db.categories.insert_one(category.model_dump())
    return category

# =========================
# PRODUCTS
# =========================

@api.get("/products")
async def get_products():
    return await db.products.find(
        {"active": True},
        {"_id": 0}
    ).to_list(1000)

@api.post("/products")
async def create_product(
    product: Product,
    user: str = Depends(verify_token)
):
    await db.products.insert_one(product.model_dump())
    return product

@api.put("/products/{id}")
async def update_product(
    id: str,
    data: dict,
    user: str = Depends(verify_token)
):
    await db.products.update_one(
        {"id": id},
        {"$set": data}
    )
    return {"ok": True}

@api.delete("/products/{id}")
async def delete_product(
    id: str,
    user: str = Depends(verify_token)
):
    await db.products.update_one(
        {"id": id},
        {"$set": {"active": False}}
    )
    return {"ok": True}

# =========================
# UPLOAD — CLOUDINARY
# =========================

@api.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: str = Depends(verify_token)
):
    try:
        result = cloudinary.uploader.upload(
            file.file,
            folder="central_joias/products",
            resource_type="image"
        )
        return {"url": result["secure_url"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# FINAL
# =========================

app.include_router(api)

@app.on_event("shutdown")
async def shutdown():
    client.close()

logging.basicConfig(level=logging.INFO)
