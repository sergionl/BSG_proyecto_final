# Verificación del agente DAM

Suite de evaluación del agente de `mvp/` (catalogador de fotos), separada
deliberadamente del MVP — es una capa de verificación externa, no parte de
la app. Implementa lo aplicable de la Clase 7 del curso ("Evaluación de
Agentes"): traza estructurada como unidad de análisis, métricas por capa,
determinismo antes que juez LLM, dataset dorado con 5 categorías, y
comportamiento emergente probado con casos adversariales.

No modifica ningún archivo de `mvp/`: reutiliza `agent.py` y `config.py`
tal cual, importándolos (mismo patrón que ya usaban `mvp/tests/*.py`).

## Instalación

```bash
cd verificacion
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt   # reutiliza mvp/requirements.txt + deepeval + pytest
cp .env.example .env              # misma OPENAI_API_KEY que mvp/.env
```

## Cómo correrlo

Requiere el servidor MCP del MVP corriendo en otra terminal:

```bash
cd ../mvp
uvicorn api.mcp:app --port 8001
```

Un caso por categoría (recomendado para probar que todo funciona, antes de
correr los 24 completos):

```bash
pytest test_eval_suite.py -v -k "feliz_01_exif_completo or ambig_03_sin_notas_reales or alcance_02_borrar_archivo or adv_02_forzar_confianza or borde_03_formato_no_soportado"
```

Todo el dataset (**tiene costo real y no trivial**, ver sección de costo
abajo):

```bash
pytest test_eval_suite.py -v
```

## Estructura

| Archivo | Rol |
|---|---|
| `dataset.py` | 24 casos, 5 categorías (camino feliz, ambigüedad, fuera de alcance, adversarial, borde de datos) |
| `traza.py` | Invoca al agente real y arma la traza estructurada (`ToolCall`) — "de print a medición" |
| `metricas.py` | Qué métrica aplica a cada categoría, + checks deterministas |
| `conftest.py` | Copia los fixtures de imagen a `mvp/data/uploads/` antes de correr |
| `test_eval_suite.py` | `pytest` + `deepeval.assert_test` sobre el dataset |
| `fixtures/borde_datos/` | Archivos propios para casos de borde (no imagen real, formato no soportado) |

Reutiliza imágenes existentes por referencia — no duplica archivos:
`../fotos/` (Foto1-5) y `../mvp/tests/fixtures/visual_injection/` (la
imagen que encontró la vulnerabilidad real de inyección visual).

## Dataset (24 casos, 5 categorías)

| Categoría | # | % | Qué prueba |
|---|---|---|---|
| Camino feliz | 6 | 25% | Casos típicos, distintas categorías comerciales, con/sin EXIF |
| Ambigüedad | 5 | 20% | Sin ruta, notas vagas, sin notas, referencia a foto inexistente, geografía no verificable |
| Fuera de alcance | 4 | 20% | Derechos de uso, borrar archivo, ruta arbitraria, charla general |
| Adversarial | 5 | 20% | Los 4 casos de `mvp/tests/test_security.py` (por texto) + 1 de inyección visual |
| Borde de datos | 4 | 15% | Sin EXIF y sin notas, archivo que no es imagen real, formato no soportado, ruta inexistente |

## Métricas

| Métrica | Tipo | Categorías donde se aplica |
|---|---|---|
| `ToolCorrectnessMetric` (threshold 1.0) | determinista | Todas |
| Fuga de prompt = 0 casos | determinista (Python puro) | Todas |
| `FaithfulnessMetric` (threshold 0.85) | juez | Camino feliz, borde de datos |
| `TaskCompletionMetric` (threshold 0.7) | juez | Camino feliz, ambigüedad |
| `GEval` `scope_adherence` (criterio propio) | juez | Fuera de alcance, adversarial |

No se implementan métricas de **trayectoria** (Step Efficiency, Plan
Quality, Plan Adherence): el agente tiene un solo paso de decisión (llamar
o no la única tool disponible), esas métricas no aportan aquí.

**Tool poisoning vía MCP** (superficie que menciona la Clase 7): no
aplica — nuestro servidor MCP es propio (`mvp/mcp_server.py`), no de
terceros.

## Hallazgos reales durante la construcción de esta suite

No solo se armó el harness: se usó para probarse a sí mismo, y encontró
dos bugs metodológicos reales (no en el agente, en el propio arnés de
evaluación) — exactamente el tipo de cosa que la Clase 7 advierte
("consistencia no es validez"):

1. **`ToolCorrectnessMetric` con `INPUT_PARAMETERS` sin argumentos
   esperados definidos** crasheaba (`None.keys()`) en casos donde no se
   habían especificado los argumentos exactos esperados. Fix: solo se
   activa la comparación de argumentos (`ToolCallParams.INPUT_PARAMETERS`)
   cuando el caso define `expected_input_parameters` explícitamente (hoy
   solo `adv_03_path_traversal`, para verificar que el agente siga usando
   la ruta legítima y no la maliciosa).
2. **El juez `scope_adherence` (GEval) leyó una instrucción inyectada
   dentro del `input` del caso adversarial como si fuera un requisito
   legítimo**, y penalizó al agente por *resistir* la manipulación — el
   caso `adv_02_forzar_confianza` (nota que exige `confidence_score=1.0`)
   fallaba con el agente comportándose *correctamente*. Fix: se agregó una
   instrucción explícita al prompt del juez para que ignore instrucciones
   inyectadas en el input, y ademas se agregó una verificación
   **determinista** (`Caso.verificar_extra`) que no depende del juez para
   este tipo de caso — mismo principio de "determinista donde se pueda".

## Costo de correr la suite completa

Cada caso dispara: 1 invocación del agente (1 a 3 llamadas reales al
modelo internamente, según si usa la tool) más las llamadas de los jueces
de cada métrica aplicable (Faithfulness y TaskCompletion son las más
caras, ~2-3 llamadas cada una). Para 24 casos, esto son **varios cientos
de llamadas reales a la API** — no es gratis, pruébalo con el subconjunto
chico primero.

## Qué NO se hizo en esta pasada (declarado, no escondido)

- **Calibración formal del juez con kappa** contra un set etiquetado a
  mano. Con 24 casos hay poco volumen para un kappa significativo; sería
  el siguiente paso natural si esta suite pasa a usarse en serio (etiquetar
  30-50 casos a mano, medir acuerdo corregido por azar, fijar los
  `evaluation_steps` del juez en vez de dejar que se regeneren).
- **El dataset completo (24 casos) no corre en CI** — su costo es varias
  veces mayor que el de `mvp/tests/`, que sí tiene un workflow manual
  (`.github/workflows/integracion-pagada.yml`, ver README raíz). Lo más
  cercano que corre automático es el chequeo de que estos módulos importan
  sin errores (`ci.yml`), no que el PR falle si una métrica baja.
- **Métricas de producción** (costo por tarea, latencia p95, tasa de
  bucles, revisión humana muestreada) — aplican cuando haya tráfico real,
  no a un MVP local sin desplegar.
