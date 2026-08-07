# Auditoría del servidor FEA-MCP v1.1.0 — 2026-08-07

Contexto: ETABS 23.3.0 / OAPI 2.016 · comtypes 1.4.16 · Python 3.14.6 (64-bit) ·
`mcp` 1.29.0. Auditoría disparada por el bloqueo de `set_stories` en el bloque R02
del protocolo de revisión, extendida a todo el servidor para no gastar un reinicio
de Claude Desktop por cada defecto.

**Cada reinicio cuesta un ciclo completo de operador.** Este documento está ordenado
para que **un solo reinicio** cierre el máximo de incógnitas.

---

## 0. Hechos verificados en esta sesión

Distinguir lo verificado de lo conjeturado es el punto entero de este documento
(ver [[ERRORES-IA]] E-005, E-015).

### 0.1 Layout de `_methods_` en comtypes 1.4.16 — VERIFICADO

Leído del fuente del wheel instalado (`comtypes/_memberspec.py`):

```python
class _ComMemberSpec(NamedTuple):
    restype     # [0]
    name        # [1]  <-- el nombre del metodo esta ACA
    argtypes    # [2]  <-- lo que describe() lee como si fuera el nombre
    paramflags  # [3]  tuple[(pflags:int, argname:str[, default]), ...]
    idlflags    # [4]  contiene el dispid como int
    doc         # [5]
```

```python
class _DispMemberSpec(NamedTuple):
    what, name, idlflags, restype, argspec      # 5 campos, layout distinto
```

Máscara de `pflags`: `1=in`, `2=out`, `4=lcid`, `8=retval`, `16=optional`.
De ahí que `3 = in/out` y `10 = out|retval`.

`COMMETHOD(idlflags, restype, methodname, *argspec)` **no conserva el argspec**:
`_resolve_argspec` lo descompone en `argtypes` + `paramflags`. La suposición del
código actual (`COMMETHOD(flags, restype, name, *argspec)`) corresponde a una
versión anterior de comtypes.

### 0.2 Estado del modelo tras R02 — VERIFICADO en runtime

- Conexión: ETABS 23.3.0, OAPI 2.016, `edificio_oficinas_SD.EDB`.
- Unidades: abrió en `lb, in, F`; corregidas a `kN, m, C` con `set_units`.
- Geometría: 36 puntos, 63 frames (27 columnas + 36 vigas), 12 áreas.
  Sin coordenadas duplicadas, sin frames duplicados por extremos, sin nodos
  sin ningún frame conectado. **Criterio de R02 cumplido.**
- Niveles: siguen siendo los 4 originales de 3.6576 m (12 ft). `set_stories`
  nunca llegó a aplicarse; los intentos fallidos fueron rechazos atómicos, el
  modelo no quedó corrupto (confirmado releyendo `get_stories`).

### 0.3 Orden de arrays en `GetStories_2` — VERIFICADO en runtime

`get_stories()` devolvió:

```
Story1: elevacion 3.6576,  altura 3.6576
Story4: elevacion 14.6304, altura 3.6576
```

`get_stories` lee `numeric[0]` como elevación y `numeric[1]` como altura, y
`find_num_lists` preserva el orden de los parámetros `[out]`. La primera lista es
creciente y la segunda constante. Por lo tanto, en esta instalación
**`StoryElevations` precede a `StoryHeights`**.

### 0.4 Firma de `SetStories` — DERIVADA de dos errores, no leída del typelib

- `(n,) + 6 arrays` → `argument 1: object of type 'int' has no len()`
  ⇒ el primer parámetro es un SAFEARRAY, **no hay conteo líder**.
- `6 arrays` sin conteo → `required argument 'SpliceHeight' missing`
  ⇒ son **siete** arrays; al omitir uno, todo se corre y el último queda vacío.
- `7 arrays` con orden `(names, heights, elevations, ...)` → `ret=1`
  ⇒ marshalea bien (ambos son `double[]`) pero ETABS rechaza el contenido.

Hipótesis resultante, coherente con 0.3:

```
SetStories(StoryNames[], StoryElevations[], StoryHeights[],
           IsMasterStory[], SimilarToStory[], SpliceAbove[], SpliceHeight[])
```

**No confirmada contra el typelib** porque `describe_oapi` está roto (§1).
Arreglar `describe` es lo que convierte esta hipótesis en un hecho.

---

## 1. BLOQUEANTE — `oapi.py::describe()` lee el campo equivocado

**Es el defecto que hace caro todo lo demás.** Con `describe` funcionando, un solo
reinicio permite volcar las firmas reales de todos los namespaces que usan R03..R10
y cerrar de golpe todas las sospechas de este documento, en vez de gastar un
reinicio por método.

Actual (`oapi.py` ~L227): `name = entry[2]` (devuelve `argtypes`) y
`argspecs = entry[3:]` (devuelve `(paramflags, idlflags, doc)`). Luego
`_decode_argspec` desempaqueta `paramflags` como si fuera un argspec único.
Resultado: nombres de método como tuplas de clases, y el filtro por substring
nunca coincide → cae al fallback engañoso "typelib no generado".

### Parche: reemplazar `oapi.py` líneas 202-255

```python
# Mascara PARAMFLAG_* de comtypes/_memberspec.py (verificado en 1.4.16).
_PARAMFLAG_BITS = ((1, "in"), (2, "out"), (4, "lcid"), (8, "retval"), (16, "optional"))
_PARAMFLAG_BY_NAME = {n: b for b, n in _PARAMFLAG_BITS}

_TYPE_ALIASES = {
    "c_double": "double", "c_float": "float", "c_long": "long", "c_int": "int",
    "c_short": "short", "c_ubyte": "byte", "c_longlong": "int64",
    "c_wchar_p": "wstr", "c_char_p": "str", "VARIANT_BOOL": "bool",
}


def _type_name(t: Any) -> str:
    """Nombre legible de un tipo ctypes/comtypes.

    POINTER(SAFEARRAY_X) lleva _itemtype_, asi que se detecta antes que el
    desempaquetado generico de puntero.
    """
    if t is None:
        return "void"
    item = getattr(t, "_itemtype_", None)
    if item is not None:
        return f"SAFEARRAY({_type_name(item)})"
    pointee = getattr(t, "_type_", None)   # en tipos simples es un str ('l','X')
    if isinstance(pointee, type):
        return _type_name(pointee) + "*"
    name = getattr(t, "__name__", None) or str(t)
    return _TYPE_ALIASES.get(name, name)


def _flag_names(pflags: Any) -> str:
    try:
        bits = int(pflags)
    except Exception:
        return str(pflags)
    names = [n for b, n in _PARAMFLAG_BITS if bits & b]
    return ",".join(names) if names else "none"


def _unpack_spec(entry: Any):
    """Normaliza una entrada de _methods_ / _disp_methods_.

    _ComMemberSpec (COMMETHOD/STDMETHOD) es un NamedTuple de 6 campos:
        (restype, name, argtypes, paramflags, idlflags, doc)
    _DispMemberSpec (DISPMETHOD/DISPPROPERTY) es de 5:
        (what, name, idlflags, restype, argspec)
    """
    what = entry[0] if isinstance(entry, tuple) and entry else None
    if isinstance(what, str) and what.startswith("DISP"):
        _w, name, idlflags, restype, argspec = entry[:5]
        params = []
        for i, item in enumerate(argspec or ()):
            idl = item[0] if len(item) > 0 else []
            typ = item[1] if len(item) > 1 else None
            argname = item[2] if len(item) > 2 else None
            bits = sum(_PARAMFLAG_BY_NAME.get(x, 0) for x in idl)
            params.append((bits or None, argname or f"arg{i}", typ, ""))
        return name, restype, params, tuple(idlflags or ())

    restype, name, argtypes, paramflags, idlflags, _doc = (list(entry) + [None] * 6)[:6]
    params = []
    for i, atype in enumerate(argtypes or ()):
        pf = paramflags[i] if paramflags and i < len(paramflags) else None
        if pf:
            bits = pf[0]
            argname = pf[1] if len(pf) > 1 and pf[1] else f"arg{i}"
            default = f" = {pf[2]!r}" if len(pf) > 2 else ""
        else:                       # STDMETHOD: no hay paramflags
            bits, argname, default = None, f"arg{i}", ""
        params.append((bits, argname, atype, default))
    return name, restype, params, tuple(idlflags or ())


def _format_method(entry: Any) -> tuple[str, str]:
    """Devuelve (nombre_plano_para_filtrar, linea_legible)."""
    name, restype, params, idlflags = _unpack_spec(entry)
    plain, kind = name or "?", ""
    for prefix, tag in (("_get_", "propget"), ("_set_", "propput"),
                        ("_setref_", "propputref")):
        if plain.startswith(prefix):
            plain, kind = plain[len(prefix):], tag
            break
    sig = ", ".join(
        f"[{_flag_names(b) if b is not None else '?'}] {n}: {_type_name(t)}{d}"
        for b, n, t, d in params)
    # comtypes devuelve, en orden, los parametros out|retval.
    returns = [n for b, n, _t, _d in params if b is not None and (b & 10)]
    extra = []
    if kind:
        extra.append(kind)
    dispid = next((f for f in idlflags if isinstance(f, int)), None)
    if dispid is not None:
        extra.append(f"dispid {dispid}")
    if returns:
        extra.append("py-> (" + ", ".join(returns) + ")")
    tail = ("   [" + "; ".join(extra) + "]") if extra else ""
    return plain, f"{plain}({sig}) -> {_type_name(restype)}{tail}"


def _iter_specs(interface: Any):
    """Recolecta _methods_/_disp_methods_ propios de cada clase COM del MRO.

    POINTER(cStory) hereda _methods_ de cStory, pero vars(POINTER(cStory))
    esta vacio: hay que recorrer el MRO.
    """
    seen = set()
    for klass in getattr(interface, "__mro__", [interface]):
        if getattr(klass, "__name__", "") in (
                "IUnknown", "IDispatch", "_compointer_base", "object", "c_void_p"):
            continue
        for attr in ("_methods_", "_disp_methods_"):
            for entry in vars(klass).get(attr, ()) or ():
                if id(entry) in seen:
                    continue
                seen.add(id(entry))
                yield entry


def describe(obj: Any, filter_text: str = "") -> str:
    """Describe los metodos de un objeto COM de la OAPI con su firma real."""
    needle = filter_text.strip().lower()
    interface = type(obj)
    com_itf = getattr(interface, "__com_interface__", interface)
    itf_name = getattr(com_itf, "__name__", str(com_itf))

    specs = list(_iter_specs(interface))
    if specs:
        total, lines = 0, []
        for entry in specs:
            try:
                plain, line = _format_method(entry)
            except Exception as e:
                lines.append(f"(entrada no interpretable: {e!r})")
                continue
            total += 1
            if needle and needle not in plain.lower():
                continue
            lines.append(line)
        if needle and not lines:
            return (f"{itf_name}: ninguno de los {total} metodos coincide con "
                    f"'{filter_text}'. Llame sin filtro para ver la lista completa.")
        header = f"{itf_name}: {len(lines)} de {total} metodo(s)"
        if needle:
            header += f" que coinciden con '{filter_text}'"
        return header + "\n" + "\n".join(sorted(lines))

    # Ruta 2: solo nombres (late binding sin typelib generado).
    lines = [n for n in dir(obj)
             if not n.startswith("_") and (not needle or needle in n.lower())]
    if not lines:
        return (f"{itf_name}: sin metodos visibles"
                f"{' que coincidan con ' + filter_text if needle else ''} "
                f"(typelib no generado; solo late binding).")
    return (f"{itf_name}: {len(lines)} nombre(s) (sin firma: typelib no generado)\n"
            + "\n".join(sorted(lines)))
```

El sufijo `py-> (...)` es deliberado: declara exactamente qué tupla devuelve
comtypes, que es justo lo que `outs()`/`ret_code()` necesitan y lo que hace falta
para auditar los defectos de columnas de §3.

Salida esperada tras el parche:

```
cStory: 1 de 17 metodo(s) que coinciden con 'SetStories'
SetStories([in] StoryNames: SAFEARRAY(BSTR), [in] StoryElevations: SAFEARRAY(double),
           [in] StoryHeights: SAFEARRAY(double), [in] IsMasterStory: SAFEARRAY(bool),
           [in] SimilarToStory: SAFEARRAY(BSTR), [in] SpliceAbove: SAFEARRAY(bool),
           [in] SpliceHeight: SAFEARRAY(double), [out,retval] pRetVal: long*)
           -> HRESULT   [dispid 15; py-> (pRetVal)]
```

---

## 2. BLOQUEANTE — `set_stories`: elevaciones y alturas invertidas

`Etabs.py::set_stories`. Tres defectos en el mismo método.

1. **Orden invertido.** Pasa `(names, heights, elevations, ...)`. Según §0.3 debe
   ser `(names, elevations, heights, ...)`. Al ser ambos `double[]`, marshalea sin
   error y ETABS lo rechaza con `ret=1` silencioso: le está llegando `[3,3,3]` como
   elevaciones, o sea tres niveles en la misma cota.
2. **El respaldo `SetStories_2` no incluye elevaciones en absoluto.** Está
   garantizado a fallar aunque la primaria se corrija.
3. **Convención de master invertida.** El código marca master al nivel más alto y
   hace que los inferiores le apunten. La configuración *siempre* válida —y el
   default correcto para una herramienta genérica— es **todos master, ninguno
   similar**: es lo que ETABS genera cuando las plantas no se declaran repetidas y
   no puede ser rechazada.

### Parche

```python
        # Todos master es la configuracion siempre valida: ETABS solo exige
        # coherencia cuando se declaran niveles similares. La version anterior
        # (todos False, ninguno master) es invalida -> ret=1 silencioso.
        is_master_all = [True] * n
        similar_none = [""] * n
        is_master_top = [False] * (n - 1) + [True]
        similar_top = [names[-1]] * (n - 1) + [""]
        splice_above = [False] * n
        splice_height = [0.0] * n
        color = [0] * n

        elevations: list[float] = []
        acc = float(base_elevation)
        for h in heights:
            acc += h
            elevations.append(acc)

        # SetStories(StoryNames[], StoryElevations[], StoryHeights[],
        #            IsMasterStory[], SimilarToStory[], SpliceAbove[],
        #            SpliceHeight[])
        # ELEVACIONES ANTES QUE ALTURAS: es el orden que devuelve GetStories_2
        # en esta instalacion y el que asume get_stories() en este archivo.
        def _siete(master, similar):
            return (names, elevations, heights, master, similar,
                    splice_above, splice_height)

        def _s2(master, similar, with_color):
            base = (float(base_elevation), n, names, elevations, heights,
                    master, similar, splice_above, splice_height)
            return base + ((color,) if with_color else ())

        oapi.call(
            model.Story,
            [
                ("SetStories",   _siete(is_master_all, similar_none)),
                ("SetStories",   _siete(is_master_top, similar_top)),
                ("SetStories_2", _s2(is_master_all, similar_none, True)),
                ("SetStories_2", _s2(is_master_all, similar_none, False)),
            ],
            "definicion de niveles",
        )
```

Eliminar la tupla `common` que queda huérfana.

> **Verificación obligatoria tras aplicar.** Si el orden real fuera el contrario,
> la primera variante marshalea igual y podría devolver `ret=0` creando niveles con
> cotas y alturas cruzadas. Llamar `get_stories()` inmediatamente después: las
> elevaciones deben ser 3/6/9 y las alturas 3/3/3. Si salen invertidas, es la señal.

**Nota:** `base_elevation` solo se aplica si cae a `SetStories_2`; la variante de 7
arrays no tiene ese parámetro. Con `base_elevation=0` (el caso del protocolo) es
inocuo, pero conviene un `logger.warning` si llega distinto de 0.

---

## 3. BLOQUEANTE — columnas corridas en reacciones y fuerzas (R10)

`get_joint_reactions` y `get_frame_forces`. Dos defectos en cada uno.

**(a) `force_cols[:6]` toma las primeras seis columnas numéricas.** Pero `StepNum`
también es numérico de longitud `n` y va **antes** de `F1`:

- `JointReact` → `NumberResults, Obj[], Elm[], LoadCase[], StepType[], StepNum[], F1..F3, M1..M3`.
  Las 6 primeras son `StepNum,F1,F2,F3,M1,M2` etiquetadas `F1..M3`. Todo corrido, M3 perdido.
- `FrameForce` → `..., ObjSta[], ElmSta[], StepNum[], P, V2, V3, T, M2, M3`.
  Hay **tres** columnas numéricas antes de P. La salida son números plausibles y
  completamente equivocados.

**(b) `case_col = strs[0]` es el nombre del objeto, no el caso.** Los arrays de
string son `Obj, Elm, LoadCase, StepType`; `strs[0]` es `Obj`, o sea el mismo
`pid`/`fid` repetido. El nombre del caso nunca se muestra.

### Parche (idéntico en ambos métodos, ajustando `pid`/`fid`)

```python
            strs = oapi.find_str_lists(r, n)
            nums = oapi.find_num_lists(r, n)
            # LoadCase es la 3a lista de strings (Obj, Elm, LoadCase, StepType).
            case_col = strs[2] if len(strs) > 2 else (strs[0] if strs else ["?"] * n)
            # Las componentes de fuerza son las SEIS ULTIMAS columnas numericas:
            # StepNum (y ObjSta/ElmSta en FrameForce) tambien tienen longitud n
            # y preceden a la primera componente, por eso [:6] estaba corrido.
            force_cols = nums[-6:] if len(nums) >= 6 else nums
            for i in range(n):
                vals = ", ".join(f"{c[i]:.3f}" for c in force_cols)
                results.append(f"{pid} | {case_col[i]} | [{vals}]")
```

Confirmar el orden real con `describe_oapi(path="Results", filter="JointReact")`
una vez aplicado §1.

---

## 4. BLOQUEANTE — materiales sin peso por unidad de volumen

`define_concrete_material` y `define_steel_material` llaman `SetMaterial`,
`SetMPIsotropic` y `SetOConcrete_1`/`SetOSteel_1`, pero **nunca
`SetWeightAndMass`**. Un material creado por API arranca con peso por unidad de
volumen 0.

Cadena de consecuencias: `add_load_pattern("D", ..., self_weight_multiplier=1.0)`
en R05 genera **peso propio nulo**. R08, R09 y R10 producen resultados
numéricamente coherentes y sin ningún error visible, pero sin carga muerta propia.
Las derivas de R09 y las reacciones de R10 saldrían mal y el chequeo de equilibrio
cerraría igual, porque el error es consistente.

**Es el defecto más peligroso del conjunto: no lanza ninguna excepción.**

### Parche (preferir el parámetro explícito, no la conversión de unidades encadenada)

```python
    def define_concrete_material(self, name: str, fc: float,
                                 E: float = 0.0, poisson: float = 0.2,
                                 unit_weight: float = 0.0) -> str:
        ...
        # unit_weight en las UNIDADES ACTIVAS. Con kN, m: 23.5631 (= 2400 kgf/m3).
        if unit_weight > 0:
            oapi.call(model.PropMaterial,
                      [("SetWeightAndMass", (name, 1, float(unit_weight)))],
                      f"peso por unidad de volumen de '{name}'")
        else:
            logger.warning("Material '%s' creado sin peso por unidad de volumen: "
                           "el peso propio del patron D sera 0.", name)
```

El protocolo ya fija `kN, m, C` antes de R03, así que el valor explícito es seguro.
Análogo para acero (77.0 kN/m³).

---

## 5. BLOQUEANTE — `define_steel_material`: parámetros corridos

Firma real:

```
SetOSteel_1(Name, Fy, Fu, EFy, EFu, SSType, SSHysType,
            StrainAtHardening, StrainAtMaxStress, StrainAtRupture,
            FinalSlope, Temp=0)
```

El código pasa `..., 0.02, 0.1, -0.1, 0.0)` ⇒ `StrainAtRupture = -0.1`
(deformación negativa, imposible) y `FinalSlope = 0.0`. Es el patrón de
`SetOConcrete_1` copiado tal cual, donde `-0.1` sí era `FinalSlope`.

```python
        oapi.call(
            model.PropMaterial,
            # StrainAtHardening=0.02, StrainAtMaxStress=0.10,
            # StrainAtRupture=0.20, FinalSlope=-0.10.
            [("SetOSteel_1", (name, float(fy), float(fu), float(fy), float(fu),
                              1, 0, 0.02, 0.10, 0.20, -0.10)),
             ("SetOSteel_1", (name, float(fy), float(fu), float(fy), float(fu),
                              1, 0, 0.02, 0.10, 0.20, -0.10, 0.0))],
            f"parametros de acero de '{name}'",
        )
```

La variante de respaldo original (`SetOSteel` con 7 args) también era inválida:
`SetOSteel` tiene los mismos 11 parámetros.

---

## 6. BLOQUEANTE (latente) — `_add_point` vs `_add_frame`: manejo contradictorio de `ref string Name`

| Método | Llamada | Trata `Name` como |
|---|---|---|
| `_add_point` | `AddCartesian(x, y, z)` → desempaqueta `name, ret` | `[out]` puro |
| `_add_frame` | `AddByCoord(xi..zj, "", prop)` → desempaqueta `name, ret` | `[in,out]` |

Las dos declaran `Name` igual en la OAPI, así que **no pueden estar ambas bien**.
Si `Name` es `[out]` puro, `_add_frame` está silenciosamente desalineado: `""` cae
en `PropName` y `prop` cae en `UserName`, creando frames **sin sección asignada**
con `ret=0`.

**No sirve resolverlo con variantes de `oapi.call`**: la variante equivocada
devuelve `ret=0`. Hay que leerlo del typelib (§1).

**Impacto en R03..R10: nulo** — la geometría ya existe y ninguno de los 15 métodos
del protocolo llama a `_add_*`. Se reporta porque `create_objects_by_coordinates`
sigue expuesta como herramienta y porque es exactamente el patrón que causó el
bloqueo de R02.

---

## 7. MEDIOS

| # | Defecto | Efecto |
|---|---|---|
| 7.1 | `add_load_combo`: `SetCaseList` **agrega**, no reemplaza | Reejecutar produce `1.2D+1.2D+1.6L+1.6L`. Borrar el combo antes de recrearlo |
| 7.2 | `add_load_pattern` / `add_load_combo` no idempotentes | `Add` falla si el nombre existe ⇒ reintentar R05/R07 tras un fallo parcial revienta. Envolver en try/except y actualizar en su lugar |
| 7.3 | `_read_areas`: base del índice de `PointDelimiter` (0 o 1) no es contractual | Un off-by-one mezcla vértices entre áreas contiguas **sin cambiar el conteo de 12**. Rompe el filtro por elevación de `assign_area_uniform_load` (R05). Usar `NumberBoundaryPts` en su lugar |
| 7.4 | `add_time_history_case`: `ModHistoryLinear`/`ModHistoryNonlinear` no existen | Los namespaces reales son `ModHistLinear`/`ModHistNonlinear`. `AttributeError` crudo fuera de `oapi.call`. Además `SetLoads` se llama con 9/7 args contra una firma de 10 |
| 7.5 | `run_analysis` sin guarda de modelo guardado | ETABS exige archivo en disco; el fallo llega como `ret≠0` opaco |
| 7.6 | `comthread`: `.result()` sin timeout con `max_workers=1` | Un diálogo modal en ETABS cuelga **todas** las herramientas siguientes, para siempre, sin error |
| 7.7 | `set_table_data`: `TableVersion=1` literal | ETABS lo usa para detectar que se escribe contra el mismo esquema leído. Debe leerse con `GetTableForEditingArray` antes |
| 7.8 | `oapi.call` trata `code is None` como éxito | Un `[out,retval] VARIANT_BOOL` que devuelve `False` se reporta OK |

---

## 8. MENORES

- Coeficiente de dilatación térmica `9.9e-6`/`11.7e-6` (valores por °C) pasado sin
  importar si las unidades activas son °F. Inocuo sin caso térmico, pero queda un
  valor incorrecto en el .EDB.
- `set_base_restraints`: la lista `values` se construye una vez y se reutiliza en el
  bucle de todos los puntos. Si el array es `[in,out]`, comtypes puede mutarla tras
  la primera llamada. Copiar por iteración.
- `define_cdcrd_spectrum`: si `Ts >= t_max` el espectro queda sin rama descendente,
  en silencio. Validar y lanzar.
- `add_response_spectrum_case` no fija `SetModalCase`; hereda el modal por defecto.
- Los tres `GetAll*` descartan el código de retorno (lo llaman `_csys`). Si devuelve
  `ret=1` con arrays vacíos, el método devuelve `[]` en silencio.
- `list_tables`: condicional sin efecto, las dos ramas producen `keys[i]`. El nombre
  legible de la tabla nunca se muestra.
- `get_story_drifts` duplica literalmente 13 líneas de `_select_output_cases`.
- Falta `@com_call` en `_stress_to_mpa` y `_select_output_cases` (latente: hoy solo
  se invocan desde métodos ya decorados).
- `get_geometries` y `create_objects_by_coordinates` son `async` pero llaman
  métodos `@com_call` bloqueantes ⇒ bloquean el event loop de anyio.
- `server.py`: el `FileHandler` se evalúa fuera de cualquier `try`; si `src/` fuera
  de solo lectura, el servidor muere en el import.
- `server.py`: `dependencies=["comtypes", "pywin32"]` contradice el
  `requirements.txt`. Inocuo salvo para `mcp install`.
- `server.py`: la rama LUSAS hace `from Lusas import Lusas`, pero `src/` no contiene
  `Lusas.py` ⇒ `ModuleNotFoundError` en vez del mensaje claro de la rama `else`.
- `config.py`: un `config.json` que no sea un objeto JSON produce `AttributeError`
  fuera del `try`, matando el servidor con un mensaje que no menciona el archivo.

---

## 9. Plan de un solo reinicio

Orden que maximiza información por ciclo:

1. **Aplicar juntos**: §1 (`describe`), §2 (`set_stories`), §3 (columnas de
   resultados), §4 (peso por unidad de volumen), §5 (`SetOSteel_1`), §7.3
   (`_read_areas`), y los `@com_call` faltantes.
2. Verificar que los cinco módulos parsean con el intérprete real
   (`pythoncore-3.14-64\python.exe -c "import ast; ..."`).
3. **Un reinicio** de Claude Desktop desde la bandeja, como Administrador.
4. **Antes de tocar el modelo**, volcar firmas reales con el `describe_oapi` ya
   corregido, para cerrar todas las sospechas de una:
   - `Story` → `SetStories` (confirma o refuta §0.4)
   - `PointObj` → `AddCartesian`, `SetRestraint`, `SetDiaphragm` (cierra §6)
   - `FrameObj` → `AddByCoord`, `SetLoadDistributed`
   - `AreaObj` → `GetAllAreas`, `SetLoadUniform` (cierra §7.3)
   - `PropMaterial` → `SetOSteel_1`, `SetWeightAndMass` (cierra §4, §5)
   - `Func.FuncRS` → `SetUser`
   - `LoadCases` → confirma `ModHistLinear` vs `ModHistoryLinear` (cierra §7.4)
   - `Results` → `JointReact`, `FrameForce`, `StoryDrifts` (cierra §3)
5. Recién entonces `set_stories`, y **verificar con `get_stories()`**: elevaciones
   3/6/9, alturas 3/3/3. Es la única forma de detectar la desalineación silenciosa.
6. `get_areas()` para validar §7.3: 12 áreas de 4 vértices, con las 4 cotas iguales
   dentro de cada área.
7. `save_model` y cierre de R02.

---

## 10. Qué está verificado y qué no

**Verificado ejecutando código o leyendo el fuente instalado:**
layout de `_ComMemberSpec` y semántica de `paramflags`/`idlflags` (§0.1);
estado y geometría del modelo (§0.2); orden de arrays de `GetStories_2` en runtime
(§0.3); los tres mensajes de error de `SetStories` (§0.4); y por lectura del código,
los defectos de §2, §3, §5, §6, §7.1, §7.2, §7.4, §7.5 y todo §8.

**Conjeturado, requiere ejecución contra ETABS real:**
el orden exacto de parámetros `[out]` de `JointReact`, `FrameForce` y `StoryDrifts`
en esta instalación (§3); que `SetStories` siga el mismo orden que `GetStories_2`
(§0.4, §2); qué lado de la contradicción de §6 es el correcto; la base del índice de
`PointDelimiter` (§7.3); que ETABS bloquee el hilo COM con diálogos modales (§7.6).
El paso 4 del plan resuelve todas estas de una sola vez.
