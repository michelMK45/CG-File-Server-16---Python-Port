function TrophyUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local stadType = as:GetString(state, "wvAttribStadType")
	local trophy = as:GetTable("wvTrophy", idx)
	
	
	if (idx == db.ntrophies) then
		db.wipeTrophy.type = as:GetInt(trophy, "trophyType")
		db.wipeTrophy.model = as:GetInt(trophy, "trophyModel") 
		db.wipeTrophy.pedestalmodel = as:GetInt(trophy, "pedestalModel") 
		db.wipeTrophy.envLighting = as:GetInt(state, "wvAttribEnvLighting")
		db.wipeTrophy.stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
		db.wipeTrophy.stadiumID = as:GetInt(state, "wvAttribStadID")
		if( stadType == "festadium") then
			db.wipeTrophy.stadiumType = 0
		else
			db.wipeTrophy.stadiumType = 1
		end
        db.wipeTrophy.ColorPri = as:GetInt(trophy, "ColorPri")
        db.wipeTrophy.ColorSec = as:GetInt(trophy, "ColorSec")
        db.wipeTrophy.ColorTer = as:GetInt(trophy, "ColorTer")
	else
		db.trophy[idx].type = as:GetInt(trophy, "trophyType")
		db.trophy[idx].model = as:GetInt(trophy, "trophyModel") 
		db.trophy[idx].pedestalmodel = as:GetInt(trophy, "pedestalModel") 
		db.trophy[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
		db.trophy[idx].stadiumLightID = as:GetInt(state, "wvAttribStadLightID")
		db.trophy[idx].stadiumID = as:GetInt(state, "wvAttribStadID")
		if( stadType == "festadium") then
			db.trophy[idx].stadiumType = 0
		else
			db.trophy[idx].stadiumType = 1
		end
        db.trophy[idx].ColorPri = as:GetInt(trophy, "ColorPri")
        db.trophy[idx].ColorSec = as:GetInt(trophy, "ColorSec")
        db.trophy[idx].ColorTer = as:GetInt(trophy, "ColorTer")
	end
end

function CommonTrophyAssetBind(trophy, dbobj, basePath, defaultId, materialPrefix)
	local gr = gRenderables
   	local lod = 0

	local trophyMeshFile = "data/sceneassets/"..basePath.."/"..basePath.."_${"..dbobj..".model}.rx3;data/sceneassets/"..basePath.."/"..basePath.."_"..defaultId..".rx3";
	local trophyTextureFile = "data/sceneassets/"..basePath.."/"..basePath.."_${"..dbobj..".model}_textures.rx3;data/sceneassets/"..basePath.."/"..basePath.."_"..defaultId.."_textures.rx3";

	gr:AddCallback(trophy, lod, "TrophyUpdate(?)")
	gr:AddAsset(trophy, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(trophy, lod, "trophy_wood", trophyMeshFile)
	gr:AddAsset(trophy, lod, "trophy_metal", trophyMeshFile)
	gr:AddAsset(trophy, lod, "trophy_coloredmetal", trophyMeshFile)
	gr:AddAsset(trophy, lod, "trophy_plastic", trophyMeshFile)
	gr:AddAsset(trophy, lod, "trophy_ribbon", trophyMeshFile)
    gr:AddAsset(trophy, lod, "trophy_ribbon_colored", trophyMeshFile)
	gr:AddAsset(trophy, lod, "trophy_glass", trophyMeshFile)
	gr:AddAsset(trophy, lod, "trophytex", trophyTextureFile)
	
	gr:AddAsset(trophy, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${"..dbobj..".envLighting}.rx3")

	local part = "trophy_wood"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_wood" )
	gr:SetSubMesh(trophy, lod, part, "trophy_wood")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	
	local part = "trophy_metal"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_metal" )
	gr:SetSubMesh(trophy, lod, part, "trophy_metal")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	
	local part = "trophy_coloredmetal"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_coloredmetal" )
	gr:SetSubMesh(trophy, lod, part, "trophy_coloredmetal")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	
	local part = "trophy_plastic"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_plastic" )
	gr:SetSubMesh(trophy, lod, part, "trophy_plastic")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	
	local part = "trophy_ribbon"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_ribbon" )
	gr:SetSubMesh(trophy, lod, part, "trophy_ribbon")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
      
    local part = "trophy_ribbon_colored"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_ribbon_colored" )
	gr:SetSubMesh(trophy, lod, part, "trophy_ribbon_colored")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetConstantARGB(trophy, lod, part, "global", "customColorPri", "${"..dbobj..".ColorPri}")
	gr:SetConstantARGB(trophy, lod, part, "global", "customColorSec", "${"..dbobj..".ColorSec}")
	gr:SetConstantARGB(trophy, lod, part, "global", "customColorTer", "${"..dbobj..".ColorTer}")
	
	local part = "trophy_glass"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "trophy_material", materialPrefix.."trophy_glass" )
	gr:SetSubMesh(trophy, lod, part, "trophy_glass")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "trophytex", "_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "trophytex", "_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "trophytex", "_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")

	return trophy;
end

function TrophyAssetBind(trophy)
	local gr = gRenderables
   	local lod = 0

	local pedestalMeshFile = "data/sceneassets/pedestal/pedestal_${db.trophy[?].pedestalmodel}.rx3";
	local pedestalTextureFile = "data/sceneassets/pedestal/pedestal_${db.trophy[?].pedestalmodel}_textures.rx3";
	
	gr:AddAsset(trophy, lod, "pedestal_painted", pedestalMeshFile)
	gr:AddAsset(trophy, lod, "pedestal_plexiglass", pedestalMeshFile)
	gr:AddAsset(trophy, lod, "pedestal_metal", pedestalMeshFile)
	gr:AddAsset(trophy, lod, "pedestaltex", pedestalTextureFile)

	CommonTrophyAssetBind(trophy, "db.trophy[?]", "trophy", "0", "");
	
	local part = "pedestal_painted"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "pedestal_material", "pedestal_painted" )
	gr:SetSubMesh(trophy, lod, part, "pedestal_painted")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "pedestaltex", "pedestal_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "pedestaltex", "pedestal_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "pedestaltex", "pedestal_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${db.trophy[?].stadiumID}_${db.trophy[?].stadiumLightID}_${db.trophy[?].stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${db.trophy[?].stadiumID}_${db.trophy[?].stadiumLightID}_${db.trophy[?].stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${db.trophy[?].stadiumID}_${db.trophy[?].stadiumLightID}_${db.trophy[?].stadiumType}")
	
	local part = "pedestal_plexiglass"
	gr:CreateMaterialFromAttribulator(trophy, lod, part, "pedestal_material", "pedestal_plexiglass" )
	gr:SetSubMesh(trophy, lod, part, "pedestal_plexiglass")
	gr:SetTexture(trophy, lod, part, "textures", "diffuseTexture", "pedestaltex", "pedestal_cm")
	gr:SetTexture(trophy, lod, part, "textures", "normalMap", "pedestaltex", "pedestal_nm")
	gr:SetTexture(trophy, lod, part, "textures", "coeffMap", "pedestaltex", "pedestal_coeff")
	gr:SetTexture(trophy, lod, part, "textures", "envDiffuseTexture", "charcmn", "envd_")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "envmap_${db.trophy[?].stadiumID}_${db.trophy[?].stadiumLightID}_${db.trophy[?].stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "envSpecTexture", "envmap_${db.trophy[?].stadiumID}_${db.trophy[?].stadiumLightID}_${db.trophy[?].stadiumType}")
	gr:SetTextureFromRuntime(trophy, lod, part, "textures", "coverageMap", "covmap_${db.trophy[?].stadiumID}_${db.trophy[?].stadiumLightID}_${db.trophy[?].stadiumType}")
	
	return trophy;
end


function CommonLeagueLogoAssetBind(leaguelogo, dbobj, basePath, defaultId)
	local gr = gRenderables
   	local lod = 0

	local leaguelogoMeshFile = "data/sceneassets/"..basePath.."/"..basePath.."_${"..dbobj..".model}.rx3;data/sceneassets/"..basePath.."/"..basePath.."_"..defaultId..".rx3";
	local leaguelogoTextureFile = "data/sceneassets/"..basePath.."/"..basePath.."_${"..dbobj..".model}_textures.rx3;data/sceneassets/"..basePath.."/"..basePath.."_"..defaultId.."_textures.rx3";

	gr:AddCallback(leaguelogo, lod, "TrophyUpdate(?)")
	gr:AddAsset(leaguelogo, lod, "shader", "data/fifarna/shader.big")

	gr:AddAsset(leaguelogo, lod, "leaguelogo_plastic", leaguelogoMeshFile)
	gr:AddAsset(leaguelogo, lod, "leaguelogotex", leaguelogoTextureFile)
	
	--gr:AddAsset(leaguelogo, lod, "charcmn", "data/sceneassets/charactercmn/charactercmn_${"..dbobj..".envLighting}.rx3")	
	gr:AddAsset(leaguelogo, lod, "wipecmn", "data/sceneassets/wipe3dcmn/wipe3dcmn_0.rx3")  
	
	local part = "leaguelogo_plastic"
	gr:CreateMaterialFromAttribulator(leaguelogo, lod, part, "leaguelogo_material", "leaguelogo" )
	gr:SetSubMesh(leaguelogo, lod, part, "leaguelogo_plastic")
	gr:SetTexture(leaguelogo, lod, part, "textures", "diffuseTexture", "leaguelogotex", "_cm")
	gr:SetTexture(leaguelogo, lod, part, "textures", "normalMap", "leaguelogotex", "_nm")
	gr:SetTexture(leaguelogo, lod, part, "textures", "coeffMap", "leaguelogotex", "_coeff")
	gr:SetTexture(leaguelogo, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(leaguelogo, lod, part, "textures", "INDIRECT_SPECULAR_TEXTURE", "wipecmn", "envs_wipe")
	gr:SetTexture(leaguelogo, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	
	--gr:SetTextureFromRuntime(leaguelogo, lod, part, "textures", "envSpecTexture", "envmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")
	--gr:SetTextureFromRuntime(leaguelogo, lod, part, "textures", "coverageMap", "covmap_${"..dbobj..".stadiumID}_${"..dbobj..".stadiumLightID}_${"..dbobj..".stadiumType}")

	return leaguelogo;
end

function LeagueLogoAssetBind(trophy)
	local gr = gRenderables
   	local lod = 0

	--gSportsRNA:Print("LeagueLogoAssetBind");

	if (wipeItem == 2) then
	CommonTrophyAssetBind(trophy, "db.wipeTrophy", "trophy", "0", "wipe_");
	else
	CommonLeagueLogoAssetBind(trophy, "db.wipeTrophy", "leaguelogo", "666");
	end

	return trophy;
end

function WipeTrophyAssetBind(trophy)
	local gr = gRenderables
   	local lod = 0

	--gSportsRNA:Print("WipeTrophyAssetBind");
	
	if (wipeItem == 1) then
	CommonLeagueLogoAssetBind(trophy, "db.wipeTrophy", "leaguelogo", "666");
	else
	CommonTrophyAssetBind(trophy, "db.wipeTrophy", "trophy", "0", "wipe_");
	end

	return trophy;
end


wipeItem = 0

function setWipeGraphicType(option)
wipeItem = option
end

--Revolution Mod 16 V1.0
--Edited by scouser09