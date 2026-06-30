function GrassUpdate(idx)
	local as = gSportsRNA
	local settingTable = as:GetTable("Settings")

	as:SetInt(settingTable, "GrassNumGridAxisCells", 64)
	local state = as:GetTable("wvState")
	local stadium = as:GetTable("wvStadium", idx)

	db.grass[idx].lightType = as:GetInt(stadium, "stadLightType")
	db.grass[idx].stadiumID = as:GetInt(stadium, "stadID")
	db.grass[idx].prefix = "stadium" --as:GetString(stadium, "stadNamePrefix")

	db.grass[idx].wearPattern = as:GetInt(stadium, "pitchWearPattern")
	db.grass[idx].mowPattern = as:GetInt(stadium, "pitchMowPattern")
	
	
	
	
	local wipe3d = as:GetTable("wvWipe", idx)
	
	db.grass[idx].tournID = as:GetInt(wipe3d, "leagueID")
	db.grass[idx].tournID = getTournamentGraphics(db.grass[idx].tournID)
	
	--CLASSIC KIT + FUT
	db.grass[idx].homeTeamID = as:GetInt(stadium, "homeKitTeamID" )
	db.grass[idx].kitYearDecade = -1
	--db.grass[idx].awayTeamID = db.grass[idx].awayKitTeamID
	if (idx > 0) then
	local player = as:GetTable("wvPlayer", 3)
	local kitYearOutfield = as:GetInt(player, "kitYear")
	if (kitYearOutfield > 0) then
	db.grass[idx].tournID = kitYearOutfield
	db.grass[idx].kitYearDecade = math.floor(kitYearOutfield/10)*10
	end
	if (futCustom) then
	local team = as:GetInt(player, "teamid")
	if (team == 130000) then
	db.grass[idx].homeTeamID = team
	end
	--player = as:GetTable("wvPlayer", 14)
	--team = as:GetInt(player, "teamid")
	--if (team == 130000) then
	--db.grass[idx].awayTeamID = team
	--end
	end
	end
	

 	db.grass[idx].defaulttournID = 0
	if (teamTournament[db.grass[idx].homeTeamID] ~= nil) then
	db.grass[idx].defaulttournID = teamTournament[db.grass[idx].homeTeamID]
	end
	
	
	
	
	
	
	db.grass[idx].wet = as:GetInt(state, "wvAttribStadWeather")
	db.grass[idx].cold = as:GetInt(state, "wvAttribStadClimate") -- 0: warm, 1: cold

	if (db.grass[idx].wet == 2) then
	db.grass[idx].wet = 1
	end
	
	
end

function GrassAssetBind(obj)
	local gr = gRenderables
   	local lod = 0

	gr:AddCallback(obj, lod, "GrassUpdate(?)")

	gr:AddAsset(obj, lod, "grasstex", "${GetRMPitchCTGrass(?)}data/sceneassets/pitch/pitch_common_textures.rx3")
	gr:AddAsset(obj, lod, "cmn", "${GetRMPitchCTGrass(?)}data/sceneassets/pitch/pitch_common_textures.rx3")
	gr:AddAsset(obj, lod, "col", "${GetRMPitchColour(?)}data/sceneassets/pitch/pitchcolor_0_textures.rx3")
	gr:AddAsset(obj, lod, "wear", "${GetRMPitchWearPatturn(?)}data/sceneassets/pitch/pitchwearpattern_${db.grass[?].wearPattern}_textures.rx3")
	gr:AddAsset(obj, lod, "mow", "${GetRMPitchMowPatturn(?)}data/sceneassets/pitch/pitchmowpattern_${db.grass[?].mowPattern}_textures.rx3")
	gr:AddAsset(obj, lod, "divottex", "data/sceneassets/pitch/dirtdecal.rx3")

	local stadiumAsset = "data/sceneassets/stadium/${db.grass[?].prefix}_${db.grass[?].stadiumID}.rx3;data/sceneassets/stadium/${db.grass[?].prefix}_666.rx3"
	gr:AddAsset(obj, lod, "stadium", stadiumAsset)

	return obj
end



function GetRMPitchMowPatturn(idx)
	local pmp = ""
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].tournID.."_"..db.grass[idx].stadiumID.."_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_0_"..db.grass[idx].tournID.."_"..db.grass[idx].stadiumID.."_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].tournID.."_0_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_0_"..db.grass[idx].kitYearDecade.."_0_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_0_"..db.grass[idx].tournID.."_0_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_"..db.grass[idx].homeTeamID.."_0_"..db.grass[idx].stadiumID.."_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_0_0_"..db.grass[idx].stadiumID.."_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_"..db.grass[idx].homeTeamID.."_0_0_textures.rx3;"
	pmp = pmp.."data/sceneassets/pitch/specificpitchmowpattern_0_0_0_textures.rx3;"
	return pmp
end


function GetRMPitchCTGrass(idx)
	local pct = ""
	pct = pct.."data/sceneassets/pitch/specificpitchct_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].stadiumID..".rx3;"
	pct = pct.."data/sceneassets/pitch/specificpitchct_0_"..db.grass[idx].stadiumID..".rx3;"
	pct = pct.."data/sceneassets/pitch/specificpitchct_"..db.grass[idx].homeTeamID.."_0.rx3;"
	pct = pct.."data/sceneassets/pitch/specificpitchct_0_0.rx3;"
	return pct
end


function GetRMPitchColour(idx)
	local pcol = ""
	pcol = pcol.."data/sceneassets/pitch/specificpitchcolor_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].stadiumID.."_textures.rx3;"
	pcol = pcol.."data/sceneassets/pitch/specificpitchcolor_0_"..db.grass[idx].stadiumID.."_textures.rx3;"
	pcol = pcol.."data/sceneassets/pitch/specificpitchcolor_"..db.grass[idx].homeTeamID.."_0_textures.rx3;"
	pcol = pcol.."data/sceneassets/pitch/specificpitchcolor_0_0_textures.rx3;"
	return pcol
end


function GetRMPitchWearPatturn(idx)
	local pwp = ""
	--ADJUST CONVENTION
	
	
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].tournID.."_"..db.grass[idx].stadiumID.."_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].tournID.."_"..db.grass[idx].stadiumID.."_0_0_textures.rx3;"
	
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].tournID.."_0_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_"..db.grass[idx].tournID.."_0_0_0_textures.rx3;"
	
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].tournID.."_0_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].tournID.."_0_0_0_textures.rx3;"
	
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].tournID.."_"..db.grass[idx].stadiumID.."_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].tournID.."_"..db.grass[idx].stadiumID.."_0_0_textures.rx3;"
	
	--pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].kitYearDecade.."_0_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].kitYearDecade.."_0_0_0_textures.rx3;"
	
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_0_"..db.grass[idx].stadiumID.."_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_0_"..db.grass[idx].stadiumID.."_0_0_textures.rx3;"
	
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_0_"..db.grass[idx].stadiumID.."_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_0_"..db.grass[idx].stadiumID.."_0_0_textures.rx3;"
	
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_0_0_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_"..db.grass[idx].homeTeamID.."_0_0_0_0_textures.rx3;"
	
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].defaulttournID.."_0_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_"..db.grass[idx].defaulttournID.."_0_0_0_textures.rx3;"
	
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_0_0_"..db.grass[idx].cold.."_"..db.grass[idx].wet.."_textures.rx3;"
	pwp = pwp.."data/sceneassets/pitch/specificpitchwearpattern_0_0_0_0_0_textures.rx3;"
	
	
	--MAKE EXCEPTIONS FOR CUP FINALS?
	

	return pwp
end

--Revolution Mod 16 V1.0
--Edited by scouser09