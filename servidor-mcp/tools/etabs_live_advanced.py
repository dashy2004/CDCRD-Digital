"""Additional opt-in test families; requires the parent runner's PID gate."""
import json


def run_advanced(adapter, out, tool, api, record, check):
    failures=[]

    def attempt(name,*args,**kwargs):
        try: return tool(name,*args,**kwargs)
        except Exception as exc:
            failures.append({'tool':name,'error':str(exc)})
            print(f'FAIL {name}: {exc}',flush=True)
            return None
        finally:
            (out/'advanced-failures.json').write_text(json.dumps(failures,indent=2,ensure_ascii=False),encoding='utf-8')

    tool('open_model',str(out/'two_storey.edb'),'kN, m, C')
    tool('save_model',str(out/'two_storey.advanced.edb'))
    api('','SetModelIsLocked',[False])
    tool('set_table_data','Functions - Time History - User Defined',
         ['Name','Time','Value'],[['TEST_PULSE',str(t),str(v)] for t,v in [(0,0),(.02,.01),(.04,0),(.06,-.01),(.08,0)]])
    api('Func','GetValues',['TEST_PULSE'])
    attempt('add_time_history_case','TEST_TH_LINEAR','TEST_PULSE',n_steps=5,time_step=.02)
    # Explicit opt-in on this synthetic copy ONLY; this branch remains unvalidated.
    attempt('add_time_history_case','TEST_TH_NL','TEST_PULSE',nonlinear=True,
            experimental_nonlinear=True,n_steps=5,time_step=.02)
    tool('describe_oapi','DesignShearWall','Start')
    tool('save_model')
    api('Analyze','SetRunCaseFlag',['',False,True])
    for case in ['Dead','TEST_G','TEST_X','Modal','TEST_RS','TEST_PD','TEST_NL','TEST_TH_LINEAR','TEST_TH_NL']:
        try: api('Analyze','SetRunCaseFlag',[case,True,False])
        except Exception as exc: failures.append({'case':case,'error':str(exc)})
    attempt('run_analysis')
    tool('get_analysis_status')
    linear=json.loads(tool('get_joint_displacements','All',item_type=2,cases=['TEST_TH_LINEAR'],max_results=1000))
    assert linear['total_results'] > 0 and any(abs(row['U1']) > 1e-12 for row in linear['results'])
    try: api('DesignShearWall','StartDesign')
    except Exception as exc: failures.append({'api':'DesignShearWall.StartDesign','error':str(exc)})
    attempt('get_shearwall_design')
    attempt('get_shearwall_rebar')
    tool('save_model')

    # Independent steel variant of the analytical fixture.
    tool('open_model',str(out/'cantilever.edb'),'kN, m, C')
    tool('save_model',str(out/'steel.edb'))
    api('','SetModelIsLocked',[False])
    tool('define_steel_material','TEST_STEEL',345000.0,fu=450000.0,E=200000000.0,unit_weight=77.0)
    tool('define_i_section','TEST_I','TEST_STEEL',.4,.2,.016,.01)
    tool('assign_sections','TEST_I','TEST_I')
    tool('save_model')
    tool('run_analysis')
    attempt('run_steel_design','AISC 360-16')
    tool('describe_oapi','DesignSteel','GetSummary')
    api('DesignSteel','GetSummaryResults',['1',0,[],[],[],[],[],[],[],0])
    tool('save_model')
    tool('close_model',save=True)
    check('closed_model_frames',len(tool('get_frames')),0)
    tool('open_model',str(out/'steel.edb'),'kN, m, C')
    check('steel_reopened_frames',len(tool('get_frames')),1)
    (out/'advanced-failures.json').write_text(json.dumps(failures,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'ADVANCED COMPLETED WITH {len(failures)} FINDINGS',flush=True)
