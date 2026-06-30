---------------------------------------------------------------------------------------------------
local SLC_STEWARD_TYPE = 0
local SLC_PHOTOGRAPHER_TYPE = 1
local SLC_CAMERAMAN_STANDING_TYPE = 2
local SLC_CAMERAMAN_PLATFORM_TYPE = 3
local SLC_MEDICAL_TYPE = 4
local SLC_BALLBOY_TYPE = 5
local SLC_GENERIC_TYPE = 6
local SLC_POLICE_TYPE = 7
local SLC_BENCH_PLAYER_HOME_TYPE = 8
local SLC_BENCH_PLAYER_AWAY_TYPE = 9
local SLC_MANAGER_HOME_TYPE = 10
local SLC_MANAGER_AWAY_TYPE = 11
local SLC_CHOREO_BALLBOY_TYPE = 12
local SLC_CAMERAMAN_HANDHELD_TYPE = 13
local SLC_ASSISTANT_MANAGER_HOME_TYPE = 14
local SLC_ASSISTANT_MANAGER_AWAY_TYPE = 15
local SLC_TOURNAMENT_OFFICIAL_TYPE = 16
local SLC_CHOREO_STEADYCAM_TYPE = 17
local SLC_CHOREO_PHOTOGRAPHER_TYPE = 18
local SLC_CHOREO_CRANECAM_TYPE = 19
local SLC_CHOREO_SHOULDER_CAM_TYPE = 20
local SLC_CHOREO_POLICE_TYPE = 21
local SLC_CHOREO_STEWARD_TYPE = 22

local SLC_NUM = 23

---------------------------------------------------------------------------------------------------
local VARIATIONS = {
      [SLC_STEWARD_TYPE]                =      { name="steward",              skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_PHOTOGRAPHER_TYPE]           =      { name="photographer",         skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 2 }, suitvariation = { 0, 1 } },
      [SLC_CAMERAMAN_STANDING_TYPE]     =      { name="cameramanhandheld",    skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_CAMERAMAN_PLATFORM_TYPE]     =      { name="cameramansitting",     skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_MEDICAL_TYPE]                =      { name="paramedic",          skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_BALLBOY_TYPE]                =      { name="ballboy",              skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_GENERIC_TYPE]                =      { name="generic",              skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_POLICE_TYPE]                 =      { name="policeofficer",        skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 1, 9 }, suitvariation = { 0, 1 } },
      [SLC_BENCH_PLAYER_HOME_TYPE]      =      { name="benchplayer",          skintone = { 1, 10 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_BENCH_PLAYER_AWAY_TYPE]      =      { name="benchplayer",          skintone = { 1, 10 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_MANAGER_HOME_TYPE]           =      { name="manager",              skintone = { 1, 10 }, bodytype = { 0, 3 }, suittype = { 0, 3 }, suitvariation = { 0, 2 } },
      [SLC_MANAGER_AWAY_TYPE]           =      { name="manager",              skintone = { 1, 10 }, bodytype = { 0, 3 }, suittype = { 0, 3 }, suitvariation = { 0, 2 } },
      [SLC_CHOREO_BALLBOY_TYPE]         =      { name="ballboy",              skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_CAMERAMAN_HANDHELD_TYPE]        =      { name="cameramanhandheld",    skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_ASSISTANT_MANAGER_HOME_TYPE] =      { name="assistantmanager",     skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_ASSISTANT_MANAGER_AWAY_TYPE] =      { name="assistantmanager",     skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_TOURNAMENT_OFFICIAL_TYPE]    =      { name="tournamentofficial",    skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_CHOREO_STEADYCAM_TYPE]        =      { name="cameramansteady",    skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_CHOREO_PHOTOGRAPHER_TYPE]    =      { name="photographer",        skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 2 }, suitvariation = { 0, 1 } },
      [SLC_CHOREO_CRANECAM_TYPE]        =      { name="photographer",        skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_CHOREO_SHOULDER_CAM_TYPE]    =      { name="cameramanhandheld",    skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } },
      [SLC_CHOREO_POLICE_TYPE]          =      { name="policeofficer",        skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 1, 9 }, suitvariation = { 0, 1 } },
      [SLC_CHOREO_STEWARD_TYPE]         =      { name="steward",              skintone = { 0, 1 }, bodytype = { 0, 1 }, suittype = { 0, 1 }, suitvariation = { 0, 1 } }
}

---------------------------------------------------------------------------------------------------
function SleUpdate(idx)
    local as = gSportsRNA
    local sle = as:GetTable("wvSle", idx)
    local state = as:GetTable("wvState") -- to get the lighting and weather
    local stadium = as:GetTable("wvStadium", 1) -- to get the policeType only in BE stadiums
    
    -- need to bring clothing color for bench player
    db.sle[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
    db.sle[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
    db.sle[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
    local stadType =  as:GetString(state, "wvAttribStadType")
    if( stadType == "festadium") then
        db.sle[idx].stadiumType = 0
    else
        db.sle[idx].stadiumType = 1
    end

    local weather = as:GetInt(state, "wvAttribStadWeather")
    local climate = as:GetInt(state, "wvAttribStadClimate") -- 0: warm, 1: cold

    if (weather == 1 or weather == 2 or climate == 1) then
        db.sle[idx].cold = 1
    else
        db.sle[idx].cold = 0
    end

    -- asset naming rules
    --  mesh_suittype_bodytype_cold.rx3
    --  tex_suittype_skintone_suitvariation_cold_textures.rx3

    -- parameters
    --  skintone
    --  bodytype
    --  suittype
    --  suitvariation
    --  customcolor
          
    local sletype = as:GetInt(sle, "sletype")
    db.sle[idx].sletype = sletype
    
    local sleindex = as:GetInt(sle, "sleindex")
    
    if ( sletype == nil or sletype < SLC_STEWARD_TYPE or sletype >= SLC_NUM ) then
        gSportsRNA:Assert( 0, "Invalid SLE["..idx.."] type ["..sletype.."]" )
        db.sle[idx].slename = "generic"
        db.sle[idx].skintone = 0
        db.sle[idx].bodytype = 0
        db.sle[idx].suittype = 0
        db.sle[idx].suitvariation = 0
        db.sle[idx].customcolor = 0
        return
    end
    local variation = VARIATIONS[ sletype ]
    
    local base_suittype = as:GetInt(sle, "suittype")
    if ( sletype == SLC_POLICE_TYPE or sletype == SLC_CHOREO_POLICE_TYPE ) then
          base_suittype = as:GetInt(stadium, "policeType")
    end

    local customcolor = as:GetInt(sle, "customcolor")
    if ( customcolor == -1 ) then
          if ( sletype == SLC_BENCH_PLAYER_HOME_TYPE or sletype == SLC_MANAGER_HOME_TYPE ) then
                 customcolor = as:GetInt(stadium, "homeKitColour")
          elseif ( sletype == SLC_BENCH_PLAYER_AWAY_TYPE or sletype == SLC_MANAGER_AWAY_TYPE ) then
                 customcolor = as:GetInt(stadium, "awayKitColour")
          end
    end
    
    -- The sleindex determines which variation this sle is
    local indexVariation = GetVariationsFromIndex(sleindex, variation, sletype)
    gSportsRNA:Print(indexVariation)

    db.sle[idx].slename = variation.name
    db.sle[idx].skintone = GetVariation( as:GetInt(sle, "skintone"), indexVariation.skintone )
    db.sle[idx].bodytype = GetVariation( as:GetInt(sle, "bodytype"), indexVariation.bodytype )
    db.sle[idx].suittype = GetVariation( base_suittype, indexVariation.suittype )
    db.sle[idx].suitvariation = GetVariation( as:GetInt(sle, "suitvariation"), indexVariation.suitvariation)
    db.sle[idx].customcolor = customcolor

    if ( sletype == SLC_CAMERAMAN_PLATFORM_TYPE ) then
        db.sle[idx].attribmatname = "simple_character_static"
    else
        db.sle[idx].attribmatname = "simple_character_skinned"
    end
    
    -- managers contain only a subset of the skintones used in players. - correct any errors
    if ( db.sle[idx].skintone == 1 or db.sle[idx].skintone == 3 or db.sle[idx].skintone == 7) then
        db.sle[idx].skintone = db.sle[idx].skintone + 1
    end
	
	
	
	local wipe3d = as:GetTable("wvWipe", 1)
	db.sle[idx].tournamentid = as:GetInt(wipe3d, "leagueID")
	db.sle[idx].tournamentid = getTournamentGraphics(db.sle[idx].tournamentid)

	
	db.sle[idx].teamid = as:GetInt(stadium, "homeKitTeamID" )
	
	if ((sletype == SLC_BENCH_PLAYER_AWAY_TYPE) or (sletype == SLC_MANAGER_AWAY_TYPE)) then
	db.sle[idx].teamid = as:GetInt(stadium, "awayKitTeamID" )
	end
	
	db.sle[idx].varient = db.sle[idx].cold
	
    
    --gSportsRNA:Print( "SLC("..idx..", "..sletype..", "..as:GetInt(sle, "sleindex").."): '"..db.sle[idx].slename.."' ["..db.sle[idx].skintone..", "..db.sle[idx].bodytype..", "..db.sle[idx].suittype..", "..db.sle[idx].suitvariation..", "..db.sle[idx].customcolor.."]" )
end

function GetVariationsFromIndex(sleindex, variation, sletype)
    local ret = { skintone = 0, bodytype = 0, suittype = 0, suitvariation = 0 }
    local i = 0
    
    -- This looks scary, but keep in mind the VAST majority dimensions are 1 element long
    -- and for most cases it will be an early exit at index 0 (e.g. for managers which always 
    -- have sleindex of 0)
    for skintone=variation.skintone[1], variation.skintone[2] - 1 do
        for bodytype=variation.bodytype[1], variation.bodytype[2] - 1 do
            for suittype=variation.suittype[1], variation.suittype[2] - 1 do
                for suitvariation=variation.suitvariation[1], variation.suitvariation[2] - 1 do
                    if sleindex == i then
                        ret.skintone = skintone
                        ret.bodytype = bodytype
                        ret.suittype = suittype
                        ret.suitvariation = suitvariation
                        return ret
                    end

                    i = i + 1
                end
            end
        end
    end
    
    -- Could be because of invalid variation parameters
    return ret
end

---------------------------------------------------------------------------------------------------
-- Get Variation based on initial value, base offset and num variations
function GetVariation( value, default )
    local var = value
    if ( var < 0 ) then
        var = default
    end
    return var
end

---------------------------------------------------------------------------------------------------
-- Get Texture based on character type
function GetTexture( idx )
    local sletype = db.sle[idx].sletype
    
    if ( sletype == SLC_MANAGER_HOME_TYPE or sletype == SLC_MANAGER_AWAY_TYPE) then
        return "${GetRMSle(?,1)}data/sceneassets/slc/${db.sle[?].slename}_${db.sle[?].suittype}_${db.sle[?].bodytype}_${db.sle[?].skintone}_${db.sle[?].suitvariation}_${db.sle[?].cold}_textures.rx3"
    else
        return "${GetRMSle(?,1)}data/sceneassets/slc/${db.sle[?].slename}_${db.sle[?].suittype}_${db.sle[?].skintone}_${db.sle[?].suitvariation}_${db.sle[?].cold}_textures.rx3"
    end
    
end

---------------------------------------------------------------------------------------------------
function SleAssetBind(sle)
    local gr = gRenderables
    --local lod = 0
    --
    
    
    gr:AddCallback(sle, 0, "SleUpdate(?)")
    --[[ 
        Mesh naming convention:
        slc/assetname_[geo variation]_[texture variation - 0?]_[lod]_[sunny/cold]
        Texture naming convention:
        slc/assetname_[geo variation]_0_0_[sunny/cold]
    --]]
    
    for lod = 0, 3 do
        gr:AddAsset(sle, lod, "shader", "data/fifarna/shader.big")
        
        
        gr:AddAsset(sle, lod, "slemesh_" .. lod, "${GetRMSle(?,0)}data/sceneassets/slc/${db.sle[?].slename}_${db.sle[?].suittype}_${db.sle[?].bodytype}_" .. (lod+1) .. "_${db.sle[?].cold}.rx3")
        gr:AddAsset(sle, lod, "sletex",  "${GetTexture(?)}")
        
        gr:AddAsset(sle, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.sle[?].envLighting}.rx3")
        
        local part = "slemesh_" .. lod
        gr:CreateMaterialFromAttribulator(sle, lod, part, "${db.sle[?].slename}_material", "${db.sle[?].attribmatname}" )
        gr:SetTexture(sle, lod, part, "textures", "diffuseTexture", "sletex", "cm")
        gr:SetTexture(sle, lod, part, "textures", "normalMap", "sletex", "nm")
        gr:SetTexture(sle, lod, part, "textures", "coeffMap", "sletex", "coeff")
        gr:SetTexture(sle, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
        gr:SetTexture(sle, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
        gr:SetConstantARGB(sle, lod, part, "global", "clothingColour", "${db.sle[?].customcolor}")
        gr:SetTextureFromRuntime(sle, lod, part, "textures", "coverageMap", "covmap_${db.sle[?].stadiumID}_${db.sle[?].stadiumLightID}_${db.sle[?].stadiumType}")
    end

    -- shadow asset
    --gr:AddCallback(sle, 4, "SleUpdate(?)")
    gr:AddAsset(sle, 4, "shader", "data/fifarna/shader.big")
    gr:AddAsset(sle, 4, "shadow", "data/sceneassets/crowd/crowd_shadow_0.rx3")
    gr:CreateMaterial(sle, 4, "shadow", "missingShader.fx")
    
    return sle
end

---------------------------------------------------------------------------------------------------
local DEFAULTSLETYPEMAP = {
    [0] =     { stype = SLC_STEWARD_TYPE,             snum = 45 },
    [1] =     { stype = SLC_PHOTOGRAPHER_TYPE,         snum = 40 },
    [2] =     { stype = SLC_CAMERAMAN_STANDING_TYPE,     snum = 4 },
    [3] =     { stype = SLC_CAMERAMAN_PLATFORM_TYPE,     snum = 5 },
    [4] =     { stype = SLC_MEDICAL_TYPE,             snum = 4 },
    [5] =     { stype = SLC_BALLBOY_TYPE,             snum = 0 },
    [6] =     { stype = SLC_GENERIC_TYPE,             snum = 5 },
    [7] =     { stype = SLC_POLICE_TYPE,                 snum = 30 },
    [8] =     { stype = SLC_BENCH_PLAYER_HOME_TYPE,     snum = 0 },
    [9] =     { stype = SLC_BENCH_PLAYER_AWAY_TYPE,     snum = 0 },
    [10] =     { stype = SLC_MANAGER_HOME_TYPE,         snum = 1 },
    [11] =     { stype = SLC_MANAGER_AWAY_TYPE,         snum = 1 },
    [12] =    { stype = SLC_CHOREO_BALLBOY_TYPE,        snum = 12 },
    [13] =    { stype = SLC_CAMERAMAN_HANDHELD_TYPE,    snum = 12 },
    [14] =    { stype = SLC_ASSISTANT_MANAGER_HOME_TYPE, snum = 12},
    [15] =    { stype    = SLC_ASSISTANT_MANAGER_AWAY_TYPE,    snum = 13},
    [16] =    { stype = SLC_TOURNAMENT_OFFICIAL_TYPE,    snum = 12},
    [17] =    { stype = SLC_CHOREO_STEADYCAM_TYPE,    snum = 4},
    [18] =    { stype = SLC_CHOREO_PHOTOGRAPHER_TYPE,    snum = 14},
    [19] =    { stype = SLC_CHOREO_CRANECAM_TYPE,        snum = 2},
    [20] =    { stype = SLC_CHOREO_SHOULDER_CAM_TYPE,    snum = 4},
    [21] =    { stype = SLC_CHOREO_POLICE_TYPE,        snum = 10},
    [22] =    { stype = SLC_CHOREO_STEWARD_TYPE,        snum = 10}
}

local SUPERLOWSLETYPEMAP = {
    [0] =     { stype = SLC_STEWARD_TYPE,         snum = 0 },
    [1] =     { stype = SLC_PHOTOGRAPHER_TYPE,     snum = 0 },
    [2] =     { stype = SLC_CAMERAMAN_STANDING_TYPE,     snum = 0 },
    [3] =     { stype = SLC_CAMERAMAN_PLATFORM_TYPE,     snum = 0 },
    [4] =     { stype = SLC_MEDICAL_TYPE,         snum = 0 },
    [5] =     { stype = SLC_BALLBOY_TYPE,         snum = 0 },
    [6] =     { stype = SLC_GENERIC_TYPE,         snum = 0 },
    [7] =     { stype = SLC_POLICE_TYPE,         snum = 0 },
    [8] =     { stype = SLC_BENCH_PLAYER_HOME_TYPE,     snum = 0 },
    [9] =     { stype = SLC_BENCH_PLAYER_AWAY_TYPE,     snum = 0 },
    [10] =     { stype = SLC_MANAGER_HOME_TYPE,     snum = 1 },
    [11] =     { stype = SLC_MANAGER_AWAY_TYPE,     snum = 1 },
    [12] =    { stype = SLC_CHOREO_BALLBOY_TYPE,    snum = 0 }
}

function CreateSleVariations(gr, batch, sleTable)
    local i = 0
        
    for stype = 0, SLC_NUM - 1 do
        local numAdded = 0
        local variation = VARIATIONS[stype]
    
        for skintone=variation.skintone[1], variation.skintone[2] - 1 do
            for bodytype=variation.bodytype[1], variation.bodytype[2] - 1 do
                for suittype=variation.suittype[1], variation.suittype[2] - 1 do
                    for suitvariation=variation.suitvariation[1], variation.suitvariation[2] - 1 do
                        if numAdded < DEFAULTSLETYPEMAP[stype].snum then
                            sleTable[i] = gr:Create("sle", i)
                            gr:AddSubObject(batch, sleTable[i], stype)
                            
                            numAdded = numAdded + 1
                            i = i + 1
                        end
                    end
                end
            end
        end
    end
end
---------------------------------------------------------------------------------------------------
-- Create sle renderables with type assignment
function AssignSleTypes( gr, batch, sles, numSles )

    local idx = 0
    
    local settingTable = gSportsRNA:GetTable("Settings")
    
    local sleTypeMap = DEFAULTSLETYPEMAP
    local as = gSportsRNA
    local settingTable = as:GetTable("Settings")
    local levelOfDetail = as:GetString(settingTable, "LevelOfDetail") 
    if (levelOfDetail == "superlow") then
        sleTypeMap = SUPERLOWSLETYPEMAP
    end
    
    for id, map in pairs(sleTypeMap) do
        gr:AddSubObject(batch, sles[idx], map.stype)

        idx = idx + 1
        
        if idx == numSles then
            break
        end
    end
    
end

function SetSleSettings()
    local settingTable = gSportsRNA:GetTable("Settings")    
    
    local sleTypeMap = DEFAULTSLETYPEMAP
    local as = gSportsRNA
    local settingTable = as:GetTable("Settings")
    local levelOfDetail = as:GetString(settingTable, "LevelOfDetail") 
    if (levelOfDetail == "superlow") then
        sleTypeMap = SUPERLOWSLETYPEMAP
    end
    
    for id, map in pairs(sleTypeMap) do
        -- Set the maximum permitted type
        gSportsRNA:SetInt(settingTable, "SLC_" .. map.stype .. "_MAXINSTANCES", map.snum)
    end
end




function GetRMSle(idx,isModel)
	local sleorder = ""
	local fileType = ""
	
	if (isModel == 1) then
	fileType = "_textures"
	end
	
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_"..db.sle[idx].teamid.."_"..db.sle[idx].tournamentid.."_"..db.sle[idx].varient..""..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_"..db.sle[idx].teamid.."_"..db.sle[idx].tournamentid.."_0"..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_"..db.sle[idx].teamid.."_0_"..db.sle[idx].varient..""..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_"..db.sle[idx].teamid.."_0_0"..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_0_"..db.sle[idx].tournamentid.."_"..db.sle[idx].varient..""..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_0_"..db.sle[idx].tournamentid.."_0"..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_0_0_"..db.sle[idx].varient..""..fileType..".rx3;"
	sleorder = sleorder.."data/sceneassets/slc/specific"..db.sle[idx].slename.."_0_0_0"..fileType..".rx3;"
	return sleorder
end

--Revolution Mod 16 V1.0
--Edited by scouser09