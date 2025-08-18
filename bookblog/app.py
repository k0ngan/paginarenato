import os
import io
import json
import uuid
import zipfile
import datetime
from pathlib import Path

import streamlit as st
from PIL import Image

# =========================
# Configuración básica
# =========================
st.set_page_config(page_title="BookBlog", page_icon="📚", layout="wide")

DATA_DIR = Path("data")
COVERS_DIR = DATA_DIR / "covers"
BOOKS_JSON = DATA_DIR / "books.json"
COMMENTS_JSON = DATA_DIR / "comments.json"


# =========================
# Utilidades de almacenamiento
# =========================
def ensure_storage():
    """Crea carpetas y archivos base si no existen."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    if not BOOKS_JSON.exists():
        BOOKS_JSON.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
    if not COMMENTS_JSON.exists():
        COMMENTS_JSON.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path):
    """Lee JSON seguro; devuelve lista vacía ante error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_json(path: Path, data):
    """Escritura atómica de JSON."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_cover(uploaded_file) -> str | None:
    """Guarda portada redimensionada como JPEG 85% en data/covers."""
    if not uploaded_file:
        return None
    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    out_path = COVERS_DIR / filename
    image = Image.open(uploaded_file).convert("RGB")
    image.thumbnail((1024, 1024))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="JPEG", quality=85)
    return str(out_path.as_posix())


# =========================
# Lógica de dominio
# =========================
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
    q = (q or "").lower().strip()
    books = load_json(BOOKS_JSON)
    if not q:
        return sorted(books, key=lambda b: b.get("created_at", ""), reverse=True)
    res = []
    for b in books:
        haystack = " ".join(
            [
                b.get("title", ""),
                b.get("author", ""),
                b.get("year", ""),
                " ".join(b.get("tags", [])),
                b.get("description", ""),
            ]
        ).lower()
        if q in haystack:
            res.append(b)
    return sorted(res, key=lambda b: b.get("created_at", ""), reverse=True)


# =========================
# Exportación / Importación
# =========================
def export_json_bytes(path: Path) -> bytes:
    data = load_json(path)
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def merge_lists_by_id(old_list: list, new_list: list) -> list:
    """Fusiona por 'id'. Lo nuevo sobreescribe coincidencias y agrega faltantes."""
    idx = {item.get("id"): i for i, item in enumerate(old_list) if item.get("id")}
    for item in new_list:
        _id = item.get("id")
        if _id and _id in idx:
            old_list[idx[_id]] = item
        else:
            old_list.append(item)
    return old_list


def import_json_bytes(path: Path, content: bytes, mode: str = "replace"):
    """
    Importa JSON en 'path'.
    mode: 'replace' (reemplaza todo) o 'merge' (fusiona por id).
    """
    incoming = json.loads(content.decode("utf-8"))
    if mode == "replace":
        save_json(path, incoming)
    else:
        current = load_json(path)
        save_json(path, merge_lists_by_id(current, incoming))


def make_backup_zip_bytes() -> bytes:
    """
    Crea un ZIP con:
      - data/books.json
      - data/comments.json
      - data/covers/* (si existen)
      - manifest.json
    """
    ensure_storage()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data/books.json", export_json_bytes(BOOKS_JSON))
        z.writestr("data/comments.json", export_json_bytes(COMMENTS_JSON))
        if COVERS_DIR.exists():
            for p in COVERS_DIR.glob("*"):
                if p.is_file():
                    z.write(p, arcname=f"data/covers/{p.name}")
        manifest = {
            "version": 1,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "notes": "Backup de BookBlog",
        }
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    buf.seek(0)
    return buf.getvalue()


def restore_from_zip_bytes(zip_bytes: bytes, mode: str = "replace"):
    """
    Restaura desde un ZIP creado por make_backup_zip_bytes():
      - Copia covers dentro de data/covers/
      - Importa books.json y comments.json (replace/merge)
      - Normaliza rutas de portada si están como nombres sueltos
    """
    ensure_storage()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # Portadas
        for name in z.namelist():
            if name.startswith("data/covers/") and not name.endswith("/"):
                out = COVERS_DIR / Path(name).name
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, open(out, "wb") as dst:
                    dst.write(src.read())

        # JSONs
        if "data/books.json" in z.namelist():
            books_bytes = z.read("data/books.json")
            import_json_bytes(BOOKS_JSON, books_bytes, mode=mode)
        if "data/comments.json" in z.namelist():
            comments_bytes = z.read("data/comments.json")
            import_json_bytes(COMMENTS_JSON, comments_bytes, mode=mode)

        # Reparar rutas de portada si vinieron como nombres
        books = load_json(BOOKS_JSON)
        changed = False
        for b in books:
            cp = (b.get("cover_path") or "").strip()
            if cp and "/" not in cp:
                candidate = (COVERS_DIR / cp)
                if candidate.exists():
                    b["cover_path"] = candidate.as_posix()
                    changed = True
        if changed:
            save_json(BOOKS_JSON, books)


# =========================
# UI
# =========================
def book_card(b):
    col1, col2 = st.columns([1, 3])
    with col1:
        if b.get("cover_path") and Path(b["cover_path"]).exists():
            st.image(b["cover_path"], use_container_width=True)
        else:
            st.write("🖼️ Sin portada")
    with col2:
        st.subheader(b.get("title", "Sin título"))
        meta = []
        if b.get("author"):
            meta.append(f"**Autor:** {b['author']}")
        if b.get("year"):
            meta.append(f"**Año:** {b['year']}")
        if b.get("tags"):
            meta.append("**Tags:** " + ", ".join(b["tags"]))
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
    st.title("📚 BookBlog — libros san agustin (Creador de la pagina Renato Pinto)")

    # Sidebar: buscador
    st.sidebar.header("Buscar")
    q = st.sidebar.text_input("Título, autor, tag o descripción")
    st.sidebar.caption("Deja vacío para ver todo.")

    # Tabs principales
    tab_list = st.tabs(["🔎 Explorar", "➕ Agregar libro", "📤 Exportar / 📥 Importar"])

    # ====== Tab: Explorar ======
    with tab_list[0]:
        results = search_books(q)
        st.write(f"Resultados: **{len(results)}**")
        if not results:
            st.info("Sin resultados.")
        else:
            for b in results:
                st.divider()
                book_card(b)

    # ====== Tab: Agregar ======
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
                cover = st.file_uploader("Portada (JPG/PNG)", type=["jpg", "jpeg", "png"])
            description = st.text_area("Descripción / reseña", height=160)
            submitted = st.form_submit_button("Guardar libro")
            if submitted:
                if not (title or "").strip():
                    st.error("El título es obligatorio.")
                else:
                    cover_path = save_cover(cover) if cover else ""
                    book = add_book(title, author, year, tags, description, cover_path)
                    st.success(f"Libro agregado: {book['title']}")
                    st.rerun()

    # ====== Tab: Exportar / Importar ======
    with tab_list[2]:
        st.subheader("📤 Exportar")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "Descargar books.json",
                data=export_json_bytes(BOOKS_JSON),
                file_name="books.json",
                mime="application/json",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "Descargar comments.json",
                data=export_json_bytes(COMMENTS_JSON),
                file_name="comments.json",
                mime="application/json",
                use_container_width=True,
            )
        with c3:
            st.download_button(
                "Backup completo (.zip)",
                data=make_backup_zip_bytes(),
                file_name="bookblog_backup.zip",
                mime="application/zip",
                use_container_width=True,
            )

        st.divider()
        st.subheader("📥 Importar")

        mode = st.radio(
            "Modo de importación",
            ["replace", "merge"],
            index=1,
            help="replace: reemplaza completamente. merge: fusiona por id.",
            horizontal=True,
        )

        st.markdown("**Importar JSON sueltos**")
        c4, c5 = st.columns(2)
        with c4:
            up_books = st.file_uploader("Subir books.json", type=["json"], key="up_books_json")
            if up_books and st.button("Importar books.json", use_container_width=True):
                import_json_bytes(BOOKS_JSON, up_books.read(), mode=mode)
                st.success("books.json importado.")
                st.rerun()
        with c5:
            up_comments = st.file_uploader("Subir comments.json", type=["json"], key="up_comments_json")
            if up_comments and st.button("Importar comments.json", use_container_width=True):
                import_json_bytes(COMMENTS_JSON, up_comments.read(), mode=mode)
                st.success("comments.json importado.")
                st.rerun()

        st.markdown("---")
        st.markdown("**Restaurar desde backup .zip** (incluye portadas)")
        up_zip = st.file_uploader("Subir bookblog_backup.zip", type=["zip"], key="up_zip_backup")
        if up_zip and st.button("Restaurar ZIP", type="primary", use_container_width=True):
            restore_from_zip_bytes(up_zip.read(), mode=mode)
            st.success("Backup restaurado.")
            st.rerun()


if __name__ == "__main__":
    main()
