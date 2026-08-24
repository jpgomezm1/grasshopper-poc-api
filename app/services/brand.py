"""Marca Mentoring · fuente única para lo que se imprime desde el backend.

Los PDF y los correos no pueden leer los tokens CSS del frontend, así que
cada superficie tenía su propia paleta a mano. Terminaron siendo tres
paletas distintas y ninguna era la de la marca vigente: el reporte y los
correos corrían un morado del POC, la hoja de vida el lima/azul viejo y el
informe clínico un verde esmeralda propio.

Este módulo existe para que eso no vuelva a pasar: los valores salen del
manual (`docs/Marca/MANUAL MENTORING.ai`) y cualquier plantilla del backend
los importa de aquí. Si cambia la marca, se cambia en este archivo y en
`journey-compass/src/index.css`, que son los dos únicos sitios.

Nota sobre las fuentes: WeasyPrint no descarga nada de internet, así que los
archivos viven en `app/templates/static/fonts/` y se referencian relativos al
`base_url` (= `app/templates`) que le pasan los servicios de PDF.
"""

# --- Paleta (lámina 3 del manual) -------------------------------------------

NARANJA = "#EE7238"        # primary
NARANJA_HONDO = "#B24310"  # naranja legible sobre fondos claros (texto/íconos)
NARANJA_TENUE = "#FAE8E0"  # fondo de chips y cajas de acento
NARANJA_CLARO = "#F2C9B4"  # bordes sobre NARANJA_TENUE

MORADO = "#47368C"         # secondary
MORADO_TENUE = "#ECE9F6"
MORADO_CLARO = "#CFC7E6"

MAGENTA = "#BB388B"        # tertiary · acento puntual, 3a serie en gráficas

CREMA = "#F9F5E9"          # fondo de marca
TINTA = "#1D1D1B"          # texto
GRIS = "#6B675E"           # texto secundario
BORDE = "#E2DDD0"
BLANCO = "#FFFFFF"

# Combinación obligatoria: sobre naranja va tinta, no blanco. Blanco sobre
# #EE7238 da 2.96:1 y no pasa WCAG AA; la tinta da 5.71:1.
SOBRE_NARANJA = TINTA

# --- Tipografía --------------------------------------------------------------

TITULARES = "'Satoshi', 'Lato', Arial, sans-serif"
CUERPO = "'Lato', 'Helvetica Neue', Arial, sans-serif"

FONT_FACE_CSS = """
@font-face {
  font-family: 'Satoshi';
  src: url('static/fonts/Satoshi-Medium.otf') format('opentype');
  font-weight: 500;
  font-style: normal;
}
@font-face {
  font-family: 'Satoshi';
  src: url('static/fonts/Satoshi-Bold.otf') format('opentype');
  font-weight: 700;
  font-style: normal;
}
@font-face {
  font-family: 'Lato';
  src: url('static/fonts/Lato-Regular.ttf') format('truetype');
  font-weight: 400;
  font-style: normal;
}
@font-face {
  font-family: 'Lato';
  src: url('static/fonts/LATO-HEAVY.TTF') format('truetype');
  font-weight: 700;
  font-style: normal;
}
"""
