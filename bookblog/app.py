import streamlit as st
import json, os, uuid, datetime
from pathlib import Path
from PIL import Image

# ------------------ Config ------------------
st.set_page_config(page_title="BookBlog", page_icon="📚", layout="wide")
DATA_DIR = Path("data")
COVERS_DIR = DATA_DIR / "covers"
BOOKS_JSON = DATA_DIR / "books.json"
COMMENTS_JSON = DATA_DIR / "comments.json"

# ------------------ Storage helpers ------------------
def ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    if not BOOKS_JSON.exists():
        BOOKS_JSON.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
    if not COMMENTS_JSON.exists():
        COMMENTS_JSON.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")

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
    # Resize suave para no guardar archivos gigantes
    image.thumbnail((1024, 1024))
    image.save(out_path, format="JPEG", quality=85)
    return str(out_path.as_posix())
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
    }
    books.append(book)
    save_json(BOOKS_JSON, books)
    return book

def add_comment(book_id, user, text):
    comments = load_json(COMMENTS_JSON)
    comment = {
        "id": uuid.uuid4().hex,
        "book_id": book_id,
        "user": (user or "Anónimo").strip(),
        "text": text.strip(),
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    comments.append(comment)
    save_json(COMMENTS_JSON, comments)
    return comment

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

# ------------------ UI ------------------
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
        st.markdown("  •  ".join(meta) if meta else "_Sin detalles_")
        if b.get("description"):
            st.markdown(b["description"])
        with st.expander("💬 Comentarios"):
            for c in get_comments(b["id"]):
                st.markdown(f"**{c['user']}** — {c['created_at']}")
                st.write(c["text"])
                st.markdown("---")
            with st.form(f"comment_form_{b['id']}"):
                user = st.text_input("Tu nombre", key=f"name_{b['id']}")
                text = st.text_area("Escribe un comentario", key=f"text_{b['id']}")
                sent = st.form_submit_button("Publicar comentario")
                if sent:
                    if text.strip():
                        add_comment(b["id"], user, text)
                        st.success("Comentario publicado.")
                        st.rerun()
                    else:
                        st.warning("El comentario no puede estar vacío.")


def main():
    ensure_storage()
    st.title("📚 BookBlog — Blog colaborativo de libros")

    # Sidebar: buscador
    st.sidebar.header("Buscar")
    q = st.sidebar.text_input("Título, autor, tag o descripción")
    st.sidebar.caption("Deja vacío para ver todo.")

    # Tabs
    tab_list = st.tabs(["🔎 Explorar", "➕ Agregar libro"])
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

    # Agregar
    with tab_list[1]:
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


if __name__ == "__main__":
    main()
