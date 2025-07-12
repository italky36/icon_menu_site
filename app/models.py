
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str

class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    qr_text: str
    image_path: str

class RouteSet(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    route: str = Field(unique=True, index=True)
    title: str
    rows: int
    cols: int
    timeout: int
    background_path: Optional[str] = None

class RouteItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    route_id: int = Field(foreign_key="routeset.id")
    item_id: int = Field(foreign_key="item.id")
    position: int
