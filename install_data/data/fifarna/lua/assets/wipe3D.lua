function FixBlackColorARGB(color)
	local newblack = 0x00353535
	local clr = color
	if (clr == 0) then
		clr = newblack
	end
	return clr
end

function Wipe3dUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local wipe3d = as:GetTable("wvWipe", idx)
	

	db.wipe3d[idx].wipeid = as:GetInt(wipe3d, "wipeID") 
	db.wipe3d[idx].wipeVersionID = as:GetInt(wipe3d, "wipeVersionID")
	db.wipe3d[idx].homePrimary = as:GetInt(wipe3d, "homePrimaryColour") 
	db.wipe3d[idx].homeSecondary = as:GetInt(wipe3d, "homeSecondaryColour")
	db.wipe3d[idx].awayPrimary = as:GetInt(wipe3d, "awayPrimaryColour") 
	db.wipe3d[idx].awaySecondary = as:GetInt(wipe3d, "awaySecondaryColour") 
	
	db.wipe3d[idx].homeTeamAssetID = as:GetInt(wipe3d, "homeTeamAssetID") 
	db.wipe3d[idx].homeKitTypeID = as:GetInt(wipe3d, "homeKitTypeID") 
	db.wipe3d[idx].homeIsCreationZoneTeam = as:GetInt(wipe3d, "homeIsCreationZoneTeam")
	db.wipe3d[idx].homeHasCzCrestImage = as:GetInt(wipe3d, "homeHasCzCrestImage")
	
	db.wipe3d[idx].awayTeamAssetID = as:GetInt(wipe3d, "awayTeamAssetID") 
	db.wipe3d[idx].awayKitTypeID = as:GetInt(wipe3d, "awayKitTypeID") 
	db.wipe3d[idx].awayIsCreationZoneTeam = as:GetInt(wipe3d, "awayIsCreationZoneTeam")
	db.wipe3d[idx].awayHasCzCrestImage = as:GetInt(wipe3d, "awayHasCzCrestImage")
		
	db.wipe3d[idx].leagueID = as:GetInt(wipe3d, "leagueID") 
	
	db.wipe3d[idx].leagueID = getTournamentGraphics(db.wipe3d[idx].leagueID)

	db.wipe3d[idx].homeLogoAsset = "data/ui/imgassets/crest/light/l${db.wipe3d[?].homeTeamAssetID}.dds"
	
	if (db.wipe3d[idx].homeIsCreationZoneTeam == 1 and db.wipe3d[idx].homeHasCzCrestImage > 0) then
		-- // The "\\" is so that the mounted image can be found properly by Apt
		db.wipe3d[idx].homeLogoAsset = "data\\ugc/cz_crest/${db.wipe3d[?].homeTeamAssetID}.png;data/ugc/cz_crest/1.png"
	end

	db.wipe3d[idx].awayLogoAsset = "data/ui/imgassets/crest/light/l${db.wipe3d[?].awayTeamAssetID}.dds"

	if (db.wipe3d[idx].awayIsCreationZoneTeam == 1 and db.wipe3d[idx].awayHasCzCrestImage > 0) then
		-- // The "\\" is so that the mounted image can be found properly by Apt
		db.wipe3d[idx].awayLogoAsset = "data\\ugc/cz_crest/${db.wipe3d[?].awayTeamAssetID}.png;data/ugc/cz_crest/1.png"
	end
	
	-- TODO Add logic for custom CC League Images!!!
	
	-- etc
	
	-- correct black colors
	db.wipe3d[idx].homePrimary = FixBlackColorARGB(db.wipe3d[idx].homePrimary)
	db.wipe3d[idx].homeSecondary = FixBlackColorARGB(db.wipe3d[idx].homeSecondary)
	db.wipe3d[idx].awayPrimary = FixBlackColorARGB(db.wipe3d[idx].awayPrimary)
	db.wipe3d[idx].awaySecondary = FixBlackColorARGB(db.wipe3d[idx].awaySecondary)
end



function Wipe3dAssetBind(wipe)
	local gr = gRenderables
   	local lod = 0
	local wipeAsset = "data/sceneassets/wipe3d/specificwipe_${db.wipe3d[?].wipeid}_${db.wipe3d[?].leagueID}.rx3;data/sceneassets/wipe3d/wipe_${db.wipe3d[?].wipeVersionID}_${db.wipe3d[?].wipeid}.rx3"
	local wipeTexturesAsset = "data/sceneassets/wipe3d/specificwipe_${db.wipe3d[?].wipeid}_${db.wipe3d[?].leagueID}_textures.rx3;data/sceneassets/wipe3d/wipe_${db.wipe3d[?].wipeVersionID}_${db.wipe3d[?].wipeid}_textures.rx3"

	gr:AddCallback(wipe, lod, "Wipe3dUpdate(?)")
	-- 3d wipes
	gr:AddAsset(wipe, lod, "shader", "data/fifarna/shader.big")
	gr:AddAsset(wipe, lod, "wipe3d", wipeAsset)
	gr:AddAsset(wipe, lod, "wipe3dtextures", wipeTexturesAsset)
	gr:AddAsset(wipe, lod, "wipediffcoeffenv", wipeAsset)
	gr:AddAsset(wipe, lod, "wipediffcoeffenvbump", wipeAsset)
	gr:AddAsset(wipe, lod, "wipediffuse", wipeAsset)
	gr:AddAsset(wipe, lod, "wipehometeam", wipeAsset)
	gr:AddAsset(wipe, lod, "wipeawayteam", wipeAsset)
	gr:AddAsset(wipe, lod, "wipeleague", wipeAsset)
	gr:AddAsset(wipe, lod, "wipehomeprimary", wipeAsset)
	gr:AddAsset(wipe, lod, "wipehomesecondary", wipeAsset)
	gr:AddAsset(wipe, lod, "wipeawayprimary", wipeAsset)
	gr:AddAsset(wipe, lod, "wipeawaysecondary", wipeAsset)
	gr:AddAsset(wipe, lod, "wipetext", wipeAsset)
	
	-- Add the assets needed
	gr:AddAsset(wipe, lod, "wipecmn", "data/sceneassets/wipe3dcmn/wipe3dcmn_${db.wipe3d[?].wipeVersionID}.rx3")	
	gr:AddAsset(wipe, lod, "kithometex", "${db.wipe3d[?].homeLogoAsset}")	
	gr:AddAsset(wipe, lod, "kitawaytex", "${db.wipe3d[?].awayLogoAsset}")	
	gr:AddAsset(wipe, lod, "leaguetex", "data/ui/imgassets/league/light/l${db.wipe3d[?].leagueID}.dds;data/ui/imgassets/league/light/l666.dds")	
	
	local part = "wipediffcoeffenv"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffcoeffenv.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	
	local part = "wipediffcoeffenvbump"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffcoeffenvbump.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
		
	local part = "wipediffuse"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffonly.fx")
	
	local part = "wipehometeam"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffcoeffenv.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "diffuseTexture", "kithometex", "") -- empty string, grab the first texture as there should only be one

	local part = "wipeawayteam"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffcoeffenv.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "diffuseTexture", "kitawaytex", "") -- empty string, grab the first texture as there should only be one
	
	local part = "wipeleague"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffcoeffenv.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "diffuseTexture", "leaguetex", "dds")
	
	local part = "wipehomeprimary"
	gr:CreateMaterial(wipe, lod, part, "wipe_recolor.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetConstantARGB(wipe, lod, part, "global", "MaterialColour", "${db.wipe3d[?].homePrimary}")
		
	local part = "wipehomesecondary"
	gr:CreateMaterial(wipe, lod, part, "wipe_recolor.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetConstantARGB(wipe, lod, part, "global", "MaterialColour", "${db.wipe3d[?].homeSecondary}")
	
	local part = "wipeawayprimary"
	gr:CreateMaterial(wipe, lod, part, "wipe_recolor.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetConstantARGB(wipe, lod, part, "global", "MaterialColour", "${db.wipe3d[?].awayPrimary}")
		
	local part = "wipeawaysecondary"
	gr:CreateMaterial(wipe, lod, part, "wipe_recolor.fx")
	gr:SetTexture(wipe, lod, part, "textures", "envDiffuseTexture", "wipecmn", "envd_wipe")
	gr:SetTexture(wipe, lod, part, "textures", "envSpecTexture", "wipecmn", "envs_wipe")
	gr:SetConstantARGB(wipe, lod, part, "global", "MaterialColour", "${db.wipe3d[?].awaySecondary}")
	
	local part = "wipetext"
	gr:CreateMaterial(wipe, lod, part, "wipe_diffonly.fx")
	gr:SetTextureFromRuntime(wipe, lod, part, "textures", "diffuseTexture", "fetex_wipe3d")

	gr:AddSubObject(wipe, gRenderObj.wipeTrophy, 1);
	
	return wipe
end

--Revolution Mod 16 V1.0
--Edited by scouser09