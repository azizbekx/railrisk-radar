"""RailRisk Radar API: FastAPI over core/, serving the React app from web/dist.
Run: .venv/bin/uvicorn api.main:app --reload --port 8000"""
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from api.common import jsonable, row  # noqa: E402
from api.routes import chat, compare, explore, profile, research, team  # noqa: E402
from core import dataset as ds, llm  # noqa: E402

app = FastAPI(title="RailRisk Radar")
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
SECRET = os.getenv("APP_SECRET") or secrets.token_hex(16)
COOKIE = "rr_session"


# ---------- jury login (APP_USERS="user:password,user2:password2"; unset = open) ----------

def users() -> dict:
    return dict(u.split(":", 1) for u in os.getenv("APP_USERS", "").split(",") if ":" in u)


def _sign(user: str) -> str:
    return f"{user}:{hmac.new(SECRET.encode(), user.encode(), hashlib.sha256).hexdigest()}"


def current_user(request: Request) -> str | None:
    if not users():
        return "guest"
    token = request.cookies.get(COOKIE, "")
    user = token.split(":", 1)[0]
    return user if token and hmac.compare_digest(token, _sign(user)) else None


@app.middleware("http")
async def auth(request: Request, call_next):
    open_paths = ("/api/login", "/api/me")
    if request.url.path.startswith("/api/") and request.url.path not in open_paths and not current_user(request):
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login):
    accounts = users()
    if body.username not in accounts or not hmac.compare_digest(accounts[body.username], body.password):
        return JSONResponse({"detail": "Wrong username or password"}, status_code=401)
    res = JSONResponse({"user": body.username})
    res.set_cookie(COOKIE, _sign(body.username), httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return res


@app.post("/api/logout")
def logout():
    res = JSONResponse({"ok": True})
    res.delete_cookie(COOKIE)
    return res


@app.get("/api/me")
def me(request: Request):
    return {"user": current_user(request), "login_required": bool(users())}


# ---------- shared metadata ----------

@app.get("/api/meta")
def meta():
    group_of = {c: g for g, cols in ds.GROUPS.items() for c in cols}
    keys = llm.keys_status()
    return jsonable({
        "scores": [{"key": c, "label": ds.label(c), "weight": w, "group": group_of.get(c)} for c, w in ds.TRI_WEIGHTS.items()],
        "groups": ds.GROUPS,
        "ops": ds.OPS, "higher_is_better": sorted(ds.HIGHER_IS_BETTER),
        "categorical": {c: ds.CAT_ORDER[c] for c in ds.CATEGORICAL},
        "levels": ds.LEVELS,
        "lenses": {name: ds.normalize_weights(w) for name, w in ds.LENSES.items()},
        "summary": ds.summary(),
        "means": ds.means().round(2).to_dict(),
        "tri_check": ds.check_tri_formula(),
        "keys": keys, "model": llm.model() if keys["llm"] else None,
    })


class RowsIn(BaseModel):
    ids: list[str]
    lens_weights: dict | None = None


@app.post("/api/rows")
def rows(body: RowsIn):
    """Compact rows for known supplier ids (shortlist, pickers). Unknown ids are dropped."""
    ids = [i for i in body.ids if i in ds.df().index]
    return jsonable([row(i, body.lens_weights) for i in ids])


@app.get("/api/lookup")
def lookup(q: str = "", limit: int = 8):
    """Supplier search by id or name for pickers: 'SUPP_00012', '12', 'Supplier 450'."""
    d = ds.df()
    q = q.strip()
    if not q:
        return []
    sid = ds.resolve(q)
    hits = [sid] if sid in d.index else []
    mask = d["supplierID"].str.contains(q, case=False, regex=False) | d["Supplier Name"].str.contains(q, case=False, regex=False)
    hits += [i for i in d[mask].index[: limit * 2] if i not in hits]
    return jsonable([row(i) for i in hits[:limit]])


for r in (explore, compare, team, profile, chat, research):
    app.include_router(r.router, prefix="/api")


# ---------- the React app ----------

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    f = DIST / path
    if path and f.is_file():
        return FileResponse(f)
    index = DIST / "index.html"
    return FileResponse(index) if index.exists() else JSONResponse({"detail": "Frontend not built: cd web && npm run build"})
