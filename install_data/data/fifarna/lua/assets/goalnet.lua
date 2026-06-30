function GoalNetUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local goalnet = as:GetTable("wvGoalNet", idx)

    db.goalnet[idx].lightType = as:GetInt(goalnet, "stadLightType")
	db.goalnet[idx].stadiumID = as:GetInt(goalnet, "stadID")
	local stadType =  as:GetString(state, "wvAttribStadType")
	if( stadType == "festadium") then
		db.goalnet[idx].stadiumType = 0
	else
		db.goalnet[idx].stadiumType = 1
	end
	db.goalnet[idx].netID = as:GetInt(goalnet, "netTexture") 
	db.goalnet[idx].netColorID = as:GetInt(goalnet, "colorTexture") 
	db.goalnet[idx].goalType = as:GetInt(goalnet, "goalType") 
	
	local stadium = as:GetTable("wvStadium", math.floor(idx/2))
	db.goalnet[idx].teamID = as:GetInt(stadium, "homeKitTeamID" )
	
end

function GoalNetAssetBind(goalnet)
	local gr = gRenderables
   	local lod = 0

	gr:AddCallback(goalnet, lod, "GoalNetUpdate(?)")
	gr:AddAsset(goalnet, lod, "shader", "data/fifarna/shader.big")
	local goalnetasset = "${GetRMNetShape(?)}data/sceneassets/goalnet/goalnet_${db.goalnet[?].netID}.rx3"
	
	 -- used by the goalnet
	gr:AddAsset(goalnet, lod, "nettexture", goalnetasset)
	gr:AddAsset(goalnet, lod, "goalplane", goalnetasset)
	gr:AddAsset(goalnet, lod, "colortexture", "${GetRMNetColour(?)}data/sceneassets/goalnet/netcolor_${db.goalnet[?].netColorID}_textures.rx3")
	gr:AddAsset(goalnet, lod, "stadium", "data/sceneassets/stadium/stadium_${db.goalnet[?].stadiumID}.rx3")
	
	-- bound below
	gr:AddAsset(goalnet, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.goalnet[?].lightType}.rx3")
	gr:AddAsset(goalnet, lod, "goalpost_textures", "${GetRMGoalPostTex(?)}data/sceneassets/goalnet/goalpost_${db.goalnet[?].goalType}_textures.rx3")
	gr:AddAsset(goalnet, lod, "goalpostsupport_textures", "${GetRMSupportPost(?)}data/sceneassets/goalnet/goalpost_${db.goalnet[?].goalType}_textures.rx3")


	local part = "goalpost_static"
	gr:AddAsset(goalnet, lod, part, "${GetRMGoalPost(?)}data/sceneassets/goalnet/goalpost_${db.goalnet[?].goalType}.rx3")
	gr:CreateMaterialFromAttribulator(goalnet, lod, part, "goalpost_mtl", "goalpost" )
	gr:SetSubMesh(goalnet, lod, part, "goalpost_static")
	gr:SetTexture(goalnet, lod, part, "textures", "diffuseTexture", "goalpost_textures", "goalpost_cm")
	gr:SetTexture(goalnet, lod, part, "textures", "normalMap", "goalpost_textures", "goalpost_nm")
	gr:SetTexture(goalnet, lod, part, "textures", "coeffMap", "goalpost_textures", "goalpost_coeff")
	--gr:SetTexture(goalnet, lod, part, "textures", "cubicEnvMap", "charcmn", "envd_")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "cubicEnvMap", "envmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "coverageMap", "covmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	
	local part = "goalpost_slide"
	gr:AddAsset(goalnet, lod, part, "${GetRMGoalPost(?)}data/sceneassets/goalnet/goalpost_${db.goalnet[?].goalType}.rx3")
	gr:CreateMaterialFromAttribulator(goalnet, lod, part, "goalpost_mtl", "goalpost" )
	gr:SetSubMesh(goalnet, lod, part, "goalpost_slide")
	gr:SetTexture(goalnet, lod, part, "textures", "diffuseTexture", "goalpost_textures", "goalpost_cm")
	gr:SetTexture(goalnet, lod, part, "textures", "normalMap", "goalpost_textures", "goalpost_nm")
	gr:SetTexture(goalnet, lod, part, "textures", "coeffMap", "goalpost_textures", "goalpost_coeff")
	--gr:SetTexture(goalnet, lod, part, "textures", "cubicEnvMap", "charcmn", "envd_")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "cubicEnvMap", "envmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "coverageMap", "covmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	
	local part = "goalpost_post"
	gr:AddAsset(goalnet, lod, part, "${GetRMGoalPost(?)}data/sceneassets/goalnet/goalpost_${db.goalnet[?].goalType}.rx3")
	gr:CreateMaterialFromAttribulator(goalnet, lod, part, "goalpost_mtl", "goalpost" )
	gr:SetSubMesh(goalnet, lod, part, "goalpost_post")
	gr:SetTexture(goalnet, lod, part, "textures", "diffuseTexture", "goalpost_textures", "goalpost_cm")
	gr:SetTexture(goalnet, lod, part, "textures", "normalMap", "goalpost_textures", "goalpost_nm")
	gr:SetTexture(goalnet, lod, part, "textures", "coeffMap", "goalpost_textures", "goalpost_coeff")
	--gr:SetTexture(goalnet, lod, part, "textures", "cubicEnvMap", "charcmn", "envd_")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "cubicEnvMap", "envmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "coverageMap", "covmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	
	local part = "goalpost_netsupport"
	gr:AddAsset(goalnet, lod, part, "${GetRMGoalPost(?)}data/sceneassets/goalnet/goalpost_${db.goalnet[?].goalType}.rx3")
	gr:CreateMaterialFromAttribulator(goalnet, lod, part, "goalpost_mtl", "goalpost" )
	gr:SetSubMesh(goalnet, lod, part, "goalpost_netsupport")
	gr:SetTexture(goalnet, lod, part, "textures", "diffuseTexture", "goalpostsupport_textures", "goalpost_cm")
	gr:SetTexture(goalnet, lod, part, "textures", "normalMap", "goalpostsupport_textures", "goalpost_nm")
	gr:SetTexture(goalnet, lod, part, "textures", "coeffMap", "goalpostsupport_textures", "goalpost_coeff")
	--gr:SetTexture(goalnet, lod, part, "textures", "cubicEnvMap", "charcmn", "envd_")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "cubicEnvMap", "envmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	gr:SetTextureFromRuntime(goalnet, lod, part, "textures", "coverageMap", "covmap_${db.goalnet[?].stadiumID}_${db.goalnet[?].lightType}_${db.goalnet[?].stadiumType}")
	
	local part = "goalplane"
	gr:CreateMaterial(goalnet, lod, part, "env_ColorOnly.fx")
	
	return goalnet
end



function GetRMNetColour(idx)
	local netcol = ""
	netcol = netcol.."data/sceneassets/goalnet/specificnetcolor_"..db.goalnet[idx].teamID.."_"..db.goalnet[idx].stadiumID.."_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificnetcolor_0_"..db.goalnet[idx].stadiumID.."_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificnetcolor_"..db.goalnet[idx].teamID.."_0_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificnetcolor_0_0_textures.rx3;"
	return netcol
end

function GetRMNetShape(idx)
	local netcol = ""
	netcol = netcol.."data/sceneassets/goalnet/specificgoalnet_"..db.goalnet[idx].teamID.."_"..db.goalnet[idx].stadiumID..".rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalnet_0_"..db.goalnet[idx].stadiumID..".rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalnet_"..db.goalnet[idx].teamID.."_0.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalnet_0_0.rx3;"
	return netcol
end

function GetRMSupportPost(idx)
	local netcol = ""
	netcol = netcol.."data/sceneassets/goalnet/specificnetsupportpost_"..db.goalnet[idx].teamID.."_"..db.goalnet[idx].stadiumID.."_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificnetsupportpost_0_"..db.goalnet[idx].stadiumID.."_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificnetsupportpost_"..db.goalnet[idx].teamID.."_0_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificnetsupportpost_0_0_textures.rx3;"
	return netcol
end

function GetRMGoalPost(idx)
	local netcol = ""
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_"..db.goalnet[idx].teamID.."_"..db.goalnet[idx].stadiumID..".rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_0_"..db.goalnet[idx].stadiumID..".rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_"..db.goalnet[idx].teamID.."_0.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_0_0.rx3;"
	return netcol
end

function GetRMGoalPostTex(idx)
	local netcol = ""
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_"..db.goalnet[idx].teamID.."_"..db.goalnet[idx].stadiumID.."_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_0_"..db.goalnet[idx].stadiumID.."_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_"..db.goalnet[idx].teamID.."_0_textures.rx3;"
	netcol = netcol.."data/sceneassets/goalnet/specificgoalpost_0_0_textures.rx3;"
	return netcol
end

--Revolution Mod 16 V1.0
--Edited by scouser09