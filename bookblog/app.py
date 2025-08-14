import streamlit as st
import json, os, uuid, datetime, hashlib
from pathlib import Path
from PIL import Image

# ------------------ Config ------------------
st.set_page_config(page_title="BookBlog", page_icon="📚", layout="wide")
DATA_DIR = Path("data")
COVERS_DIR = DATA_DIR / "covers"
BOOKS_JSON = DATA_DIR / "books.json"
COMMENTS_JSON = DATA_DIR / "comments.json"
USERS_JSON = DATA_DIR / "users.json"

# ------------------ Storage helpers ------------------
def ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    if not BOOKS_JSON.exists():
        BOOKS_JSON.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
    if not COMMENTS_JSON.exists():
        COMMENTS_JSON.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
    if not USERS_JSON.exists():
        # admin por defecto: admin / admin123 (cámbialo)
        users = [create_user_record("admin", "admin123", role="admin")]
        USERS_JSON.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def save_cover(uploaded_file) -> str | None:
    if not uploaded_file:
        return None
    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    out_path = COVERS_DIR / filename
    image = Image.open(uploaded_file).convert("RGB")
    image.thumbnail((1024, 1024))
    image.save(out_path, format="JPEG", quality=85)
    return str(out_path.as_posix())

# ------------------ Auth helpers ------------------
def hash_password(password: str, salt: str | None = None):
    salt = salt or uuid.uuid4().hex
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, h

def create_user_record(username: str, password: str, role: str = "user"):
    salt, h = hash_password(password)
    return {
        "id": uuid.uuid4().hex,
        "username": username.strip(),
        "salt": salt,
        "password_hash": h,
        "role": role,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

def get_user(username: str):
    users = load_json(USERS_JSON)
    for u in users:
        if u["username"].lower() == username.lower():
            return u
    return None

def add_user(username: str, password: str, role: str = "user"):
    users = load_json(USERS_JSON)
    if any(u["username"].lower() == username.lower() for u in users):
        raise ValueError("El usuario ya existe.")
    rec = create_user_record(username, password, role)
    users.append(rec)
    save_json(USERS_JSON, users)
    return rec

def update_user_password(user_id: str, new_password: str):
    users = load_json(USERS_JSON)
    for u in users:
        if u["id"] == user_id:
            salt, h = hash_password(new_password)
            u["salt"] = salt
            u["password_hash"] = h
            save_json(USERS_JSON, users)
            return u
    raise ValueError("Usuario no encontrado.")

def delete_user(user_id: str):
    users = load_json(USERS_JSON)
    users = [u for u in users if u["id"] != user_id]
    save_json(USERS_JSON, users)

def authenticate(username: str, password: str):
    u = get_user(username)
    if not u:
        return None
    salt = u["salt"]
    _, h = hash_password(password, salt=salt)
    if h == u["password_hash"]:
        return {"id": u["id"], "username": u["username"], "role": u["role"]}
    return None

def is_admin():
    return st.session_state.get("auth_user", {}).get("role") == "admin"

# ------------------ Domain helpers ------------------
def add_book(title, author, year, tags, description, cover_path):
    books = load_json(BOOKS_JSON)
    book = {
        "id": uuid.uuid4().hex,
        "title": title.strip(),
        "author": author.strip(),
        "year": year.strip() if year else "",
        "tags": [t.strip() for t in tags.split(",")] if tags else [],
        "description": description.strip(),
        "cover_path": cover_path or "",
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "owner": st.session_state.get("auth_user", {}).get("username", "system")
    }
    books.append(book)
    save_json(BOOKS_JSON, books)
    return book

def delete_book(book_id):
    books = load_json(BOOKS_JSON)
    book = next((b for b in books if b["id"] == book_id), None)
    if book and book.get("cover_path") and Path(book["cover_path"]).exists():
        try:
            Path(book["cover_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    books = [b for b in books if b["id"] != book_id]
    save_json(BOOKS_JSON, books)
    # borra comentarios asociados
    comments = load_json(COMMENTS_JSON)
    comments = [c for c in comments if c.get("book_id") != book_id]
    save_json(COMMENTS_JSON, comments)

def add_comment(book_id, user, text):
    comments = load_json(COMMENTS_JSON)
    comment = {
        "id": uuid.uuid4().hex,
        "book_id": book_id,
        "user": (user or st.session_state.get("auth_user", {}).get("username") or "Anónimo").strip(),
        "text": text.strip(),
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    comments.append(comment)
    save_json(COMMENTS_JSON, comments)
    return comment

def delete_comment(comment_id):
    comments = load_json(COMMENTS_JSON)
    comments = [c for c in comments if c["id"] != comment_id]
    save_json(COMMENTS_JSON, comments)

def get_comments(book_id):
    comments = load_json(COMMENTS_JSON)
    return [c for c in comments if c.get("book_id") == book_id]

def search_books(q: str):
    q = q.lower().strip()
    books = load_json(BOOKS_JSON)
    if not q:
        return sorted(books, key=lambda b: b.get("created_at", ""), reverse=True)
    res = []
    for b in books:
        haystack = " ".join([
            b.get("title",""), b.get("author",""), b.get("year",""),
            " ".join(b.get("tags",[])), b.get("description","")
        ]).lower()
        if q in haystack:
            res.append(b)
    return sorted(res, key=lambda b: b.get("created_at", ""), reverse=True)

# ------------------ UI pieces ------------------
def sidebar_auth():
    st.sidebar.header("Cuenta")
    if st.session_state.get("auth_user"):
        u = st.session_state.auth_user
        st.sidebar.success(f"Conectado: **{u['username']}** ({u['role']})")
        if st.sidebar.button("Cerrar sesión"):
            st.session_state.auth_user = None
            st.rerun()
    else:
        with st.sidebar.form("login_form"):
            username = st.text_input("Usuario", key="login_user")
            password = st.text_input("Contraseña", type="password", key="login_pass")
            submitted = st.form_submit_button("Iniciar sesión")
            if submitted:
                user = authenticate(username, password)
                if user:
                    st.session_state.auth_user = user
                    st.sidebar.success("Sesión iniciada.")
                    st.rerun()
                else:
                    st.sidebar.error("Credenciales inválidas.")

def book_card(b):
    col1, col2 = st.columns([1,3])
    with col1:
        if b.get("cover_path") and Path(b["cover_path"]).exists():
            st.image(b["cover_path"], use_container_width=True)
        else:
            st.write("🖼️ Sin portada")
    with col2:
        st.subheader(b["title"])
        meta = []
        if b.get("author"): meta.append(f"**Autor:** {b['author']}")
        if b.get("year"): meta.append(f"**Año:** {b['year']}")
        if b.get("tags"): meta.append("**Tags:** " + ", ".join(b["tags"]))
        if b.get("owner"): meta.append(f"**Creador:** {b['owner']}")
        st.markdown("  •  ".join(meta) if meta else "_Sin detalles_")
        if b.get("description"):
            st.markdown(b["description"])
        with st.expander("💬 Comentarios"):
            for c in get_comments(b["id"]):
                st.markdown(f"**{c['user']}** — {c['created_at']}")
                st.write(c["text"])
                if is_admin():
                    if st.button("Eliminar comentario", key=f"delc_{c['id']}"):
                        delete_comment(c["id"])
                        st.success("Comentario eliminado.")
                        st.rerun()
                st.markdown("---")
            if st.session_state.get("auth_user"):
                with st.form(f"comment_form_{b['id']}"):
                    user = st.text_input("Tu nombre (opcional)", key=f"name_{b['id']}")
                    text = st.text_area("Escribe un comentario", key=f"text_{b['id']}")
                    sent = st.form_submit_button("Publicar comentario")
                    if sent:
                        if text.strip():
                            add_comment(b["id"], user, text)
                            st.success("Comentario publicado.")
                            st.rerun()
                        else:
                            st.warning("El comentario no puede estar vacío.")
            else:
                st.info("Inicia sesión para comentar.")

        # Acciones de admin
        if is_admin():
            with st.popover("Acciones de admin"):
                if st.button("Eliminar libro", key=f"dellib_{b['id']}"):
                    delete_book(b["id"])
                    st.success("Libro eliminado.")
                    st.rerun()

# ------------------ Main ------------------
def main():
    ensure_storage()
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None

    st.title("📚 BookBlog — Blog colaborativo de libros")
    sidebar_auth()

    st.sidebar.header("Buscar")
    q = st.sidebar.text_input("Título, autor, tag o descripción", key="q")
    st.sidebar.caption("Deja vacío para ver todo.")

    tabs = ["🔎 Explorar", "➕ Agregar libro", "ℹ️ Ayuda"]
    if is_admin():
        tabs.append("🛠 Admin")
    tab_list = st.tabs(tabs)

    # Explorar
    with tab_list[0]:
        results = search_books(q)
        st.write(f"Resultados: **{len(results)}**")
        if not results:
            st.info("Sin resultados.")
        else:
            for b in results:
                st.divider()
                book_card(b)

    # Agregar libro (requiere login)
    with tab_list[1]:
        if not st.session_state.get("auth_user"):
            st.warning("Debes iniciar sesión para agregar libros.")
        else:
            st.subheader("Nuevo libro")
            with st.form("new_book"):
                c1, c2 = st.columns(2)
                with c1:
                    title = st.text_input("Título*", max_chars=150)
                    author = st.text_input("Autor", max_chars=120)
                    year = st.text_input("Año", max_chars=10, placeholder="Ej: 2021")
                with c2:
                    tags = st.text_input("Tags (separados por coma)", placeholder="fantasía, sci-fi, clásico")
                    cover = st.file_uploader("Portada (JPG/PNG)", type=["jpg","jpeg","png"])
                description = st.text_area("Descripción / reseña", height=160)
                submitted = st.form_submit_button("Guardar libro")
                if submitted:
                    if not title.strip():
                        st.error("El título es obligatorio.")
                    else:
                        cover_path = save_cover(cover) if cover else ""
                        book = add_book(title, author, year, tags, description, cover_path)
                        st.success(f"Libro agregado: {book['title']}")
                        st.rerun()

    # Ayuda
    with tab_list[2]:
        st.markdown("""
**Cómo funciona**
- Todo se guarda en archivos JSON dentro de `./data/`.
- Portadas en `./data/covers/`.
- No usa bases de datos SQL.

**Roles**
- **user**: puede agregar libros y comentar.
- **admin**: además puede crear/eliminar usuarios, eliminar libros y comentarios.

**Notas**
- Se crea un admin por defecto: `admin` / `admin123`. **Cámbialo** en la pestaña Admin o editando `data/users.json`.
- En despliegues serverless, el almacenamiento local puede ser efímero. Usa un volumen persistente o un bucket (S3/GCS) montado en `./data`.
""")

    # Admin
    if is_admin():
        with tab_list[3]:
            st.subheader("Administración")
            st.markdown("Gestión de usuarios y moderación.")

            # Gestión de usuarios
            with st.expander("👤 Usuarios", expanded=True):
                users = load_json(USERS_JSON)
                st.write(f"Total usuarios: **{len(users)}**")
                for u in users:
                    cols = st.columns([2,2,2,3,2])
                    cols[0].write(f"**{u['username']}**")
                    cols[1].write(u["role"])
                    cols[2].write(u["created_at"])
                    # Acciones
                    with cols[3]:
                        with st.form(f"reset_{u['id']}"):
                            newp = st.text_input("Nueva contraseña", type="password", key=f"np_{u['id']}")
                            r = st.form_submit_button("Resetear contraseña")
                            if r and newp.strip():
                                update_user_password(u["id"], newp.strip())
                                st.success("Contraseña actualizada.")
                                st.rerun()
                    with cols[4]:
                        disable_del = (st.session_state.auth_user["id"] == u["id"]) or (u["username"] == "admin")
                        if st.button("Eliminar", key=f"del_{u['id']}", disabled=disable_del):
                            if not disable_del:
                                delete_user(u["id"])
                                st.success("Usuario eliminado.")
                                st.rerun()

                st.markdown("---")
                with st.form("new_user"):
                    st.markdown("**Crear nuevo usuario**")
                    nu = st.text_input("Usuario")
                    npw = st.text_input("Contraseña", type="password")
                    role = st.selectbox("Rol", ["user", "admin"])
                    ok = st.form_submit_button("Crear")
                    if ok:
                        try:
                            add_user(nu, npw, role)
                            st.success(f"Usuario creado: {nu} ({role})")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

            # Moderación rápida de libros
            with st.expander("📕 Libros", expanded=False):
                books = load_json(BOOKS_JSON)
                for b in books:
                    cols = st.columns([3,2,2,2,2])
                    cols[0].write(f"**{b['title']}**")
                    cols[1].write(b.get("author",""))
                    cols[2].write(b.get("owner","?"))
                    cols[3].write(b.get("created_at",""))
                    if cols[4].button("Eliminar", key=f"adm_del_{b['id']}"):
                        delete_book(b["id"])
                        st.success("Libro eliminado.")
                        st.rerun()

if __name__ == "__main__":
    main()
