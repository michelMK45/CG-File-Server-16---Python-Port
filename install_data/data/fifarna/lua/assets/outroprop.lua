function OutroPropUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local outropropstate = as:GetTable("wvOutroprop", idx)

	db.outroprop[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
	db.outroprop[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
	db.outroprop[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	local stadType =  as:GetString(state, "wvAttribStadType")
	if( stadType == "festadium") then
		db.outroprop[idx].stadiumType = 0
	else	
		db.outroprop[idx].stadiumType = 1
	end
	db.outroprop[idx].teamID = as:GetInt(outropropstate, "teamid")
	db.outroprop[idx].leagueID = as:GetInt(outropropstate, "leagueid")
	db.outroprop[idx].homeFlagID = as:GetInt(outropropstate, "homeflagid")
	db.outroprop[idx].awayFlagID = as:GetInt(outropropstate, "awayflagid")
	
	local wipe3d = as:GetTable("wvWipe", 1)
	local leagueIDnew = as:GetInt(wipe3d, "leagueID")
	
	if (db.outroprop[idx].leagueID == 0) then
	db.outroprop[idx].leagueID = leagueIDnew
	end
	
	db.outroprop[idx].leagueIDorig = db.outroprop[idx].leagueID
	db.outroprop[idx].leagueID = getTournamentGraphics(db.outroprop[idx].leagueID)
end

function OutroPropAssetBind(outroprop)
	local gr = gRenderables
	local lod = 0

	local podiumMeshName = "data/sceneassets/prop/prop_102.rx3"
	local penMeshName = "data/sceneassets/prop/prop_103.rx3"
	local boardMeshName = "data/sceneassets/prop/prop_104.rx3"
	local flagBearerMeshName = "data/sceneassets/prop/flagbearer.rx3"

	gr:AddCallback(outroprop, lod, "OutroPropUpdate(?)")

	gr:AddAsset(outroprop, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(outroprop, lod, "podium_textures", "${GetRMPodium(?)}data/sceneassets/prop/prop_102_textures.rx3")
	gr:AddAsset(outroprop, lod, "pen_textures", "${GetRMMediaPen(?)}data/sceneassets/prop/prop_103_textures.rx3")
	gr:AddAsset(outroprop, lod, "board_textures", "${GetRMPodium(?)}data/sceneassets/prop/prop_104_textures.rx3")
	gr:AddAsset(outroprop, lod, "flagBearer_textures", "data/sceneassets/prop/flagbearer_textures.rx3")

	gr:AddAsset(outroprop, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.outroprop[?].envLighting}.rx3")
	gr:AddAsset(outroprop, lod, "globaltex", "data/sceneassets/globaltex/globaltex_0.rx3")

	gr:AddAsset(outroprop, lod, "podium_metal", podiumMeshName)
	gr:AddAsset(outroprop, lod, "podium_plastic", podiumMeshName)
	gr:AddAsset(outroprop, lod, "prop_teamlogo", podiumMeshName)
	gr:AddAsset(outroprop, lod, "podium_leaguelogo", podiumMeshName)

	gr:AddAsset(outroprop, lod, "pen_wood", penMeshName)
	gr:AddAsset(outroprop, lod, "pen_teamlogo", penMeshName)
	gr:AddAsset(outroprop, lod, "pen_leaguelogo", penMeshName)

	gr:AddAsset(outroprop, lod, "board_plastic", boardMeshName)
	gr:AddAsset(outroprop, lod, "board_teamlogo", boardMeshName)
	gr:AddAsset(outroprop, lod, "board_leaguelogo", boardMeshName)

	gr:AddAsset(outroprop, lod, "flagBearer_bearer", flagBearerMeshName)
	gr:AddAsset(outroprop, lod, "flagBearer_fifaflag", flagBearerMeshName)
	gr:AddAsset(outroprop, lod, "flagBearer_flaghome", flagBearerMeshName)
	gr:AddAsset(outroprop, lod, "flagBearer_flagaway", flagBearerMeshName)

	gr:AddAsset(outroprop, lod, "teamtex", "data/ui/imgassets/crest/light/l${db.outroprop[?].teamID}.dds")
	gr:AddAsset(outroprop, lod, "leaguetex", "${GetRMPodiumLogo(?)}data/ui/imgassets/league512x128/dark/l${db.outroprop[?].leagueIDorig}.dds;data/ui/imgassets/league512x128/dark/l666.dds")
	gr:AddAsset(outroprop, lod, "homeflagtex", "data/sceneassets/flag/flag_${db.outroprop[?].homeFlagID}.rx3")
	gr:AddAsset(outroprop, lod, "awayflagtex", "data/sceneassets/flag/flag_${db.outroprop[?].awayFlagID}.rx3")

	-- The Podium ***********************************************************************************************
	local part = "podium_plastic"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "podium_material", "prop_plastic" )
	gr:SetSubMesh(outroprop, lod, part, "prop_plastic")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "podium_textures", "_cm")
	--gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "leaguetex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "podium_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "podium_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "podium_metal"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "podium_material", "prop_metal" )
	gr:SetSubMesh(outroprop, lod, part, "prop_metal")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "podium_textures", "_cm")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "podium_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "podium_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "prop_teamlogo"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "podium_material", "prop_alpha" )
	gr:SetSubMesh(outroprop, lod, part, "prop_teamlogo")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "teamtex", "")
	--gr:SetTexture(outroprop, lod, part, "textures", "logoTexture", "teamtex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "podium_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "podium_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "podium_leaguelogo"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "podium_material", "prop_alpha" )
	gr:SetSubMesh(outroprop, lod, part, "prop_leaguelogo")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "leaguetex", "")
	--gr:SetTexture(outroprop, lod, part, "textures", "logoTexture", "leaguetex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "podium_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "podium_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")


	-- The Media Pen ********************************************************************************************
	local part = "pen_wood"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "pen_material", "prop_wood" )
	gr:SetSubMesh(outroprop, lod, part, "prop_wood")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "pen_textures", "_cm")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "pen_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "pen_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "pen_teamlogo"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "pen_material", "prop_alpha" )
	gr:SetSubMesh(outroprop, lod, part, "prop_teamlogo")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "teamtex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "pen_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "pen_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "pen_leaguelogo"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "pen_material", "prop_alpha" )
	gr:SetSubMesh(outroprop, lod, part, "prop_leaguelogo")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "leaguetex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "pen_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "pen_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	-- The Media Board ********************************************************************************************
	local part = "board_plastic"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "board_material", "prop_plastic" )
	gr:SetSubMesh(outroprop, lod, part, "prop_plastic")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "board_textures", "_cm")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "board_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "board_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "board_teamlogo"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "board_material", "prop_alpha" )
	gr:SetSubMesh(outroprop, lod, part, "prop_teamlogo")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "teamtex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "board_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "board_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "board_leaguelogo"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "board_material", "prop_alpha" )
	gr:SetSubMesh(outroprop, lod, part, "prop_leaguelogo")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "leaguetex", "")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "board_textures", "_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "board_textures", "_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	-- The Flag Bearer ********************************************************************************************
	local part = "flagBearer_bearer"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "flagBearer_bearer_material", "prop_wood" )
	gr:SetSubMesh(outroprop, lod, part, "flagbearer")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "flagBearer_textures", "flagbearer_cm")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "flagBearer_textures", "flagbearer_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "flagBearer_textures", "flagbearer_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "flagBearer_flaghome"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "flag_material", "prop_wood" )
	gr:SetSubMesh(outroprop, lod, part, "flaghome")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "homeflagtex", "flag_${db.outroprop[?].homeFlagID}_0")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "flagBearer_textures", "flag_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "flagBearer_textures", "flag_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	local part = "flagBearer_flagaway"
	gr:CreateMaterialFromAttribulator(outroprop, lod, part, "flag_material", "prop_wood" )
	gr:SetSubMesh(outroprop, lod, part, "flagaway")
	gr:SetTexture(outroprop, lod, part, "textures", "diffuseTexture", "awayflagtex", "flag_${db.outroprop[?].awayFlagID}_0")
	gr:SetTexture(outroprop, lod, part, "textures", "normalMap", "flagBearer_textures", "flag_nm")
	gr:SetTexture(outroprop, lod, part, "textures", "coeffMap", "flagBearer_textures", "flag_coeff")
	gr:SetTexture(outroprop, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTexture(outroprop, lod, part, "textures", "envSpecTexture", "charcmn", "envs_")
	gr:SetTextureFromRuntime(outroprop, lod, part, "textures", "coverageMap", "covmap_${db.outroprop[?].stadiumID}_${db.outroprop[?].stadiumLightID}_${db.outroprop[?].stadiumType}")

	return outroprop
end


function GetRMPodium(idx)
	local pcol = ""
	pcol = pcol.."data/sceneassets/prop/podium_"..db.outroprop[idx].leagueID.."_textures.rx3;"
	return pcol
end

function GetRMMediaPen(idx)
	local pcol = ""
	pcol = pcol.."data/sceneassets/prop/mediapen_"..db.outroprop[idx].leagueID.."_textures.rx3;"
	return pcol
end

function GetRMPodiumLogo(idx)
	local pcol = ""
	pcol = pcol.."data/ui/imgassets/league512x128/podium/logo_"..db.outroprop[idx].leagueID..".dds;"
	return pcol
end

--Revolution Mod 16 V1.3.5
--Edited by scouser09