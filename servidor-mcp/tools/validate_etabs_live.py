"""Opt-in synthetic ETABS checks. Never attach to an existing user session.

Windows only. --phase launch creates a NEW process; later phases require the
same PID and OS creation time from the private output directory. No ROT fallback.
Run with the Python environment containing comtypes, mcp and pydantic.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def processes():
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "@(Get-Process ETABS -ErrorAction SilentlyContinue | Select-Object "
         "Id,@{n='Started';e={$_.StartTime.ToUniversalTime().ToString('o')}}) "
         "| ConvertTo-Json -Compress"],
        check=True, capture_output=True, text=True,
    )
    rows = json.loads(result.stdout or "[]")
    return {int(row["Id"]): row["Started"] for row in (rows if isinstance(rows, list) else [rows])}


class Progress:
    async def report_progress(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["launch", "relaunch", "baseline", "suite", "results", "advanced", "roundtrip", "lifecycle", "walls", "close"], required=True)
    parser.add_argument("--exe", default=r"C:\Program Files\Computers and Structures\ETABS 23\ETABS.exe")
    options = parser.parse_args()
    out = options.output.resolve()
    statefile = out / "instance.json"
    if options.phase in ('launch','relaunch'):
        if options.phase == 'relaunch':
            old=json.loads(statefile.read_text(encoding='utf-8'))
            if old.get('synthetic_only') is not True or old['pid'] in processes():
                raise RuntimeError('Relaunch requires confirmed termination of the old owned process')
            shutil.copy2(statefile, out / f'instance-{old["pid"]}.json')
        elif out.exists():
            raise RuntimeError("Launch requires a new output directory; refusing to overwrite")
        else:
            out.mkdir(parents=True)
        before = processes()
        from comthread import run_in_com

        def launch():
            import comtypes.client
            helper = comtypes.client.CreateObject("ETABSv1.Helper")
            import comtypes.gen.ETABSv1 as typelib
            helper = helper.QueryInterface(typelib.cHelper)
            own = helper.CreateObject(options.exe)
            result = own.ApplicationStart()
            if result != 0:
                raise RuntimeError(f"ApplicationStart returned {result}")
            # Release the COM proxy on the STA that created it. Returning it
            # to the caller would also move its final Release to another thread.
            return None

        print("START new ETABS instance (no GetActiveObject)", flush=True)
        run_in_com(launch)
        after = processes()
        created = set(after) - set(before)
        if len(created) != 1:
            raise RuntimeError(f"Cannot identify new instance unambiguously: {sorted(created)}; no model was touched")
        pid = created.pop()
        state = {"pid": pid, "started": after[pid], "excluded_pids": sorted(before),
                 "synthetic_only": True, "exe": options.exe}
        statefile.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(json.dumps(state), flush=True)
        return

    state = json.loads(statefile.read_text(encoding="utf-8"))
    if (state.get("synthetic_only") is not True or
            processes().get(state["pid"]) != state["started"] or
            state["pid"] in state["excluded_pids"]):
        raise RuntimeError("Instance identity changed; refusing connection")
    from Etabs import Etabs, GeomObject
    from comthread import run_in_com
    adapter = Etabs(process_id=state["pid"])
    current = run_in_com(lambda: adapter._model().GetModelFilename())
    unsaved = current in (None, '', '(Untitled)')
    if not unsaved and not Path(current).resolve().is_relative_to(out):
        raise RuntimeError("A foreign model was opened in the test instance; refusing changes")
    if unsaved and adapter.get_points():
        raise RuntimeError("Unidentified unsaved geometry in the test instance; refusing changes")
    records = []
    for suffix in ('calls', 'failures'):
        previous = out / f'{options.phase}-{suffix}.json'
        if previous.exists():
            shutil.copy2(previous, out / f'{options.phase}-{time.time_ns()}-{suffix}.json')

    def record(name, fn, *args, **kwargs):
        print(f"START {name}", flush=True)
        start = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            encoded = [x.model_dump() if hasattr(x, "model_dump") else x for x in result] if isinstance(result, list) else result
            records.append({"name": name, "status": "returned", "seconds": time.monotonic() - start, "result": encoded})
            print(f"RETURN {name}: {str(encoded)[:800]}", flush=True)
            return result
        except Exception as exc:
            records.append({"name": name, "status": "failed", "error": str(exc)})
            raise
        finally:
            (out / f"{options.phase}-calls.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    def tool(name, *args, **kwargs):
        return record(name, getattr(adapter, name), *args, **kwargs)

    def api(path, method, args=None):
        result = json.loads(tool("call_oapi", path, method, args))
        if result["ret"] != 0:
            raise AssertionError(f"{path}.{method}: {result}")
        return result["outs"]

    def check(name, actual, expected, rel=1e-5, absolute=1e-10):
        passed=math.isclose(actual, expected, rel_tol=rel, abs_tol=absolute)
        records.append({"name": name, "status": "verified" if passed else "failed",
                        "actual": actual, "expected": expected, "rel_tol":rel,"abs_tol":absolute})
        (out / f"{options.phase}-calls.json").write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
        assert passed, (name, actual, expected)

    if options.phase == "close":
        tool("exit_etabs", False)
        return
    if options.phase == 'roundtrip':
        tool('open_model',str(out/'cantilever.edb'),'kN, m, C')
        tool('save_model',str(out/'roundtrip.edb'))
        tool('refresh_text_model')
        tool('open_model',str(out/'roundtrip.$et'),'kN, m, C')
        check('text_import_frames',len(tool('get_frames')),1)
        check('text_import_points',len(tool('get_points')),2)
        tool('save_model',str(out/'roundtrip.reimport.edb'))
        api('Analyze','SetRunCaseFlag',['',False,True])
        api('Analyze','SetRunCaseFlag',['TEST_AXIAL',True,False])
        tool('run_analysis')
        displacement=json.loads(tool('get_joint_displacements','2',cases=['TEST_AXIAL']))
        check('text_roundtrip_axial',displacement['results'][0]['U3'],-.0001)
        tool('save_model')
        return
    if options.phase == 'lifecycle':
        tool('open_model',str(out/'steel.edb'),'kN, m, C')
        tool('close_model',save=True)
        check('closed_model_frames',len(tool('get_frames')),0)
        tool('open_model',str(out/'steel.edb'),'kN, m, C')
        check('steel_reopened_frames',len(tool('get_frames')),1)
        return
    if options.phase == 'walls':
        tool('open_model',str(out/'two_storey.edb'),'kN, m, C')
        tool('save_model',str(out/'walls.edb'))
        for name in ('get_shearwall_design','get_shearwall_rebar'):
            try:
                tool(name)
            except Exception as exc:
                if 'No hay resultados de diseño de muros' not in str(exc):
                    raise
                print(f'GUARD VERIFIED: {exc}',flush=True)
        return
    if options.phase == "suite":
        from etabs_live_suite import run_suite
        run_suite(adapter, out, tool, api, record, check)
        (out / "suite-calls.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if options.phase == "advanced":
        from etabs_live_advanced import run_advanced
        run_advanced(adapter, out, tool, api, record, check)
        (out / "advanced-calls.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if options.phase == "results":
        from etabs_live_suite import run_results
        run_results(adapter, out, tool, api, record, check)
        (out / "results-calls.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        return

    # Explicitly synthetic, linear cantilever; active units kN, m, C.
    # 100 kN compression: FL/EA = -0.0001 m for L=3m, E=25e6, A=.12.
    tool("get_model_info")
    api("", "InitializeNewModel", [6])
    api("File", "NewBlank")
    tool("set_units", "kN, m, C")
    tool("get_units")
    tool("set_stories", ["TEST_ROOF"], [3.0])
    tool("define_concrete_material", "TEST_C30", 30000.0, E=25000000.0, unit_weight=25.0)
    tool("define_rect_section", "TEST_RECT", "TEST_C30", 0.4, 0.3)
    geometry = [GeomObject(type="line", xs=[0, 0], ys=[0, 0], zs=[0, 3])]
    result = record("create_objects_by_coordinates", asyncio.run,
                    adapter.create_objects_by_coordinates(geometry, Progress()))
    assert not any("error" in str(row).lower() for row in result), result
    frames = tool("get_frames")
    points = tool("get_points")
    check("frame_count", len(frames), 1)
    check("point_count", len(points), 2)
    tool("assign_sections", "TEST_RECT", "TEST_RECT")
    tool("set_base_restraints")
    tool("add_load_pattern", "TEST_AXIAL", "viva", 0)
    tool("add_load_pattern", "TEST_LATERAL", "viva", 0)
    top = max(points, key=lambda p: p.zs[0]).id
    base = min(points, key=lambda p: p.zs[0]).id
    api("PointObj", "SetLoadForce", [top, "TEST_AXIAL", [0, 0, -100, 0, 0, 0], True])
    api("PointObj", "SetLoadForce", [top, "TEST_LATERAL", [10, 0, 0, 0, 0, 0], True])
    tool("add_load_combo", "TEST_COMBO", {"TEST_AXIAL": 1.2, "TEST_LATERAL": 1.6})
    for name in ["get_stories", "get_materials", "get_frame_sections", "get_area_sections",
                 "get_load_patterns", "get_load_combos", "get_restraints", "get_diaphragms"]:
        tool(name)
    tool("save_model", str(out / "cantilever.edb"))
    api("Analyze", "SetRunCaseFlag", ["", False, True])
    for case in ["TEST_AXIAL", "TEST_LATERAL"]:
        api("Analyze", "SetRunCaseFlag", [case, True, False])
    tool("run_analysis")
    tool("get_analysis_status")
    axial = json.loads(tool("get_joint_displacements", top, cases=["TEST_AXIAL"]))
    assert axial["total_results"] == 1, axial
    check("axial_FL_over_EA", axial["results"][0]["U3"], -100 * 3 / (25000000 * .3 * .4))
    lateral = json.loads(tool("get_joint_displacements", top, cases=["TEST_LATERAL"]))
    # Independent Euler-Bernoulli plus rectangular shear deformation (As=5A/6).
    I = .3 * .4 ** 3 / 12
    expected = 10 * 3 ** 3 / (3 * 25000000 * I) + 10 * 3 / ((25000000 / 2.4) * (.3 * .4 * 5 / 6))
    check("lateral_bending_plus_shear", lateral["results"][0]["U1"], expected, rel=.002)
    tool("get_joint_reactions", [base], ["TEST_AXIAL", "TEST_LATERAL"])
    tool("get_frame_forces", [frames[0].id], ["TEST_AXIAL", "TEST_LATERAL"])
    tool("get_story_drifts", cases=["TEST_LATERAL"])
    tool("save_model")
    tool("open_model", str(out / "cantilever.edb"), "kN, m, C")
    check("reopened_points", len(tool("get_points")), 2)
    reopened = json.loads(tool("get_joint_displacements", top, cases=["TEST_AXIAL"]))
    check("reopened_axial", reopened["results"][0]["U3"], axial["results"][0]["U3"])
    (out / "baseline-calls.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print("BASELINE VERIFIED", flush=True)


if __name__ == "__main__":
    main()
