# -*- coding: utf-8 -*-
"""RevitWrite - endpoints de escritura para Revit 2027 via pyRevit Routes.

Contrato de diseno (derivado de ERRORES-IA E-027, E-041, E-043, E-044, E-045):

  1. Ningun fallback silencioso. Si falta un prerrequisito de identidad
     (familia, tipo, nivel), el endpoint responde 4xx/5xx con el motivo.
     Nunca sustituye por "el primero disponible".
  2. Toda escritura va dentro de una Transaction explicita. Si algo falla
     a mitad, RollBack.
  3. Todo endpoint escribe al log en disco ANTES y DESPUES de actuar.
     El log envuelve tambien los imports (E-040).
  4. Las respuestas informan lo que realmente paso, no lo que se pidio.
     Nunca se afirma exito desde la entrada propia (E-024).
"""

import os
import json
import traceback
import datetime

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_log"
)
LOG_PATH = os.path.join(LOG_DIR, "revitwrite.log")


def log(msg):
    try:
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a") as fh:
            fh.write("[%s] %s\n" % (stamp, msg))
    except Exception:
        pass


try:
    import clr
    from System import Int64
    from System.Collections.Generic import List

    from pyrevit import routes
    from pyrevit.api import DB

    log("=" * 70)
    log("startup.py cargando RevitWrite")

    api = routes.API("revitwrite")

    # ---------------------------------------------------------------- utils

    def eid(value):
        """int de python -> ElementId. Revit 2024+ usa el overload Int64."""
        return DB.ElementId(Int64(int(value)))

    def eid_value(element_id):
        """ElementId -> int. En Revit 2024+ la propiedad es .Value (Int64).
        IntegerValue fue eliminada; el fallback existe solo por si el
        servidor se reusa contra un host mas viejo."""
        try:
            return int(element_id.Value)
        except AttributeError:
            return int(element_id.IntegerValue)

    def get_param(el, name):
        p = el.LookupParameter(name)
        if p is None:
            return None
        st = p.StorageType
        if st == DB.StorageType.String:
            return p.AsString()
        if st == DB.StorageType.Integer:
            return p.AsInteger()
        if st == DB.StorageType.Double:
            return p.AsDouble()
        if st == DB.StorageType.ElementId:
            return eid_value(p.AsElementId())
        return None

    def fail(msg, status=400, **extra):
        log("FALLO %s | %s | %s" % (status, msg, extra))
        payload = {"ok": False, "error": msg}
        payload.update(extra)
        return routes.make_response(data=payload, status=status)

    def ok(**payload):
        payload["ok"] = True
        return payload

    def body(request):
        """Decodifica el cuerpo del request.

        pyRevit 6.5.3 sobre IronPython 3.4 revienta en json.loads(bytes)
        cuando el Content-Type es application/json, ANTES de llegar aca
        (routes/server/server.py:89). Por eso el cliente manda text/plain y
        el parseo se hace de este lado, decodificando primero."""
        d = getattr(request, "data", None)
        if d is None:
            return {}
        if isinstance(d, dict):
            return d
        if isinstance(d, (bytes, bytearray)):
            d = bytes(d).decode("utf-8")
        if isinstance(d, str):
            d = d.strip()
            if not d:
                return {}
            return json.loads(d)
        return {}

    def resolve_ids(doc, raw_ids):
        """Convierte ids crudos a ElementId, separando los inexistentes.
        No descarta en silencio: devuelve las dos listas."""
        found, missing = [], []
        for raw in raw_ids:
            e = doc.GetElement(eid(raw))
            if e is None:
                missing.append(int(raw))
            else:
                found.append(e.Id)
        return found, missing

    # --------------------------------------------------------------- lectura

    @api.route("/status", methods=["GET"])
    def status(doc):
        n_col = (
            DB.FilteredElementCollector(doc)
            .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
            .WhereElementIsNotElementType()
            .GetElementCount()
        )
        n_reb = (
            DB.FilteredElementCollector(doc)
            .OfCategory(DB.BuiltInCategory.OST_Rebar)
            .WhereElementIsNotElementType()
            .GetElementCount()
        )
        n_lvl = (
            DB.FilteredElementCollector(doc)
            .OfClass(DB.Level)
            .GetElementCount()
        )
        return ok(
            document=doc.Title,
            path=doc.PathName,
            levels=n_lvl,
            structural_columns=n_col,
            rebar=n_reb,
            log_path=LOG_PATH,
        )

    @api.route("/levels", methods=["GET"])
    def levels(doc):
        out = []
        for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level):
            out.append(
                {
                    "id": eid_value(lv.Id),
                    "name": lv.Name,
                    "elevation_ft": lv.Elevation,
                    "elevation_m": lv.Elevation * 0.3048,
                }
            )
        out.sort(key=lambda x: x["elevation_ft"])
        return ok(count=len(out), levels=out)

    @api.route("/columns", methods=["GET"])
    def columns(doc):
        out = []
        col = (
            DB.FilteredElementCollector(doc)
            .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
            .WhereElementIsNotElementType()
        )
        for el in col:
            sym = doc.GetElement(el.GetTypeId())
            fam = None
            tname = None
            if sym is not None:
                tname = DB.Element.Name.GetValue(sym)
                try:
                    fam = sym.Family.Name
                except Exception:
                    fam = None
            lvl = doc.GetElement(el.LevelId) if el.LevelId is not None else None
            out.append(
                {
                    "id": eid_value(el.Id),
                    "type": tname,
                    "family": fam,
                    "mark": get_param(el, "Mark"),
                    "level": lvl.Name if lvl is not None else None,
                }
            )
        return ok(count=len(out), columns=out)

    def value_string(el, name):
        """Texto legible de un parametro (AsValueString). Para enums como
        Layout Rule, donde el int crudo obliga a mapear de memoria contra
        una tabla de enum no verificada (E-042)."""
        try:
            p = el.LookupParameter(name)
            if p is None:
                return None
            return p.AsValueString()
        except Exception:
            return None

    def constraint_digest(el):
        """Estado de constraints de un Rebar.

        Responde la pregunta que decide 7 maestros vs 42: si los handles
        estan amarrados a caras del anfitrion, la barra sigue la cara al
        cambiar la altura del host; si no lo estan, es geometria fija.

        Escrito contra la firma volcada de esta instalacion (2026-08-13),
        no contra la API recordada. Cualquier fallo se REPORTA en el campo
        'error' del propio set: no se omite ni se sustituye por un default
        (E-043). Un set sin datos de constraint no es un set sin constraints.
        """
        d = {
            "shape_driven": None,
            "constraints_editable": None,
            "handles_total": None,
            "handles_constrained": None,
            "host_face_types": None,
            "constraint_types": None,
            "error": None,
        }
        try:
            d["shape_driven"] = bool(el.IsRebarShapeDriven())
        except Exception as ex:
            d["error"] = "IsRebarShapeDriven: %s" % ex
            return d
        try:
            d["constraints_editable"] = bool(el.ConstraintsCanBeEdited())
        except Exception as ex:
            d["error"] = "ConstraintsCanBeEdited: %s" % ex
            return d
        try:
            mgr = el.GetRebarConstraintsManager()
            if mgr is None:
                d["error"] = "GetRebarConstraintsManager devolvio None"
                return d
            all_h = mgr.GetAllHandles()
            con_h = mgr.GetAllConstrainedHandles()
            d["handles_total"] = int(all_h.Count)
            d["handles_constrained"] = int(con_h.Count)

            faces = {}
            ctypes = {}
            for h in con_h:
                try:
                    c = mgr.GetCurrentConstraintOnHandle(h)
                    if c is None:
                        continue
                    try:
                        ct = str(c.GetConstraintType())
                        ctypes[ct] = ctypes.get(ct, 0) + 1
                    except Exception:
                        pass
                    try:
                        ft = str(c.GetRebarConstraintTargetHostFaceType())
                        faces[ft] = faces.get(ft, 0) + 1
                    except Exception:
                        # No toda constraint apunta a una cara del host
                        # (puede ir a otra barra o a un target custom).
                        faces["<no-host-face>"] = faces.get("<no-host-face>", 0) + 1
                except Exception as ex:
                    d["error"] = "handle: %s" % ex
            d["host_face_types"] = faces
            d["constraint_types"] = ctypes
        except Exception as ex:
            d["error"] = "constraints manager: %s" % ex
        return d

    @api.route("/rebar", methods=["GET"])
    def rebar(doc):
        out = []

        # NO tocar RebarConstraintsManager desde este handler. Corre en el
        # hilo del servidor de Routes, fuera del contexto de API de Revit;
        # instanciar el manager de constraints ahi tumbo Revit el 2026-08-13
        # (ver ERRORES-IA E-049). El analisis de constraints vive en el
        # pushbutton "Constraints", que corre en el hilo de UI.
        col = (
            DB.FilteredElementCollector(doc)
            .OfCategory(DB.BuiltInCategory.OST_Rebar)
            .WhereElementIsNotElementType()
        )
        for el in col:
            host_id = None
            try:
                host_id = eid_value(el.GetHostId())
            except Exception:
                pass
            bt = doc.GetElement(el.GetTypeId())
            row = {
                "id": eid_value(el.Id),
                "host_id": host_id,
                "host_mark": get_param(el, "Host Mark"),
                "bar_type": DB.Element.Name.GetValue(bt) if bt else None,
                "shape": get_param(el, "Shape Name"),
                "quantity": get_param(el, "Quantity"),
                "bar_length_ft": get_param(el, "Bar Length"),
                "schedule_mark": get_param(el, "Schedule Mark"),
                "layout_rule": value_string(el, "Layout Rule"),
            }
            out.append(row)

        log("/rebar: %d sets" % len(out))
        return ok(count=len(out), rebar=out)

    # ------------------------------------------------------------- reflexion

    @api.route("/reflect", methods=["POST"])
    def reflect(doc, request):
        """Vuelca la firma REAL de un tipo de la API de Revit de esta
        instalacion. Existe para no volver a escribir codigo contra una API
        recordada en vez de leida (E-042)."""
        data = body(request)
        type_path = data.get("type_name")
        member_filter = (data.get("member") or "").lower()
        if not type_path:
            return fail("falta 'type_name', ej: 'Structure.Rebar' o 'ElementTransformUtils'")

        target = DB
        for part in type_path.split("."):
            target = getattr(target, part, None)
            if target is None:
                return fail("no existe DB.%s en este Revit" % type_path, status=404)

        ctype = clr.GetClrType(target)
        methods = []
        for m in ctype.GetMethods():
            if member_filter and member_filter not in m.Name.lower():
                continue
            methods.append(
                {
                    "name": m.Name,
                    "static": m.IsStatic,
                    "returns": m.ReturnType.FullName,
                    "params": [
                        {"name": p.Name, "type": p.ParameterType.FullName}
                        for p in m.GetParameters()
                    ],
                }
            )
        props = [p.Name for p in ctype.GetProperties()
                 if not member_filter or member_filter in p.Name.lower()]
        log("reflect %s filtro=%s -> %d metodos" % (type_path, member_filter, len(methods)))
        return ok(
            type=ctype.FullName,
            method_count=len(methods),
            methods=methods,
            properties=props,
        )

    # -------------------------------------------------------------- escritura

    @api.route("/delete", methods=["POST"])
    def delete(doc, request):
        data = body(request)
        raw = data.get("ids") or []
        if not raw:
            return fail("falta 'ids' (lista de element ids)")

        found, missing = resolve_ids(doc, raw)
        if not found:
            return fail("ninguno de los ids existe en el documento",
                        status=404, missing=missing)

        log("delete: pedidos=%d existen=%d faltan=%d" % (len(raw), len(found), len(missing)))
        t = DB.Transaction(doc, "MCP: borrar elementos")
        t.Start()
        try:
            ids = List[DB.ElementId]()
            for i in found:
                ids.Add(i)
            deleted = doc.Delete(ids)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            log("delete ROLLBACK | %s" % traceback.format_exc())
            return fail("excepcion al borrar, transaccion revertida: %s" % ex, status=500)

        n = len(deleted) if deleted is not None else 0
        log("delete OK: %d elementos eliminados (incluye dependientes)" % n)
        return ok(
            requested=len(raw),
            existed=len(found),
            missing=missing,
            deleted_count=n,
            note="deleted_count incluye elementos dependientes borrados en cascada",
        )

    @api.route("/copy", methods=["POST"])
    def copy(doc, request):
        """Copia elementos con una traslacion. Si se copian juntos un anfitrion
        y su acero, la copia conserva el vinculo de hospedaje."""
        data = body(request)
        raw = data.get("ids") or []
        if not raw:
            return fail("falta 'ids'")
        dx = float(data.get("dx", 0.0))
        dy = float(data.get("dy", 0.0))
        dz = float(data.get("dz", 0.0))
        if dx == 0.0 and dy == 0.0 and dz == 0.0:
            return fail("traslacion nula: dx, dy y dz son todos 0. "
                        "Una copia en el mismo lugar es casi siempre un error de llamada")

        found, missing = resolve_ids(doc, raw)
        if not found:
            return fail("ninguno de los ids existe", status=404, missing=missing)
        if missing:
            return fail("faltan ids en el documento; se aborta para no copiar "
                        "un conjunto parcial", status=404, missing=missing)

        log("copy: %d elementos, delta=(%.4f, %.4f, %.4f) ft" % (len(found), dx, dy, dz))
        t = DB.Transaction(doc, "MCP: copiar elementos")
        t.Start()
        try:
            ids = List[DB.ElementId]()
            for i in found:
                ids.Add(i)
            new_ids = DB.ElementTransformUtils.CopyElements(
                doc, ids, DB.XYZ(dx, dy, dz)
            )
            t.Commit()
        except Exception as ex:
            t.RollBack()
            log("copy ROLLBACK | %s" % traceback.format_exc())
            return fail("excepcion al copiar, transaccion revertida: %s" % ex, status=500)

        out = [eid_value(i) for i in new_ids]
        log("copy OK: %d nuevos ids" % len(out))
        return ok(source_count=len(found), new_count=len(out), new_ids=out)

    @api.route("/set_param", methods=["POST"])
    def set_param(doc, request):
        data = body(request)
        assignments = data.get("assignments")
        name = data.get("name")
        if not assignments and not name:
            return fail("falta 'name' + 'ids' + 'value', o bien 'assignments'")

        if not assignments:
            raw = data.get("ids") or []
            value = data.get("value")
            assignments = [{"id": i, "value": value} for i in raw]

        log("set_param '%s': %d asignaciones" % (name, len(assignments)))
        applied, skipped = [], []
        t = DB.Transaction(doc, "MCP: fijar parametro")
        t.Start()
        try:
            for item in assignments:
                el = doc.GetElement(eid(item["id"]))
                if el is None:
                    skipped.append({"id": item["id"], "why": "no existe"})
                    continue
                p = el.LookupParameter(name)
                if p is None:
                    skipped.append({"id": item["id"], "why": "sin parametro '%s'" % name})
                    continue
                if p.IsReadOnly:
                    skipped.append({"id": item["id"], "why": "parametro de solo lectura"})
                    continue
                st = p.StorageType
                v = item["value"]
                if st == DB.StorageType.String:
                    p.Set(str(v))
                elif st == DB.StorageType.Integer:
                    p.Set(int(v))
                elif st == DB.StorageType.Double:
                    p.Set(float(v))
                elif st == DB.StorageType.ElementId:
                    p.Set(eid(v))
                else:
                    skipped.append({"id": item["id"], "why": "StorageType no soportado"})
                    continue
                applied.append(item["id"])
            t.Commit()
        except Exception as ex:
            t.RollBack()
            log("set_param ROLLBACK | %s" % traceback.format_exc())
            return fail("excepcion, transaccion revertida: %s" % ex, status=500)

        # relectura: no afirmar exito desde la propia entrada (E-024)
        verified = []
        for i in applied:
            el = doc.GetElement(eid(i))
            verified.append({"id": i, "read_back": get_param(el, name)})

        log("set_param OK: %d aplicados, %d omitidos" % (len(applied), len(skipped)))
        return ok(parameter=name, applied=len(applied),
                  skipped=skipped, verified=verified)

    @api.route("/find", methods=["POST"])
    def find(doc, request):
        """Busca instancias por categoria + familia + tipo + nivel.
        Pensado para armar conjuntos de borrado sin adivinar ids."""
        data = body(request)
        cat_name = data.get("category", "OST_StructuralColumns")
        bic = getattr(DB.BuiltInCategory, cat_name, None)
        if bic is None:
            return fail("categoria desconocida: %s" % cat_name, status=404)

        fam_filter = data.get("family")
        type_filter = data.get("type")
        level_filter = data.get("level")

        out = []
        col = (
            DB.FilteredElementCollector(doc)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
        )
        for el in col:
            sym = doc.GetElement(el.GetTypeId())
            tname = DB.Element.Name.GetValue(sym) if sym is not None else None
            fname = None
            if sym is not None:
                try:
                    fname = sym.Family.Name
                except Exception:
                    pass
            lvl = doc.GetElement(el.LevelId) if el.LevelId is not None else None
            lname = lvl.Name if lvl is not None else None

            if fam_filter and fam_filter != fname:
                continue
            if type_filter and type_filter != tname:
                continue
            if level_filter and level_filter != lname:
                continue
            out.append({
                "id": eid_value(el.Id),
                "family": fname,
                "type": tname,
                "level": lname,
                "mark": get_param(el, "Mark"),
            })
        log("find cat=%s fam=%s type=%s lvl=%s -> %d" %
            (cat_name, fam_filter, type_filter, level_filter, len(out)))
        return ok(count=len(out), elements=out)

    log("RevitWrite registrado: 8 endpoints en /revitwrite/")

except Exception:
    log("FALLO FATAL EN CARGA DE startup.py\n%s" % traceback.format_exc())
    raise
