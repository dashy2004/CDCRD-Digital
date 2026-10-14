-- CDCRD: deterministic Civil 3D package importer. Uses BeamNG's public engine API.
local M = {}
local im = ui_imgui
local pathBuffer
local message = 'Seleccione el manifest.json de un nivel nuevo.'
local windowName = 'cdcrdCivilImport'

local function fail(text) error(text, 0) end
local function finite(v) return type(v) == 'number' and v == v and math.abs(v) < math.huge end
local function relativePath(p)
  if type(p) ~= 'string' or p == '' or p:find('\\') or p:find(':') or p:sub(1,1) == '/' then
    fail('Ruta relativa invalida')
  end
  for part in p:gmatch('[^/]+') do
    if part == '.' or part == '..' then fail('Ruta fuera del paquete') end
  end
  return p
end

local function readPackage(manifestPath)
  local id = manifestPath:match('^/levels/([a-z][a-z0-9_]*)/manifest%.json$')
  if not id then fail('Instale el paquete como /levels/<id>/manifest.json') end
  if #id > 48 then fail('Id del nivel demasiado largo') end
  local root = '/levels/' .. id .. '/'
  local data = jsonReadFile(manifestPath)
  if not data or data.schema ~= 'cdcrd.beamng.package/1' or data.units ~= 'm' or data.level_id ~= id then
    fail('Schema, unidades o id del nivel incompatibles')
  end
  if getCurrentLevelIdentifier() ~= id then fail('Abra el nivel de destino antes de importar') end
  local t = data.terrain
  if not t or not finite(t.size) or t.size < 128 or t.size > 8192 or t.size % 1 ~= 0 then
    fail('Tamano de terreno invalido')
  end
  local size = t.size
  while size > 1 and size % 2 == 0 do size = size / 2 end
  if size ~= 1 or not finite(t.square_size) or t.square_size <= 0 or not finite(t.max_height) or t.max_height <= 0 then
    fail('Escala o potencia de dos invalida')
  end
  if t.row0 ~= 'maxY' or t.height_scale_divisor ~= 65536 or t.flip_y ~= false then
    fail('Orientacion o escala vertical no soportada')
  end
  local function checkFile(p)
    relativePath(p)
    if not FS:fileExists(root .. p) then fail('Archivo ausente: ' .. p) end
    if not data.sha256_hex_strings or type(data.sha256_hex_strings[p]) ~= 'string' then fail('Archivo sin SHA256 binario: ' .. p) end
    if not hashStringSHA256 then fail('Este build no permite verificar SHA256') end
    local file = io.open(root .. p, 'rb')
    if not file then fail('No se pudo leer: ' .. p) end
    local bytes = file:read('*all')
    file:close()
    -- Native hashStringSHA256 truncates binary strings at the first NUL byte.
    local hex = bytes:gsub('.', function(c) return string.format('%02x', c:byte()) end)
    if hashStringSHA256(hex):lower() ~= data.sha256_hex_strings[p]:lower() then fail('SHA256 no coincide: ' .. p) end
  end
  checkFile(t.heightmap)
  if t.holemap then checkFile(t.holemap) end
  if t.material_mask then checkFile(t.material_mask) end
  if type(data.meshes) ~= 'table' or #data.meshes == 0 then fail('Paquete sin mallas') end
  for _, mesh in ipairs(data.meshes) do
    if not mesh.file:match('%.dae$') then fail('La malla debe ser DAE') end
    checkFile(mesh.file)
  end
  local p = data.spawn_local_m
  if type(p) ~= 'table' or #p ~= 3 or not finite(p[1]) or not finite(p[2]) or not finite(p[3]) then
    fail('Posicion inicial invalida')
  end
  if scenetree.findObject('cdx_civil_import') then fail('Este nivel ya contiene una importacion; use una revision nueva') end
  return data, root
end

local function createMaterial(name, root, color, groundType)
  local existing = scenetree.findObject(name)
  if existing then return existing end
  local material = createObject('Material')
  material.mapTo = name
  material:setField('diffuseColor', 0, color)
  material:setField('diffuseMap', 0, root .. 'art/textures/' .. name .. '.png')
  material:setField('groundType', 0, groundType)
  material:setField('doubleSided', 0, '1')
  material:registerObject(name)
  return material
end

local function importPackage(manifestPath)
  local data, root = readPackage(manifestPath)
  local created = {}
  local group
  local ok, result = xpcall(function()
    if not scenetree.MissionGroup then fail('El nivel no tiene MissionGroup') end
    group = createObject('SimGroup')
    group:registerObject('cdx_civil_import')
    table.insert(created, group)
    scenetree.MissionGroup:addObject(group)
    createMaterial('road_asphalt', root, '0.13 0.13 0.13 1', 'ASPHALT')
    createMaterial('road_earth', root, '0.32 0.27 0.19 1', 'DIRT')
    local matName = 'cdx_' .. data.level_id .. '_dirt'
    local terrainMaterial = scenetree.findObject(matName)
    if not terrainMaterial then
      terrainMaterial = createObject('TerrainMaterial')
      terrainMaterial.internalName = matName
      terrainMaterial.diffuseMap = root .. 'art/textures/road_earth.png'
      terrainMaterial.diffuseSize = 100
      terrainMaterial.detailMap = root .. 'art/textures/road_earth.png'
      terrainMaterial.detailSize = 5
      terrainMaterial.groundmodelName = 'DIRT'
      terrainMaterial:registerObject(matName)
      table.insert(created, terrainMaterial)
    end
    local terrain = TerrainBlock()
    terrain:setName('cdx_civil_terrain')
    terrain:registerObject('cdx_civil_terrain')
    table.insert(created, terrain)
    terrain:setPosition(vec3(0,0,0))
    terrain:setTerrFileLvlFolder(root)
    group:addObject(terrain)
    local maps = {}
    if data.terrain.material_mask then
      maps = {{path=root .. data.terrain.material_mask, material=matName,
        materialId=im.IntPtr(0), channel='R', channelId=im.IntPtr(0)}}
    end
    local imported = terrain:importMaps(root .. data.terrain.heightmap, data.terrain.square_size,
      data.terrain.max_height, data.terrain.holemap and root .. data.terrain.holemap or '',
      {matName}, maps, false)
    if imported ~= true then fail('BeamNG rechazo la importacion del terreno') end
    local terrainFile = root .. 'cdx_civil_terrain.ter'
    if terrain:save(terrainFile) == false then fail('No se pudo guardar el terreno') end
    terrain:setField('terrainFile', 0, terrainFile)
    for i, mesh in ipairs(data.meshes) do
      local obj = createObject('TSStatic')
      obj.shapeName = root .. mesh.file
      obj:setField('collisionType', 0, 'Collision Mesh')
      obj:setField('decalType', 0, 'Collision Mesh')
      obj:setField('prebuildCollisionData', 0, '1')
      obj:setPosition(vec3(0,0,0))
      obj:setScale(vec3(1,1,1))
      obj:registerObject('cdx_civil_road_' .. i)
      table.insert(created, obj)
      group:addObject(obj)
    end
    local spawn = scenetree.findObject('spawn_default')
    if spawn then spawn:setPosition(vec3(unpack(data.spawn_local_m))) end
    if editor and editor.setDirty then editor.setDirty() end
    local audit = {schema='cdcrd.beamng.import-result/1', ok=true, level_id=data.level_id,
      terrain_file=terrainFile, mesh_count=#data.meshes, terrain_size=data.terrain.size,
      spawn_local_m=data.spawn_local_m, saved_scene=false}
    if not jsonWriteFile(root .. 'import_result.json', audit, true) then fail('No se pudo escribir el resultado') end
    return audit
  end, debug.traceback)
  if not ok then
    for i = #created, 1, -1 do pcall(function() created[i]:delete() end) end
    error(result, 0)
  end
  return result
end

local function saveImportedLevel()
  local root = '/levels/' .. getCurrentLevelIdentifier() .. '/'
  if not scenetree.findObject('cdx_civil_import') then fail('No hay importacion para guardar') end
  if not editor or not editor.saveLevel then fail('Active el World Editor para guardar') end
  editor.saveLevel()
  local paths = FS:findFiles(root .. 'main/', 'items.level.json', -1, true, false)
  local savedTerrain, savedRoad, savedGroup = false, false, false
  for _, file in ipairs(paths or {}) do
    local content = readFile(file) or ''
    if content:find('"cdx_civil_terrain"', 1, true) then savedTerrain = true end
    if content:find('"cdx_civil_road_1"', 1, true) then savedRoad = true end
    if content:find('"cdx_civil_import"', 1, true) then savedGroup = true end
  end
  if not (savedTerrain and savedRoad and savedGroup) then fail('La escena no quedo serializada; revise el registro del editor') end
  local result = jsonReadFile(root .. 'import_result.json') or {}
  result.saved_scene = true
  jsonWriteFile(root .. 'import_result.json', result, true)
  return result
end

local function onEditorInitialized()
  pathBuffer = im.ArrayChar(512, '/levels/mi_carretera/manifest.json')
  editor.registerWindow(windowName, im.ImVec2(560, 210))
  editor.addWindowMenuItem('Importar Civil 3D', function() editor.showWindow(windowName) end)
end

local function onEditorGui()
  if not editor.isWindowVisible(windowName) then return end
  if editor.beginWindow(windowName, 'Civil 3D a BeamNG.drive') then
    im.Text('Paquete instalado en un nivel nuevo:')
    im.InputText('Manifest', pathBuffer)
    if im.Button('Buscar...') then
      editor_fileDialog.openFile(function(data)
        pathBuffer = im.ArrayChar(512, data.filepath)
      end, {{'Manifest JSON', '*.json'}}, false, '/levels/', true)
    end
    im.SameLine()
    if im.Button('Importar terreno y carretera') then
      local ffi = require('ffi')
      local ok, result = pcall(importPackage, ffi.string(pathBuffer))
      message = ok and 'Importado. Guarde el nivel y vuelva a cargarlo para comprobar.' or tostring(result)
    end
    if im.Button('Guardar nivel importado') then
      local ok, result = pcall(saveImportedLevel)
      message = ok and 'Nivel guardado.' or tostring(result)
    end
    im.TextWrapped(message)
  end
  editor.endWindow()
end

M.importPackage = importPackage
M.validatePackage = readPackage
M.saveImportedLevel = saveImportedLevel
M.onEditorInitialized = onEditorInitialized
M.onEditorGui = onEditorGui
return M
