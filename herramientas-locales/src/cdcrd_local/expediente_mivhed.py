"""Inventario documental local del MIVHED. Los resultados son para revisión técnica."""

import hashlib
import json
import ntpath
import os
import re
import stat
from collections import Counter
from pathlib import Path, PureWindowsPath


def registrar(subparsers):
    cmd = subparsers.add_parser(
        "expediente-mivhed", help="Cotejar plantillas y evidencias locales del MIVHED"
    )
    cmd.add_argument(
        "--esquemas",
        type=Path,
        required=True,
        help="Directorio con schema<ID de versión>.json del formulario público",
    )
    cmd.add_argument("--corpus", type=Path, help="JSON opcional del corpus de checklists")
    cmd.add_argument(
        "--evidencias", type=Path, help="Evaluaciones JSON con archivos de respaldo relativos"
    )


def _sin_duplicados(pares):
    datos = {}
    for clave, valor in pares:
        if clave in datos:
            raise ValueError(f"Clave JSON duplicada: {clave}")
        datos[clave] = valor
    return datos


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8-sig"), object_pairs_hook=_sin_duplicados)


def _texto(valor):
    return isinstance(valor, str) and bool(valor.strip())


def _entero(valor):
    return type(valor) is int and valor > 0


def _lista(valor, nombre):
    if not isinstance(valor, list):
        raise ValueError(f"Se esperaba una lista en {nombre}")
    return valor


def _indexar(filas, clave):
    resultado = {}
    for fila in _lista(filas, clave):
        if not isinstance(fila, dict):
            raise ValueError(f"Registro inválido para {clave}")
        valor = fila.get(clave)
        if not (_texto(valor) or _entero(valor)) or valor in resultado:
            raise ValueError(f"{clave} ausente, inválido o repetido: {valor!r}")
        resultado[valor] = fila
    return resultado


def _opciones(prop):
    if prop["type"] == "boolean" and "enum" not in prop and "const" not in prop:
        return ["cumple", "no_cumple"]
    opciones = prop.get("enum")
    if (
        prop["type"] == "string"
        and isinstance(opciones, list)
        and opciones
        and all(v in ("cumple", "no_cumple", "no_aplica") for v in opciones)
        and len(set(opciones)) == len(opciones)
        and "const" not in prop
    ):
        return opciones
    raise ValueError("Tipo o enumeración de respuesta sin soporte")


def _referencias(prop, indice, item):
    ids = _lista(
        prop.get("x_legal_reference_ids", prop["x_basis"].get("legalReferenceIds")),
        "x_legal_reference_ids",
    )
    if not all(_entero(k) for k in ids) or len(set(ids)) != len(ids):
        raise ValueError("IDs de referencia inválidos o repetidos")
    locales = _indexar(item["baseLegal"], "referenceId") if item is not None else {}
    if item is not None and set(locales) != set(ids):
        raise ValueError(f"Las referencias del corpus difieren del esquema para {item['id']}")
    referencias = []
    for k in ids:
        ref = indice[str(k)]
        if ref["referenceId"] != k:
            raise ValueError(f"ID de referencia discordante: {k}")
        archivada = locales[k]["versionArchivada"] if item is not None else None
        if item is not None and type(archivada) is not bool:
            raise ValueError(f"Estado de archivo inválido para la referencia {k}")
        referencias.append(
            {
                "id": k,
                "cita": " ".join((ref.get("citationText") or "").split()),
                "archivada": archivada,
            }
        )
    return referencias


def _plantilla(schema, version_id, corpus):
    plantilla, version = schema["x_template"], schema["x_template_version"]
    codigo = plantilla["code"]
    if (
        not _texto(codigo)
        or not _entero(plantilla["templateId"])
        or version["templateId"] != plantilla["templateId"]
        or version["templateVersionId"] != version_id
    ):
        raise ValueError(f"Identidad incompatible con schema{version_id}.json")
    if corpus is not None and (codigo, plantilla["templateId"], version["versionNumber"]) != (
        corpus["codigo"],
        corpus["templateId"],
        corpus["version"],
    ):
        raise ValueError(f"Identidad o versión del corpus incompatible para {codigo}")
    locales = _indexar(corpus["items"], "itemId") if corpus is not None else {}
    indice = schema["x_normative_index"]["legalReferences"]
    condiciones = {}
    for condicion in schema.get("allOf", []):
        for clave, condicion_valor in condicion.get("if", {}).get("properties", {}).items():
            valor = condicion_valor.get("const")
            respuesta = "no_cumple" if valor is False else valor
            sufijo = {"no_cumple": "_nc_reasons", "no_aplica": "_na_reasons"}.get(respuesta)
            campos = condicion.get("then", {}).get("required", [])
            if sufijo and clave + sufijo in campos:
                condiciones.setdefault(clave, []).append(respuesta)
    filas = []
    for clave, prop in schema["properties"].items():
        if not re.fullmatch(r"item_[0-9]+", clave):
            continue
        info = prop["x_item"]
        ident, numero = info["templateItemId"], info["displayNumber"]
        if not _entero(ident) or not _entero(numero) or clave != f"item_{ident}":
            raise ValueError(f"ID o número de ítem incompatible en {codigo}/{clave}")
        item_key = f"{codigo}#{numero}"
        locales_item = locales.pop(ident) if corpus is not None else None
        titulo = " ".join(prop["title"].split())
        if locales_item is not None and (
            locales_item["id"],
            locales_item["numero"],
            " ".join(locales_item["descripcion"].split()),
        ) != (item_key, numero, titulo):
            raise ValueError(f"El criterio del corpus difiere de {item_key}")
        opciones = _opciones(prop)
        discrepa = None
        if locales_item is not None:
            heredadas = [s.strip().lower().replace(" ", "_") for s in locales_item["evaluacion"]]
            discrepa = set(heredadas) != set(opciones)
        referencias = _referencias(prop, indice, locales_item)
        filas.append(
            {
                "criterio": item_key,
                "lista": codigo,
                "numero": numero,
                "itemId": ident,
                "descripcion": titulo,
                "version": version["versionNumber"],
                "templateVersionId": version_id,
                "opciones": opciones,
                "opciones_difieren_corpus": discrepa,
                "referencias": referencias,
                "justificacion_normativa": prop["x_basis"].get("authorJustificationText"),
                "requiere_nota_nc": bool(info.get("nonComplianceNoteRequired")),
                "requiere_motivo": condiciones.get(clave, []),
                "motivos": {r["number"]: r["reasonKind"] for r in prop.get("x_reasons", [])},
                "estado": "sin_evaluar",
            }
        )
    filas.sort(key=lambda fila: fila["numero"])
    if not filas or locales or [fila["numero"] for fila in filas] != list(range(1, len(filas) + 1)):
        raise ValueError(f"Secuencia de ítems o cobertura del corpus incompatible para {codigo}")
    return filas


def _catalogo(esquemas, ruta_corpus):
    comprobadas = None
    if ruta_corpus is not None:
        corpus = _leer(ruta_corpus)
        if corpus["_meta"]["esquema"] != "mivhed-norm-checklists/1":
            raise ValueError("Esquema del corpus no reconocido")
        comprobadas = _indexar(corpus["checklists"], "templateVersionId")
        versiones = list(comprobadas)
    else:
        versiones = [
            int(m[1])
            for ruta in sorted(esquemas.glob("schema*.json"))
            if (m := re.fullmatch(r"schema([1-9][0-9]*)[.]json", ruta.name))
        ]
    if not versiones or not all(_entero(v) for v in versiones):
        raise ValueError("Sin versiones válidas de plantillas")
    filas = []
    for v in versiones:
        ruta = esquemas / f"schema{v}.json"
        if not ruta.is_file():
            raise ValueError(f"Falta schema{v}.json")
        filas.extend(
            _plantilla(_leer(ruta)["jsonSchema"], v, comprobadas[v] if comprobadas else None)
        )
    return _indexar(filas, "criterio")


def _reservado_windows(nombre):
    # ntpath también expone la semántica Windows en hosts POSIX.
    if hasattr(ntpath, "isreserved"):
        return ntpath.isreserved(nombre)
    return any(PureWindowsPath(p).is_reserved() for p in PureWindowsPath(nombre).parts)


def _fuente(dato, base):
    nombre = dato.get("archivo")
    if not _texto(nombre):
        raise ValueError("Falta el archivo de evidencia")
    ruta = Path(nombre)
    win = PureWindowsPath(nombre)
    if (
        ruta.is_absolute()
        or win.drive
        or win.root
        or ".." in win.parts
        or ":" in nombre
        or _reservado_windows(nombre)
    ):
        raise ValueError("El archivo debe ser relativo a la carpeta del manifiesto")
    destino = (base / ruta).resolve()
    if not destino.is_relative_to(base):
        raise ValueError("El archivo de evidencia queda fuera del expediente")
    loc = dato.get("localizador")
    salida = {"archivo": nombre, "localizador": loc, "sha256": None}
    problemas = []
    if not _texto(loc):
        problemas.append("Falta localizador de evidencia (lámina, página, objeto o tabla)")
    return destino, salida, problemas


def _firma(estado):
    return estado.st_dev, estado.st_ino, estado.st_size, estado.st_mtime_ns


def _huella_estable(destino):
    try:
        inicial = destino.stat()
        if not stat.S_ISREG(inicial.st_mode):
            return None, None, "La evidencia debe ser un archivo regular"
        with destino.open("rb") as stream:
            firma = _firma(os.fstat(stream.fileno()))
            if firma == _firma(inicial):
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if firma == _firma(os.fstat(stream.fileno())) == _firma(destino.stat()):
                    return firma, digest, None
        return None, None, "El archivo cambió durante la lectura"
    except FileNotFoundError:
        return None, None, "Archivo ausente o retirado"
    except OSError as exc:
        return None, None, f"No se pudo verificar el archivo ({type(exc).__name__})"


def _adjuntar_huellas(usos, base):
    # La misma edición respalda todas sus citas. Revalidar después de leer
    # el último archivo detecta también cambios mientras se verificaban otros.
    cache = {ruta: _huella_estable(ruta) for ruta in usos}
    for ruta, citas in usos.items():
        firma, digest, error = cache[ruta]
        if not error:
            try:
                if _firma(ruta.stat()) != firma:
                    error = "El archivo cambió antes de cerrar el inventario"
            except OSError:
                error = "El archivo dejó de estar disponible antes de cerrar el inventario"
        for fila, salida, declarada in citas:
            problema = error
            if not problema:
                # Un alias declarado puede cambiar de destino mientras el archivo
                # original continúa intacto.
                if (base / salida["archivo"]).resolve() != ruta:
                    problema = "Cambió el destino de la ruta de evidencia"
                else:
                    salida["sha256"] = digest
                    if "sha256" in declarada and declarada["sha256"] != digest:
                        problema = "SHA-256 discordante"
            if problema:
                fila["incidencias"].append(f"{problema}: {salida['archivo']}")
                if fila["estado"] == "documentada":
                    fila["estado"] = "evidencia_incompleta"


def _vincular(filas, ruta):
    base = ruta.resolve().parent
    evaluaciones = _indexar(_leer(ruta)["evaluaciones"], "criterio")
    usos = {}
    for clave, dato in evaluaciones.items():
        if clave not in filas:
            raise ValueError(f"Criterio desconocido: {clave}")
        fila = filas[clave]
        if (
            not _entero(dato.get("templateVersionId"))
            or dato["templateVersionId"] != fila["templateVersionId"]
        ):
            raise ValueError(f"Versión de evaluación incompatible: {clave}")
        respuesta, nota = dato["respuesta"], dato.get("justificacion")
        fuentes, problemas = [], []
        for fuente in _lista(dato.get("fuentes", []), "fuentes"):
            if not isinstance(fuente, dict):
                raise ValueError("Formato inválido de fuente de evidencia")
            destino, verificada, notas = _fuente(fuente, base)
            usos.setdefault(destino, []).append((fila, verificada, fuente))
            fuentes.append(verificada)
            problemas.extend(notas)
        if not fuentes:
            problemas.append("Falta evidencia vinculada")
        if (
            respuesta == "no_aplica" or (respuesta == "no_cumple" and fila["requiere_nota_nc"])
        ) and not _texto(nota):
            problemas.append("Falta justificación de la respuesta")
        motivos = _lista(dato.get("motivos", []), "motivos")
        if all(isinstance(m, str) for m in motivos) and len(set(motivos)) != len(motivos):
            problemas.append("Los motivos deben ser únicos")
        tipo = {"no_cumple": "non_compliance", "no_aplica": "not_applicable"}.get(respuesta)
        if respuesta in fila["requiere_motivo"] and not motivos:
            problemas.append("Falta motivo requerido por el formulario")
        if any(
            not _texto(m) or m not in fila["motivos"] or fila["motivos"][m] != tipo for m in motivos
        ):
            problemas.append("Motivo incompatible con el criterio y la respuesta")
        estado = "evidencia_incompleta" if problemas else "documentada"
        if respuesta not in fila["opciones"]:
            estado = "respuesta_invalida"
            problemas.append("Respuesta ausente del esquema oficial")
        fila.update(
            respuesta=respuesta,
            motivos_declarados=motivos,
            justificacion=nota,
            fuentes=fuentes,
            incidencias=problemas,
            estado=estado,
        )
    _adjuntar_huellas(usos, base)


def ejecutar(args):
    """Un documento puede respaldar una declaración sin demostrar su corrección técnica."""
    try:
        filas = _catalogo(args.esquemas, args.corpus)
        if args.evidencias is not None:
            _vincular(filas, args.evidencias)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Formato de entrada MIVHED inválido: {exc}") from exc
    estados = Counter(f["estado"] for f in filas.values())
    resumen = {
        "listas": len({f["lista"] for f in filas.values()}),
        "criterios": len(filas),
        "opciones_discrepantes": sum(f["opciones_difieren_corpus"] is True for f in filas.values()),
        "referencias_archivadas": sum(
            r["archivada"] is True for f in filas.values() for r in f["referencias"]
        ),
        "referencias_sin_estado": sum(
            r["archivada"] is None for f in filas.values() for r in f["referencias"]
        ),
        "sin_base_legal_ni_justificacion": sum(
            not f["referencias"] and not _texto(f["justificacion_normativa"])
            for f in filas.values()
        ),
        "sin_evaluar": estados["sin_evaluar"],
        "documentadas": estados["documentada"],
        "respuestas_invalidas": estados["respuesta_invalida"],
        "evidencias_incompletas": estados["evidencia_incompleta"],
    }
    return {
        "corpus_contrastado": args.corpus is not None,
        "alcance": "Inventario y trazabilidad documental para revisión profesional",
        "resumen": resumen,
        "criterios": list(filas.values()),
    }
