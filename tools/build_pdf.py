"""Genera el PDF de entrega del Checkpoint 1.

Uso (desde la raíz del proyecto, dentro del contenedor):
    python tools/build_pdf.py --apellido Perez --nombre Ana

Capturas esperadas (PNG o JPG) en docs/capturas/:
    estructura.png  -> Explorador de VS Code con la jerarquía completa
    terminal.png    -> Terminal del contenedor ejecutando src/check_env.py

Si falta alguna captura, el PDF se genera igual con un recuadro de aviso
para poder previsualizarlo.
"""

import argparse
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAPTURAS = PROJECT_ROOT / "docs" / "capturas"
OUTPUT_DIR = PROJECT_ROOT / "docs"

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=colors.HexColor("#1F3A5F"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#1F3A5F"))
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10.5, leading=15)
CAPTION = ParagraphStyle("Caption", parent=BODY, fontSize=9, textColor=colors.grey, alignment=TA_CENTER)
TITLE = ParagraphStyle("Title", parent=styles["Title"], fontSize=24, leading=30, textColor=colors.HexColor("#1F3A5F"))
SUBTITLE = ParagraphStyle("Subtitle", parent=BODY, fontSize=13, alignment=TA_CENTER)
CODE = ParagraphStyle(
    "Code", fontName="Courier", fontSize=8.5, leading=11,
    backColor=colors.HexColor("#F4F6F8"), borderColor=colors.HexColor("#D0D7DE"),
    borderWidth=0.5, borderPadding=8, leftIndent=8, rightIndent=8,
)


def find_capture(name: str) -> Path | None:
    for ext in (".png", ".jpg", ".jpeg"):
        path = CAPTURAS / f"{name}{ext}"
        if path.exists():
            return path
    return None


def capture_block(name: str, caption: str, max_h: float = 15 * cm) -> list:
    path = find_capture(name)
    if path is None:
        aviso = Table(
            [[Paragraph(f"<b>Falta la captura</b><br/>Guardala como docs/capturas/{name}.png", BODY)]],
            colWidths=[CONTENT_W], rowHeights=[5 * cm],
        )
        aviso.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.red),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        print(f"  [AVISO] No se encontró docs/capturas/{name}.png")
        return [KeepTogether([aviso, Spacer(1, 4), Paragraph(caption, CAPTION)])]

    iw, ih = ImageReader(str(path)).getSize()
    scale = min(CONTENT_W / iw, max_h / ih, 1.0)
    img = Image(str(path), width=iw * scale, height=ih * scale)
    img.hAlign = "CENTER"
    return [KeepTogether([img, Spacer(1, 4), Paragraph(caption, CAPTION)])]


def code_block(rel_path: str) -> list:
    text = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8").rstrip()
    return [KeepTogether([Paragraph(f"<b>{rel_path}</b>", BODY), Spacer(1, 6), Preformatted(text, CODE)]), Spacer(1, 14)]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(MARGIN, 1.2 * cm, "Checkpoint 1 - Entorno Inicial de Automatización")
    canvas.drawRightString(PAGE_W - MARGIN, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def build(apellido: str, nombre: str) -> Path:
    out = OUTPUT_DIR / f"{apellido}_{nombre}_Checkpoint_1.pdf"
    doc = SimpleDocTemplate(
        str(out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="Checkpoint 1 - Entorno Inicial de Automatización", author=f"{nombre} {apellido}",
    )

    story = [
        Spacer(1, 6 * cm),
        Paragraph("Checkpoint 1", TITLE),
        Paragraph("Entorno Inicial de Automatización", TITLE),
        Spacer(1, 1 * cm),
        Paragraph("Documento de validación técnica del entorno de desarrollo", SUBTITLE),
        Spacer(1, 3 * cm),
        Paragraph(f"<b>{nombre} {apellido}</b>", SUBTITLE),
        Paragraph(date.today().strftime("%d/%m/%Y"), SUBTITLE),
        PageBreak(),

        Paragraph("Resumen del entorno", H1),
        Paragraph(
            "El proyecto se ejecuta dentro de un <b>Dev Container</b> definido con Docker, "
            "lo que garantiza que el código corra igual en cualquier máquina. La imagen parte de "
            "<font face='Courier'>python:3.10-slim</font> e incluye <font face='Courier'>build-essential</font> "
            "para compilar dependencias de IA. VS Code instala automáticamente las extensiones de "
            "Python, Pylance, Jupyter y Docker al abrir el contenedor.", BODY),
        Spacer(1, 8),
        Paragraph(
            "Las credenciales se gestionan con un archivo <font face='Courier'>.env</font> (excluido de git y "
            "de la imagen) a partir de la plantilla <font face='Courier'>.env.example</font>. El archivo "
            "<font face='Courier'>.dockerignore</font> evita copiar <font face='Courier'>.git/</font>, "
            "<font face='Courier'>data/</font> y <font face='Courier'>.env</font> al contexto de construcción. "
            "Todas las rutas del código son relativas a la raíz del proyecto.", BODY),
        PageBreak(),

        Paragraph("1. Estructura de carpetas", H1),
        Paragraph("Explorador de VS Code mostrando la jerarquía completa del proyecto.", BODY),
        Spacer(1, 8),
        *capture_block("estructura", "Figura 1. Estructura del proyecto en VS Code"),
        PageBreak(),

        Paragraph("2. Configuración del contenedor", H1),
        Paragraph("2.1 Dockerfile", H2),
        *code_block("Dockerfile"),
        PageBreak(),
        Paragraph("2.2 devcontainer.json", H2),
        *code_block(".devcontainer/devcontainer.json"),
        Paragraph("2.3 .env.example", H2),
        *code_block(".env.example"),
        PageBreak(),

        Paragraph("3. Verificación del entorno", H1),
        Paragraph(
            "Ejecución de <font face='Courier'>python src/check_env.py</font> en la terminal de VS Code "
            "dentro del contenedor. El script muestra la versión de Python, confirma que corre dentro "
            "de Docker, verifica que las variables de entorno son accesibles y que existen las carpetas "
            "del proyecto.", BODY),
        Spacer(1, 8),
        *capture_block("terminal", "Figura 2. Terminal del contenedor ejecutando check_env.py con éxito"),
    ]

    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=footer)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el PDF del Checkpoint 1")
    parser.add_argument("--apellido", required=True)
    parser.add_argument("--nombre", required=True)
    args = parser.parse_args()

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    out = build(args.apellido.strip(), args.nombre.strip())
    print(f"PDF generado: {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
