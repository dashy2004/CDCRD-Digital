"""Synthetic extension of validate_etabs_live; never run without its identity gate."""
import asyncio
import json


class Progress:
    async def report_progress(self, *args):
        pass


def run_suite(adapter, out, tool, api, record, check):
    from Etabs import GeomObject
    from oapi_catalog import search_oapi_catalog
    failures = []

    def attempt(name, *args, **kwargs):
        try:
            value = tool(name, *args, **kwargs)
            if isinstance(value, str) and any(word in value for word in ['Fallos:', 'ERROR:', 'no leidos']):
                failures.append({'tool': name, 'result': value})
            return value
        except Exception as exc:
            failures.append({'tool': name, 'error': str(exc)})
            print(f'FAIL {name}: {exc}', flush=True)
            return None
        finally:
            (out / 'suite-failures.json').write_text(json.dumps(failures, indent=2, ensure_ascii=False), encoding='utf-8')

    def create(objects):
        result = record('create_objects_by_coordinates', asyncio.run,
                        adapter.create_objects_by_coordinates(objects, Progress()))
        if any('error' in str(row).lower() for row in result):
            raise RuntimeError(result)

    # First preserve and independently inspect the already-verified cantilever.
    tool('open_model', str(out / 'cantilever.edb'), 'kN, m, C')
    tool('reconnect')
    tool('refresh_view')
    tool('list_tables', 'Joint Displacements')
    tool('get_table_data', 'Joint Displacements', max_rows=10)
    api('Results.Setup','DeselectAllCasesAndCombosForOutput')
    api('Results.Setup','SetCaseSelectedForOutput',['TEST_AXIAL'])
    raw = api('Results', 'JointReact', ['1', 0])
    # Selection preserved by baseline: TEST_AXIAL only.
    check('axial_reaction_equilibrium', raw[8][0], 100.0)
    tool('refresh_text_model')
    tool('read_e2k', str(out / 'cantilever.$et'), 'stories')
    record('search_oapi_catalog', search_oapi_catalog, 'JointDispl')
    tool('describe_oapi', 'LoadCases', 'Hist')

    api('', 'InitializeNewModel', [6])
    api('File', 'NewBlank')
    tool('save_model', str(out / 'two_storey.build.edb'))
    tool('set_stories', ['TEST_L1', 'TEST_L2'], [3.0, 3.0])
    tool('define_concrete_material', 'TEST_C30', 30000.0, E=25000000.0, unit_weight=25.0)
    tool('define_rect_section', 'TEST_COL', 'TEST_C30', .4, .4)
    tool('define_rect_section', 'TEST_BEAM', 'TEST_C30', .5, .3)
    # Section geometry alone defaults to column reinforcement in ETABS.
    api('PropFrame', 'SetRebarBeam', ['TEST_BEAM','A615Gr60','A615Gr60',.05,.05,0.,0.,0.,0.])
    api('PropFrame', 'GetRebarBeam', ['TEST_BEAM'])
    tool('define_steel_material', 'TEST_STEEL', 345000.0, fu=450000.0, E=200000000.0, unit_weight=77.0)
    tool('define_i_section', 'TEST_I', 'TEST_STEEL', .4, .2, .016, .01)
    tool('define_pipe_section', 'TEST_PIPE', 'TEST_STEEL', .2, .01)
    api('PropArea', 'SetSlab', ['TEST_SLAB', 0, 1, 'TEST_C30', .15])
    api('PropArea', 'SetWall', ['TEST_WALL', 1, 1, 'TEST_C30', .2])
    corners = [(0, 0), (6, 0), (6, 4), (0, 4)]
    objects = []
    for level in (0, 3):
        for x, y in corners:
            objects.append(GeomObject(type='line', xs=[x,x], ys=[y,y], zs=[level,level+3]))
        for i in range(4):
            a, b = corners[i], corners[(i+1)%4]
            objects.append(GeomObject(type='line', xs=[a[0],b[0]], ys=[a[1],b[1]], zs=[level+3]*2))
        objects.append(GeomObject(type='surface', xs=[p[0] for p in corners], ys=[p[1] for p in corners], zs=[level+3]*4))
        objects.append(GeomObject(type='surface', xs=[0]*4, ys=[0,4,4,0], zs=[level,level,level+3,level+3]))
    create(objects)
    check('two_level_points', len(tool('get_points')), 12)
    frames = tool('get_frames')
    areas = tool('get_areas')
    check('two_level_frames', len(frames), 16)
    check('two_level_areas', len(areas), 4)
    record('get_all_geometries', asyncio.run, adapter.get_geometries(Progress()))
    tool('assign_sections', 'TEST_COL', 'TEST_BEAM')
    slabs = [a.id for a in areas if len(set(a.zs)) == 1]
    walls = [a.id for a in areas if len(set(a.zs)) != 1]
    for a in slabs: api('AreaObj', 'SetProperty', [a, 'TEST_SLAB'])
    for a in walls: api('AreaObj', 'SetProperty', [a, 'TEST_WALL'])
    tool('set_base_restraints')
    tool('set_rigid_diaphragm', 'TEST_D1', 3)
    tool('set_rigid_diaphragm', 'TEST_D2', 6)
    tool('set_rigid_diaphragm', 'TEST_D1', 3)
    try:
        tool('set_rigid_diaphragm', 'TEST_D1', 3, True)
    except Exception as exc:
        assert 'otra rigidez' in str(exc)
    else:
        raise AssertionError('Changing existing diaphragm rigidity was silently accepted')
    # Read-after-write of diaphragm types and object assignment.
    check('diaphragm_rigid_flag', api('Diaphragm', 'GetDiaphragm', ['TEST_D1'])[0], False)
    tool('set_frame_modifiers', 'TEST_BEAM', i22=.8, i33=.8)
    check('frame_modifier_i33', api('PropFrame', 'GetModifiers', ['TEST_BEAM'])[0][5], .8)
    tool('set_area_modifiers', 'TEST_SLAB', m11=.8, m22=.8)
    check('area_modifier_m11', api('PropArea', 'GetModifiers', ['TEST_SLAB'])[0][3], .8)
    beams = [f.id for f in frames if f.zs[0] == f.zs[1]]
    columns = [f.id for f in frames if f.zs[0] != f.zs[1]]
    tool('set_frame_releases', beams[0], end=['M3'])
    check('beam_end_release', api('FrameObj', 'GetReleases', [beams[0]])[1][5], True)
    tool('set_frame_releases', beams[0])
    tool('add_load_pattern', 'TEST_G', 'otra', 0)
    tool('add_load_pattern', 'TEST_X', 'otra', 0)
    tool('assign_area_uniform_load', 'TEST_G', 2.0, elevations=[3,6])
    tool('assign_frame_distributed_load', 'TEST_G', 1.0, elevations=[3,6])
    tool('add_load_combo', 'TEST_ULS', {'TEST_G':1.2, 'TEST_X':1.6})
    for p in tool('get_points'):
        if p.zs[0] > 0:
            api('PointObj', 'SetLoadForce', [p.id, 'TEST_X', [2.5,0,0,0,0,0], True])
    tool('set_mass_source', {'Dead':1.0}, 'TEST_MASS')
    tool('set_base_springs', kz=100000.0)
    tool('set_point_spring', '1', kz=200000.0)
    attempt('set_panel_zone', ['5'])
    attempt('set_pier_label', walls, 'TEST_PIER')
    # Dedicated tools should preserve two independent user spectra.
    attempt('define_cdcrd_spectrum', 'TEST_RS_A', .6, .3)
    attempt('define_cdcrd_spectrum', 'TEST_RS_B', .5, .2)
    attempt('get_spectrum', 'TEST_RS_A')
    attempt('add_response_spectrum_case', 'TEST_RS', 'TEST_RS_A', 'X', 9.80665)
    attempt('add_pdelta_case', 'TEST_PD', load_pattern='TEST_G')
    attempt('add_nonlinear_static_case', 'TEST_NL', 'TEST_X', initial_case='TEST_PD')
    check('pdelta_geometry_type', api('LoadCases.StaticNonlinear','GetGeometricNonlinearity',['TEST_PD'])[0],1)
    assert api('LoadCases.StaticNonlinear','GetLoads',['TEST_PD'])[1:3] == [['Load'],['TEST_G']]
    assert api('LoadCases.StaticNonlinear','GetLoads',['TEST_NL'])[1:3] == [['Load'],['TEST_X']]
    attempt('get_frame_section_dims', ['TEST_COL','TEST_BEAM','TEST_I','TEST_PIPE'])
    attempt('get_area_sections_full')
    tool('get_diaphragms')
    tool('get_stories')
    tool('get_restraints')
    units = json.loads(tool('call_oapi','','GetPresentUnits', returns_status=False))
    check('raw_units_value',units['value'],6)
    tool('get_load_patterns')
    tool('get_load_combos')
    # Auxiliary geometry is separate, never delete a structural node.
    create([GeomObject(type='point', xs=[20], ys=[20], zs=[0])])
    auxiliary = next(p.id for p in tool('get_points') if p.xs[0] == 20)
    tool('move_objects', 'point', [auxiliary], dx=1)
    check('moved_auxiliary_x', next(p.xs[0] for p in tool('get_points') if p.id==auxiliary), 21)
    tool('delete_object', 'point', auxiliary)
    tool('add_load_pattern', 'TEST_DELETE', 'otra', 0)
    tool('delete_definition', 'load_case', 'TEST_DELETE')
    tool('delete_definition', 'load_pattern', 'TEST_DELETE')
    tool('save_model', str(out / 'two_storey.edb'))
    api('Analyze', 'SetRunCaseFlag', ['', False, True])
    for case in ['TEST_G','TEST_X','Modal','TEST_RS','TEST_PD','TEST_NL']:
        try: api('Analyze','SetRunCaseFlag',[case,True,False])
        except Exception as exc: failures.append({'case':case,'error':str(exc)})
    tool('run_analysis')
    failures.extend(run_results(adapter,out,tool,api,record,check))
    (out / 'suite-failures.json').write_text(json.dumps(failures, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'SUITE COMPLETED WITH {len(failures)} FINDINGS', flush=True)


def run_results(adapter,out,tool,api,record,check):
    failures=[]
    def attempt(name,*args,**kwargs):
        try: return tool(name,*args,**kwargs)
        except Exception as exc:
            failures.append({'tool':name,'error':str(exc)})
            print(f'FAIL {name}: {exc}',flush=True)
            return None
        finally:
            (out/'results-failures.json').write_text(json.dumps(failures,indent=2,ensure_ascii=False),encoding='utf-8')
    frames=tool('get_frames')
    beams=[f.id for f in frames if f.zs[0] == f.zs[1]]
    columns=[f.id for f in frames if f.zs[0] != f.zs[1]]
    tool('get_analysis_status')
    tool('get_modal_results')
    tool('get_joint_reactions', cases=['TEST_G'])
    total = 0.0
    for p in tool('get_points'):
        if p.zs[0] == 0:
            reaction = api('Results', 'JointReact', [p.id,0])
            total += sum(reaction[8])
    check('gravity_equilibrium_kN', total, 2*6*4*2 + 2*(6+4)*2, rel=1e-5)
    tool('get_joint_displacements', 'All', item_type=2, cases=['TEST_X'], max_results=3)
    tool('get_story_drifts', ['TEST_X'])
    tool('get_frame_forces', beams[:1], ['TEST_G'])
    attempt('run_concrete_design', 'ACI 318-19')
    beam_result = attempt('get_concrete_design_beam', beams[0], 0)
    assert beam_result and 'estacion(es)' in beam_result, beam_result
    attempt('get_concrete_design_column', columns[0], 0)
    attempt('get_concrete_design_joint', columns[0], 0)
    tool('save_model')
    tool('refresh_text_model')
    tool('open_model', str(out / 'two_storey.edb'), 'kN, m, C')
    check('two_level_reopened_frames', len(tool('get_frames')), 16)
    check('two_level_reopened_areas', len(tool('get_areas')), 4)
    return failures
