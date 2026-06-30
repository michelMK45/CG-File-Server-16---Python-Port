function AccessoryUpdate(idx)
	local as = gSportsRNA
	local accessory = as:GetTable("wvAccessory", idx)
	
	local state = as:GetTable("wvState") -- to get the lighting and weather
	db.accessory[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
	db.accessory[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
	local stadType =  as:GetString(state, "wvAttribStadType")
	if( stadType == "festadium") then
		db.accessory[idx].stadiumType = 0
	else
		db.accessory[idx].stadiumType = 1
	end
	db.accessory[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")

	--RM
	local player = as:GetTable("wvPlayer", math.floor(idx/10))
	db.accessory[idx].playerid = as:GetInt(player, "playerassetid")
	db.accessory[idx].kit = as:GetInt(player, "kit")
	db.accessory[idx].teamid = as:GetInt(player, "teamid") 
	db.accessory[idx].kitType = as:GetInt(player, "kitType") %20
	db.accessory[idx].kitYear = as:GetInt(player, "kitYear")
	
	
	
	local isVirtualPro = as:GetInt(player, "isVirtualPro")
	local isCreatePlayer = as:GetInt(player, "isCreatePlayer")
	local kitNumber = as:GetInt(player, "kitNumber")
	local shoeType = as:GetInt(player, "shoeType")
	local eyeColor = as:GetInt(player, "eyeColor")
	local hair = as:GetInt(player, "hair")
	local hairColor = as:GetInt(player, "hairColor")
	local bodySkinToneType = as:GetInt(player, "playerBodySkinToneType")
	
	--VP FIX
	if (isVirtualPro == 1) then
	db.accessory[idx].playerid = 30999
	else
	if (isCreatePlayer == 1) then
	if (shoeType == identifyVP[1]) then
	if (hair == identifyVP[2]) then
	if (hairColor == identifyVP[3]) then
	if (eyeColor == identifyVP[4]) then
	if (bodySkinToneType == identifyVP[5]) then
	if (kitNumber == identifyVP[6]) then
	db.accessory[idx].playerid = 30999	
	end
	end
	end
	end
	end
	end
	end
	end
	
	
	
	
	
	
	
	if (db.accessory[idx].kitType == 5) then
	db.accessory[idx].teamid = 6004
	db.accessory[idx].playerid = db.accessory[idx].playerid + 500000
	end
	
	local wipe3d = as:GetTable("wvWipe", 1)
	db.accessory[idx].tournid = as:GetInt(wipe3d, "leagueID")
	db.accessory[idx].tournid = getTournamentGraphics(db.accessory[idx].tournid)
	
	
	
	local teamside = as:GetInt(player, "teamside")
	
	local outidx = 9
	if (teamside == 1) then
	outidx = 20
	end
	
	local outplayer = as:GetTable("wvPlayer", outidx)
	
	local kitOutfield = as:GetInt(outplayer, "kit") 
	local kitTypeOutfield = as:GetInt(outplayer, "kitType") 
	local kitYearOutfield = as:GetInt(outplayer, "kitYear")

	--CLASSIC KIT BOOT DECADE
	db.accessory[idx].kitYearDecade = -1
	if (kitYearOutfield > 0) then
	db.accessory[idx].tournid = kitYearOutfield
	db.accessory[idx].kitYearDecade = math.floor(kitYearOutfield/10)*10
	end
	
	
	
	
	db.accessory[idx].speckitType = -1
	
	local isgoalie = as:GetInt(player, "goalie")


	local stadium = as:GetTable("wvStadium", 1)
		
	local homeKitTeamID = as:GetInt(stadium, "homeKitTeamID" )
	local awayKitTeamID = as:GetInt(stadium, "awayKitTeamID" )
	local homeKitTypeID = as:GetInt(stadium, "homeKitTypeID" )
	local awayKitTypeID = as:GetInt(stadium, "awayKitTypeID" )
	


	if ((isgoalie == 1) and (math.floor(idx/10) > 1)) then
	
	--ALTERNATE GK
	if ((kitOutfield ~= 7000)) then
	db.accessory[idx].speckitType = kitTypeOutfield + 30
	end
	
	if (db.accessory[idx].kitYear == 0) then
	if (teamside == 0) then
	db.accessory[idx].speckitType = getGKKit(db.accessory[idx].kit,homeKitTypeID,homeKitTeamID,awayKitTeamID,db.accessory[idx].kitType,db.accessory[idx].speckitType)
	else
	db.accessory[idx].speckitType = getGKKit(db.accessory[idx].kit,awayKitTypeID,homeKitTeamID,awayKitTeamID,db.accessory[idx].kitType,db.accessory[idx].speckitType)
	end
	end
	
	end
	
	
	
	
	--NON GK KIT
	if ((isgoalie == 0) and (math.floor(idx/10) > 1)) then
	
	--SPECIFIC MATCH KIT
	if (db.accessory[idx].kitYear == 0) then
	db.accessory[idx].speckitType = getGameKit(db.accessory[idx].kit,homeKitTeamID,awayKitTeamID,db.accessory[idx].kitType,db.accessory[idx].speckitType)
	end
	
	end
	
	
	
	
	
	if (idx%10 == 0) then
	if ((isCreatePlayer ~= 1) or (teamside ~= -1)) then
	LoadAsync("data/fifarna/lua/assignments/players/player_"..db.accessory[idx].playerid..".lua")
	LoadAsyncWait()
	end
	end
	
	
	

	
	-- if (db.accessory[idx].kitYear ~= 0) then
	-- db.accessory[idx].tournid = db.accessory[idx].kitYear
	-- end
	
	--GET SLEEVE LENGTH
	local weather = as:GetInt(state, "wvAttribStadWeather" )
	local climate = as:GetInt(state, "wvAttribStadClimate")
	local winterAcc = getWinterAccessoriesWeather(weather,climate)
	local jerseySleeveLength = as:GetInt(player, "jerseySleeveLength")
	local seasonal = jerseySleeveLength
	
	if (isCreatePlayer ~= 1) then
	seasonal = as:GetInt(player, "seasonaljersey")
	end
	
	seasonal = getWinterAccessories(db.accessory[idx].playerid,seasonal)
	jerseySleeveLength = getSleeveLength(db.accessory[idx].playerid,jerseySleeveLength)
	if (winterAcc) then
		jerseySleeveLength = seasonal
	end

    -- Calculation below is to minimize the amount of textures loaded for accessories. Forces the sharing of 1 colormap for left/right meshes.
    -- This is assuming all accessories that require left and right variations have model = even# for left, odd# for right
    -- AND
    -- all single-variation accessories have even# for model
    -- Ideal solution: retrieve modelvar from database so that we don't have to make assumptions here
    local modelNum = as:GetInt(accessory, "accessoryModel")
	
	local modelNum2 = modelNum
	
	--ACCESSORY MODEL
	modelNum = getAccessoryModel(db.accessory[idx].playerid,modelNum,kitYearOutfield)
	
	--DISABLE
	if (acc and (modelNum < 28)) then 
	modelNum = -1
	end
	
	
	--IF LONG SLEEVES
	if (jerseySleeveLength > 0) then
	if (modelNum == 8) then
		modelNum = -1
	end
	if (modelNum == 9) then
		modelNum = -1
	end
	if ((modelNum > 23) and (modelNum < 28)) then
		modelNum = -1
	end
	end
	
	
	db.accessory[idx].model = modelNum - math.abs(modelNum % 2)
	db.accessory[idx].modelvar = math.abs(modelNum % 2)
	db.accessory[idx].color = as:GetInt(accessory, "accessoryColor")
	db.accessory[idx].material = "accessory"
	db.accessory[idx].accessoryname = "accessory"
	db.accessory[idx].coloridx = 0
	db.accessory[idx].isgkglove = 0
	db.accessory[idx].gender = as:GetInt(accessory, "gender")
	
	--ACCESSORY COLOUR
	db.accessory[idx].color = getAccessoryColour(db.accessory[idx].playerid,modelNum2,db.accessory[idx].color)
	
	-- special case for gkgloves
	if ( db.accessory[idx].model == 18 ) then
		db.accessory[idx].model = db.accessory[idx].color
		db.accessory[idx].accessoryname = "gkglove"
		db.accessory[idx].material = "gkglove"
		db.accessory[idx].isgkglove = 1
	elseif (db.accessory[idx].model > 27 and db.accessory[idx].model < 36) then
		-- referee cards are 28 and 30, just use diffuse.
		db.accessory[idx].material = "accessory"
	elseif (db.accessory[idx].model > 4) then
		db.accessory[idx].coloridx = db.accessory[idx].color
		db.accessory[idx].color = 0  -- use 0 for runtime recolouring
		db.accessory[idx].material = "gkglove"
		
	else
		-- referee watches, referee earpieces
		-- db.accessory[idx].coloridx = db.accessory[idx].color
		-- db.accessory[idx].color = 0  -- use 0 for runtime recolouring
		-- db.accessory[idx].material = "accessories_matte"
	end
end

---------------------------------------------------------------------------------------------------
-- Get accessory color to dispatch to shader 
function GetAccessoryColorARGB(idx)
	-- gamma'd list r*r g*g b*b
	accessoryColorList = { 0x00cdcdcd, 0x000a0a0a, 0x00000072, 0x00720000, 
						   0x00cece00, 0x00000900, 0x009b0900, 0x00090026, 
						   0x00060000, 0x00e112e1, 0x00130001, 0x000038e1, 
						   0x0000001f, 0x003f3f3f }

	local clr = accessoryColorList[db.accessory[idx].coloridx + 1] 
	
	if (clr == nil) then
		clr = 0x00ffffff
	end
	return clr
end

---------------------------------------------------------------------------------------------------
function GetAccessoryMesh(idx)
	if (db.accessory[idx].isgkglove == 1) then
		return "data/sceneassets/${db.accessory[?].accessoryname}/${db.accessory[?].accessoryname}_${db.accessory[?].color}.rx3"
	else
		return "${GetRMAccessory(?,0)}data/sceneassets/${db.accessory[?].accessoryname}/${db.accessory[?].accessoryname}_${db.accessory[?].model}_${db.accessory[?].modelvar}_${db.accessory[?].gender}.rx3"
	end
end

---------------------------------------------------------------------------------------------------
function GetAccessoryTexture(idx)
	if (db.accessory[idx].isgkglove == 1) then
		return "${GetRMGKGlove(?)}data/sceneassets/${db.accessory[?].accessoryname}/${db.accessory[?].accessoryname}_${db.accessory[?].model}_textures.rx3"
	else
		return "${GetRMAccessory(?,1)}data/sceneassets/${db.accessory[?].accessoryname}/${db.accessory[?].accessoryname}_${db.accessory[?].model}_${db.accessory[?].color}_textures.rx3"
	end
end

---------------------------------------------------------------------------------------------------
function AccessoryAssetBind(accessory)
	local gr = gRenderables
   	local lod = 0

	local VISIBILITY_GROUP_INGAME = 64
	
	gr:AddCallback(accessory, lod, "AccessoryUpdate(?)")
	gr:AddAsset(accessory, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(accessory, lod, "accessorymesh", "${GetAccessoryMesh(?)}")
	gr:AddAsset(accessory, lod, "accessorytex", "${GetAccessoryTexture(?)}" )
	gr:AddAsset(accessory, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.accessory[?].envLighting}.rx3")	
	
	local part = "accessorymesh"
	gr:CreateMaterialFromAttribulator(accessory, lod, part, "accessory", "${db.accessory[?].material}" )
	gr:SetTexture(accessory, lod, part, "textures", "diffuseTexture", "accessorytex", "${db.accessory[?].accessoryname}_cm")
	gr:SetTexture(accessory, lod, part, "textures", "normalMap", "accessorytex", "${db.accessory[?].accessoryname}_nm")
	gr:SetTexture(accessory, lod, part, "textures", "coeffMap", "accessorytex", "${db.accessory[?].accessoryname}_coeff")
	gr:SetTexture(accessory, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(accessory, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetConstantARGB(accessory, lod, part, "global", "MaterialColour", "${GetAccessoryColorARGB(?)}")
	gr:SetTextureFromRuntime(accessory, lod, part, "textures", "coverageMap", "covmap_${db.accessory[?].stadiumID}_${db.accessory[?].stadiumLightID}_${db.accessory[?].stadiumType}")
    gr:SetTextureFromRuntime(accessory, lod, part, "textures", "stadiumShadowMap", "shadowmap_${db.accessory[?].stadiumID}_${db.accessory[?].stadiumLightID}_${db.accessory[?].stadiumType}")
	gr:SetVisibilityGroup(accessory, lod, part, VISIBILITY_GROUP_INGAME); 
	
	return accessory
end


acc = false

function removeAccessories()
acc = true
end



accessoryModel = {}
accessoryColour = {}

function swapAccessory(player,old,new,colour)

if (accessoryModel[player] == nil) then
accessoryModel[player] = {}
end

if (accessoryColour[player] == nil) then
accessoryColour[player] = {}
end

accessoryModel[player][old] = new
accessoryColour[player][old] = colour
end

function getAccessoryModel(player,old,year)

if (((old == 2) or ((old > 4) and (old < 28))) and (year > 0)) then
if (old == 18) then
if (year <= classicKitGKGlovesYear) then
return -1
end
else
if (year <= classicKitAccessoriesYear) then
return -1
end
end
end


if (accessoryModel[player] ~= nil) then
if (accessoryModel[player][old] ~= nil) then
return accessoryModel[player][old]
end
end

return old
end

function getAccessoryColour(player,old,colour)

if (accessoryColour[player] ~= nil) then
if (accessoryColour[player][old] ~= nil) then
return accessoryColour[player][old]
end
end

return colour
end


function GetRMAccessory(idx,isModel)
	local pct = ""
	local fileType = ""
	
	if (isModel == 1) then
	fileType = "_textures"
	end
		
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_"..db.accessory[idx].speckitType.."_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_"..db.accessory[idx].kitType.."_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_0_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_0_"..db.accessory[idx].teamid.."_"..db.accessory[idx].speckitType.."_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_0_"..db.accessory[idx].teamid.."_"..db.accessory[idx].kitType.."_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_0_"..db.accessory[idx].teamid.."_0_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].playerid.."_0_"..db.accessory[idx].speckitType.."_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].playerid.."_0_"..db.accessory[idx].kitType.."_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/specific"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].playerid.."_0_0_"..(db.accessory[idx].model+db.accessory[idx].modelvar)..""..fileType..".rx3;"
	
	pct = pct.."data/sceneassets/"..db.accessory[idx].accessoryname.."/generic"..db.accessory[idx].accessoryname.."_"..db.accessory[idx].model.."_0_"..db.accessory[idx].coloridx..""..fileType..".rx3;"
	
	
	return pct
end


function GetRMGKGlove(idx)
	local pct = ""
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_"..db.accessory[idx].speckitType.."_"..db.accessory[idx].tournid.."_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_"..db.accessory[idx].kitType.."_"..db.accessory[idx].tournid.."_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_0_"..db.accessory[idx].tournid.."_textures.rx3;"
	
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_0_"..db.accessory[idx].speckitType.."_"..db.accessory[idx].tournid.."_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_0_"..db.accessory[idx].kitType.."_"..db.accessory[idx].tournid.."_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_0_0_"..db.accessory[idx].tournid.."_textures.rx3;"
	
	pct = pct.."data/sceneassets/gkglove/playergkglove_0_"..db.accessory[idx].teamid.."_"..db.accessory[idx].speckitType.."_"..db.accessory[idx].tournid.."_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_0_"..db.accessory[idx].teamid.."_"..db.accessory[idx].kitType.."_"..db.accessory[idx].tournid.."_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_0_"..db.accessory[idx].teamid.."_0_"..db.accessory[idx].tournid.."_textures.rx3;"
	--pct = pct.."data/sceneassets/gkglove/playergkglove_0_"..db.accessory[idx].teamid.."_0_0_textures.rx3;"
	
	pct = pct.."data/sceneassets/gkglove/playergkglove_0_0_0_"..db.accessory[idx].kitYearDecade.."_textures.rx3;"
	
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_"..db.accessory[idx].speckitType.."_0_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_"..db.accessory[idx].kitType.."_0_textures.rx3;"
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_"..db.accessory[idx].teamid.."_0_0_textures.rx3;"
	
	pct = pct.."data/sceneassets/gkglove/playergkglove_"..db.accessory[idx].playerid.."_0_0_0_textures.rx3;"
	return pct
end



classicKitGKGlovesYear = 0
classicKitAccessoriesYear = 0

function removeClassicKitGKGloves(year)
classicKitGKGlovesYear = year
end

function removeClassicKitAccessories(year)
classicKitAccessoriesYear = year
end



--Revolution Mod 16 V1.0
--Edited by scouser09