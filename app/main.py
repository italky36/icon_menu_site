import os
import pathlib
import shutil

from fastapi import FastAPI, Request, Form, Depends, Response, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlmodel import SQLModel, Session, create_engine, select, delete
from passlib.hash import bcrypt
from dotenv import load_dotenv

from app.models import User, Item, RouteSet, RouteItem

# Load .env
load_dotenv()
DEFAULT_ROUTE = os.getenv("DEFAULT_ROUTE", "menu1")
INACTIVITY_TIMEOUT = int(os.getenv("INACTIVITY_TIMEOUT", "60000"))

# Database
DATABASE_URL = "sqlite:///db.sqlite3"
engine = create_engine(DATABASE_URL)

# FastAPI
app = FastAPI()

# Base directory
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

# Mount static and media
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)
app.mount(
    "/media",
    StaticFiles(directory=str(BASE_DIR / "media")),
    name="media"
)

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Dependency for DB session
def get_session():
    with Session(engine) as session:
        yield session

# Startup: create tables & default admin
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if not session.exec(select(User).where(User.username=="admin")).first():
            session.add(User(username="admin", hashed_password=bcrypt.hash("admin")))
            session.commit()

# Auth check
def is_authenticated(request: Request) -> bool:
    return request.cookies.get("auth") == "true"

# Root redirect
@app.get("/")
def redirect_to_default():
    return RedirectResponse(f"/r/{DEFAULT_ROUTE}")

# Login form
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Process login
@app.post("/login")
def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.username==username)).first()
    if user and bcrypt.verify(password, user.hashed_password):
        resp = RedirectResponse(url="/admin", status_code=302)
        resp.set_cookie(key="auth", value="true", httponly=True)
        return resp
    return HTMLResponse(
        "<h3>Неверный логин или пароль</h3><a href='/login'>Попробовать снова</a>",
        status_code=401
    )

# Logout
@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/")
    resp.delete_cookie("auth")
    return resp

# Admin dashboard
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    return templates.TemplateResponse("admin.html", {"request": request})

# CRUD Items
@app.get("/admin/items", response_class=HTMLResponse)
def list_items(request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    items = session.exec(select(Item)).all()
    return templates.TemplateResponse("items.html", {"request": request, "items": items})

@app.post("/admin/items")
def add_item(
    request: Request,
    label: str = Form(...),
    qr_text: str = Form(...),
    image: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    img_path = f"/media/icons/{image.filename}"
    dest = BASE_DIR / img_path[1:]
    with open(dest, "wb") as f:
        shutil.copyfileobj(image.file, f)
    session.add(Item(label=label, qr_text=qr_text, image_path=img_path))
    session.commit()
    return RedirectResponse("/admin/items", status_code=302)

@app.get("/admin/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item_form(request: Request, item_id: int, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    item = session.get(Item, item_id)
    return templates.TemplateResponse("edit_item.html", {"request": request, "item": item})

@app.post("/admin/items/{item_id}/edit")
def edit_item(
    request: Request,
    item_id: int,
    label: str = Form(...),
    qr_text: str = Form(...),
    image: UploadFile = File(None),
    session: Session = Depends(get_session)
):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    item = session.get(Item, item_id)
    item.label = label
    item.qr_text = qr_text
    if image and image.filename:
        img_path = f"/media/icons/{image.filename}"
        dest = BASE_DIR / img_path[1:]
        with open(dest, "wb") as f:
            shutil.copyfileobj(image.file, f)
        item.image_path = img_path
    session.add(item)
    session.commit()
    return RedirectResponse("/admin/items", status_code=302)

@app.post("/admin/items/{item_id}/delete")
def delete_item(item_id: int, session: Session = Depends(get_session)):
    session.exec(delete(RouteItem).where(RouteItem.item_id==item_id))
    session.exec(delete(Item).where(Item.id==item_id))
    session.commit()
    return RedirectResponse("/admin/items", status_code=302)

# CRUD RouteSets
@app.get("/admin/routes", response_class=HTMLResponse)
def list_routes(request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    routes = session.exec(select(RouteSet)).all()
    return templates.TemplateResponse("routes.html", {"request": request, "routes": routes})

@app.post("/admin/routes")
def add_route(
    request: Request,
    route: str = Form(...),
    title: str = Form(...),
    rows: int = Form(...),
    cols: int = Form(...),
    timeout: int = Form(...),
    background: UploadFile = File(None),
    session: Session = Depends(get_session)
):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    bg_path = None
    if background and background.filename:
        rel = f"/media/backgrounds/{background.filename}"
        dest = BASE_DIR / rel[1:]
        with open(dest, "wb") as f:
            shutil.copyfileobj(background.file, f)
        bg_path = rel
    session.add(RouteSet(
        route=route,
        title=title,
        rows=rows,
        cols=cols,
        timeout=timeout,
        background_path=bg_path
    ))
    session.commit()
    return RedirectResponse("/admin/routes", status_code=302)

@app.get("/admin/routes/{route_id}/edit", response_class=HTMLResponse)
def edit_route_form(request: Request, route_id: int, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    rs = session.get(RouteSet, route_id)
    if not rs:
        raise HTTPException(status_code=404, detail="Route not found")
    return templates.TemplateResponse("edit_route.html", {"request": request, "route": rs})

@app.post("/admin/routes/{route_id}/edit")
def edit_route(
    request: Request,
    route_id: int,
    route: str = Form(...),
    title: str = Form(...),
    rows: int = Form(...),
    cols: int = Form(...),
    timeout: int = Form(...),
    background: UploadFile = File(None),
    session: Session = Depends(get_session)
):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    rs = session.get(RouteSet, route_id)
    if not rs:
        raise HTTPException(status_code=404, detail="Route not found")
    rs.route = route
    rs.title = title
    rs.rows = rows
    rs.cols = cols
    rs.timeout = timeout
    if background and background.filename:
        rel = f"/media/backgrounds/{background.filename}"
        dest = BASE_DIR / rel[1:]
        with open(dest, "wb") as f:
            shutil.copyfileobj(background.file, f)
        rs.background_path = rel
    session.add(rs)
    session.commit()
    return RedirectResponse("/admin/routes", status_code=302)

# Assign Items to Route
@app.get("/admin/routes/{route_id}/assign", response_class=HTMLResponse)
def get_assign(request: Request, route_id: int, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    route = session.get(RouteSet, route_id)
    all_items = session.exec(select(Item)).all()
    links = session.exec(select(RouteItem).where(RouteItem.route_id==route_id)).all()
    assigned_ids = [l.item_id for l in links]
    assigned = [session.get(Item, i) for i in assigned_ids]
    available = [it for it in all_items if it.id not in assigned_ids]
    return templates.TemplateResponse("assign.html", {"request": request, "route": route, "assigned": assigned, "available": available})

@app.post("/admin/routes/{route_id}/assign")
def post_assign(
    request: Request,
    route_id: int,
    order: str = Form(...),
    session: Session = Depends(get_session)
):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    session.exec(delete(RouteItem).where(RouteItem.route_id == route_id))
    session.commit()
    for idx, item_id in enumerate(order.split(","), start=1):
        session.add(RouteItem(route_id=route_id, item_id=int(item_id), position=idx))
    session.commit()
    return RedirectResponse(f"/admin/routes/{route_id}/assign", status_code=302)

# Public view of a route
@app.get("/r/{route_name}", response_class=HTMLResponse)
def view_route(request: Request, route_name: str, session: Session = Depends(get_session)):
    route = session.exec(select(RouteSet).where(RouteSet.route==route_name)).first()
    if not route:
        return RedirectResponse(f"/r/{DEFAULT_ROUTE}")
    links = session.exec(select(RouteItem).where(RouteItem.route_id==route.id).order_by(RouteItem.position)).all()
    items_data = []
    for l in links:
        it = session.get(Item, l.item_id)
        items_data.append({"label":it.label, "qr_text":it.qr_text, "image_path":it.image_path})
    return templates.TemplateResponse("view_route.html", {"request": request, "route": route, "items": items_data, "inactivity_timeout": INACTIVITY_TIMEOUT})
