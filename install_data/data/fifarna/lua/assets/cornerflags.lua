function CornerFlagsUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")

	db.cornerflags[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	db.cornerflags[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
	db.cornerflags[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
	local stadType =  as:GetString(state, "wvAttribStadType")
	if( stadType == "festadium") then
		db.cornerflags[idx].stadiumType = 0	
	else	
		db.cornerflags[idx].stadiumType = 1
	end
	
	local stadium = as:GetTable("wvStadium",1)
	db.cornerflags[idx].teamID = as:GetInt(stadium, "homeKitTeamID" )
	
	local wipe3d = as:GetTable("wvWipe", 1)
	db.cornerflags[idx].tournamentID = as:GetInt(wipe3d, "leagueID")
	db.cornerflags[idx].tournamentID = getTournamentGraphics(db.cornerflags[idx].tournamentID)
end

function CornerFlagsAssetBind(cornerflag)
	local gr = gRenderables
	local lod = 0

	gr:AddCallback(cornerflag, lod, "CornerFlagsUpdate(?)")

	gr:AddAsset(cornerflag, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(cornerflag, lod, "mesh0", "data/sceneassets/cornerflag/cornerflag_0.rx3")
	gr:AddAsset(cornerflag, lod, "tex0", "${GetRMCornerFlagPole(?)}data/sceneassets/cornerflag/cornerflag_0_textures.rx3")
	gr:AddAsset(cornerflag, lod, "flagcmn", "data/sceneassets/flag/flag_common_textures.rx3")

	gr:AddAsset(cornerflag, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.cornerflags[?].envLighting}.rx3")	
	gr:AddAsset(cornerflag, lod, "flagtexture", "${GetRMCornerFlag(?)}data/sceneassets/flag/cornerflag_${db.cornerflags[?].teamID}.rx3;data/sceneassets/flag/flag_0.rx3")
	
	local part = "mesh0"
	gr:CreateMaterialFromAttribulator(cornerflag, lod, part, "cornerflag_mat", "prop_plastic" )
	gr:SetTexture(cornerflag, lod, part, "textures", "diffuseTexture", "tex0", "cornerflag_cm")
	gr:SetTexture(cornerflag, lod, part, "textures", "normalMap", "tex0", "cornerflag_nm")
	gr:SetTexture(cornerflag, lod, part, "textures", "coeffMap", "tex0", "cornerflag_coeff")
	gr:SetTexture(cornerflag, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(cornerflag, lod, part, "textures", "envSpecTexture", "charcmn", "env_")
	gr:SetTextureFromRuntime(cornerflag, lod, part, "textures", "coverageMap", "covmap_${db.cornerflags[?].stadiumID}_${db.cornerflags[?].stadiumLightID}_${db.cornerflags[?].stadiumType}")

	return cornerflag
end


function GetRMCornerFlag(idx)
	local corner = ""
	corner = corner.."data/sceneassets/flag/cornerflag_"..db.cornerflags[idx].teamID.."_"..db.cornerflags[idx].tournamentID.."_"..db.cornerflags[idx].stadiumID..".rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_0_"..db.cornerflags[idx].tournamentID.."_"..db.cornerflags[idx].stadiumID..".rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_"..db.cornerflags[idx].teamID.."_"..db.cornerflags[idx].tournamentID.."_0.rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_0_"..db.cornerflags[idx].tournamentID.."_0.rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_"..db.cornerflags[idx].teamID.."_0_"..db.cornerflags[idx].stadiumID..".rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_0_0_"..db.cornerflags[idx].stadiumID..".rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_"..db.cornerflags[idx].teamID.."_0_0.rx3;"
	corner = corner.."data/sceneassets/flag/cornerflag_0_0_0.rx3;"
	return corner
end


function GetRMCornerFlagPole(idx)
	local corner = ""
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_"..db.cornerflags[idx].teamID.."_"..db.cornerflags[idx].tournamentID.."_"..db.cornerflags[idx].stadiumID.."_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_0_"..db.cornerflags[idx].tournamentID.."_"..db.cornerflags[idx].stadiumID.."_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_"..db.cornerflags[idx].teamID.."_"..db.cornerflags[idx].tournamentID.."_0_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_0_"..db.cornerflags[idx].tournamentID.."_0_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_"..db.cornerflags[idx].teamID.."_0_"..db.cornerflags[idx].stadiumID.."_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_0_0_"..db.cornerflags[idx].stadiumID.."_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_"..db.cornerflags[idx].teamID.."_0_0_textures.rx3;"
	corner = corner.."data/sceneassets/cornerflag/cornerflagpole_0_0_0_textures.rx3;"
	return corner
end

--Revolution Mod 16 V1.0
--Edited by scouser09