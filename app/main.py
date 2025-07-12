
import os, shutil
from fastapi import FastAPI, Request, Form, Depends, Response, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Session, create_engine, select, delete
from passlib.hash import bcrypt
from dotenv import load_dotenv

from app.models import User, Item, RouteSet, RouteItem

load_dotenv()
DEFAULT_ROUTE = os.getenv("DEFAULT_ROUTE", "menu1")
INACTIVITY_TIMEOUT = int(os.getenv("INACTIVITY_TIMEOUT", "60000"))

DATABASE_URL = "sqlite:///db.sqlite3"
engine = create_engine(DATABASE_URL)
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")
templates = Jinja2Templates(directory="templates")

def get_session():
    with Session(engine) as session:
        yield session

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if not session.exec(select(User).where(User.username=="admin")).first():
            session.add(User(username="admin", hashed_password=bcrypt.hash("admin")))
            session.commit()

def is_authenticated(request: Request):
    return request.cookies.get("auth") == "true"

@app.get("/")
def redirect_to_default():
    return RedirectResponse(url=f"/r/{DEFAULT_ROUTE}")

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(response: Response, username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username==username)).first()
    if user and bcrypt.verify(password, user.hashed_password):
        response = RedirectResponse(url="/admin", status_code=302)
        response.set_cookie(key="auth", value="true", httponly=True)
        return response
    return HTMLResponse("<h3>Invalid credentials</h3><a href='/login'>Try again</a>", status_code=401)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("auth")
    return response

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/admin/items", response_class=HTMLResponse)
def list_items(request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    items = session.exec(select(Item)).all()
    return templates.TemplateResponse("items.html", {"request": request, "items": items})

@app.post("/admin/items")
def add_item(request: Request, label: str = Form(...), qr_text: str = Form(...), image: UploadFile = File(...), session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    img_path = f"media/icons/{image.filename}"
    with open(img_path, "wb") as f:
        shutil.copyfileobj(image.file, f)
    item = Item(label=label, qr_text=qr_text, image_path="/" + img_path)
    session.add(item)
    session.commit()
    return RedirectResponse("/admin/items", status_code=302)

@app.get("/admin/routes", response_class=HTMLResponse)
def list_routes(request: Request, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    routes = session.exec(select(RouteSet)).all()
    return templates.TemplateResponse("routes.html", {"request": request, "routes": routes})

@app.post("/admin/routes")
def add_route(request: Request, route: str = Form(...), title: str = Form(...), rows: int = Form(...), cols: int = Form(...), timeout: int = Form(...), background: UploadFile = File(None), session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    bg_path = None
    if background:
        rel = f"/media/backgrounds/{background.filename}"
        with open(f".{rel}", "wb") as f:
            shutil.copyfileobj(background.file, f)
        bg_path = rel
    new_route = RouteSet(route=route, title=title, rows=rows, cols=cols, timeout=timeout, background_path=bg_path)
    session.add(new_route)
    session.commit()
    return RedirectResponse("/admin/routes", status_code=302)

@app.get("/admin/routes/{route_id}/assign", response_class=HTMLResponse)
def get_assign(request: Request, route_id: int, session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    route = session.get(RouteSet, route_id)
    all_items = session.exec(select(Item)).all()
    assigned_links = session.exec(select(RouteItem).where(RouteItem.route_id==route_id)).all()
    assigned = [session.get(Item, ri.item_id) for ri in assigned_links]
    assigned_ids = [ri.item_id for ri in assigned_links]
    available = [it for it in all_items if it.id not in assigned_ids]
    return templates.TemplateResponse("assign.html", {"request": request, "route": route, "assigned": assigned, "available": available})

@app.post("/admin/routes/{route_id}/assign")
def post_assign(request: Request, route_id: int, order: str = Form(...), session: Session = Depends(get_session)):
    if not is_authenticated(request):
        return RedirectResponse("/login")
    session.exec(delete(RouteItem).where(RouteItem.route_id==route_id))
    session.commit()
    for idx, item_id in enumerate(order.split(","), start=1):
        session.add(RouteItem(route_id=route_id, item_id=int(item_id), position=idx))
    session.commit()
    return RedirectResponse(f"/admin/routes/{route_id}/assign", status_code=302)

@app.get("/r/{route_name}", response_class=HTMLResponse)
def view_route(request: Request, route_name: str, session: Session = Depends(get_session)):
    route = session.exec(select(RouteSet).where(RouteSet.route==route_name)).first()
    if not route:
        return RedirectResponse(f"/r/{DEFAULT_ROUTE}")
    ri_list = session.exec(select(RouteItem).where(RouteItem.route_id==route.id).order_by(RouteItem.position)).all()
    items = [session.get(Item, ri.item_id) for ri in ri_list]
    return templates.TemplateResponse("view_route.html", {
        "request": request, "route": route, "items": items,
        "inactivity_timeout": INACTIVITY_TIMEOUT
    })
