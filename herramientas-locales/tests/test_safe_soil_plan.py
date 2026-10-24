import copy
import json

import pytest

from cdcrd_local.foundation_exchange import digest, prepare
from cdcrd_local.safe_soil_plan import prepare_soil_plan, run_files


@pytest.fixture
def inputs():
    points = [{"id":str(i+1),"xyz":p} for i,p in enumerate([[0,0,0],[2000,0,0],[2000,2000,0],[0,2000,0]])]
    snapshot = {"schema":"cdcrd.csi-points/1", "source":{"application":"SAFE","model":r"C:\test\SYNTHETIC_SOIL.FDB","units_enum":9},
                "frame":{"id":"LOCAL","axes":"Global","length_unit":"mm"},"points":points}
    geometry = {"model":snapshot["source"]["model"],"units_enum":9,"frame":snapshot["frame"],"points":points,
                "areas":[{"id":"A1","point_ids":["1","2","3","4"],"section":"MAT","opening":False,"matrix":[1,0,0,0,1,0,0,0,1]}]}
    context = {"schema":"cdcrd.safe-soil-context/1","snapshot":snapshot,"geometry":geometry,
               "geometry_sha256":digest(geometry),"soil_state":{"assignments":{"A1":"None"},"properties":[]},
               "model_locked":False,"model_writes":0}
    seal_context(context)
    query = prepare(snapshot, {"source_frame":"LOCAL","source_origin":[0,0,0],"site_origin_m":[100,200,9],
                "rotation_deg":0,"site_frame":"SITE","vertical_datum":"TEST","point_ids":["1","2","3","4"],
                "control_tolerance_m":.002,"controls":[{"id":"C1","source_xyz":[0,0,0],"site_xyz_m":[100,200,9]},
                    {"id":"C2","source_xyz":[2000,0,0],"site_xyz_m":[102,200,9]}]})
    samples = {"schema":"cdcrd.foundation-samples/1","query_sha256":query["query_sha256"],"site_frame":"SITE",
               "vertical_datum":"TEST","length_unit":"m","source":{"drawing":"synthetic.dwg","surface":"ABC","is_out_of_date":False},
               "samples":[{"id":p["id"],"status":"ok","xy_m":p["site_xyz_m"][:2],"terrain_z_m":10.} for p in query["points"]]}
    geo = {"source":"SYNTHETIC ONLY", "allowable_bearing_kpa":150.,"subgrade_modulus_kn_m3":18000.,"applicable_point_ids":["1","2","3","4"]}
    config = {"area_ids":["A1"],"property_name":"CDX_SOIL","compression_only":True}
    return context, query, samples, geo, config


def seal_context(context):
    context.pop("context_sha256",None)
    context["geometry_sha256"] = digest(context["geometry"])
    context["context_sha256"] = digest(context)


def test_complete_plan_has_traceable_evidence_and_no_writes(inputs):
    before = copy.deepcopy(inputs)
    plan = prepare_soil_plan(*inputs)
    assert plan["model_writes"] == 0 and not plan["analysis_run"]
    assert plan["geotechnical"]["subgrade_modulus_kn_m3"] == 18000.
    assert plan["civil_source"]["surface"] == "ABC" and len(plan["terrain_rows"]) == 4
    body = dict(plan)
    assert body.pop("plan_sha256") == digest(body)
    assert inputs == before


@pytest.mark.parametrize("mutation", [
    lambda x:x[0].update(model_locked=True),
    lambda x:x[0]["geometry"].update(model=r"C:\project\copy.fdb"),
    lambda x:x[0]["snapshot"]["source"].update(application="ETABS"),
    lambda x:x[0]["geometry"].update(units_enum=7),
    lambda x:x[0]["soil_state"]["properties"].append("CDX_SOIL"),
    lambda x:x[0]["soil_state"]["assignments"].update(A1="OTHER"),
    lambda x:x[0]["geometry"]["areas"][0].update(opening=True),
    lambda x:x[0]["geometry"]["areas"][0].update(matrix=[1,0,0,0,-1,0,0,0,-1]),
    lambda x:x[1].update(snapshot_sha256="bad"),
    lambda x:x[2]["source"].update(is_out_of_date=True),
    lambda x:x[2]["samples"][0].update(status="error",terrain_z_m=None,error="outside"),
    lambda x:x[3].update(applicable_point_ids=["1","2"]),
    lambda x:x[3].update(subgrade_modulus_kn_m3=-1),
    lambda x:x[3].update(allowable_bearing_kpa=True),
    lambda x:x[4].update(area_ids=["A2"]),
    lambda x:x[4].update(area_ids=["A1","A1"]),
    lambda x:x[4].update(property_name="bad name"),
    lambda x:x[4].update(compression_only="true"),
])
def test_mismatch_or_incomplete_evidence_rejected(inputs, mutation):
    mutation(inputs)
    seal_context(inputs[0])
    with pytest.raises((ValueError,KeyError)):
        prepare_soil_plan(*inputs)


def test_tampered_context_is_rejected(inputs):
    inputs[0]["soil_state"]["properties"] = ["OTHER"]
    with pytest.raises(ValueError, match="modificado"):
        prepare_soil_plan(*inputs)


def test_files_never_overwrite(inputs, tmp_path):
    files = [tmp_path/f"input_{i}.json" for i in range(5)]
    for file,data in zip(files,inputs):
        file.write_text(json.dumps(data))
    out = tmp_path/"plan.json"
    run_files(*files,out)
    original = out.read_bytes()
    with pytest.raises(FileExistsError):
        run_files(*files,out)
    assert out.read_bytes() == original
