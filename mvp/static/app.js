const form = document.getElementById("form-analizar");
const estadoEl = document.getElementById("estado");
const resultadoEl = document.getElementById("resultado");
const historialEl = document.getElementById("historial");
const btnEnviar = document.getElementById("btn-enviar");
const inputImagenes = document.getElementById("imagenes");

const EXIF_LABELS = {
  camera_brand: "Marca de camara",
  camera_model: "Modelo de camara",
  iso: "ISO",
  aperture: "Apertura",
  focal_length_mm: "Distancia focal (mm)",
};

function mostrarEstado(texto, tipo) {
  estadoEl.textContent = texto;
  estadoEl.className = tipo ? `estado-${tipo}` : "";
  estadoEl.classList.remove("oculto");
}

function ocultarEstado() {
  estadoEl.classList.add("oculto");
}

// --- helpers para armar HTML con negritas reales (nada de "**texto**") ---

function campo(etiqueta, valor) {
  const p = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = `${etiqueta}: `;
  p.appendChild(strong);
  p.appendChild(document.createTextNode(valor ?? "-"));
  return p;
}

function parrafoDestacado(texto) {
  const p = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = texto;
  p.appendChild(strong);
  return p;
}

function seccion(titulo) {
  const div = document.createElement("div");
  div.className = "seccion-resultado";
  const h4 = document.createElement("h4");
  h4.textContent = titulo;
  div.appendChild(h4);
  return div;
}

function renderExif(exif) {
  const div = seccion("Metadatos EXIF");
  const presentes = [];
  const faltantes = [];

  for (const [campoExif, etiqueta] of Object.entries(EXIF_LABELS)) {
    const valor = exif ? exif[campoExif] : null;
    if (valor === null || valor === undefined || valor === "") {
      faltantes.push(etiqueta);
    } else {
      presentes.push([etiqueta, valor]);
    }
  }

  for (const [etiqueta, valor] of presentes) {
    div.appendChild(campo(etiqueta, valor));
  }
  if (faltantes.length) {
    div.appendChild(
      parrafoDestacado(`El archivo no contiene los siguientes datos: ${faltantes.join(", ")}`)
    );
  }
  return div;
}

function renderContenido(contenido) {
  const div = seccion("Analisis de contenido");
  if (!contenido) {
    div.appendChild(campo("Sujeto", "-"));
    return div;
  }
  div.appendChild(campo("Sujeto", contenido.primary_subject));
  div.appendChild(campo("Ambiente", contenido.environment));
  div.appendChild(campo("Keywords", (contenido.keywords || []).join(", ") || "-"));
  div.appendChild(campo("Colores", (contenido.color_palette || []).join(", ") || "-"));
  return div;
}

function renderClasificacion(clasificacion) {
  const div = seccion("Clasificacion comercial");
  div.appendChild(campo("Categoria", clasificacion?.primary_category));
  div.appendChild(campo("Subcategoria", clasificacion?.secondary_category || "-"));
  return div;
}

function renderCalidad(calidad) {
  const div = seccion("Control de calidad");
  const confianza =
    calidad?.confidence_score != null ? calidad.confidence_score.toFixed(2) : "-";
  div.appendChild(campo("Confianza", confianza));

  if (calidad?.flagged_for_review) {
    div.appendChild(parrafoDestacado("Marcada para revision humana"));
    if (calidad.review_reason) {
      div.appendChild(campo("Motivo", calidad.review_reason));
    }
  } else {
    div.appendChild(campo("Revisar", "No"));
  }
  return div;
}

function renderImagenConToggle(archivo, dataUrl) {
  const wrap = document.createElement("div");
  wrap.className = "wrap-imagen";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn-toggle-imagen";
  btn.textContent = "Mostrar foto";

  const img = document.createElement("img");
  img.src = dataUrl;
  img.alt = archivo;
  img.className = "foto-preview oculto";

  btn.addEventListener("click", () => {
    const visible = !img.classList.contains("oculto");
    img.classList.toggle("oculto");
    btn.textContent = visible ? "Mostrar foto" : "Ocultar foto";
  });

  wrap.appendChild(btn);
  wrap.appendChild(img);
  return wrap;
}

function crearTarjetaResultado(r) {
  const item = document.createElement("article");
  item.className = r.error ? "item-historial item-error" : "item-historial";

  const titulo = document.createElement("h3");
  titulo.textContent = r.archivo;
  item.appendChild(titulo);

  if (r.imagen_data_url) {
    item.appendChild(renderImagenConToggle(r.archivo, r.imagen_data_url));
  }

  if (r.error) {
    item.appendChild(parrafoDestacado(r.error));
    return item;
  }

  const datos = r.datos;
  if (!datos) {
    const p = document.createElement("p");
    p.textContent = r.texto || "Sin datos.";
    item.appendChild(p);
    return item;
  }

  if (!datos.ok) {
    item.appendChild(parrafoDestacado(datos.error || "No se pudo analizar esta foto."));
    return item;
  }

  // EXIF va primero, tal como se pidio.
  item.appendChild(renderExif(datos.exif_metadata));
  item.appendChild(renderContenido(datos.content_analysis));
  item.appendChild(renderClasificacion(datos.commercial_classification));
  item.appendChild(renderCalidad(datos.quality_control));

  return item;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resultadoEl.classList.add("oculto");
  btnEnviar.disabled = true;

  const totalFotos = inputImagenes.files.length;
  mostrarEstado(
    `Analizando ${totalFotos} fotografia(s)... esto puede tardar unos segundos por foto.`,
    "cargando"
  );

  const formData = new FormData(form);

  try {
    const response = await fetch("/api/analizar", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      mostrarEstado(data.error || "Ocurrio un error al analizar las fotos.", "error");
      return;
    }

    ocultarEstado();
    const resultados = data.resultados || [];
    const exitosas = resultados.filter((r) => !r.error && r.datos?.ok !== false).length;
    resultadoEl.textContent = `Analizadas ${exitosas}/${resultados.length} foto(s). Ver detalle abajo.`;
    resultadoEl.classList.remove("oculto");

    for (const r of resultados) {
      historialEl.prepend(crearTarjetaResultado(r));
    }
    form.reset();
  } catch (err) {
    mostrarEstado(
      "No se pudo contactar al servidor. Verifica que el backend este corriendo.",
      "error"
    );
  } finally {
    btnEnviar.disabled = false;
  }
});
