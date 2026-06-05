"""Consentimiento parental para menores · M-006 (2026-06-04).

Texto que el padre/madre/acudiente lee y FIRMA (e-sign nativo) para autorizar
que un estudiante MENOR DE 16 use la plataforma (tests vocacionales + journey).
Cumplimiento Ley 1581/2012 (Colombia) · GDPR cuando aplique.

⚠️ TEXTO PLACEHOLDER · pendiente del texto legal LITERAL del cliente.
Subir `CONSENT_VERSION` cuando cambie el texto.
"""

# Edad bajo la cual se exige consentimiento parental para usar la plataforma.
MINOR_AGE_THRESHOLD = 16

CONSENT_VERSION = "v1-draft"

# Validez del enlace de firma enviado al acudiente.
CONSENT_TOKEN_TTL_HOURS = 72

# [TEXTO LEGAL PENDIENTE DEL CLIENTE] — placeholder de trabajo.
CONSENT_TEXT = (
    "Como padre, madre o acudiente, autorizo a que el/la estudiante menor de "
    "edad a mi cargo utilice la plataforma Grasshopper, incluyendo la "
    "realización de tests de orientación vocacional y su acompañamiento. "
    "Entiendo que los resultados son orientativos, no constituyen un "
    "diagnóstico clínico, y que el tratamiento de los datos personales se "
    "realiza conforme a la política de privacidad de Grasshopper y a la Ley "
    "1581 de 2012 (y al GDPR cuando aplique). Declaro ser el adulto "
    "responsable del/la estudiante y otorgar este consentimiento de forma "
    "libre e informada. "
    "[TEXTO LEGAL PENDIENTE DE CONFIRMACIÓN DEL CLIENTE]"
)
