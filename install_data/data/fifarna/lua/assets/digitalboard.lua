function DigitalBoardUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local board = as:GetTable("wvDigitalBoard", idx)

	db.digitalboard[idx].model = as:GetInt(board, "model")

	db.digitalboard[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
	db.digitalboard[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
	db.digitalboard[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	local stadType =  as:GetString(state, "wvAttribStadType")
	if( stadType == "festadium") then	
		db.digitalboard[idx].stadiumType = 0	
	else	
		db.digitalboard[idx].stadiumType = 1
	end
	
	local wipe3d = as:GetTable("wvWipe", 1)
	db.digitalboard[idx].leagueID = as:GetInt(wipe3d, "leagueID")
	db.digitalboard[idx].leagueID = getTournamentGraphics(db.digitalboard[idx].leagueID)
	
end

function SetupDigitalBoardAsset(gr, obj, lod, part, submesh, meshpath)
	gr:AddAsset(obj, lod, part, meshpath)
	gr:SetSubMesh(obj, lod, part, submesh)
end

function SetupDigitalBoardMaterial(gr, obj, lod, part, attribname, basecolor)
	gr:CreateMaterialFromAttribulator( obj, lod, part, part.."_mat", attribname )
	gr:SetTexture(obj, lod, part, "textures", "diffuseTexture", "prop_textures", "_cm")
	gr:SetTexture(obj, lod, part, "textures", "normalMap", "prop_textures", "_nm")
	gr:SetTexture(obj, lod, part, "textures", "coeffMap", "prop_textures", "_coeff")
	gr:SetTexture(obj, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(obj, lod, part, "textures", "envSpecTexture", "envmap_${db.digitalboard[?].stadiumID}_${db.digitalboard[?].stadiumLightID}_${db.digitalboard[?].stadiumType}")
	gr:SetTextureFromRuntime(obj, lod, part, "textures", "coverageMap", "covmap_${db.digitalboard[?].stadiumID}_${db.digitalboard[?].stadiumLightID}_${db.digitalboard[?].stadiumType}")
	if (basecolor == nil) then
		return
	end
	gr:SetConstantARGB(obj, lod, part, "global", "tintcolor", basecolor)
end

function DigitalBoardAssetBind(digitalboard)
	local gr = gRenderables
	local lod = 0

	gr:AddCallback(digitalboard, lod, "DigitalBoardUpdate(?)")
	gr:AddAsset(digitalboard, lod, "shader", "data/fifarna/shader.big")

	gr:AddAsset(digitalboard, lod, "prop_textures", "${GetRMDigitalBoard(?,1)}data/sceneassets/prop/prop_${db.digitalboard[?].model}_textures.rx3")
	gr:AddAsset(digitalboard, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${db.digitalboard[?].envLighting}.rx3")	

	local meshpath = "${GetRMDigitalBoard(?,0)}data/sceneassets/prop/prop_${db.digitalboard[?].model}.rx3"

	SetupDigitalBoardAsset(gr, digitalboard, lod, "prop_plastic", "prop_plastic", meshpath)
	SetupDigitalBoardMaterial(gr, digitalboard, lod, "prop_plastic", "prop_plastic", nil, nil)

	SetupDigitalBoardAsset(gr, digitalboard, lod, "outsubtens", "outsubtens", meshpath)
	SetupDigitalBoardMaterial(gr, digitalboard, lod, "outsubtens", "outsubtens", 0xFFFF0000)

	SetupDigitalBoardAsset(gr, digitalboard, lod, "outsubones", "outsubones", meshpath)
	SetupDigitalBoardMaterial(gr, digitalboard, lod, "outsubones", "outsubones", 0xFFFF0000)

	SetupDigitalBoardAsset(gr, digitalboard, lod, "insubtens", "insubtens", meshpath)
	SetupDigitalBoardMaterial(gr, digitalboard, lod, "insubtens", "insubtens", 0xFF00FF00)

	SetupDigitalBoardAsset(gr, digitalboard, lod, "insubones", "insubones", meshpath)
	SetupDigitalBoardMaterial(gr, digitalboard, lod, "insubones", "insubones", 0xFF00FF00)

	return digitalboard
end


function GetRMDigitalBoard(idx,isModel)
	local pct = ""
	local fileType = ""
	
	if (isModel == 1) then
	fileType = "_textures"
	end
	
	pct = pct.."data/sceneassets/prop/digitalboard_"..db.digitalboard[idx].leagueID..""..fileType..".rx3;"

	return pct
end

--Revolution Mod 16 V1.3.5
--Edited by scouser09