function StadiumUpdate(idx)
	local as = gSportsRNA
	local state = as:GetTable("wvState")
	local stadium = as:GetTable("wvStadium", idx)
	local crowd = as:GetTable("wvCrowd", idx)
	

	db.stadium[idx].lightType = as:GetInt(stadium, "stadLightType")
	db.stadium[idx].stadiumID = as:GetInt(stadium, "stadID")
	
	db.stadium[idx].stadiumType = idx
	
	db.stadium[idx].mowPattern = as:GetInt(stadium, "pitchMowPattern")
	db.stadium[idx].wearPattern = as:GetInt(stadium, "pitchWearPattern")
	db.stadium[idx].skyCategoryId = as:GetInt(state, "wvAttribSkyCategory")
	db.stadium[idx].skyAssetId = as:GetInt(state, "wvAttribSkyID")
	
	db.stadium[idx].adboardID = as:GetInt(stadium, "adboardID" )
	db.stadium[idx].adboardIDfallback = 0 --as:GetInt(stadium, "adboardIDfallback" )
	db.stadium[idx].adboardGroup = as:GetInt(stadium, "adboardGroup" )
	
	db.stadium[idx].homeKitTeamID = as:GetInt(stadium, "homeKitTeamID" )
	db.stadium[idx].homeKitTypeID = as:GetInt(stadium, "homeKitTypeID" )
	db.stadium[idx].awayKitTeamID = as:GetInt(stadium, "awayKitTeamID" )
	db.stadium[idx].awayKitTypeID = as:GetInt(stadium, "awayKitTypeID" )
	
	db.stadium[idx].isHomeFCZ = as:GetInt(stadium, "isHomeCreationZone")
	db.stadium[idx].isAwayFCZ = as:GetInt(stadium, "isAwayCreationZone")
	
	db.stadium[idx].homeTeamAssetId = as:GetInt(stadium, "homeTeamAssetId")
	db.stadium[idx].hasCzCrestImage = as:GetInt(stadium, "hasCzCrestImage")
	
	db.stadium[idx].homePrimaryColour = as:GetInt(stadium, "homePrimaryColour")
	db.stadium[idx].homeSecondaryColour = as:GetInt(stadium, "homeSecondaryColour")
	db.stadium[idx].awayPrimaryColour = as:GetInt(stadium, "awayPrimaryColour")
	db.stadium[idx].awaySecondaryColour = as:GetInt(stadium, "awaySecondaryColour")
	
	db.stadium[idx].homeBannerId = db.stadium[idx].homeKitTeamID
	db.stadium[idx].awayBannerId = db.stadium[idx].awayKitTeamID
	
	db.stadium[idx].homeBannerPrimaryColour = 0xffff0000
	db.stadium[idx].homeBannerSecondaryColour = 0xff00ff00
	db.stadium[idx].awayBannerPrimaryColour = 0xffff0000
	db.stadium[idx].awayBannerSecondaryColour = 0xff00ff00
	
	db.stadium[idx].weather = as:GetInt(state, "wvAttribStadWeather" )

	
	if ( db.stadium[idx].isHomeFCZ == 1 ) then
		db.stadium[idx].homeBannerId = 7500
		db.stadium[idx].homeBannerPrimaryColour = db.stadium[idx].homePrimaryColour
		db.stadium[idx].homeBannerSecondaryColour = db.stadium[idx].homeSecondaryColour
	end
	
	if ( db.stadium[idx].isAwayFCZ == 1 ) then
		db.stadium[idx].awayBannerId = 7500
		db.stadium[idx].awayBannerPrimaryColour = db.stadium[idx].awayPrimaryColour
		db.stadium[idx].awayBannerSecondaryColour = db.stadium[idx].awaySecondaryColour
	end
	
	-- If we swap the home/away banners, don't draw the away banners (because they take up most of the stadium)
	local swapHomeAwayCrowd = as:GetInt(stadium, "swapHomeAwayCrowd")
	if ( swapHomeAwayCrowd == 1 ) then
		db.stadium[idx].homeBannerId, db.stadium[idx].awayBannerId = 0, db.stadium[idx].homeBannerId
		db.stadium[idx].homeBannerPrimaryColour, db.stadium[idx].awayBannerPrimaryColour = db.stadium[idx].awayBannerPrimaryColour, db.stadium[idx].homeBannerPrimaryColour
		db.stadium[idx].homeBannerSecondaryColour, db.stadium[idx].awayBannerSecondaryColour = db.stadium[idx].awayBannerSecondaryColour, db.stadium[idx].homeBannerSecondaryColour
	end

	db.stadium[idx].dressingAssetID = as:GetInt(stadium, "tournamentDressingID")
	
	-- query the type of crowd distribution
	db.stadium[idx].crowdDistribution = as:GetInt(crowd, "crowdDistribution")
	
	
	--TEAM STATEMENTS
	importTeamStatements(db.stadium[idx].homeKitTeamID,db.stadium[idx].awayKitTeamID)
	
	local wipe3d = as:GetTable("wvWipe", idx)
	
	db.stadium[idx].tournID = as:GetInt(wipe3d, "leagueID")
	db.stadium[idx].tournID = getTournamentGraphics(db.stadium[idx].tournID)
	
	--CLASSIC KIT + FUT
	db.stadium[idx].homeTeamID = db.stadium[idx].homeKitTeamID
	db.stadium[idx].awayTeamID = db.stadium[idx].awayKitTeamID
	db.stadium[idx].kitYearDecade = -1
	if (idx > 0) then
	local player = as:GetTable("wvPlayer", 9)
	local kitYearOutfield = as:GetInt(player, "kitYear")
	if (kitYearOutfield > 0) then
	db.stadium[idx].tournID = kitYearOutfield
	db.stadium[idx].kitYearDecade = math.floor(kitYearOutfield/10)*10
	end
	if (futCustom) then
	local team = as:GetInt(player, "teamid")
	if (team == 130000) then
	db.stadium[idx].homeTeamID = team
	end
	player = as:GetTable("wvPlayer", 20)
	team = as:GetInt(player, "teamid")
	if (team == 130000) then
	db.stadium[idx].awayTeamID = team
	end
	end
	end
	

 	db.stadium[idx].defaulttournID = 0
	if (teamTournament[db.stadium[idx].homeTeamID] ~= nil) then
	db.stadium[idx].defaulttournID = teamTournament[db.stadium[idx].homeTeamID]
	end
	

	
	db.stadium[idx].envLighting = as:GetInt(state, "wvAttribEnvLighting")
	
	-- if (db.stadium[idx].crowdDistribution == 1) then
	-- db.stadium[idx].tournID = 223
	-- end
	
end

function GetHomeCrestAssetSrc(idx)
	if ( db.stadium[idx].isHomeFCZ == 1 ) then
		if ( db.stadium[idx].hasCzCrestImage > 0 ) then
			return "data/ugc/cz_crest/${db.stadium[?].homeTeamAssetId}.png;data/ugc/cz_crest/1.png"
		else
			return "data/sceneassets/crest/crest_${db.stadium[?].homeTeamAssetId}.rx3"
		end
	else
		if ( db.stadium[idx].crowdDistribution == 0 ) then
			return "data/ui/imgassets/crest/light/l${db.stadium[?].homeKitTeamID}.dds"
		else
			return "data/sceneassets/banner/banner_0.rx3" -- transparent texture
		end
	end
end

function GetCrestTexName(idx)
	if ( db.stadium[idx].hasCzCrestImage > 0 ) then
		return "png"
	else
		return ""
	end
end

function StadiumAssetBind(stadium)
	local gr = gRenderables
	local enableVariablePitchSize = 0
	local lod = 0
	local priority = 0
	local banneridx = 0
	local maxbanners = 11
	--local stadiumAsset = "data/sceneassets/stadium/stadium_${db.stadium[?].stadiumID}_${db.stadium[?].lightType}_container_0.rx3;data/sceneassets/stadium/stadium_666_1_container_0.rx3"
	--local stadiumTextureAsset = "data/sceneassets/stadium/stadium_${db.stadium[?].stadiumID}_${db.stadium[?].lightType}_Textures.rx3"
	
	local stadiumAsset = "${GetRMStadModel(?)}data/sceneassets/stadium/stadium_${db.stadium[?].stadiumID}.rx3;data/sceneassets/stadium/stadium_666.rx3"
	local stadiumTextureAsset = "${GetRMStadTex(?)}data/sceneassets/stadium/stadium_${db.stadium[?].stadiumID}_${db.stadium[?].lightType}_textures.rx3;data/sceneassets/stadium/stadium_666_1_textures.rx3"
	
	local precomputeLocation = "type${db.stadium[?].stadiumType}_data/sceneassets/radiosity/stadium_${db.stadium[?].stadiumID}.rad" -- "typeX_" will be stripped from the beginning of the string
	
	-- Load all the stadium assets at a higher priority than the rest, so we can get it loaded early	
    gr:SetPriorityBoost(stadium, lod, 10)

	-- Get all assets we require in...
	gr:AddCallback(stadium, lod, "StadiumUpdate(?)")
	gr:AddAsset(stadium, lod, "shader", "data/fifarna/shader.big")

	gr:AddAsset(stadium, lod, "stadium",                          stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "stadiumtextures",           stadiumTextureAsset, priority)
    
    -- Add all the radiosity assets
    gr:AddAsset(stadium, lod, "radiosityPrecompute", precomputeLocation, priority)
	
	-- Assets we need to intercept
	gr:AddAsset(stadium, lod, "pitch",                            stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "pitchnoline",                      stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "jumbotron",                        stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboard",                          stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboardgeneric",                   stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboardscrolling",                 stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboarddigital",                   stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboarddigitalwide",               stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboarddigitalglow",               stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboardsingledigital",             stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "adboardsingledigitalglow",         stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "genericad",                        stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "crest",                            stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "homeprimary",                      stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "homesecondary",                    stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "bannerhome",                       stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "banneraway",                       stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "diffuseshadow",                    stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "tournament",                       stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockhalves",                     stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclocktimeanalog",                 stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockminutesones",                stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockminutestens",                stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclocksecondsones",                stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclocksecondstens",                stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockscorehomeones",              stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockscorehometens",              stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockscoreawayones",              stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "sclockscoreawaytens",              stadiumAsset, priority)
	gr:AddAsset(stadium, lod, "diffusewet",                       stadiumAsset, priority)

	
	-- Stadium Banners with dynamic distribution  (Not used on Fifa)
	local bannermat
	local maxbanners = 30
	for banneridx=0, maxbanners-1 do 
		bannermat = "bannergroup" .. banneridx
		gr:AddAsset(stadium, lod, bannermat,                      stadiumAsset, priority)
	end
	
	
	-- Additional assets to load
	gr:AddAsset(stadium, lod, "mow", "data/sceneassets/pitch/pitchmowpattern_${db.stadium[?].mowPattern}_textures.rx3", priority)
	gr:AddAsset(stadium, lod, "cmn", "${GetRMPitchCT(?)}data/sceneassets/pitch/pitch_common_textures.rx3", priority)
	gr:AddAsset(stadium, lod, "col", "data/sceneassets/pitch/pitchcolor_0_textures.rx3", priority)
	gr:AddAsset(stadium, lod, "globaltex", "${GetRMGlobalTex(?)}data/sceneassets/globaltex/globaltex_0.rx3", priority)
	gr:AddAsset(stadium, lod, "wear", "data/sceneassets/pitch/pitchwearpattern_${db.stadium[?].wearPattern}_textures.rx3", priority)
	--TODO direct it into host city texture
	gr:AddAsset(stadium, lod, "adboardsingletex", "${GetRMAdboard(?,0)}data/sceneassets/adboard/adboard_${db.stadium[?].adboardID}_${db.stadium[?].adboardGroup}.rx3;data/sceneassets/adboard/adboard_${db.stadium[?].adboardIDfallback}_0.rx3", priority)
	--gr:AddAsset(stadium, lod, "adboardsingletex2", "${GetRMAdboard(?,2)}data/sceneassets/adboard/adboard_${db.stadium[?].adboardID}_${db.stadium[?].adboardGroup}.rx3;data/sceneassets/adboard/adboard_${db.stadium[?].adboardIDfallback}_0.rx3", priority)
	-- Generic ad sheet default
	gr:AddAsset(stadium, lod, "adboardgenerictex", "${GetRMAdboard(?,1)}data/sceneassets/adboard/adboard_1_0.rx3", priority)	
	gr:AddAssetEx(stadium, lod, "extracttexture ${GetCrestTexName(?)}", "homecresttex", "${GetHomeCrestAssetSrc(?)}")
	gr:AddAsset(stadium, lod, "homebannertex", "${GetRMBanner(?,1)}data/sceneassets/banner/banner_${db.stadium[?].homeBannerId}.rx3;data/sceneassets/banner/banner_0.rx3", priority)
	gr:AddAsset(stadium, lod, "awaybannertex", "${GetRMBanner(?,2)}data/sceneassets/banner/banner_${db.stadium[?].awayBannerId}.rx3;data/sceneassets/banner/banner_0.rx3", priority)
	gr:AddAsset(stadium, lod, "genericadtex", "${GetRMGenericAdboard(?)}data/sceneassets/genericad/genericad_${db.stadium[?].adboardID}.rx3;data/sceneassets/genericad/genericad_0.rx3", priority)
	gr:AddAsset(stadium, lod, "skytexture", "data/sceneassets/sky/sky_${db.stadium[?].skyCategoryId}_${db.stadium[?].skyAssetId}.rx3", priority)
	gr:AddAsset(stadium, lod, "weathertex", "data/sceneassets/weather/weather_${db.stadium[?].weather}.rx3", priority)
	gr:AddAsset(stadium, lod, "dressingtex", "${GetRMStadDressing(?)}data/sceneassets/tournament/tournament_${db.stadium[?].dressingAssetID}_0.rx3;data/sceneassets/tournament/tournament_0_0.rx3", priority)
	
		
	-- Now generate custom materials (these should be named after the shader they are to replace)
	
	part = "pitch"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "pitch_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "noiseTexture", "cmn", "multifreq_noise")
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "col", "grass_color")
	gr:SetTexture(stadium, lod, part, "textures", "alphamask", "wear", "grass_wear")
	gr:SetTextureFromRuntime(stadium, lod, part, "textures", "cubicEnvMap", "envmap_${db.stadium[?].stadiumID}_${db.stadium[?].lightType}_${db.stadium[?].stadiumType}")

	local as = gSportsRNA
	local settingTable = as:GetTable("Settings")
	local levelOfDetail = as:GetString(settingTable, "LevelOfDetail")
	
	if (levelOfDetail == "low" or levelOfDetail == "superlow") then
		gr:SetTexture(stadium, lod, part, "textures", "normalMap", "mow", "grass_normal")
    	else
          	gr:SetTextureFromRuntime(stadium, lod, part, "textures", "normalMap", "dynamicmowpattern_${db.stadium[?].stadiumType}")
   	end

	gr:SetTextureFromRuntime(stadium, lod, part, "textures", "wetnessMap", "dynamicwetness_${db.stadium[?].stadiumType}")
		
	if ( enableVariablePitchSize == 0 )  then
		gr:SetTexture(stadium, lod, part, "textures", "pitchLinesMap", "cmn", "grass_pitchlines")
	else
		gr:SetTextureFromRuntime(stadium, lod, part, "textures", "pitchLinesMap", "grass_pitchlines[${?}]")
	end
	
	part = "pitchnoline"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "pitchnoline_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "noiseTexture", "cmn", "multifreq_noise")
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "col", "grass_color")
	gr:SetTexture(stadium, lod, part, "textures", "alphamask", "wear", "grass_wear")
	
	gr:SetTextureFromRuntime(stadium, lod, part, "textures", "cubicEnvMap", "envmap_${db.stadium[?].stadiumID}_${db.stadium[?].lightType}_${db.stadium[?].stadiumType}")

	-- Render to texture jumbotron
	part = "jumbotron"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "jumbotron_mtl", part)
	gr:SetTextureFromRuntime(stadium, lod, part, "textures", "diffuseTexture", "jumbotron")
	gr:SetTexture(stadium, lod, part, "textures", "incandescenceMap", "globaltex", "led")
	
	part = "adboard"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "adboard_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "adboardsingletex", "adboard")

	part = "adboardgeneric"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "adboardgeneric_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "adboardgenerictex", "adboard")	
	
	part = "adboardscrolling"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "adboardscrolling_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "adboardsingletex", "adboard")

	part = "adboarddigital"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "adboarddigital_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "adboardsingletex", "adboard")
	gr:SetTexture(stadium, lod, part, "textures", "incandescenceMap", "globaltex", "digitalgrid")	
	
	part = "adboarddigitalwide"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "adboarddigital_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "adboardsingletex", "adboard")
	gr:SetTexture(stadium, lod, part, "textures", "incandescenceMap", "globaltex", "digitalgrid")	

	part = "adboarddigitalglow"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "adboarddigitalglow_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "adboardsingletex", "adboard")

	-- The home team crest in the stadium
	part = "crest"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "homecrest_mtl", part)
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "homecresttex", "${GetCrestTexName(?)}")
	
	-- Stadium Banners
	part = "bannerhome"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "bannerhome_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "homebannertex", "banner_")
	gr:SetConstantARGB(stadium, lod, part, "global", "customColorPri", "${db.stadium[?].homeBannerPrimaryColour}")
	gr:SetConstantARGB(stadium, lod, part, "global", "customColorSec", "${db.stadium[?].homeBannerSecondaryColour}")
	
	part = "banneraway"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "banneraway_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "awaybannertex", "banner_")
	gr:SetConstantARGB(stadium, lod, part, "global", "customColorPri", "${db.stadium[?].awayBannerPrimaryColour}")
	gr:SetConstantARGB(stadium, lod, part, "global", "customColorSec", "${db.stadium[?].awayBannerSecondaryColour}")

    ------------------------------------------------------------------------------------------------------
	-- Stadium Banners with dynamic distribution
	local texname
	for banneridx=0, maxbanners-1 do 
		part = "bannergroup" .. banneridx
		--texname = string.format( "banner%s", banneridx )
		gr:CreateMaterialFromAttribulator(stadium, lod, part, part.."_mtl", part)
		gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "homebannertex", "banner")
		--gr:SetTextureFromRuntime(stadium, lod, part, "textures", "diffuseTexture", texname)
	end
    ------------------------------------------------------------------------------------------------------

	-- Stadium Dressing
	part = "tournament"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "tournament_mtl", part)
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "dressingtex", "tournament")

	-- Team colours
	part = "homeprimary"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "homeprimary_mtl", part )
	gr:SetConstantARGB(stadium, lod, part, "global", "envColour", "${db.stadium[?].homePrimaryColour}")
	
	part = "homesecondary"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "homesecondary_mtl", part )
	gr:SetConstantARGB(stadium, lod, part, "global", "envColour", "${db.stadium[?].homeSecondaryColour}")
	
	-- Generic adboards
	part = "genericad"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "genericad_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "genericadtex", "genericad")
	
	-- Flatshadow enabled geometry
	part = "diffuseshadow"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "diffuseshadow_mtl", part )

	-- Dynamic Scoreclock
	part = "sclocktimeanalog"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "sctimeanalog_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_analog")
	
	part = "sclockhalves"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "schalvesnalog_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclockminutesones"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scminutesones_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclockminutestens"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scminutestens_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclocksecondsones"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scsecondsones_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclocksecondstens"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scsecondstens_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclockscorehomeones"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scscorehomeones_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclockscorehometens"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scscorehometens_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclockscoreawayones"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scscoreawayones_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
	part = "sclockscoreawaytens"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "scscoreawaytens_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "globaltex", "sclock_digits")
	
-- Weather 
	part = "diffusewet"
	gr:CreateMaterialFromAttribulator(stadium, lod, part, "diffusewet_mtl", part )
	gr:SetTexture(stadium, lod, part, "textures", "diffuseTexture", "weathertex", "weather_cm")
	gr:SetTexture(stadium, lod, part, "textures", "coeffMap", "weathertex", "weather_coeff")
	gr:SetTexture(stadium, lod, part, "textures", "normalMap", "weathertex", "weather_nm")
	
end



function GetRMAdboard(idx,ad)
	local adorder = ""
	
	local rand = math.random(0,3)
	local upperAd = false
	
	if (ad == 1) then
	upperAd = true
	end
	
	if (ad == 2) then
	if (stadSplitAdboard[db.stadium[idx].stadiumID] == 1) then
	upperAd = true
	end
	end

	
	if (upperAd) then
	--adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_6000.rx3;"
	--adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_6000.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0_6000.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].tournID.."_0_6000.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID.."_6000.rx3;"
	--adorder = adorder.."data/sceneassets/adboard/specificadboard_0_0_"..db.stadium[idx].stadiumID.."_60000.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_0_0_6000.rx3;"
	end

		
	if (getTournamentFinal(db.stadium[idx].tournID,db.stadium[idx].stadiumID,db.stadium[idx].crowdDistribution)) then
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].tournID.."_0_4.rx3;"
	end
	
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].kitYearDecade.."_0_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].tournID.."_0_"..db.stadium[idx].defaulttournID..".rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_"..db.stadium[idx].tournID.."_0_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_0_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_0_0_"..rand..".rx3;"
	adorder = adorder.."data/sceneassets/adboard/specificadboard_"..db.stadium[idx].homeTeamID.."_0_0_0.rx3;"
 	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_0_0_"..db.stadium[idx].defaulttournID..".rx3;"
 	adorder = adorder.."data/sceneassets/adboard/specificadboard_0_0_0_0.rx3;"
 	return adorder
end


function GetRMPitchCT(idx)
	local pct = ""
	pct = pct.."data/sceneassets/pitch/specificpitchct_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].stadiumID..".rx3;"
	pct = pct.."data/sceneassets/pitch/specificpitchct_0_"..db.stadium[idx].stadiumID..".rx3;"
	pct = pct.."data/sceneassets/pitch/specificpitchct_"..db.stadium[idx].homeTeamID.."_0.rx3;"
	pct = pct.."data/sceneassets/pitch/specificpitchct_0_0.rx3;"
	return pct
end


function GetRMStadDressing(idx)
	local tex = ""
	tex = tex.."data/sceneassets/tournament/specifictournament_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID..".rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_0_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID..".rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0.rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_0_"..db.stadium[idx].tournID.."_0.rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID..".rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_0_0_"..db.stadium[idx].stadiumID..".rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_"..db.stadium[idx].homeTeamID.."_0_0.rx3;"
	tex = tex.."data/sceneassets/tournament/specifictournament_0_0_0.rx3;"
	return tex
end


function GetRMStadModel(idx)
	local stad = ""
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_0_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_0_"..db.stadium[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_0_0_"..db.stadium[idx].tournID..".rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_"..db.stadium[idx].homeTeamID.."_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_0_"..db.stadium[idx].homeTeamID.."_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].envLighting.."_0_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_0_0.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_0_0_0.rx3;"
	return stad
end


function GetRMStadTex(idx)
	local stad = ""
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_textures.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_0_"..db.stadium[idx].tournID.."_textures.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_"..db.stadium[idx].homeTeamID.."_0_textures.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].envLighting.."_0_0_textures.rx3;"
	stad = stad.."data/sceneassets/stadium/specificstadium_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].lightType.."_0_0_textures.rx3;"
	return stad
end


function GetRMBanner(idx,ven)
	local ban = ""
	
	if (getInvertHomeAwayBanners(db.stadium[idx].homeTeamID,db.stadium[idx].stadiumID) == 1) then
	if (ven == 2) then
	ven = 1
	else
	ven = 2
	end
	end
	
	local team = db.stadium[idx].homeTeamID
	local opp = db.stadium[idx].awayTeamID
	local var = math.random(0,3)
	
	if (ven == 2) then
	team = db.stadium[idx].awayTeamID
	opp = db.stadium[idx].homeTeamID
	end
	

	
	ban = ban.."data/sceneassets/banner/specificbanner_0_0_0_0_"..db.stadium[idx].stadiumID..".rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_"..db.stadium[idx].tournID.."_"..opp.."_"..ven.."_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_"..db.stadium[idx].tournID.."_"..opp.."_0_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_0_"..opp.."_"..ven.."_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_0_"..opp.."_0_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_"..db.stadium[idx].tournID.."_0_"..ven.."_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_"..db.stadium[idx].tournID.."_0_0_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_0_0_"..ven.."_"..var..".rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_0_0_"..ven.."_0.rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_0_0_0_"..var..".rx3;"
	ban = ban.."data/sceneassets/banner/specificbanner_"..team.."_0_0_0_0.rx3;"
	ban = ban.."data/sceneassets/banner/banner_"..team..".rx3;"
	return ban
end


stadSplitAdboard = {}

function assignAlternateStaticAdboard(stad)
stadSplitAdboard[stad] = 1
end


function GetRMStadiumLogo(idx)
	local logo = ""
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].awayTeamID..".dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID.."_"..db.stadium[idx].awayTeamID..".dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0_"..db.stadium[idx].awayTeamID..".dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_0_0_"..db.stadium[idx].awayTeamID..".dds;"
	
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID.."_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_0_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_0_0_"..db.stadium[idx].stadiumID.."_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_"..db.stadium[idx].homeTeamID.."_0_0_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_0_"..db.stadium[idx].tournID.."_0_0.dds;"
	logo = logo.."data/ui/imgassets/crest/stadium/stadium_0_0_0_0.dds;"

	return logo
end


function GetRMGenericAdboard(idx)
	local adorder = ""
		
	if (getTournamentFinal(db.stadium[idx].tournID,db.stadium[idx].stadiumID,db.stadium[idx].crowdDistribution)) then
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_"..db.stadium[idx].tournID.."_0_4.rx3;"
	end
	
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_"..db.stadium[idx].kitYearDecade.."_0_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_"..db.stadium[idx].tournID.."_0_"..db.stadium[idx].defaulttournID..".rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_"..db.stadium[idx].tournID.."_0_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_0_"..db.stadium[idx].stadiumID.."_0.rx3;"
	adorder = adorder.."data/sceneassets/genericad/specificgenericad_"..db.stadium[idx].homeTeamID.."_0_0_0.rx3;"
 	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_0_0_"..db.stadium[idx].defaulttournID..".rx3;"
 	adorder = adorder.."data/sceneassets/genericad/specificgenericad_0_0_0_0.rx3;"
 	return adorder
end


function GetRMGlobalTex(idx)
	local gtex = ""
	
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID..".rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_"..db.stadium[idx].homeTeamID.."_0_"..db.stadium[idx].stadiumID..".rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_0_"..db.stadium[idx].tournID.."_"..db.stadium[idx].stadiumID..".rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_0_0_"..db.stadium[idx].stadiumID..".rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_"..db.stadium[idx].homeTeamID.."_"..db.stadium[idx].tournID.."_0.rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_"..db.stadium[idx].homeTeamID.."_0_0.rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_0_"..db.stadium[idx].tournID.."_0.rx3;"
	gtex = gtex.."data/sceneassets/globaltex/specificglobaltex_0_0_0.rx3;"

	return gtex
end

bannerInvert = {}

function invertHomeAwayBanners(team,stadium)

if (bannerInvert[team] == nil) then
bannerInvert[team] = {}
end

bannerInvert[team][stadium] = 1

end


function getInvertHomeAwayBanners(team,stadium)

if (bannerInvert[team] ~= nil) then
if (bannerInvert[team][stadium] ~= nil) then
return bannerInvert[team][stadium]
end
end

return 0
end

--Revolution Mod 16 V1.0
--Edited by scouser09