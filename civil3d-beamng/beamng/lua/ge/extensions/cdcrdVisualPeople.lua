-- Visual people for illustrative non-contact crossing scenes, not human physics.
local M = {}
local actors = {}
local clock, crossingStart, running, cfg = 0, nil, false, nil
local function clear()
  local group = scenetree.findObject('cdx_visual_people')
  if group then group:delete() end
  actors = {}; running = false; crossingStart = nil; clock = 0
end
local function place(actor, frame, x, y, z)
  if actor.current ~= frame then
    if actor.current then actor.objects[actor.current]:setHidden(true) end
    actor.objects[frame]:setHidden(false); actor.current = frame
  end
  actor.objects[frame]:setPosition(vec3(x,y,z))
  actor.position = {x,y,z}
end
local function setup(options)
  assert(type(options)=='table' and options.level==getCurrentLevelIdentifier(), 'Actor level mismatch')
  assert(options.level:match('^cdx_'), 'Owned level required')
  clear();cfg=options
  local root='/levels/'..options.level..'/art/actors/'
  local poses=jsonReadFile(root..'poses.json');assert(poses, 'Missing inspected actor frames')
  local group=createObject('SimGroup');group:registerObject('cdx_visual_people');group.canSave=false
  scenetree.MissionGroup:addObject(group)
  for i, spec in ipairs(options.people) do
    assert(spec.kind=='adult' or spec.kind=='student', 'Invalid actor kind')
    local actor={spec=spec, objects={}}
    for n, name in ipairs(poses[spec.kind]) do
      local obj=createObject('TSStatic');obj.shapeName=root..name
      obj:setField('collisionType',0,'None');obj:setField('decalType',0,'None')
      obj:registerObject('cdx_actor_'..i..'_'..n);obj.canSave=false
      obj:setScale(vec3(1,1,1));obj:setHidden(true);group:addObject(obj)
      table.insert(actor.objects,obj)
    end
    table.insert(actors,actor)
    place(actor,1,spec.position[1],spec.position[2],spec.position[3])
  end
end
local function start()
  clock=0;running=true;crossingStart=cfg.start_s
end
local function beginCrossing()
  if not crossingStart then crossingStart=clock end
end
local function onUpdate(dtReal,dtSim)
  if not running then return end
  clock=clock+(dtSim or 0)
  for _,actor in ipairs(actors) do
    local spec=actor.spec
    if spec.kind=='student' and crossingStart then
      local elapsed=clock-crossingStart-(spec.delay or 0)
      local distance=math.max(0,math.min(7.9,elapsed*1.25))
      local y=spec.position[2]-distance
      local absoluteY=y-cfg.origin_shift_y
      local edge=math.max(0,math.min(1,(math.abs(absoluteY)-3.05)/.4))
      local z=cfg.road_z+.14*edge
      local frame=(distance>0 and distance<7.9) and (2+math.floor(math.max(0,elapsed)*24)%25) or 1
      place(actor,frame,spec.position[1],y,z)
    end
  end
end
local function readback()
  local positions={}
  for i,a in ipairs(actors) do positions[i]={kind=a.spec.kind,position=a.position,frame=a.current} end
  return {time_s=clock,crossing_start_s=crossingStart,positions=positions,visual_only=true}
end
M.setup=setup;M.start=start;M.beginCrossing=beginCrossing;M.readback=readback
M.onUpdate=onUpdate;M.onClientEndMission=clear
return M
