# -*- coding: utf-8 -*-
# Read-only MEP helpers, injected only for the two MEP tools. IronPython syntax.
MEP_CATEGORIES = {
    "mechanical": ["OST_DuctCurves", "OST_FlexDuctCurves", "OST_DuctFitting",
                   "OST_DuctAccessory", "OST_DuctTerminal", "OST_MechanicalEquipment"],
    "plumbing_fire": ["OST_PipeCurves", "OST_FlexPipeCurves", "OST_PipeFitting",
                      "OST_PipeAccessory", "OST_PlumbingFixtures", "OST_Sprinklers"],
    "electrical": ["OST_ElectricalEquipment", "OST_ElectricalFixtures",
                   "OST_LightingFixtures", "OST_LightingDevices", "OST_CableTray",
                   "OST_CableTrayFitting", "OST_Conduit", "OST_ConduitFitting",
                   "OST_Wire", "OST_DataDevices", "OST_FireAlarmDevices",
                   "OST_CommunicationDevices", "OST_SecurityDevices"]
}


def mep_audit(doc, DB, P, connectivity):
    requested = P.get("disciplines")
    disciplines = list(MEP_CATEGORIES) if requested is None else requested
    if not isinstance(disciplines, (list, tuple)) or not disciplines:
        raise ValueError("disciplines must be a nonempty list")
    if any(d not in MEP_CATEGORIES for d in disciplines):
        raise ValueError("Unknown discipline; use mechanical, plumbing_fire, electrical")
    limit = P.get("max_details", 500)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0 or limit > 10000:
        raise ValueError("max_details must be an integer between 0 and 10000")
    out = {"schema_version": 1, "read_only": True, "status": "complete",
           "scope": "active_document_instances_all_phases_and_design_options",
           "linked_documents_included": False, "categories": [], "systems": [],
           "elements": [], "findings": [], "finding_counts": {}, "errors": [],
           "error_count": 0, "element_count": 0, "details_truncated": False,
           "connectors": {"physical_checked": 0, "logical_or_other_skipped": 0},
           "limits": ["Not a compliance certificate or sizing calculation.",
                      "Open connectors are review candidates, including intentional endpoints.",
                      "No clash detection; no linked-model or phase-specific federation.",
                      "System membership does not prove circuit completeness or performance."]}
    systems = {}

    def error(stage, element_id, exc):
        out["status"] = "partial"
        out["error_count"] += 1
        if len(out["errors"]) < limit:
            out["errors"].append({"stage": stage, "element_id": element_id, "message": str(exc)})

    def finding(code, element_id, connector_index=None):
        out["finding_counts"][code] = out["finding_counts"].get(code, 0) + 1
        if len(out["findings"]) < limit:
            out["findings"].append({"code": code, "severity": "review",
                                    "element_id": element_id, "connector_index": connector_index})

    def register_system(system, system_ids):
        if system is None:
            return
        sid = eidv(system.Id)
        if sid not in system_ids:
            system_ids.append(sid)
        if sid not in systems:
            systems[sid] = {"id": sid, "name": element_name(system), "observed_element_count": 0}

    for discipline in sorted(set(disciplines)):
        for category in MEP_CATEGORIES[discipline]:
            errors_before_category = out["error_count"]
            row = {"discipline": discipline, "category": category, "count": 0, "status": "complete"}
            out["categories"].append(row)
            try:
                bic = getattr(DB.BuiltInCategory, category)
                elements = DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType()
                for el in elements:
                    row["count"] += 1
                    out["element_count"] += 1
                    element_id = None
                    try:
                        element_id = eidv(el.Id)
                        errors_before_element = out["error_count"]
                        system_ids = []
                        record = {"id": element_id, "category": category,
                                  "name": element_name(el), "system_ids": system_ids,
                                  "connector_count": None, "connectors_status": "unavailable"}
                        model = getattr(el, "MEPModel", None)
                        manager = getattr(el, "ConnectorManager", None)
                        if manager is None and model is not None:
                            manager = model.ConnectorManager
                        if model is not None and hasattr(model, "GetElectricalSystems"):
                            try:
                                for system in model.GetElectricalSystems() or []:
                                    register_system(system, system_ids)
                            except Exception as exc:
                                error("electrical_systems", element_id, exc)
                        if manager is None:
                            if connectivity:
                                finding("CONNECTORS_UNAVAILABLE", element_id)
                        else:
                            connectors = list(manager.Connectors)
                            record["connector_count"] = len(connectors)
                            record["connectors_status"] = "read"
                            if not connectors and connectivity:
                                finding("NO_CONNECTORS", element_id)
                            for index, connector in enumerate(connectors):
                                try:
                                    register_system(connector.MEPSystem, system_ids)
                                except Exception as exc:
                                    error("connector_system", element_id, exc)
                                if not connectivity:
                                    continue
                                try:
                                    kind = str(connector.ConnectorType)
                                    if kind not in ("End", "Curve", "Physical"):
                                        out["connectors"]["logical_or_other_skipped"] += 1
                                        continue
                                    out["connectors"]["physical_checked"] += 1
                                    if not connector.IsConnected:
                                        finding("OPEN_PHYSICAL_CONNECTOR", element_id, index)
                                except Exception as exc:
                                    error("connector_connectivity", element_id, exc)
                            if (connectivity and connectors and not system_ids and
                                    out["error_count"] == errors_before_element):
                                finding("NO_OBSERVED_SYSTEM", element_id)
                        for sid in system_ids:
                            systems[sid]["observed_element_count"] += 1
                        if len(out["elements"]) < limit:
                            out["elements"].append(record)
                    except Exception as exc:
                        error("element", element_id, exc)
            except Exception as exc:
                row["status"] = "partial"
                error("category:" + category, None, exc)
            if out["error_count"] > errors_before_category:
                row["status"] = "partial"
    out["systems"] = [systems[key] for key in sorted(systems)]
    out["details_truncated"] = (out["element_count"] > len(out["elements"]) or
                                sum(out["finding_counts"].values()) > len(out["findings"]) or
                                out["error_count"] > len(out["errors"]))
    if not out["element_count"] and out["status"] == "complete":
        out["status"] = "no_elements_in_scope"
    return out
